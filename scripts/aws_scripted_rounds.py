"""Run the two scripted demo rounds against a running server and record which engine answered.

    HUDDLE_MODE=aws HUDDLE_BEDROCK_MODEL_ID=<id> AWS_REGION=<region> uvicorn server.api:app --port 8000
    python scripts/aws_scripted_rounds.py --require-bedrock   # exits 1 if any call fell back to mock

Prints a markdown table of engine and latency per step (paste into docs/aws-run.md). In mock mode it
still runs and shows engine=mock, which proves the script, not Bedrock.
"""
import argparse
import sys

import httpx

SCRIPT = {
    "everyday": [("Maya", "Under sixty dollars each, I would love good food, and no crowds."),
                 ("Ben", "Around eighty dollars, something relaxed and social.")],
    "care": [("Maya", "I can do maybe twelve hours and $600 a month but not nights"),
             ("Ben", "I live far away, about 8 hours and $500 a month"),
             ("Chen", "Six hours, $400 a month, and I can't drive or do transport")],
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--require-bedrock", action="store_true")
    args = ap.parse_args()
    c = httpx.Client(base_url=args.base, timeout=120)
    rows, fell_back = [], False

    for mode, people in SCRIPT.items():
        r = c.post("/api/agent/tool", json={"name": "start_huddle", "arguments": {
            "mode": mode, "participants": [{"name": n} for n, _ in people]}}).json()
        tok = {p["name"]: p["token"] for p in r["participants"]}
        for name, say in people:
            p = c.post("/api/agent/parse", json={"token": tok[name], "text": say}).json()
            rows.append((mode, f"parse {name}", p["engine"], p["latency_ms"], p.get("engine_error", "")))
            fell_back |= p["engine"] != "bedrock"
            if p["missing"]:
                print(f"note: {mode}/{name} still missing {p['missing']}", file=sys.stderr)
                continue
            c.post("/api/agent/tool", json={"name": "submit_private_answer", "arguments": {
                "token": tok[name], "answer": {**p["draft"], "consent": True}}})
        c.post("/api/agent/tool", json={"name": "close_round", "arguments": {"token": tok[people[0][0]]}})
        e = c.get("/api/agent/explain", params={"token": tok[people[0][0]]}).json()
        rows.append((mode, "explain result", e["engine"], e["latency_ms"], e.get("engine_error", "")))
        fell_back |= e["engine"] != "bedrock"

    print("| round | step | engine | latency (ms) | error |\n|---|---|---|---|---|")
    for row in rows:
        print("| " + " | ".join(str(x) for x in row) + " |")
    if args.require_bedrock and fell_back:
        print("\nFAIL: at least one step did not use Bedrock.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
