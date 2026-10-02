"""End-to-end simulation of a FICTIONAL family using synthetic speech.

Chain exercised with real audio: speaker identification -> Whisper transcription -> voice-only
dialogue -> MCP tool -> private store -> engine result. The voices are text-to-speech, the siblings are
invented, and no human took part, so this proves the pipeline works and says NOTHING about whether
Huddle helps real families.

    python tests/family_sim.py      # writes docs/family-simulation.md (needs the `voice` extra, macOS clips)
"""
import json
import os
import socket
import sys
import tempfile
import threading
import time
from datetime import date
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
AUDIO = ROOT / "tests" / "audio"
FAMILY = json.loads((AUDIO / "family" / "family.json").read_text())

# What each fictional sibling privately means to say, for checking what was stored.
EXPECTED = {
    "Maya": {"hours_per_week": 12.0, "dollars_per_month": 600.0, "dealbreakers": ["nights"]},
    "Ben": {"hours_per_week": 8.0, "dollars_per_month": 500.0, "dealbreakers": ["far_away"]},
    "Chen": {"hours_per_week": 6.0, "dollars_per_month": 400.0, "dealbreakers": ["transport"]},
}


def _words(s: str) -> list[str]:
    sys.path.insert(0, str(ROOT / "tests"))
    from voice_eval import words  # reuse the number-normalising scorer

    return words(s)


def _wer(ref: str, hyp: str) -> float:
    from voice_eval import wer

    return wer(_words(ref), _words(hyp))


def run_family(base_url: str) -> dict:
    c = httpx.Client(base_url=base_url, timeout=180)

    def tool(name, **args):
        return c.post("/api/agent/tool", json={"name": name, "arguments": args}).json()

    # 1. Each sibling enrols their voice from clips we already have (3 enrolment clips each)
    for name, p in FAMILY.items():
        for clip in sorted((AUDIO / "enrol" / p["enrol_voice_dir"]).glob("*.wav")):
            r = c.post("/api/voice/enrol", params={"name": name}, content=clip.read_bytes())
            r.raise_for_status()

    # 2. The host opens a care round for the three siblings
    started = tool("start_huddle", mode="care", participants=[{"name": n} for n in FAMILY])
    tokens = {p["name"]: p["token"] for p in started["participants"]}

    steps, sessions, assistant_lines = [], {}, []
    for name in FAMILY:  # each sibling takes their turn at the device
        open_turn = c.post("/api/agent/turn", json={"token": tokens[name]}).json()
        sessions[name] = open_turn["session_id"]
        assistant_lines.append(open_turn["say"])
        for i, spoken in enumerate(FAMILY[name]["says"]):
            wav = (AUDIO / "family" / name.lower() / f"{i}.wav").read_bytes()
            who = c.post("/api/voice/identify", content=wav).json()
            heard = c.post("/api/voice/transcribe", content=wav).json()["text"]
            # Route the utterance to whoever the SYSTEM thinks is speaking; a mistake would show.
            token = tokens.get(who["name"]) or tokens[name]
            turn = c.post("/api/agent/turn", json={
                "token": token, "session_id": sessions[name] if who["name"] in (None, name) else None,
                "utterance": heard}).json()
            assistant_lines.append(turn.get("say", ""))
            steps.append({"speaker": name, "step": i, "said": spoken, "heard": heard,
                          "wer": _wer(spoken, heard), "identified": who["name"], "score": who["score"],
                          "stage": turn.get("stage"), "saved": turn.get("saved", False)})

    stored = {n: c.get("/me/answers", params={"token": t}).json() for n, t in tokens.items()}
    result = tool("get_group_result", token=tokens["Maya"])
    own = {n: tool("get_group_result", token=t)["my_share"] for n, t in tokens.items()}  # private per person
    return {"steps": steps, "stored": stored, "result": result, "assistant_lines": assistant_lines,
            "own_share": own}


def write_report(rep: dict, path: Path) -> None:
    steps = rep["steps"]
    ident_ok = sum(1 for s in steps if s["identified"] == s["speaker"])
    mean_wer = sum(s["wer"] for s in steps) / len(steps)
    res = rep["result"]["result"]
    rows = "".join(
        f"| {s['speaker']} | {s['step']} | {s['said']} | {s['heard']} | {s['wer']:.0%} | "
        f"{s['identified'] or 'unknown'} ({s['score']}) | {s['stage']} |\n" for s in steps)
    low = min(steps, key=lambda s: s["score"])
    short = [s["score"] for s in steps if s["step"] == len(FAMILY[s["speaker"]]["says"]) - 1]
    assignments = "".join(
        f"- {a['name']}: " + "; ".join(t["label"] + (" (shared)" if t["shared"] else "") for t in a["tasks"]) + "\n"
        for a in res["assignments"])
    own = "".join(
        f"- {n}: " + ("; ".join(f"{s['label']} {s['hours']} h" for s in lines) or "no task") + "\n"
        for n, lines in rep["own_share"].items())
    path.write_text(f"""# Fictional family simulation (synthetic voices)

Run {date.today()} by `python tests/family_sim.py`.

**This is a fictional family spoken by text-to-speech voices (macOS `say`). No human took part.** It checks
that the voice pipeline works end to end with real audio: speaker identification, Whisper transcription,
the voice-only dialogue, the MCP tool, the private store and the engine. It tells us **nothing** about
whether Huddle makes decisions easier for real people; that needs the real-group test in `docs/user-test.md`.

The cast: Maya, Ben and Chen, three invented siblings sharing a parent's care.

## What happened
- Speaker identified correctly: **{ident_ok}/{len(steps)}** utterances.
- Mean Whisper word error on these scripted sentences: **{mean_wer:.1%}**.
- All three answers stored through the MCP tool: **{all(v["answered"] for v in rep["stored"].values())}**.
- No assistant reply contained a digit (voice-only privacy rule): **{not any(any(ch.isdigit() for ch in ln) for ln in rep["assistant_lines"])}**.

## Caveats (read before quoting any number above)
- Clean text-to-speech with no background noise: Whisper and speaker ID are at their best here. Real microphones, rooms and moods will be worse.
- **The weakest identification was the shortest line.** The closing "Save it." clips scored {min(short):.2f} to {max(short):.2f} cosine against a threshold of 0.50 (lowest overall: {low['speaker']} step {low['step']}, {low['score']}). A one-second confirmation is a fragile thing to identify a speaker from; with real voices it may be missed, so the dialogue's confirm step must not depend on speaker ID alone.
- One run, one fictional family, three voices that happen to be very different from each other.

## The result the family got
{res["headline"]}

Who owns what (what the whole group sees; no hours):

{assignments}
Each sibling's own hours (each returned only to that sibling's token; shown together here only because this family is fictional):

{own}
Gap in hours: {res["gap_hours_bucket"]}; gap in money: {res["gap_dollars_bucket"]}.

## Step by step
| Speaker | Step | Scripted line | Whisper heard | Word error | Identified as (cosine) | Dialogue stage after |
|---|---|---|---|---|---|---|
{rows}
""")


# ---- stand-alone: start a throwaway server and write the report ------------------------------------

if __name__ == "__main__":
    tmp = tempfile.mkdtemp()
    os.environ["HUDDLE_DB_URL"] = f"sqlite:///{tmp}/family.db"
    os.environ["HUDDLE_MODE"] = "mock"
    sys.path.insert(0, str(ROOT))
    import uvicorn

    from server.api import app

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    os.environ["HUDDLE_MCP_URL"] = f"http://127.0.0.1:{port}/mcp"
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.1)
    report = run_family(f"http://127.0.0.1:{port}")
    write_report(report, ROOT / "docs" / "family-simulation.md")
    server.should_exit = True
    print((ROOT / "docs" / "family-simulation.md").read_text())
