# Huddle: Development Plan (feed this file to Claude Code)

Project: **Huddle**, a private group-decision agent for the Amazon Developer Hackathon (https://amazonappdev2026.devpost.com/).
Idea source: `hackathon-ideas/amazonappdev2026-user-ideas.md` (U2, v5).
Today: 2026-10-02. **Submission deadline: Oct 23, 2026, 12:00pm PT.** Internal freeze: **Oct 21 evening**. AWS credit request deadline: **Oct 21, 12:00pm PT** (request today).

---

## 0. How Claude should use this file

1. Read the whole file before writing code. Sections 1 and 2 are hard constraints; section 9 is the build order.
2. Work phase by phase. At the end of each phase, run that phase's acceptance checks and report results truthfully (pass/fail with output) before moving on.
3. Keep a running `docs/friction-log.md` and `docs/product-feedback.md` (see section 8). Append to them whenever you hit a problem with any tool, API or SDK (MCP SDK, Strands, Bedrock, AgentCore, speaker-recognition model, and so on). They earn up to +10% in judging.
4. Do not add features outside section 4. If time is short, cut from the "stretch" list in order.
5. Never claim the privacy is cryptographic. Wording is "never shown or attributed" (see section 5).

---

## 1. Hackathon requirements (verified 2026-10-02 from the Devpost page, rules and FAQ)

### Hard requirements (miss one and the entry fails)
| # | Requirement | Source wording / detail | How Huddle satisfies it |
|---|---|---|---|
| R1 | Stage 1 pass/fail: project "reasonably fits the theme and reasonably applies the required APIs/SDKs" | Theme: "Build across Amazon Devices and shape what's next" (Fire TV, Alexa+, Ring, Bee) | Primary track **Alexa+**; Huddle is a household voice agent |
| R2 | Alexa+ track tech | "Working Agent Skill or a self-hosted MCP server", **MCP spec min 2025-11-25, Streamable HTTP**. Alternative: a "simulated Alexa+ experience" is allowed, but then "the code repository must still include the simulation's source code, and the demo video must clearly show the simulated experience." | Build a **self-hosted MCP server (Streamable HTTP, spec 2025-11-25+)** and a web simulator that acts as Alexa+ |
| R3 | Runtime use proven in repo | For Alexa+, repo must show track tech "imported and actually called (a library import, an app/backend entry point, or a loaded agent/flow/MCP config)" | The simulator's agent connects to the MCP server over HTTP at runtime; MCP SDK import is in `server/` |
| R4 | Text description | "explain what it does and how it works" | `README.md` plus Devpost text (draft in `docs/devpost-description.md`) |
| R5 | Code repo on **GitHub** (GitLab etc. not accepted) | Public with an OSI licence file **visible in the repo's About section**, OR private and shared with testing@devpost.com plus the six named Amazon GitHub profiles listed in the Official Rules | **Public repo, MIT or Apache-2.0 licence**, check the About sidebar shows it |
| R6 | Demo video | **< 3:00**, YouTube or Vimeo, **public, English**, must show the project functioning on the device it was built for; no third-party trademarks or copyrighted music | Record the simulator; no music, or royalty-free with a licence; avoid Amazon/Alexa logos beyond plain text naming |
| R7 | Product feedback on **every tool/API/SDK used** | Covers: tools used and purpose; what worked (setup, docs, testing, performance, reliability); what needs improvement; onboarding "zero to hello world"; would you build again (Y/N plus why) | `docs/product-feedback.md` |
| R8 | Track and mini-challenge selection | One primary track; a project wins at most one track prize and one mini-challenge prize | Alexa+ plus AWS Builder plus Open Source (see below) |
| R9 | Pre-hackathon work disclosure | Pre-existing projects must be significantly updated after Aug 31, 2026, and the update must be demoed. Project must not have had financial or preferential support from Amazon/Devpost | Huddle is **new**; start the repo fresh and say so |
| R10 | Original work, third-party tools used within their licences | Entrant must own the work and be authorized to use any tools | Keep a `THIRD_PARTY.md` listing models and libraries and their licences |
| R11 | Eligibility | Age of majority; not residents of Brazil, Quebec, Russia, Crimea, Cuba, Iran, North Korea; not Amazon/Devpost employees | Confirm for every team member |

### Judging (Stage 2): four criteria, **equally weighted (25% each)**
1. **Tech Implementation**: how effectively the required tech is used.
2. **Design**: a "complete, coherent product experience".
3. **Potential Impact**: a "credible, specific case for solving customer needs".
4. **Quality of the Idea**: a "creative, imaginative use of the required tools".
Bonus: **friction log up to +10%** (assessed in Stage 1 by Amazon's team). Format: specific task attempted, steps taken, expected vs actual result, severity rating, workaround used, actionable suggestion.

### Mini-challenges (both are cheap for Huddle, so enter both)
- **AWS Builder** ($5K + $5K credits): "incorporates AWS services (Bedrock, AgentCore, Strands SDK, Kiro Crew, SageMaker...) with documented integrations." Judged inside Tech Implementation. You must describe which AWS services you used and how in the Product Feedback answer. (Kiro Crew alone also qualifies as a dev tool.)
- **Open Source** ($5K + $5K credits): create a new open-source project or contribute to a public repo during the hackathon window alongside the primary submission. Submit: contribution URL, project repo URL, GitHub username, description of the work and why it matters. Huddle's public MIT repo qualifies if it is created after Aug 31, 2026. Confirm on the rules page that the main repo alone satisfies it; if in doubt, also make one small PR or a separate small repo (for example the `huddle-private-match` library, split out as its own package).

### Prizes in play
Alexa+ 1st $25K + $15K AWS credits; AWS Builder $5K + $5K; Open Source $5K + $5K. Judging Nov 9-20; winners Dec 3, 2026.

### Platform facts that shape the build (from FAQ)
- Alexa+ developer tools (Category SDK, MCP Toolkit, CLI, Web Simulator) are **preview, select partners only**. We cannot use real Alexa+. Demonstrate through **our own web-based simulator / front end**.
- No physical device needed. A **locally runnable public repo plus the demo video** is enough; hosting is not required (judges build and test it themselves). So: `docker compose up` or `make dev` must work from a clean clone with **mock mode needing no AWS credentials**.
- AWS: $150 promotional credits per individual (request by Oct 21). Spin up AWS resources only for testing, tear down after. Mock Bedrock during early development.
- Because Alexa's native `personId` is not available, voice recognition is a **stand-in** (speaker embeddings). Label it clearly as such in the demo and README.

### Open items to confirm on Day 1 (do not assume)
- [ ] Read the full Official Rules text once for anything the summary above missed (six GitHub handles, licence list, the "device" wording in the video rule, any limit on pre-recorded or simulated content).
- [ ] Confirm that a simulator front end plus an MCP server satisfies "project functioning on the device it was built for" for Alexa+ (ask via the Devpost discussion tab or organizer contact; save the answer in `docs/confirmations.md`).
- [ ] Confirm that the Open Source mini-challenge counts the main repo.
- [ ] Request AWS credits (form linked from the hackathon page).

---

## 2. Product scope

**One line:** Huddle asks each person *privately*, in the way that suits them (voice at home, a link when remote), computes what is compatible, and proposes one plan with the trade-off explained, without revealing who limited it.

**It decides. It does not plan.** No booking, no expense splitting, no itineraries, no calendar access, no medical, legal or financial advice, no health records.

### Modes (one engine)
- **Everyday mode (on-ramp):** weekend or holiday plan. Inputs per person: must-haves, dealbreakers, budget ceiling, vibe.
- **Care mode (main story):** siblings share care of an aging parent. Inputs per person: hours/week available, monthly dollars they can contribute, dealbreakers (task types they cannot do: nights, transport, appointments, finances, daily check-ins; or "lives far away"). Output: aggregate gap and a task and money split that respects every private limit.
- **Stretch:** friend trips (same engine, new template).

### Core mechanic: private preference matching
- Private answers are stored server-side, never returned to any other participant by any endpoint or MCP tool.
- The engine computes group-level results only, in **coarse buckets**, never attributed.
- Care mode shows **assignments but not capacities**.
- Honest limits (say them in the README and video): this is no-attribution plus bucketing, not cryptographic secrecy. In a 2-person group, the other person can infer your number from a bucket. Groups of 3+ hide who set the limit.

---

## 3. Architecture

```
huddle/
  server/                     # Python 3.12, FastAPI + official MCP Python SDK
    mcp_server.py             # MCP server, Streamable HTTP, spec 2025-11-25+
    api.py                    # REST for simulator + link flow
    engine/
      privacy.py              # buckets, k-anonymity guard, leak guard
      everyday.py             # weekend/holiday matching
      care.py                 # care-mode aggregate + assignment solver
      rounds.py               # round lifecycle: open, remind, deadline, defaults, close
    agent/
      huddle_agent.py         # Strands agent on Bedrock (mock provider fallback)
      prompts.py
    voice/
      speaker_id.py           # enrol + identify (speaker embeddings)
      stt.py                  # transcription (browser Web Speech API primary; server fallback optional)
    db.py                     # SQLite (SQLModel)
  web/                        # Vite + React + TypeScript: the "Alexa+ simulator" and the link flow
    src/simulator/            # Echo-style voice UI, enrolment, per-person private panels
    src/link/                 # /r/<token> private answer page for remote people
    src/reveal/               # group result screen (aggregate only)
  deploy/                     # AgentCore deployment, Dockerfile, compose
  tests/
  docs/
  LICENSE (MIT)  README.md  THIRD_PARTY.md  Makefile
```

### Technology choices (and why each is load-bearing)
| Tech | Use | Requirement served |
|---|---|---|
| **MCP Python SDK**, Streamable HTTP, protocol 2025-11-25+ | The household agent's tools: `start_huddle`, `submit_private_answer`, `get_group_result`, `close_round`, `nudge_pending` | R2, R3 (Alexa+ track) |
| **Strands Agents SDK + Amazon Bedrock** | The conversational agent that asks questions, parses free-form answers into structured fields, and explains trade-offs. Use a Claude model on Bedrock. Check the Bedrock model catalog for the current model ID; do not hard-code from memory | AWS Builder |
| **Bedrock AgentCore** (Runtime to host the agent/MCP server, optionally Memory or Identity) | Hosted deployment used for the demo recording and judging window, torn down after | AWS Builder |
| **Speaker embeddings** (SpeechBrain ECAPA-TDNN `speechbrain/spkrec-ecapa-voxceleb`, Apache-2.0, or Resemblyzer) | Stand-in for Alexa person recognition: maps a voice to a profile so several people at one device keep separate private answers | Core mechanic |
| **Link flow** (`/r/<token>`, signed single-use, expiring) | Remote participants answer privately from any phone; also the fallback if voice ID fails | Core mechanic |
| SQLite | Rounds, participants, private answers | Local-runnable repo |

**Mock mode:** `HUDDLE_MODE=mock` swaps Bedrock for a deterministic stub, and speaker ID for a profile switcher. The repo must run fully in mock mode with zero credentials. `HUDDLE_MODE=aws` uses real Bedrock and AgentCore.

**Voice in the simulator:** record in the browser (`MediaRecorder`), send audio to `/api/voice/identify` for speaker ID, and transcribe with the browser Web Speech API (no cost, works in Chrome). Keep a text input as a fallback.

---

## 4. Features, with acceptance criteria

### MVP (must ship, in priority order)
**F1. MCP server (R2, R3).**
- Streamable HTTP endpoint at `/mcp`; declares protocol version 2025-11-25 or later; tools listed in section 3.
- Acceptance: a test client using the official MCP SDK connects over HTTP, lists tools and completes a full round. Record the negotiated protocol version in a test assertion (>= 2025-11-25). If the installed SDK does not support that version, upgrade or pin a version that does, and log it in the friction log.

**F2. Private answer store and round lifecycle.**
- A round has: id, mode, participants (name, channel: voice or link), deadline, state.
- States: `collecting` -> `reminded` -> `closed`. At the deadline, non-responders get **defaults** (everyday: the median bucket and no dealbreakers; care: 0 hours and $0, which makes the gap visible), and the result states that defaults were applied.
- Acceptance: no endpoint or MCP tool other than the owner's own `GET /me/answers` returns another person's raw answers (see F3 leak test).

**F3. Privacy engine (`engine/privacy.py`) and leak guard.**
- Buckets: money in fixed bands (for example $0-100, 100-250, 250-500, 500-1000, 1000+); hours in 5-hour bands.
- Reveal rule: only aggregate results; group size k >= 3 for any aggregate that depends on a single limiting value; for k = 2 show the warning banner "With two people, the other person may be able to infer your number."
- **Leak test (required, automated):** seed a round with distinctive sentinel values (for example $437, 13 h). Call every API route and MCP tool as every participant. Assert that no response body contains any other participant's sentinel value or their exact bucket attributed by name. Run in CI.

**F4. Everyday mode.**
- Fixed option set for the demo (for example 6 weekend activities with a price band and tags). Matching = filter by every dealbreaker, then rank by vibe overlap, within the group-wide budget bucket.
- Output: top plan plus one-sentence trade-off ("Picked X; two of you preferred Y, but the budget bucket ruled it out"), never naming who.

**F5. Care mode.**
- Inputs per person (private): hours/week, $/month, dealbreaker tasks.
- Care need (entered by whoever starts the round, visible to all): total hours/week and $/month, plus a task list with hours (for example daily check-in 7 h, appointments and transport 6 h, meals 8 h, finances/paperwork 3 h, overnight 6 h).
- Aggregate reveal: "The plan needs 30 h/week and $1,800/month; together you can cover 26 h and $1,500; gap 4 h and $300", with gap-closing options (paid respite hours, reduce overnight cover, shift tasks). Gap figures are bucketed.
- Assignment solver: greedy or small LP (`scipy.optimize.linprog` or a hand-rolled greedy). Respect each person's hours, dollars and dealbreakers. Output the task split without showing capacities.
- Acceptance: unit tests with 3 people and known inputs yielding a valid split and the expected gap; a test that infeasible inputs produce a gap, not an error; a test for the "assignments hint at capacity" caveat being displayed on screen.
- Guardrails: UI label "Decision aid, not medical, legal or financial advice"; collect no health data; free-text fields are scanned and a warning is shown if they look like health details.

**F6. Simulator front end (the "Alexa+" the judges see).**
- Echo-style screen with a wake prompt ("Alexa, plan our Saturday" typed or spoken; use generic styling, no Amazon logos).
- Voice enrolment for 2-3 people (say 3 phrases each). Identification shows "Recognized: Maya" and the person's private panel opens.
- Each person has a private answer panel; a "what the server holds" debug panel (toggle) that shows only that the answers are stored, not their values, to support the "nobody sees it" wow moment.
- Reveal screen: aggregate, trade-off, final plan, banner with the honest-limits note.
- Link flow page for the remote person.
- Acceptance: a non-developer can complete both rounds in under 5 minutes from a clean `make dev`.

**F7. Agent (Strands on Bedrock).**
- Turns a spoken answer ("I can do maybe ten hours but not nights") into a structured private answer; asks one follow-up if a field is missing; produces the trade-off sentence.
- All structured answers must be validated by Pydantic before storage; the agent never sees other participants' raw answers (it is invoked per person with only that person's input, and again on the **aggregate** only to explain the result).
- Acceptance: in `aws` mode, run the same two scripted rounds; log latency; record any friction.

**F8. Failure path (shown in the demo).**
- One sibling never answers: scheduled reminder fires (simulate with a short deadline), then defaults apply and the plan says so.

### Stretch (cut in this order, last item first)
1. Family memory log (next-day private question, saved card per event).  2. Friend-trip mode.  3. Fairness record across rounds.  4. SMS delivery (US needs A2P 10DLC; skip).  5. Secure multi-party computation (out of scope).

### Extensions added after the plan (2026-10-04)
The repo now also has a household chore planner and a private "My time" schedule (see README and `docs/scheduling.md`). On
2026-10-04 the owner asked for calendar files, a daily briefing and reminders, built in the same style as the scheduling code:
- **Calendar files:** read an `.ics` file (or a read-only calendar address) as the person's own private commitments, and export commitments or chores as `.ics`. This is **not** a sync with, or sign-in to, Outlook, Google or Apple Calendar; "calendar access" below still means that, and stays out of scope.
- **Daily briefing:** `get_daily_briefing`, "what's my day", and a Today card: the caller's own items only.
- **Opt-in reminders:** starting soon, and a Sunday digest, through the existing notifier; no Alexa notification is claimed.

### Out of scope (do not build)
Itineraries, bookings, expense splitting, calendar access, real-time flight/hotel prices (use mock data), accounts and login beyond signed round tokens.

---

## 5. Honesty and safety rules (judges reward credible claims)
- Wording: "private", "never shown or attributed". Never "secret", "encrypted" or "secure" for the matching itself.
- State the two-person inference limit in the README, the UI and the video.
- Voice ID is a **stand-in** for Alexa person recognition. Alexa's own personalization docs note "personalization isn't authentication". Say that voice identification here is for separating profiles and not for security.
- Impact claims: only the sourced AARP figures (63 million US family caregivers, about $7,200/year out of pocket, per https://www.aarp.org/press/releases/2025-07-24-new-report-reveals-crisis-point-for-americas-63-million-family-caregivers.html) are facts. "Families stall on splitting care" and "Huddle reduces stress" are **hypotheses** unless the user test (section 7) supports them. Do not present them as findings.
- Consent: every participant opts in before answering; adults only.

---

## 6. Build schedule (21 days; 4 buffer days)

| Phase | Dates | Deliverable | Gate |
|---|---|---|---|
| **P0 Setup and verification** | Oct 2-3 | Repo, licence, CI, AWS credits requested, Day-1 confirmations (section 1), novelty search (Devpost, GitHub, web: group decision tools, private budget matching, Alexa family planners), friction log started | Confirmations saved in `docs/confirmations.md`; if the novelty search finds a near-duplicate, record how Huddle differs |
| **P1 Engine and MCP** | Oct 3-7 | F1, F2, F3 (with leak test), F4 | `pytest` green; MCP test client completes an everyday round |
| **P2 Care mode** | Oct 7-10 | F5 with tests | Care scenario (3 people) produces the expected gap and split |
| **P3 Simulator and link flow** | Oct 8-13 (overlaps P2) | F6 in mock mode | End-to-end demo run in mock mode, no credentials |
| **P4 Voice ID** | Oct 11-14 | Speaker enrolment and identification, measured accuracy on 3+ voices (record the numbers in `docs/voice-accuracy.md`) | Accuracy acceptable, otherwise ship the profile switcher and label it |
| **P5 AWS integration** | Oct 12-16 | F7 on Bedrock plus Strands; deploy to AgentCore; document each integration | Scripted rounds run in `aws` mode |
| **P6 Real-group test** | Oct 14-17 | 2-3 real groups (family or friends) run a round; record time to decision, a 1-5 "how stressful was deciding" before/after, one quote per person | Results saved in `docs/user-test.md` (honest numbers, even if mediocre) |
| **P7 Polish and failure path** | Oct 16-18 | F8, accessibility pass, empty/error states, README | Fresh clone runs with `make dev` |
| **P8 Demo and submission assets** | Oct 18-20 | Video, Devpost text, product feedback, friction log finalized | Video < 3:00, public, uploaded |
| **P9 Buffer and submit** | Oct 21-22 | Submit on **Oct 21 evening** or Oct 22 | Submission page re-checked line by line against section 10 |
| Hard deadline | **Oct 23, 12:00pm PT** | Do not plan to use this day | |

Cut rules: if P4 (voice) slips past Oct 14, switch to the profile switcher. If P5 slips past Oct 17, ship the Bedrock calls without AgentCore hosting (the AWS Builder claim stays valid with Bedrock plus Strands as long as they are called at runtime and documented).

---

## 7. Testing plan
- Unit: privacy buckets, k rule, care solver (feasible, infeasible, dealbreaker conflict), round lifecycle with a fake clock.
- **Leak test** (F3): a CI gate.
- Protocol: MCP client conformance check (version negotiation, tool listing, Streamable HTTP).
- Voice: confusion matrix on 3+ speakers, 5+ clips each; report accuracy.
- E2E: Playwright script running the full demo in mock mode.
- Human: 2-3 real groups as in P6. Do not fabricate results.

---

## 8. Documentation deliverables
- `docs/friction-log.md`: entries in the required format (task attempted, steps taken, expected vs actual, severity, workaround, actionable suggestion). Aim for 8+ honest entries across MCP SDK, Strands, Bedrock, AgentCore, speaker model.
- `docs/product-feedback.md`: one section per tool/API/SDK used. Each covers purpose, what worked, what to improve, zero-to-hello-world experience, would you build again (Y/N and why). Include the AWS services used and how (needed for the AWS Builder mini-challenge).
- `docs/devpost-description.md`: what it does, how it works, track and mini-challenge selection, pre-hackathon disclosure ("new project started after Aug 31, 2026"), honest limits.
- `README.md`: what it is, architecture diagram, quickstart (`make dev` in mock mode; `HUDDLE_MODE=aws` setup), the stand-in disclosure, privacy limits, licence.
- `THIRD_PARTY.md`: libraries, models and licences.

---

## 9. First prompts for Claude Code (copy in order)

1. "Read `hackathon-ideas/huddle-development-plan.md`. Create the repo skeleton from section 3 in `~/Desktop/OpenSource/huddle` (new git repo, MIT licence, Makefile with `dev`, `test`, `lint`), plus empty `docs/friction-log.md`, `docs/product-feedback.md`, `docs/confirmations.md`. Do not implement features yet."
2. "Implement P1: `engine/privacy.py` (buckets, k rule) and the leak test harness first, then `rounds.py`, `everyday.py`, then the MCP server over Streamable HTTP with the tools in section 3. Use the official MCP Python SDK and verify the protocol version is >= 2025-11-25 in a test. Log any SDK problem in the friction log."
3. "Implement P2: care mode per F5 with the solver and tests."
4. "Implement P3: the Vite + React simulator and link flow in mock mode; use the `frontend-design` skill for a distinctive, accessible design; no Amazon logos."
5. "Implement P4: speaker enrolment and identification with SpeechBrain ECAPA; produce a confusion matrix; add the profile-switcher fallback."
6. "Implement P5: Strands agent on Bedrock with mock fallback; AgentCore deployment config; document each AWS service in product-feedback."
7. "Implement P7-P8 items: failure path, README, Playwright E2E, demo script."

---

## 10. Demo video script (< 3:00; aim for 2:40)

| Time | Beat | Shows |
|---|---|---|
| 0:00-0:15 | Hook: "Some decisions stall because nobody wants to say their real number out loud." | Title card, plain text |
| 0:15-0:35 | Everyday: "Alexa, plan our Saturday." Two people answer privately; one plan with a trade-off | Voice recognized, private panels, reveal |
| 0:35-1:55 | **Care mode (main story):** three siblings, one by link from another city. Server holds the numbers, nobody sees them. Aggregate gap "4 h and $300", options to close it, then a split that respects every limit without naming who set one | Debug panel, aggregate reveal, split |
| 1:55-2:15 | Failure path: one sibling never answers; reminder; defaults applied and stated | Timer, reminder, banner |
| 2:15-2:35 | Under the hood: MCP server over Streamable HTTP, Strands on Bedrock, AgentCore, the leak test passing | Terminal and architecture slide |
| 2:35-2:50 | Honest limits and results from the real-group test; "same engine, any group decision" | One slide with real numbers |

Video checklist: no music (or properly licensed), no third-party logos, English, public on YouTube or Vimeo, clearly labels the simulator and the voice-ID stand-in.

---

## 11. Final submission checklist (re-check on Oct 21)
- [ ] Repo on **GitHub**, public, licence visible in the About section (or private and shared with testing@devpost.com plus the six named Amazon profiles)
- [ ] Repo shows MCP SDK imported and called at runtime; MCP spec >= 2025-11-25, Streamable HTTP
- [ ] Fresh clone: `make dev` works in mock mode without credentials
- [ ] Simulator source code in the repo; the video clearly shows the simulated experience
- [ ] Video < 3:00, public, English, no unlicensed music or trademarks
- [ ] Text description; primary track = Alexa+; AWS Builder and Open Source selected
- [ ] Open Source mini-challenge fields: contribution URL, repo URL, GitHub username, description
- [ ] Product feedback covers **every** tool/API/SDK used and names the AWS services and how they were used
- [ ] Friction log in the required format
- [ ] Pre-hackathon work disclosure completed (new project)
- [ ] AWS credits requested by Oct 21 12:00pm PT; resources torn down after judging
- [ ] Claims in the text match section 5 (no unsupported impact claims)
- [ ] Submitted before **Oct 23, 12:00pm PT** (target Oct 21-22)
