"""F3 leak test (CI gate): no response to participant X may contain participant Y's raw values
or Y's exact bucket next to Y's name. Covers every REST route and every MCP tool."""
import json

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from server import api
from server.engine import privacy

# Distinctive sentinels: dollars no band edge or option price can equal; fractional hours
# so a whole-hour task assignment can never coincide with them.
EVERYDAY = {"Maya": 437, "Ben": 613, "Chen": 829}
SENTINELS = {n: [v] for n, v in EVERYDAY.items()}
BUCKETS = {n: [privacy.money_bucket(v)] for n, v in EVERYDAY.items()}

# Routes/tools exercised below; the meta-test fails if a new one is added without coverage.
COVERED_ROUTES = {"/api/health", "/api/rounds", "/api/status", "/api/answers", "/me/answers",
                  "/api/result", "/api/close", "/api/nudge", "/api/server-holds"}
COVERED_TOOLS = {"start_huddle", "submit_private_answer", "get_group_result", "close_round",
                 "nudge_pending"}


def _answer(v):
    return {"consent": True, "budget_ceiling": v, "vibe": ["foodie"], "must_haves": [],
            "dealbreakers": []}


def _check(label, body, viewer):
    leaks = privacy.find_leaks(body, SENTINELS, viewer) + \
        privacy.find_attributed_buckets(body, BUCKETS, viewer)
    assert not leaks, f"{label} as {viewer} leaked: {leaks}\n{body[:400]}"


def test_every_rest_route_is_covered():
    paths = {r.path for r in api.app.routes if getattr(r, "path", "").startswith(("/api", "/me"))}
    assert paths == COVERED_ROUTES


async def test_leak_rest_every_route_every_participant(fresh_db):
    transport = httpx.ASGITransport(app=api.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = (await c.post("/api/rounds", json={
            "mode": "everyday", "deadline_seconds": 3600,
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
                        assert (str(EVERYDAY[viewer]) in resp.text) == answered  # owner only
                        continue
                    calls.append((f"{stage} {path}", resp.text, viewer))
            for label, body, viewer in calls:
                _check(label, body, viewer)
            calls.clear()

        await sweep("start")
        for name in ("Maya", "Ben"):
            resp = await c.post("/api/answers", json={"token": toks[name],
                                                      "answer": _answer(EVERYDAY[name])})
            _check("submit", resp.text, name)
        await sweep("partial")
        resp = await c.post("/api/answers", json={"token": toks["Chen"],
                                                  "answer": _answer(EVERYDAY["Chen"])})
        _check("submit", resp.text, "Chen")
        await sweep("closed")
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
