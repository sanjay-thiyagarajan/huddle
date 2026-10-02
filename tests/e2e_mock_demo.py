"""Scripted care round against a running server (make dev / uvicorn on :8000), mock mode.

Not collected by pytest (no test_ prefix). Run: python tests/e2e_mock_demo.py [base_url]
"""
import json
import sys

import httpx

base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
c = httpx.Client(base_url=base, timeout=30)


def tool(name, **args):
    return c.post("/api/agent/tool", json={"name": name, "arguments": args}).json()


r = tool("start_huddle", mode="care", participants=[
    {"name": "Maya"}, {"name": "Ben"}, {"name": "Chen", "channel": "link"}])
tok = {p["name"]: p["token"] for p in r["participants"]}

for name, say in [("Maya", "I can do maybe twelve hours and $600 a month but not nights"),
                  ("Ben", "I live far away, about 8 hours and $500 a month")]:
    draft = c.post("/api/agent/parse", json={"token": tok[name], "text": say}).json()
    assert not draft["missing"], draft
    print(name, "->", draft["draft"])
    print("  ", tool("submit_private_answer", token=tok[name], answer={**draft["draft"], "consent": True}))

# Remote sibling answers through the private link flow
print("pending:", tool("nudge_pending", token=tok["Maya"])["pending"])
print(c.post("/api/answers", json={"token": tok["Chen"], "answer": {
    "consent": True, "hours_per_week": 6, "dollars_per_month": 400, "dealbreakers": ["transport"]}}).json())

res = tool("get_group_result", token=tok["Maya"])["result"]
keys = ("headline", "gap_hours_bucket", "gap_dollars_bucket", "warnings")
print(json.dumps({k: res[k] for k in keys}, indent=1))
for a in res["assignments"]:  # the group sees ownership only
    print(" ", a["name"], [t["label"] + (" (shared)" if t["shared"] else "") for t in a["tasks"]])
print("each person's own hours (private to them):")
for name, token in tok.items():
    own = tool("get_group_result", token=token)["my_share"]
    print(" ", name, [(s["label"], s["hours"]) for s in own])
assert res["gap_hours_bucket"] == "0-5 h" and res["gap_dollars_bucket"] == "$250-500"
print("OK")
