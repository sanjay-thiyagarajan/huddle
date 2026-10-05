# Devpost description (draft)

**Placeholders in [BRACKETS] are things that do not exist yet. Do not submit with any left in.**

## Huddle: a fair, private home

**Tagline:** Everyone tells Huddle privately what they can take on. Huddle proposes a fair plan, without saying who set which limit.

### The problem
In a home the load piles up on one person, and it comes in three sizes: the **heavy** (caring for a parent), the **daily** (the chores) and the **occasional** (a weekend, a trip). Each depends on numbers people find hard to say aloud: how much time they can really give, what they can spend, what they can't do. Whoever speaks first sets the group's limit; everyone else stays quiet or carries more. The evidence on how unequal the load is: BLS American Time Use Survey 2025 (women 2.8 hours a day on household activities, men 2.1, among those who did any); Pew Research (59% of women say they do more of the chores); Daminger 2019 (interviews with 35 couples: one partner did more of the anticipating and monitoring); Ervin et al., *The Lancet Public Health* 2022 (in 11 of 14 studies, more distress as unpaid labour rose); and for care, AARP and the National Alliance for Caregiving, *Caregiving in the U.S. 2025* (63 million caregivers, roughly $7,200 a year out of pocket). None of these test Huddle; that it eases the load is a **hypothesis**. [USER TEST RESULT SUMMARY, or "we have not yet tested it with real households".]

### One home, three sizes of load
Huddle handles all three the same way (*private limits in, one unattributed plan out*) in **one household**: the same people and one private profile each.
- **The heavy: care.** Siblings share a parent's care between them: the hours each can give (check-ins, appointments and transport, meals, paperwork, overnight cover), the money each can put in, the tasks they can't do. Huddle does not hire nurses, book providers or move money; when the family can't cover the need, it suggests paid help as one option.
- **The daily: chores.** A fair agent plans each week from everyone's private availability, preferences and skills (hard limits, then a fair share with mental load weighted up, then preferences, then rotation of heavy chores), keeps a ledger of what people actually did, and **offers** new chores to the best-fit person, who can accept or decline (a decline, or 24 hours of silence, sends it to the next; nobody can see who was asked). Chores are added any time in plain words or pre-planned.
- **The occasional: a weekend or trip.** One plan and the trade-off, nobody named.
- **Your own time.** One private schedule across family, friends, work and personal life; a clash is explained and settled by conversation; find-a-time returns a time and a trade-off, never who couldn't make which (`docs/scheduling.md`).
- **They connect.** The care you've taken on counts in your chore share (using only what the household already sees: who owns each task and its total hours). Whoever carries heavy care gets an optional private hint when leisure is planned. A heavy week reported privately lightens the next. Details: `docs/fairness-agent.md`; evidence: `docs/evidence-household-load.md`. Chore apps with fairness scores and AI assistants exist (`docs/novelty-search.md`); keeping each person's limits private from the household is the difference.

### How we built it
- **Alexa+ track.** A self-hosted **MCP server** (official Python SDK, **Streamable HTTP, protocol 2025-11-25**) exposes 30 tools: seven for family decisions (`start_huddle`, `submit_private_answer`, `get_group_result`, `close_round`, `nudge_pending`, `submit_checkin`, `revisit_round`), eleven for the household (`create_household`, `get_household`, `set_my_profile`, `add_chore`, `plan_week`, `respond_to_assignment`, `hand_back_chore`, `complete_chore`, `week_checkin`, `ask_household_agent`, `start_household_decision`) and twelve for a person's own schedule (`get_my_time`, `add_commitment`, `update_commitment`, `set_schedule_rules`, `start_gathering`, `answer_gathering`, `ask_schedule_agent`, `get_daily_briefing`, `import_calendar`, `export_calendar`, `subscribe_calendar`, `set_reminder_prefs`). The server is written for a host that has never seen the repo: its instructions tell a voice assistant to ask who can hear, never say an answer back and ask for consent; every tool has a title, explicit behaviour hints and an output schema; and CI lists the tools from a second, non-Python client (the MCP Inspector CLI). Alexa+ developer tools are preview and select-partner only, so the Alexa+ experience is a **web simulator** in the repo; its agent calls the MCP server over HTTP at runtime. The video labels it as simulated.
- **Privacy engine.** Coarse bands, a k ≥ 3 rule for anything that hinges on one limit, and an automated **leak test** that seeds distinctive values and calls every route and tool as every participant, failing if anyone else's value (or their band next to their name) appears.
- **Chore planner.** An integer program that works in strict order: hard limits, then a fair share in proportion to each person's own availability (a leximin, so the rest of the household stays balanced even when one person is already over their share), then preferences and skills, then rotation. Care taken on counts, using only public task ownership.
- **Care solver.** An integer program (SciPy `milp`) that maximises hours covered and then spreads the load, respecting each person's hours and dealbreakers.
- **Voice-only mode for a shared speaker.** The assistant first asks whether anyone is nearby and offers a private phone link or the screen; it never says a private value aloud unless asked (opt-in read-back); the draft stays on the server and is saved through the MCP tool. See `docs/alexa-fit.md` for why this matters and what is simulated.
- **Voice.** Browser speech recognition, optional local Whisper, and SpeechBrain ECAPA speaker identification as a **stand-in** for Alexa person recognition.
- **AWS.** [AMAZON BEDROCK + STRANDS AGENTS SDK: describe what ran and the measured latency. NOT YET RUN.] [STRANDS AGENT AS THE MCP HOST (`scripts/aws_mcp_host.py --bedrock`): paste which tools the model chose. Discovery and tool calls through Strands' MCP client are tested; the MODEL STEP IS NOT YET RUN.] [BEDROCK AGENTCORE RUNTIME hosting: describe. NOT YET DEPLOYED.]
- Open source (MIT): React + Vite, FastAPI, SQLite, Playwright, Docker.

### Honest limits
- Privacy here is no-attribution plus bucketing, **not cryptographic secrecy**. With two people the other can infer your number; with three or more, who set a limit is hidden. The UI says so.
- Care mode shows the group who owns each task and never anyone's hours (each person sees only their own, privately). It can still hint: a person who owns a task alone can cover at least that task's hours. On a shared screen, a selected profile's own hours are visible to anyone nearby.
- Household inputs (availability, preferences, how a week felt) are self-reported. Caps, a floor on availability and a bounded adjustment limit the effect, but cannot prove honesty. Someone who owns a chore alone has shown they can do at least that much. See `docs/fairness-agent.md`.
- Voice ID is a stand-in, not security; accuracy was measured on synthetic voices only. [REAL-VOICE RESULT, if collected.]
- The Alexa+ experience is simulated. Reminders are real (a background scheduler; in-app banners and notifications while a page is open; email only when SMTP is configured) but there is no SMS, web push or Alexa notification.

### Tracks and challenges
Primary track: **Alexa+**. Mini-challenges: **AWS Builder** [only if the AWS parts above ran] and **Open Source** (public MIT repo created after Aug 31, 2026).

### Pre-hackathon work
New project, started after Aug 31, 2026. No prior code reused. No financial or preferential support from Amazon or Devpost.

### What we learned / friction
See `docs/friction-log.md` and `docs/product-feedback.md` in the repo.
