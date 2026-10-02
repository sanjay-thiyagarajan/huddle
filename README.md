# Huddle

A private group-decision agent. It asks each person privately (voice at home, a link when remote), computes what is compatible, and proposes one plan with the trade-off explained, without revealing who limited it. It decides; it does not plan or book.

Built for the [Amazon Developer Hackathon](https://amazonappdev2026.devpost.com/) (primary track: Alexa+; mini-challenges: AWS Builder, Open Source). New project, started after Aug 31, 2026.

**Status:** P0-P3 done, plus the P7 items that need no outside input (Playwright E2E, accessibility audit, Docker) (engine, MCP server, care mode, simulator and link flow, mock mode). P4 built and measured on synthetic voices only (see [docs/voice-accuracy.md](docs/voice-accuracy.md)); not yet built: Bedrock/Strands/AgentCore (P5), real-voice and real-group tests (P4/P6). See [docs/development-plan.md](docs/development-plan.md).

## Quickstart (mock mode, no AWS credentials)

```
make install
make dev     # API + MCP on :8000, simulator on http://localhost:5173
make test    # includes the privacy leak test
make e2e     # Playwright (needs Google Chrome): demo flows, failure path, axe a11y audit
make docker  # or: docker compose up --build  -> http://localhost:8000
```

## How it works

- `server/mcp_server.py`: self-hosted MCP server, Streamable HTTP at `/mcp`, protocol 2025-11-25 (official `mcp` SDK, pinned `<2`). Tools: `start_huddle`, `submit_private_answer`, `get_group_result`, `close_round`, `nudge_pending`.
- The simulator (`web/`) stands in for Alexa+. Its agent calls the MCP server over HTTP at runtime (`/api/agent/tool` proxies to `/mcp`).
- `server/engine/`: `privacy.py` (buckets, k rule, leak guard), `rounds.py` (lifecycle: collecting, reminded, closed, with defaults for non-responders), `everyday.py`, `care.py` (integer task split via `scipy.optimize.milp`).
- Private answers are stored server-side and returned only to their owner (`GET /me/answers`).
- `tests/test_leak.py` seeds distinctive values and calls every REST route and MCP tool as every participant; it fails if another person's value (or their bucket next to their name) appears. `tests/e2e_mock_demo.py` runs a scripted care round against a live server.

## Honest limits

- Answers are never shown or attributed. This is no-attribution plus bucketing, **not cryptographic secrecy**. With two people, the other person can infer your number; the UI says so.
- Care mode shows assignments, not capacities, but an assignment can hint at what someone can do.
- Voice identification (SpeechBrain ECAPA, optional: `pip install '.[voice]'`) and the profile switcher stand in for Alexa person recognition. They separate profiles; they are not security. Only an embedding is stored, never the recording; `DELETE /api/voice/profiles/{name}` removes it.
- Voice accuracy has only been measured on text-to-speech voices (25/25 identified, 5/5 unknown speakers rejected). That says the pipeline works, not how it behaves for real family voices.
- Care mode is a decision aid, not medical, legal or financial advice. It collects no health data.
- Checked by hand in Chrome (mock mode): care round via the simulator, spoken-answer parsing, server-holds panel, close with defaults, reveal, and the link page. Playwright E2E (`make e2e`) now automates the care round with a remote link, the reminder-then-defaults path, DOM checks that no other person's value appears, and an axe WCAG A/AA audit in light and dark.

## Licence

MIT. Third-party components: [THIRD_PARTY.md](THIRD_PARTY.md).
