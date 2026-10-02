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
BUCKETS = {n: [privacy.money_bucket(EVERYDAY[n]), privacy.hours_bucket(CARE_HOURS[n])]
           for n in EVERYDAY}

# Routes/tools exercised below; the meta-test fails if a new one is added without coverage.
COVERED_ROUTES = {"/api/health", "/api/rounds", "/api/status", "/api/answers", "/me/answers",
                  "/api/result", "/api/close", "/api/nudge", "/api/server-holds",
                  "/api/agent/tool", "/api/agent/parse", "/api/agent/explain", "/api/checkin",
                  "/api/plan-card", "/api/household"}
# Voice routes take audio, not tokens, and return no answers: asserted in test_voice.py.
VOICE_ROUTES = {"/api/voice/enrol", "/api/voice/identify", "/api/voice/transcribe",
                "/api/voice/profiles", "/api/voice/profiles/{name}"}
COVERED_TOOLS = {"start_huddle", "submit_private_answer", "get_group_result", "close_round",
                 "nudge_pending", "submit_checkin", "revisit_round"}


def _answer(v):
    return {"consent": True, "budget_ceiling": v, "vibe": ["foodie"], "must_haves": [],
            "dealbreakers": []}


def _care_answer(name):
    return {"consent": True, "hours_per_week": CARE_HOURS[name],
            "dollars_per_month": CARE_DOLLARS[name], "dealbreakers": ["nights"]}


MODE_CASES = [("everyday", lambda n: _answer(EVERYDAY[n]), lambda n: str(EVERYDAY[n])),
              ("care", _care_answer, lambda n: str(CARE_HOURS[n]))]


def _check(label, body, viewer):
    leaks = privacy.find_leaks(body, SENTINELS, viewer) + \
        privacy.find_attributed_buckets(body, BUCKETS, viewer)
    assert not leaks, f"{label} as {viewer} leaked: {leaks}\n{body[:400]}"


def test_every_rest_route_is_covered():
    paths = {r.path for r in api.app.routes if getattr(r, "path", "").startswith(("/api", "/me"))}
    assert paths == COVERED_ROUTES | VOICE_ROUTES


@pytest.mark.parametrize("mode,make_answer,own_marker", MODE_CASES)
async def test_leak_rest_every_route_every_participant(fresh_db, mode, make_answer, own_marker):
    transport = httpx.ASGITransport(app=api.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = (await c.post("/api/rounds", json={
            "mode": mode, "deadline_seconds": 3600,
            "participants": [{"name": n} for n in EVERYDAY]})).json()
        toks = {p["name"]: p["token"] for p in r["participants"]}
        calls = []  # (label, response) gathered before and after submission and close

        async def sweep(stage):
            for viewer, tok in toks.items():
                for method, path in [("get", "/api/status"), ("get", "/api/result"),
                                     ("get", "/api/server-holds"), ("post", "/api/nudge"),
                                     ("get", "/me/answers")]:
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
            resp = await c.post("/api/answers", json={"token": toks[name],
                                                      "answer": make_answer(name)})
            _check("submit", resp.text, name)
        await sweep("partial")
        resp = await c.post("/api/answers", json={"token": toks["Chen"],
                                                  "answer": make_answer("Chen")})
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
                body = json.dumps([c.model_dump() for c in res.content]) + \
                    json.dumps(res.structuredContent)
                _check(f"{label}:{tool}", body, viewer)
                return res

            res = await sess.call_tool("start_huddle", {
                "mode": "everyday", "participants": [{"name": n} for n in EVERYDAY]})
            assert not res.isError, res.content
            toks = {p["name"]: p["token"] for p in res.structuredContent["participants"]}
            for viewer, tok in toks.items():
                for tool in ("get_group_result", "nudge_pending"):
                    await call(tool, {"token": tok}, viewer, "start")
            for name, tok in toks.items():
                await call("submit_private_answer",
                           {"token": tok, "answer": _answer(EVERYDAY[name])}, name, "submit")
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
        r = (await c.post("/api/agent/tool", json={"name": "start_huddle", "arguments": {
            "mode": "care", "participants": [{"name": n} for n in EVERYDAY]}})).json()
        toks = {p["name"]: p["token"] for p in r["participants"]}
        for name, tok in toks.items():
            text = f"I can do {CARE_HOURS[name]} hours and ${CARE_DOLLARS[name]} a month, not nights"
            parsed = await c.post("/api/agent/parse", json={"token": tok, "text": text})
            _check("parse", parsed.text, name)
            sub = await c.post("/api/agent/tool", json={"name": "submit_private_answer", "arguments": {
                "token": tok, "answer": _care_answer(name)}})
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
            for fn in (rounds.status, rounds.get_result, rounds.plan_card, rounds.my_answers,
                       rounds.household_history):
                body = json.dumps(fn(session, tok, t0), default=str)
                if fn is rounds.my_answers:
                    assert str(CARE_HOURS[viewer]) in body  # owner sees own
                    continue
                _check(f"chain {fn.__name__}", body, viewer)
    result = rounds.get_result(session, toks2["Ben"], t0)["result"]
    assert result["fairness"] and result["fairness"]["plans"] == 2
