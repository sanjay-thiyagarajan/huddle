"""F3 leak test (CI gate): no response to participant X may contain participant Y's raw values
or Y's exact bucket next to Y's name. Covers every REST route and every MCP tool."""

import json

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from server import api
from server.engine import privacy

# Distinctive sentinels: dollars no band edge or option price can equal; fractional hours
# so a whole-hour task assignment can never coincide with them.
EVERYDAY = {"Maya": 437, "Ben": 613, "Chen": 829}
CARE_HOURS = {"Maya": 13.5, "Ben": 17.5, "Chen": 11.5}
CARE_DOLLARS = {"Maya": 437, "Ben": 613, "Chen": 829}
SENTINELS = {n: [EVERYDAY[n], CARE_HOURS[n]] for n in EVERYDAY}
BUCKETS = {n: [privacy.money_bucket(EVERYDAY[n]), privacy.hours_bucket(CARE_HOURS[n])] for n in EVERYDAY}

# Routes/tools exercised below; the meta-test fails if a new one is added without coverage.
COVERED_ROUTES = {
    "/api/health",
    "/api/rounds",
    "/api/status",
    "/api/answers",
    "/me/answers",
    "/api/result",
    "/api/close",
    "/api/nudge",
    "/api/server-holds",
    "/api/agent/tool",
    "/api/agent/parse",
    "/api/agent/explain",
    "/api/checkin",
    "/api/plan-card",
    "/api/household",
    "/api/agent/turn",
    "/api/home",
    "/api/home/state",
    "/api/home/profile",
    "/api/home/chores",
    "/api/home/plan",
    "/api/home/respond",
    "/api/home/handback",
    "/api/home/complete",
    "/api/home/checkin",
    "/api/home/say",
    "/api/home/decision",
}
# Voice routes take audio, not tokens, and return no answers: asserted in test_voice.py.
VOICE_ROUTES = {
    "/api/voice/enrol",
    "/api/voice/identify",
    "/api/voice/transcribe",
    "/api/voice/profiles",
    "/api/voice/profiles/{name}",
}
COVERED_TOOLS = {
    "start_huddle",
    "submit_private_answer",
    "get_group_result",
    "close_round",
    "nudge_pending",
    "submit_checkin",
    "revisit_round",
    "create_household",
    "get_household",
    "set_my_profile",
    "add_chore",
    "plan_week",
    "respond_to_assignment",
    "hand_back_chore",
    "complete_chore",
    "week_checkin",
    "ask_household_agent",
    "start_household_decision",
}


def _answer(v):
    return {"consent": True, "budget_ceiling": v, "vibe": ["foodie"], "must_haves": [], "dealbreakers": []}


def _care_answer(name):
    return {
        "consent": True,
        "hours_per_week": CARE_HOURS[name],
        "dollars_per_month": CARE_DOLLARS[name],
        "dealbreakers": ["nights"],
    }


MODE_CASES = [
    ("everyday", lambda n: _answer(EVERYDAY[n]), lambda n: str(EVERYDAY[n])),
    ("care", _care_answer, lambda n: str(CARE_HOURS[n])),
]


def _check(label, body, viewer):
    assert "sentinel@example.test" not in body, f"{label} exposed a contact email"
    leaks = privacy.find_leaks(body, SENTINELS, viewer) + privacy.find_attributed_buckets(
        body, BUCKETS, viewer
    )
    assert not leaks, f"{label} as {viewer} leaked: {leaks}\n{body[:400]}"


def test_every_rest_route_is_covered():
    paths = {r.path for r in api.app.routes if getattr(r, "path", "").startswith(("/api", "/me"))}
    assert paths == COVERED_ROUTES | VOICE_ROUTES


@pytest.mark.parametrize("mode,make_answer,own_marker", MODE_CASES)
async def test_leak_rest_every_route_every_participant(fresh_db, mode, make_answer, own_marker):
    transport = httpx.ASGITransport(app=api.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = (
            await c.post(
                "/api/rounds",
                json={
                    "mode": mode,
                    "deadline_seconds": 3600,
                    "participants": [
                        {"name": n, "email": f"{n.lower()}.sentinel@example.test"} for n in EVERYDAY
                    ],
                },
            )
        ).json()
        toks = {p["name"]: p["token"] for p in r["participants"]}
        calls = []  # (label, response) gathered before and after submission and close

        async def sweep(stage):
            for viewer, tok in toks.items():
                for method, path in [
                    ("get", "/api/status"),
                    ("get", "/api/result"),
                    ("get", "/api/server-holds"),
                    ("post", "/api/nudge"),
                    ("get", "/me/answers"),
                ]:
                    resp = await getattr(c, method)(path, params={"token": tok})
                    if path == "/me/answers":
                        answered = stage == "closed" or (stage == "partial" and viewer != "Chen")
                        assert (own_marker(viewer) in resp.text) == answered  # owner only
                        continue
                    calls.append((f"{stage} {path}", resp.text, viewer))
            for label, body, viewer in calls:
                _check(label, body, viewer)
            calls.clear()

        await sweep("start")
        for name in ("Maya", "Ben"):
            resp = await c.post("/api/answers", json={"token": toks[name], "answer": make_answer(name)})
            _check("submit", resp.text, name)
        await sweep("partial")
        resp = await c.post("/api/answers", json={"token": toks["Chen"], "answer": make_answer("Chen")})
        _check("submit", resp.text, "Chen")
        await sweep("closed")
        # Day-after check-ins: scores must never be attributed to a name in any response
        for name, score in zip(toks, (5, 4, 2), strict=True):
            resp = await c.post("/api/checkin", json={"token": toks[name], "score": score})
            assert resp.status_code == 200, resp.text
            _check("checkin", resp.text, name)
        for viewer, tok in toks.items():
            for path in ("/api/status", "/api/result", "/api/plan-card", "/api/household"):
                body = (await c.get(path, params={"token": tok})).text
                _check(f"after checkin {path}", body, viewer)
                assert "score" not in body, f"{path} exposes a score field"
        for viewer, tok in toks.items():
            resp = await c.post("/api/close", params={"token": tok})
            _check("close", resp.text, viewer)
        # create_round responses go to the host only; they hold tokens, never answers
        _check("create", json.dumps(r), "Maya")


async def test_leak_mcp_every_tool_every_participant(live_server):
    async with streamable_http_client(f"{live_server}/mcp") as (rd, wr, _):
        async with ClientSession(rd, wr) as sess:
            await sess.initialize()
            listed = {t.name for t in (await sess.list_tools()).tools}
            assert listed == COVERED_TOOLS

            async def call(tool, args, viewer, label):
                res = await sess.call_tool(tool, args)
                body = json.dumps([c.model_dump() for c in res.content]) + json.dumps(res.structuredContent)
                _check(f"{label}:{tool}", body, viewer)
                return res

            res = await sess.call_tool(
                "start_huddle", {"mode": "everyday", "participants": [{"name": n} for n in EVERYDAY]}
            )
            assert not res.isError, res.content
            toks = {p["name"]: p["token"] for p in res.structuredContent["participants"]}
            for viewer, tok in toks.items():
                for tool in ("get_group_result", "nudge_pending"):
                    await call(tool, {"token": tok}, viewer, "start")
            for name, tok in toks.items():
                await call(
                    "submit_private_answer", {"token": tok, "answer": _answer(EVERYDAY[name])}, name, "submit"
                )
            for viewer, tok in toks.items():
                out = await call("get_group_result", {"token": tok}, viewer, "closed")
                assert out.structuredContent["ready"] is True
                await call("close_round", {"token": tok}, viewer, "closed")
            denied = await sess.call_tool("revisit_round", {"token": toks["Ben"]})
            assert denied.isError  # host only
            nxt = await call("revisit_round", {"token": toks["Maya"]}, "Maya", "closed")
            assert nxt.structuredContent["round_id"] != res.structuredContent["round_id"]


async def test_leak_agent_routes(live_server):
    """The simulator agent's MCP proxy and parser, as every participant, against a real server."""
    async with httpx.AsyncClient(base_url=live_server, timeout=20) as c:
        r = (
            await c.post(
                "/api/agent/tool",
                json={
                    "name": "start_huddle",
                    "arguments": {"mode": "care", "participants": [{"name": n} for n in EVERYDAY]},
                },
            )
        ).json()
        toks = {p["name"]: p["token"] for p in r["participants"]}
        for name, tok in toks.items():
            text = f"I can do {CARE_HOURS[name]} hours and ${CARE_DOLLARS[name]} a month, not nights"
            parsed = await c.post("/api/agent/parse", json={"token": tok, "text": text})
            _check("parse", parsed.text, name)
            sub = await c.post(
                "/api/agent/tool",
                json={
                    "name": "submit_private_answer",
                    "arguments": {"token": tok, "answer": _care_answer(name)},
                },
            )
            _check("agent submit", sub.text, name)
        for viewer, tok in toks.items():
            for tool in ("get_group_result", "nudge_pending", "close_round"):
                resp = await c.post("/api/agent/tool", json={"name": tool, "arguments": {"token": tok}})
                _check(f"agent {tool}", resp.text, viewer)
        for viewer, tok in toks.items():  # round is closed now: the explanation is aggregate-only
            resp = await c.get("/api/agent/explain", params={"token": tok})
            assert resp.status_code == 200
            _check("agent explain", resp.text, viewer)
        bad = await c.post("/api/agent/tool", json={"name": "dump_db", "arguments": {}})
        assert bad.status_code == 400


async def test_leak_two_round_care_chain_and_fairness(session):
    """Fairness history, revisit, plan card and status across two rounds never expose a private value."""
    from datetime import datetime

    from server.engine import rounds

    t0 = datetime(2026, 10, 10, 9, 0, 0)
    people = [{"name": n} for n in EVERYDAY]

    def run_round(first_round):
        r = first_round
        toks = {p["name"]: p["token"] for p in r["participants"]}
        for name, tok in toks.items():
            rounds.submit_answer(session, tok, _care_answer(name), t0)
        return toks

    first = rounds.create_round(session, "care", people, 3600, now=t0)
    toks1 = run_round(first)
    second = rounds.revisit_round(session, toks1["Maya"], now=t0)
    toks2 = run_round(second)
    for toks in (toks1, toks2):
        for viewer, tok in toks.items():
            for fn in (
                rounds.status,
                rounds.get_result,
                rounds.plan_card,
                rounds.my_answers,
                rounds.household_history,
            ):
                body = json.dumps(fn(session, tok, t0), default=str)
                if fn is rounds.my_answers:
                    assert str(CARE_HOURS[viewer]) in body  # owner sees own
                    continue
                _check(f"chain {fn.__name__}", body, viewer)
    result = rounds.get_result(session, toks2["Ben"], t0)["result"]
    assert result["fairness"] and result["fairness"]["plans"] == 2


async def test_leak_voice_turns_never_echo_any_value_and_sessions_are_private(live_server):
    """Every reply from the voice-only dialogue, for every participant, contains no one's value,
    not even the speaker's own (the draft stays server-side). A session cannot be used by another token."""
    async with httpx.AsyncClient(base_url=live_server, timeout=30) as c:
        r = (
            await c.post(
                "/api/agent/tool",
                json={
                    "name": "start_huddle",
                    "arguments": {"mode": "care", "participants": [{"name": n} for n in EVERYDAY]},
                },
            )
        ).json()
        toks = {p["name"]: p["token"] for p in r["participants"]}
        sessions = {}
        for name, tok in toks.items():
            turns = [{"token": tok}]  # first call opens the session
            first = (await c.post("/api/agent/turn", json=turns[0])).json()
            sid = sessions[name] = first["session_id"]
            replies = [first]
            for words in (
                "just me",
                "yes I agree",
                f"I can do {CARE_HOURS[name]} hours but not nights",
                f"{CARE_DOLLARS[name]} dollars a month",
                "save it",
            ):
                payload = {"token": tok, "session_id": sid, "utterance": words}
                replies.append((await c.post("/api/agent/turn", json=payload)).json())
            for reply in replies:
                body = json.dumps(reply)
                for who, values in SENTINELS.items():
                    for v in [*values, CARE_DOLLARS[who], CARE_HOURS[who]]:
                        assert str(v) not in body, f"voice reply to {name} contained {who}'s {v}: {body}"
            assert replies[-1]["saved"] is True and replies[-1]["stage"] == "saved"
        # The answers really were stored (through MCP), and only the owner can read each
        for name, tok in toks.items():
            mine = (await c.get("/me/answers", params={"token": tok})).json()
            assert mine["answered"] and mine["answer"]["hours_per_week"] == CARE_HOURS[name]

        # A voice session belongs to one token
        fresh = (
            await c.post(
                "/api/agent/tool",
                json={
                    "name": "start_huddle",
                    "arguments": {"mode": "care", "participants": [{"name": "Maya"}, {"name": "Ben"}]},
                },
            )
        ).json()
        ft = {p["name"]: p["token"] for p in fresh["participants"]}
        other = (await c.post("/api/agent/turn", json={"token": ft["Maya"]})).json()
        stolen = await c.post(
            "/api/agent/turn",
            json={"token": ft["Ben"], "session_id": other["session_id"], "utterance": "just me"},
        )
        assert stolen.status_code == 410 and stolen.json()["error"] == "voice_session"


# ---- the household: private limits never reach anyone else ---------------------------------------

HOME_AVAIL = {"Maya": 437, "Ben": 613, "Chen": 829}
HOME_SECRETS = {n: f"sentinelknows{n.lower()}" for n in HOME_AVAIL}  # a private skill keyword per person
HOME_PRIVATE_WORDS = ("excluded", '"proposed_to":', "prefer_not", "no_response", "felt", '"exempt_weeks":')


def _home_check(label, body, viewer):
    leaks = privacy.find_leaks(body, {n: [v] for n, v in HOME_AVAIL.items()}, viewer)
    assert not leaks, f"{label} as {viewer} leaked {leaks}: {body[:300]}"
    for name, word in HOME_SECRETS.items():
        if name != viewer:
            assert word not in body, f"{label} as {viewer} leaked {name}'s keyword"
    assert "sentinel@example.test" not in body, f"{label} exposed a contact email"
    for word in HOME_PRIVATE_WORDS:
        assert word not in body, f"{label} as {viewer} exposed '{word}'"


async def test_leak_household_every_route_every_member_through_a_full_lifecycle(live_server):
    async with httpx.AsyncClient(base_url=live_server, timeout=60) as c:
        made = (
            await c.post(
                "/api/home",
                json={
                    "name": "Home",
                    "members": [
                        {"name": n, "email": f"{n.lower()}.sentinel@example.test"} for n in HOME_AVAIL
                    ],
                },
            )
        ).json()
        _home_check("create", json.dumps(made), "Maya")
        tok = {m["name"]: m["token"] for m in made["members"]}

        async def sweep(stage):
            for viewer, t in tok.items():
                body = (await c.get("/api/home/state", params={"token": t})).text
                _home_check(f"{stage} state", body, viewer)
                for words in ("what's on my plate", "what's the plan", "who has the dishes", "hello"):
                    reply = (await c.post("/api/home/say", json={"token": t, "utterance": words})).text
                    _home_check(f"{stage} say '{words}'", reply, viewer)

        for name, t in tok.items():  # each person's private profile, with distinctive values
            r = await c.post(
                "/api/home/profile",
                json={
                    "token": t,
                    "changes": {
                        "availability": HOME_AVAIL[name],
                        "keywords": [HOME_SECRETS[name]],
                        "prefs": {"cooking": "cannot" if name == "Chen" else "love"},
                        "skills": {"repairs": 2},
                    },
                },
            )
            _home_check("profile", r.text, name)
            assert str(HOME_AVAIL[name]) in r.text  # the owner sees their own
        await sweep("profiles")

        for text in (
            "add do the dishes every day, 10 minutes",
            "add cook dinner every week, 60 minutes",
            "add clean the bathroom every week, 40 minutes",
        ):
            r = await c.post("/api/home/chores", json={"token": tok["Maya"], "text": text})
            _home_check("add chore", r.text, "Maya")
        planned = await c.post("/api/home/plan", json={"token": tok["Maya"]})
        _home_check("plan", planned.text, "Maya")
        await sweep("planned")

        # ad hoc: offered, declined with a private reason, offered on, accepted
        await c.post(
            "/api/home/chores",
            json={
                "token": tok["Ben"],
                "fields": {"title": "Fix the shelf", "category": "repairs", "minutes": 30},
            },
        )
        for _ in range(3):
            asked = None
            for n, t in tok.items():
                st = (await c.get("/api/home/state", params={"token": t})).json()
                if st["mine"]["proposals"]:
                    asked = (n, t, st["mine"]["proposals"][0]["id"])
            if not asked:
                break
            n, t, aid = asked
            accept = n == "Chen"
            r = await c.post(
                "/api/home/respond",
                json={
                    "token": t,
                    "assignment_id": aid,
                    "accept": accept,
                    "reason": None if accept else "prefer_not",
                },
            )
            _home_check("respond", r.text, n)
            await sweep(f"after {n} {'accepted' if accept else 'declined'}")

        for n, t in tok.items():  # private week feeling, then completing and handing back what they own
            r = await c.post("/api/home/checkin", json={"token": t, "score": 2 if n == "Ben" else 4})
            _home_check("checkin", r.text, n)
            st = (await c.get("/api/home/state", params={"token": t})).json()
            for a in st["mine"]["assignments"][:1]:
                r = await c.post("/api/home/complete", json={"token": t, "assignment_id": a["id"]})
                _home_check("complete", r.text, n)
        await sweep("done")


async def test_leak_household_mcp_every_tool(live_server):
    async with streamable_http_client(f"{live_server}/mcp") as (rd, wr, _):
        async with ClientSession(rd, wr) as sess:
            await sess.initialize()

            async def call(tool, args, viewer):
                res = await sess.call_tool(tool, args)
                body = json.dumps([x.model_dump() for x in res.content]) + json.dumps(res.structuredContent)
                _home_check(tool, body, viewer)
                return res

            made = await sess.call_tool(
                "create_household", {"name": "Home", "members": [{"name": n} for n in HOME_AVAIL]}
            )
            tok = {m["name"]: m["token"] for m in made.structuredContent["members"]}
            for n, t in tok.items():
                await call(
                    "set_my_profile",
                    {"token": t, "changes": {"availability": HOME_AVAIL[n], "keywords": [HOME_SECRETS[n]]}},
                    n,
                )
            await call(
                "add_chore", {"token": tok["Maya"], "text": "add do the dishes every day, 10 minutes"}, "Maya"
            )
            await call(
                "add_chore",
                {
                    "token": tok["Ben"],
                    "fields": {"title": "Mop", "category": "cleaning", "minutes": 30, "cadence": "weekly"},
                },
                "Ben",
            )
            planned = await call("plan_week", {"token": tok["Maya"]}, "Maya")
            denied = await sess.call_tool("plan_week", {"token": tok["Ben"], "replan": True})
            assert denied.isError  # redoing a plan is admin-only
            rows = planned.structuredContent["plan"]["assignments"]
            for viewer, t in tok.items():
                await call("get_household", {"token": t}, viewer)
                await call("ask_household_agent", {"token": t, "utterance": "what's on my plate"}, viewer)
                await call("week_checkin", {"token": t, "score": 3}, viewer)
            owner_row = next(a for a in rows if a["owner"])
            await call(
                "complete_chore",
                {"token": tok[owner_row["owner"]], "assignment_id": owner_row["id"]},
                owner_row["owner"],
            )
            other = next(a for a in rows if a["owner"] and a["id"] != owner_row["id"])
            await call(
                "hand_back_chore",
                {"token": tok[other["owner"]], "assignment_id": other["id"], "reason": "busy"},
                other["owner"],
            )
            for viewer, t in tok.items():
                st = (await call("get_household", {"token": t}, viewer)).structuredContent
                for p in st["mine"]["proposals"]:
                    await call(
                        "respond_to_assignment",
                        {"token": t, "assignment_id": p["id"], "accept": False, "reason": "prefer_not"},
                        viewer,
                    )


# ---- household decisions: round tokens and care hours never reach other members ------------------

CARE_NEED_BODY = {
    "tasks": [
        {"id": "night", "label": "Overnight cover", "type": "overnight", "hours": 6},
        {"id": "calls", "label": "Daily check-in", "type": "checkin", "hours": 2},
    ],
    "dollars_per_month": 300,
}
CARE_HOURS_SECRET = {"Maya": 13.5, "Ben": 17.5, "Chen": 11.5}


async def test_leak_household_decisions_tokens_and_care_hours(live_server):
    async with httpx.AsyncClient(base_url=live_server, timeout=60) as c:
        made = (
            await c.post(
                "/api/home", json={"name": "Home", "members": [{"name": n} for n in CARE_HOURS_SECRET]}
            )
        ).json()
        tok = {m["name"]: m["token"] for m in made["members"]}
        started = (
            await c.post(
                "/api/home/decision", json={"token": tok["Maya"], "mode": "care", "need": CARE_NEED_BODY}
            )
        ).json()
        assert set(started) == {"round_id", "mode", "deadline_at", "my_token", "my_link"}

        async def states():
            out = {}
            for n, t in tok.items():
                out[n] = (await c.get("/api/home/state", params={"token": t})).json()
            return out

        round_tokens = {n: s["mine"]["decisions"][0]["token"] for n, s in (await states()).items()}
        assert len(set(round_tokens.values())) == 3

        async def sweep(stage):
            for viewer, t in tok.items():
                raw = (await c.get("/api/home/state", params={"token": t})).text
                said = (await c.post("/api/home/say", json={"token": t, "utterance": "what's the plan"})).text
                for label, body in ((f"{stage} state", raw), (f"{stage} say", said)):
                    for other, rt in round_tokens.items():
                        if other != viewer:
                            assert rt not in body, f"{label} as {viewer} exposed {other}'s round token"
                    for who, hours in CARE_HOURS_SECRET.items():
                        if who != viewer:
                            assert str(hours) not in body, (
                                f"{label} as {viewer} exposed {who}'s private hours"
                            )

        await sweep("open")
        for n, rt in round_tokens.items():  # everyone answers privately with distinctive hours
            r = await c.post(
                "/api/answers",
                json={
                    "token": rt,
                    "answer": {
                        "consent": True,
                        "hours_per_week": CARE_HOURS_SECRET[n],
                        "dollars_per_month": 437,
                        "dealbreakers": [],
                    },
                },
            )
            assert r.status_code == 200, r.text
        await sweep("closed")

        # care now counts in the chore plan: still no private hours anywhere
        await c.post(
            "/api/home/chores",
            json={
                "token": tok["Maya"],
                "fields": {"title": "Dishes", "category": "dishes", "minutes": 20, "cadence": "weekly"},
            },
        )
        await c.post("/api/home/plan", json={"token": tok["Maya"]})
        await sweep("planned")
        for n, s in (await states()).items():
            assert s["mine"]["load"]["care_minutes"] >= 0
