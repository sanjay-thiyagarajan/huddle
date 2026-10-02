# Amazon Developer Hackathon: user-submitted ideas
https://amazonappdev2026.devpost.com/ · judged 2026-10-02 · deadline Oct 23, 2026 12:00pm PT (21 days left)
User constraints: minimum reach 1,000,000 users per idea (default)
Brief (from earlier research in this project): Stage 1 pass/fail on theme fit and required API/SDK use; Stage 2 four equal criteria (25% each): Tech Implementation, Design, Potential Impact, Quality of the Idea; friction log up to +10%. Alexa+ track needs an Agent Skill or self-hosted MCP server (spec 2025-11-25+). Prizes: $25K / $15K / $4K + AWS credits.

## Ranking
| ID | Name | Track | Judge /10 | P(top) | P(any) | Risk | Status |
|---|---|---|---|---|---|---|---|
| U2 | Huddle: family and friends decide together, privately | Alexa+ + AWS Builder (+ Open Source if criteria fit) | 7.5 (ceiling ~8 until novelty and a real-group test are done) | ~0.05% | ~0.15% | medium | active |

## Ideas

### U2 Huddle (private group decisions: weekends and holidays, plus family care) · Track: Alexa+ · Mini-challenge: AWS Builder · Risk: medium
Status: refined 2026-10-02 (v5: added family-care mode to lift Potential Impact). History: calendar merger (6.1) -> ask-each-person weekend planner (6.9) -> + friend trips (7.0) -> this version (7.4).

**Pitch**: Some decisions stall because people won't say the real number out loud: what they can afford, how many hours they can give, what they can't do. Huddle's agent asks each person *privately*, in the way that suits them (voice at home, a link when remote), then proposes one plan with the trade-off explained, and never reveals who limited it. It does the deciding, not the planning: no booking, no expense splitting, no itineraries (Wanderlog and Cozi cover those).

**Two modes on one engine**
- **Everyday mode (the on-ramp):** weekend and holiday plans. Low stakes, used often, easy to demo, builds the habit of answering privately.
- **Care mode (the heavy use):** siblings and relatives deciding how to share the care of an aging parent. Each privately states hours per week they can give, a monthly amount they can contribute, and dealbreakers (can't do nights, lives far away). The engine proposes a split of tasks and money that respects every private limit, and shows the group only the aggregate ("the plan needs 30 h/week and $1,800/month; together you can cover 26 h and $1,500; gap: 4 h and $300") with options to close the gap, such as paid respite. It gives no medical, legal or financial advice and collects no health records, only capacity numbers.
- Friend trips use the same engine and are a stretch goal, since Wanderlog already owns trip planning.

**The one mechanic that makes it distinctive: private preference matching.**
- Each person gives private answers: must-haves, dealbreakers, a budget ceiling, a vibe. No one sees anyone else's answers.
- The server computes what is compatible and surfaces only the group-level result ("options between $400-600 work for everyone"), in coarse buckets, never attributed to a person.
- Honest limit (state it in the video): this is no-attribution plus bucketing, not cryptographic secrecy. In a two-person group the other person can infer your number from the bucket. Groups of 3+ hide who set the limit. A stretch goal is secure multi-party computation; it is out of scope for the MVP.

**Reach (>= 1M users)**: Gate pass. Care mode: 63 million Americans, nearly 1 in 4 adults, provided ongoing care in the past year; they pay about $7,200 a year out of pocket; nearly half had at least one major financial impact (debt, stopped saving, unable to afford food); nearly 1 in 4 give 40+ hours a week (AARP, https://www.aarp.org/press/releases/2025-07-24-new-report-reveals-crisis-point-for-americas-63-million-family-caregivers.html). The AARP page says nothing about siblings disagreeing over care, so "families stall on splitting care" is my inference and needs a source or a user test. Everyday mode: every multi-person household; the US households figure is still unsourced (the Census page returned 403). Mechanism: self-hostable open-source MCP server plus a link flow that works on any phone, so adoption does not depend on owning an Echo.

**Impact statement (human benefit)**: Huddle takes the stress out of group decisions. Nobody has to nag, negotiate or say an awkward number out loud, so the decision is made faster and with less friction. That frees up what matters: more family time and fewer arguments, a weekend that suits everyone, and, in care mode, siblings who share the load fairly and feel supported instead of resentful. After a plan happens, the agent can ask each person one private question ("what was the best moment?") and keep a small family memory log, so good times are captured and not just scheduled.
- These benefits are hypotheses, not findings. The only facts in this section are the sourced AARP figures under Reach. Do not state "reduces stress" or "improves family relationships" as results unless a test supports it.
- Make them demonstrable instead: in a test with 2-3 real groups, record time to decision, a before/after "how stressful was deciding?" rating (1-5), and one quote per person. A one-slide result like "decided in 4 minutes instead of 2 days of messages" is evidence a judge can weigh.
- Cheap to build: the memory log is a stretch feature (one next-day question per person, a saved card per event); cut it first if time is short.

**Evidence for the impact claims (fetched this session; the rest is unverified)**
- Socializing and communicating fell from 41 minutes per day in 2015 to 35 minutes in 2025, and the share of people doing it on an average day fell from 38% to 30% (BLS American Time Use Survey 2025, https://www.bls.gov/news.release/atus.nr0.htm). This is about socializing in general, not family time specifically.
- Adults aged 35-44, the main parenting years, have the least leisure of any age group: 3.89 hours per day, against an overall average of 5.16 (BLS ATUS 2025 leisure table, https://www.bls.gov/charts/american-time-use/activity-leisure.htm).
- 41% of US parents say parenting is tiring and 29% say it is stressful all or most of the time (Pew Research Center, survey of 3,757 parents of children under 18, Sept-Oct 2022, https://www.pewresearch.org/social-trends/2023/01/24/parenting-in-america-today/). This supports the stress framing; it is not about family time.
- Not found: a direct, sourced measure that family time or family recreation has declined. ATUS publishes no separate "time with family" figure in the release I read. The 2023 US Surgeon General advisory on loneliness may have one (the page returned 403), so check it before quoting anything from memory.
- Not shown anywhere yet: that families stall on group decisions, or that Huddle reduces that stress. That still needs the 2-3 group test.

**Platform reality (verified from the hackathon FAQ)**: Alexa+ developer tools are in preview for select partners only. Entrants build a self-hosted MCP server (or Agent Skill) and demo it "via your own web-based simulator or front end." A locally runnable public repo plus the demo video is enough. Therefore:
- Alexa's native `personId` and `MessageAlert` cannot be demonstrated on real Alexa+. Alexa documents them for custom skills (personId per recognized voice, opt-in "Personalize skills", "personalization isn't authentication"); whether MCP servers receive them is unconfirmed.
- The web simulator plays the role of Alexa. To keep voice match load-bearing, build a speaker-recognition stand-in (speaker embeddings, e.g. an open-source model, enrolled per family member) that maps a voice to a profile. Label it clearly in the demo as the stand-in for Alexa's person recognition. A profile switcher is the fallback if accuracy is poor.

**Judge's scorecard** (Stage 1 / compliance gate: pass if the MCP server is called at runtime and the demo shows the simulated Alexa+ experience; spec version 2025-11-25 or later)
| Criterion (25% each) | Now | After this refinement | What 9-10 would require |
|---|---|---|---|
| Tech Implementation | 7 | 7.5 | Working speaker-recognition stand-in with measured accuracy on 3+ voices; the privacy-preserving intersection with a test proving no individual value leaves the server; MCP spec-compliant server on AgentCore with Bedrock/Strands; a live unscripted round in the demo |
| Design | 7.5 | 8 | A scripted 3-minute demo with the failure path shown (non-responder, deadline, defaults); accessible voice-and-link flow; one clear "wow" moment where nobody's number leaks yet the plan fits everyone |
| Potential Impact | 6.5 | 7.5 | Evidence that families stall on splitting care (a source or a test with 2-3 real sibling groups: completion rate, time to decision, a quote). The AARP figures establish the size and cost of the problem, not the stall; do not claim more. Care mode must stay a decision aid, not advice |
| Quality of the Idea | 6.5 | 7 (provisional) | Verified absence of near-duplicates (search was impossible this session) and a user quote or test showing people share more privately than in a group chat |
Weighted: **7.5 / 10** · verdict: solid, near contender. Not 8+ because the family-stall claim is unevidenced and novelty is unverified. A 10 is not defensible: it would need all four of the right-hand cells at once, and two of them depend on evidence that does not exist yet.

**Required tech: why it is load-bearing**
- MCP server (Alexa+ track): the product's interface is a conversational agent a household talks to; the rules require it for the track and the demo must show it called at runtime.
- Speaker recognition (stand-in for Alexa person ID): without knowing who is speaking, private answers from several people in one room would merge into one profile. Evidence: Alexa personalization docs (personId separate from account userId).
- Bedrock / Strands / AgentCore (AWS Builder mini-challenge): the planning agent asks questions, summarizes trade-offs, and runs on these services; the code must import and call them at runtime. Evidence: rules page list (Bedrock, AgentCore, Strands SDK, Kiro, SageMaker).
- SMS or link for remote people: holiday and friend groups include people who do not share this Alexa; without it half the group cannot answer. For the demo use links (US SMS needs A2P 10DLC registration; about $0.0083 per message plus carrier fees per Twilio).

**Scope: 3-minute MVP vs stretch**
- MVP: web simulator with voice-matched profiles for 2-3 people; one remote person by link; one short weekend round (the on-ramp) and one care round (hours and money capacity with a bucketed aggregate reveal and gap-closing options); a plan with an explained trade-off; deadline, one reminder, defaults for non-responders.
- Stretch (cut first): family memory log (next-day question and saved card), friend-trip mode, fairness record across rounds (who gave way last time), SMS delivery, real flight/hotel prices (free-tier quota of the Amadeus API was not verifiable; mock prices for the demo), secure multi-party computation.
- Out of scope: itineraries, bookings, expense splitting, calendar access (read-only free/busy is a possible later add-on).

**Day-1 verification list (in this order)**
1. Confirm in Official Rules or by asking organizers that a simulated Alexa+ experience with its own front end satisfies Stage 1 for the Alexa+ track (the FAQ says yes; confirm it covers the runtime-technology requirement).
2. Check the Open Source mini-challenge criteria before relying on it, and the AWS Builder criteria.
3. Run the novelty search (Devpost, GitHub, web): group decision tools, private budget matching, Alexa family planners. Cutting this check dropped Quality of the Idea to a provisional 7.
4. Prove the speaker-recognition stand-in works on 3 voices; if not, use the profile switcher and say so.
5. Source the households and group-travel figures.

**Risks**
- Care mode touches money and family conflict: collect capacity numbers only, no health data, no advice, a clear "decision aid" label; assignments can hint at relative capacity, so show assignments but not capacities, and say so.
- Nobody replies: deadline, one reminder, sensible defaults; show it in the demo.
- Consent: every member opts in; target adults (child-directed skills cannot use personalization).
- Privacy overclaim: do not say "secret"; say "never shown or attributed", and state the two-person limit.
- Crowded space: keep the scope to deciding; do not build planner features.
- Amazon may ship something similar inside Alexa+.

**Demo plan (under 3 minutes)**
1. 20 s: "Alexa, plan our Saturday" (simulator, voice recognized); two private answers; one plan with an explained trade-off.
2. 90 s, the main story: three siblings must share the care of their mother. "Alexa, let's sort out Mom's care." Each answers privately (one by voice, one by link from another city); show on screen that the server holds the numbers but nobody sees them.
3. Alexa shows the aggregate gap (4 h, $300) and options to close it, then a split that respects every limit, without naming who set a limit.
4. Failure path: one sibling never answers; the reminder fires; defaults apply and the plan says so.
5. Close: same engine, any group decision (friend trip is the next mode).

**Submission plan**: primary track Alexa+; AWS Builder mini-challenge (run the planning agent on Bedrock/Strands, host on AgentCore); maybe Open Source if criteria fit (public repo, self-hostable MCP server); product-feedback form and friction log (+up to 10% bonus) kept from day 1; demo video under 3 minutes.

**Win probability**: base ~0.05% (1 top prize / ~2,000 expected Alexa+ entries; entry count is an estimate) x multiplier ~1.0 (criteria fit 1.2, past-winner resemblance 0.9, novelty 1.0 unverified, sponsor-tech depth 1.2, feasibility 0.9, demo 1.3, crowding 0.7) = ~0.05% (0.03-0.12%); any prize ~0.15%. Biggest uncertainty: whether the novelty and Stage 1 simulated-Alexa checks hold.
**Changelog**: v1 calendar merger 6.1; v2 ask-each-person 6.9; v3 + trips 7.0; v4 private matching, simulator-based voice ID, scope cuts 7.4; v5 care mode added as the heavy use, trips moved to stretch, AARP-sourced reach 7.5.
