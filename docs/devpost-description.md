# Devpost description (draft)

**Placeholders in [BRACKETS] are things that do not exist yet. Do not submit with any left in.**

## Huddle: a private group-decision agent

**Tagline:** Everyone answers privately. Huddle finds the plan that fits, without saying who set which limit.

### The problem
Some group decisions hinge on numbers people don't want to say aloud: what they can spend, how many hours they can give, what they can't do. Whoever speaks first sets the group's limit, so the decision stalls or bends around the most open person. The sharpest case is siblings sharing the care of an ageing parent. Context (AARP and the National Alliance for Caregiving, *Caregiving in the U.S. 2025*): 63 million Americans provided ongoing care for an adult or a child in the past year, at roughly $7,200 a year out of pocket on average, and nearly half had a major financial impact. That our approach eases the stall is a **hypothesis**; [USER TEST RESULT SUMMARY, or "we have not yet tested it with real families"].

### What it does
Huddle is for a family's stream of decisions, hard and easy, handled one way: private limits in, one unattributed plan out. The care plan comes first; weekend and trip plans follow for the same household without retyping who's in it, and whoever carries heavy care tasks gets an optional private hint when leisure plans are made (built only from the published care split, shown only to them, never applied for them).

Huddle asks each person privately (by voice at a shared device, or a one-time link on their phone), works out what is compatible, and proposes one plan with the trade-off explained and nobody named. It handles non-responders with a reminder and a stated default, lets people change their answer until the round closes, and checks in the next day. If the check-in shows someone isn't comfortable, the host starts a follow-up round for the same people (everyone answers fresh); in care mode a fair-share record rotates heavy tasks across rounds using past assignments only. The result comes as a plan card the assistant can read aloud.
- **Care mode:** each sibling privately gives hours/week, dollars/month and tasks they can't do. The group sees the gap in bands, a task split that respects every limit, and ways to close the gap.
- **Weekend plan** and **trip** decisions run on the same engine and belong to the same household as the care plan.
It decides; it does not book, split expenses or give medical, legal or financial advice.

### How we built it
- **Alexa+ track.** A self-hosted **MCP server** (official Python SDK, **Streamable HTTP, protocol 2025-11-25**) exposes `start_huddle`, `submit_private_answer`, `get_group_result`, `close_round`, `nudge_pending`, `submit_checkin` and `revisit_round`. Alexa+ developer tools are preview and select-partner only, so the Alexa+ experience is a **web simulator** in the repo; its agent calls the MCP server over HTTP at runtime. The video labels it as simulated.
- **Privacy engine.** Coarse bands, a k ≥ 3 rule for anything that hinges on one limit, and an automated **leak test** that seeds distinctive values and calls every route and tool as every participant, failing if anyone else's value (or their band next to their name) appears.
- **Care solver.** An integer program (SciPy `milp`) that maximises hours covered and then spreads the load, respecting each person's hours and dealbreakers.
- **Voice-only mode for a shared speaker.** The assistant first asks whether anyone is nearby and offers a private phone link or the screen; it never says a private value aloud unless asked (opt-in read-back); the draft stays on the server and is saved through the MCP tool. See `docs/alexa-fit.md` for why this matters and what is simulated.
- **Voice.** Browser speech recognition, optional local Whisper, and SpeechBrain ECAPA speaker identification as a **stand-in** for Alexa person recognition.
- **AWS.** [AMAZON BEDROCK + STRANDS AGENTS SDK: describe what ran and the measured latency. NOT YET RUN.] [BEDROCK AGENTCORE RUNTIME hosting: describe. NOT YET DEPLOYED.]
- Open source (MIT): React + Vite, FastAPI, SQLite, Playwright, Docker.

### Honest limits
- Privacy here is no-attribution plus bucketing, **not cryptographic secrecy**. With two people the other can infer your number; with three or more, who set a limit is hidden. The UI says so.
- Assignments in care mode can hint at someone's capacity.
- Voice ID is a stand-in, not security; accuracy was measured on synthetic voices only. [REAL-VOICE RESULT, if collected.]
- The Alexa+ experience is simulated; reminders are simulated.

### Tracks and challenges
Primary track: **Alexa+**. Mini-challenges: **AWS Builder** [only if the AWS parts above ran] and **Open Source** (public MIT repo created after Aug 31, 2026).

### Pre-hackathon work
New project, started after Aug 31, 2026. No prior code reused. No financial or preferential support from Amazon or Devpost.

### What we learned / friction
See `docs/friction-log.md` and `docs/product-feedback.md` in the repo.
