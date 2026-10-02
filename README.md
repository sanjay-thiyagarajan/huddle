# Huddle

**A fair, private home.** Everyone in the household tells Huddle privately what they can take on. Huddle proposes a fair plan, with the trade-off explained, without saying who set which limit.

Built for the [Amazon Developer Hackathon](https://amazonappdev2026.devpost.com/): primary track **Alexa+**, mini-challenges **AWS Builder** and **Open Source**. A new project, started after Aug 31, 2026, released under the MIT licence.

---

## The problem

In a home, the load tends to pile up on one person. It comes in three sizes: the **heavy** (caring for a parent), the **daily** (the chores) and the **occasional** (a weekend, a trip). Each one depends on numbers people find hard to say out loud: how much time they can really give, how much they can spend, what they can't do. When someone has to speak first, that person's limit becomes the group's limit, and everyone else stays quiet or ends up carrying more.

The evidence on how unequal the load is (the sources, and what each does and doesn't show, are in [docs/evidence-household-load.md](docs/evidence-household-load.md)):

- On an average day in the U.S., women spent 2.8 hours on household activities and men 2.1 hours, among those who did any ([BLS, American Time Use Survey 2025](https://www.bls.gov/news.release/atus.htm)).
- 59% of women said they do more of the household chores than their partner, and 38% of women were very satisfied with how chores are divided in October 2020, against 55% of men ([Pew Research Center, 2021](https://www.pewresearch.org/short-reads/2021/01/25/for-american-couples-gender-gaps-in-sharing-household-responsibilities-persist-amid-pandemic/)).
- In interviews with 35 couples, one partner did more of the anticipating and monitoring behind household tasks even when couples described the split as shared ([Daminger, *American Sociological Review*, 2019](https://behavioralscientist.org/how-couples-share-cognitive-labor-and-why-it-matters/)).
- Across 14 studies, in 11 women reported more depressive or psychological distress as their unpaid labour demands rose (Ervin et al., *The Lancet Public Health*, 2022).
- The heaviest case is caring for a parent. From [AARP and the National Alliance for Caregiving, *Caregiving in the U.S. 2025*](https://www.aarp.org/press/releases/2025-07-24-new-report-reveals-crisis-point-for-americas-63-million-family-caregivers.html): 63 million Americans (nearly 1 in 4 adults) provided ongoing care for an adult or a child in the past year, at roughly $7,200 a year out of pocket on average, and nearly half had at least one major financial impact.

## One home, three sizes of load

Huddle treats them the same way: *private limits in, one unattributed plan out.* And they share **one household**, with the same people and the same private profile, so what you carry in one counts in the others.

| Size | What it is | How Huddle handles it |
|---|---|---|
| **The heavy**: caring for a parent | The family sharing a parent's care between them: the hours each person can give (check-ins, appointments and transport, meals, paperwork, overnight cover), the money each can put in each month, and the tasks they can't do | A decision. Everyone answers privately; the family gets who owns which task, the gap in bands and ways to close it. Each person sees their own hours privately |
| **The daily**: household chores | A stream of small jobs, week after week | A fair agent plans each week from everyone's private availability, preferences and skills, offers new chores to the best-fit person, and remembers who carried what |
| **The occasional**: a weekend, a trip | A one-off group choice | A decision: one plan and the trade-off, nobody named |

```mermaid
flowchart TB
  H["<b>One household</b><br/>the same people, one private profile each"]
  C["<b>The heavy</b><br/>caring for a parent"]
  D["<b>The daily</b><br/>chores, planned fairly each week"]
  O["<b>The occasional</b><br/>a weekend or a trip"]
  H --> C
  H --> D
  H --> O
  C -->|"care you take on counts<br/>in your chore share"| D
  C -->|"a private hint when<br/>leisure is planned"| O
```

- **Care counts in your chores.** If you've taken on overnight care, the chore plan counts it, so you aren't also handed a full chore load. It uses only what the household already sees (who owns each care task, and its total hours), never anyone's private hours.
- **Care shapes the occasional.** Whoever carries heavy care tasks gets an optional private hint when a weekend or trip is planned. It's never applied for them.
- **Fairness has memory.** A ledger of what people actually did, a heavy week reported privately, and rotation of heavy tasks mean the same person doesn't keep getting the hardest job.

Huddle decides; it doesn't hire nurses, book providers, move money, split expenses, read calendars, or give medical, legal or financial advice. Care mode collects no health data. When the family can't cover a parent's care between them, the plan suggests paid help as one option at a placeholder rate.

## What Huddle does

1. **Asks each person privately**, in the way that suits them: by voice at a shared device, or on their own phone through a private link.
2. **Works out what is compatible** and reports only group-level results, in coarse bands, plus who owns what.
3. **Proposes one plan and explains the trade-off**, without naming anyone ("Picked X; some of you preferred Y, but the budget ruled it out").
4. **Plans the chores fairly each week.** Hard limits first, then a fair share in proportion to each person's own availability (heavier chores and mental load such as planning and booking weigh more), then preferences and skills, then rotation. Chores can be added any time in plain words ("clean the gutters by Saturday, about an hour") or pre-planned with a due date or recurrence.
5. **Negotiates ad hoc chores.** A new chore is offered to the best-fit person, who can accept or decline; if they decline, or don't answer for 24 hours, the agent asks the next. Nobody can see who was asked or who declined.
6. **Talks plainly**: "what's on my plate", "I did the bins", "who has the laundry", by typing, speaking, or through the MCP tools.
7. **Reminds people for real**: a scheduler sends reminders in-app and, if the host entered an address, by email, plus a stated default if someone never answers.
8. **Checks in afterwards**: privately after a decision, and privately after each chore week.
9. **Hands over a plan card** the assistant can read aloud, and a copyable weekly chore plan.

How the chore agent decides, what is private and what is visible, and where its limits are: [docs/fairness-agent.md](docs/fairness-agent.md).

### On a shared speaker
Answering a private number out loud can be overheard, so the **voice-only mode** (see [docs/alexa-fit.md](docs/alexa-fit.md)) starts by asking whether anyone is within earshot and offers the person's private phone link or the screen instead. The assistant never says an answer back unless asked, the draft stays on the server, it is saved through the MCP tool, and consent is spoken.

## Privacy model

- Private answers are stored server-side and returned only to their owner.
- The group sees aggregates in coarse bands, and who owns each task, never anyone's hours or limits, and never who set a limit. Each person's own hours are returned only for their own token.
- In the household, each member's availability, preferences, skills, exemptions, decline reasons and how a week felt are returned only to them. The group sees chores, who owns them, and an aggregate fairness report; the audit trail never says who was asked or why.
- Matching is private, not cryptographic: with three or more people, who set a limit stays hidden; with two people, the other person can work out your number, and the app says so.
- Voice identification is a stand-in for Alexa person recognition. It separates profiles on a shared device; it does not authenticate anyone.
- An automated **leak test** seeds distinctive values and calls every route and MCP tool as every participant, failing if anyone else's value appears.

## How a family decision works

```mermaid
sequenceDiagram
  autonumber
  participant D as Device agent (Alexa+ stand-in)
  participant M as Huddle MCP server
  participant S as Round service and private store
  participant R as Remote person (phone)
  D->>M: start_huddle(mode, people)
  M->>S: open round, mint one private token per person
  M-->>D: tokens and private links
  D->>M: submit_private_answer(token, answer)
  R->>S: answer on private page /r/:token
  S->>S: reminders on a schedule, defaults at the deadline
  S->>S: all answered or deadline: close and compute
  Note over S: privacy engine turns private answers into bands and task ownership
  D->>M: get_group_result(token)
  M-->>D: aggregate result plus the caller's own share
  D->>M: submit_checkin(token, score) or revisit_round(token, mode)
```

## How a chore gets assigned

```mermaid
sequenceDiagram
  autonumber
  participant A as Anyone in the household
  participant G as Household agent
  participant B as Best-fit member
  participant N as Next member
  A->>G: "add fix the squeaky door"
  G->>G: understand it (kind, time, due date), then rank people by fairness first and fit second
  G->>B: offer the chore (only they see it)
  alt accepts
    B-->>G: accept
    G-->>A: the owner is shown to the household
  else declines, or silent for 24 hours
    B-->>G: decline (the reason stays private)
    G->>N: offer it to the next person
  end
  Note over G: the household only ever sees "being offered", never who was asked or who declined
```

## Technical architecture

```mermaid
flowchart LR
  subgraph Clients["Clients"]
    direction TB
    SIM["Simulator<br/>React + Vite<br/>family decisions, household chores,<br/>voice-only mode"]
    LINK["Private pages /r/:token, /h/:token<br/>a remote person's phone"]
  end

  subgraph Edge["Interfaces and agent"]
    direction TB
    REST["REST API<br/>/api/*"]
    AGENT["Household agent<br/>parsing, voice-only dialogue,<br/>chores in plain words"]
    MCP["MCP server<br/>Streamable HTTP /mcp<br/>spec 2025-11-25"]
  end

  subgraph Core["Services"]
    direction TB
    ROUNDS["Round service<br/>lifecycle, check-in, household,<br/>audit trail, plan card"]
    HOME["Household service<br/>private profiles, weekly fair plans,<br/>offers, ledger"]
    SCHED["Scheduler<br/>reminders, deadlines"]
    VOICE["Voice<br/>ECAPA speaker ID, Whisper"]
    NOTIFY["Notifier<br/>in-app, email"]
  end

  subgraph Logic["Decision logic"]
    direction TB
    ENGINE["Decision engines<br/>care (integer program), weekend, trip,<br/>chore planner (fair share)"]
    PRIV["Privacy engine<br/>bands, k rule, leak guard"]
  end

  subgraph Data["Storage and external services"]
    direction TB
    DB[("SQLite<br/>private answers, shares,<br/>contacts, events")]
    SMTP["SMTP provider<br/>(optional)"]
    BR["Amazon Bedrock<br/>Strands Agents SDK<br/>(aws mode)"]
  end

  SIM --> REST
  LINK --> REST
  REST --> AGENT
  AGENT -->|"MCP tool calls"| MCP
  REST --> ROUNDS
  REST --> HOME
  REST --> VOICE
  MCP --> ROUNDS
  MCP --> HOME
  SCHED --> HOME
  HOME --> ENGINE
  HOME --> DB
  SCHED --> ROUNDS
  SCHED --> NOTIFY
  ROUNDS --> ENGINE
  ENGINE --> PRIV
  ROUNDS --> DB
  VOICE --> DB
  NOTIFY --> SMTP
  AGENT -.-> BR
```

| Layer | Where | What it does |
|---|---|---|
| MCP server | `server/mcp_server.py` | Eighteen tools over Streamable HTTP (seven for family decisions, eleven for the household), called at runtime by the household agent |
| Privacy engine | `server/engine/privacy.py` | Bands, the k rule, the leak guard |
| Round service | `server/engine/rounds.py` | Lifecycle, answers, revision, check-in, household chain, reminders, audit trail |
| Decision engines | `server/engine/care.py`, `everyday.py`, `trip.py` | Care split via `scipy.optimize.milp`; weekend and trip matching |
| Chore planner | `server/engine/chores.py` | Fair weekly split of household chores (integer program): hard limits, fair share by private availability, ledger, preferences, rotation |
| Household service | `server/engine/home.py` | Persistent households, private profiles, ad hoc and pre-planned chores, offers (ask, accept, decline, re-ask), ledger, reminders, weekly auto-plan |
| Household agent | `server/agent/` | Mock parser by default; Strands agent on Bedrock in `aws` mode; the voice-only dialogue; chores understood from plain words |
| Voice | `server/voice/` | SpeechBrain ECAPA speaker identification and local Whisper transcription |
| Notifier | `server/notify.py` | In-app and email reminders |
| Simulator | `web/` | The Alexa+ stand-in and the private link pages |

## Deployment architecture

The same container image runs locally and on AWS. It serves the simulator, the REST API and the MCP endpoint on one port.

```mermaid
flowchart LR
  Browser["Browser<br/>simulator and private pages"]
  Agent["MCP client<br/>Alexa+ agent or test client"]

  subgraph Local["Local or any Docker host (mock mode, no AWS needed)"]
    C1["huddle container :8000<br/>FastAPI + built simulator<br/>/api  /mcp  /r/*"]
    V1[("volume<br/>SQLite")]
    C1 --- V1
  end

  subgraph AWS["AWS (aws mode)"]
    COG["Amazon Cognito<br/>JWT inbound auth"]
    AC["Bedrock AgentCore Runtime<br/>Huddle server on 0.0.0.0:8000/mcp<br/>stateless Streamable HTTP"]
    STR["Strands Agents SDK<br/>in the server process"]
    BED["Amazon Bedrock<br/>foundation model"]
    COG -->|authorizes| AC
    AC --- STR --> BED
  end

  SMTP["SMTP provider<br/>(optional)"]

  Browser -->|"HTTP :8000"| C1
  Agent -->|"HTTPS invocations, Bearer JWT"| AC
  C1 -.-> SMTP
  AC -.-> SMTP
```

- **Local:** `make docker` (or `docker compose up --build`) builds `deploy/Dockerfile` and serves everything on `http://localhost:8000`. No AWS credentials are needed.
- **AWS:** the same server image listens on `0.0.0.0:8000/mcp`, the contract AgentCore Runtime expects of an MCP server. Steps are in [deploy/agentcore/README.md](deploy/agentcore/README.md). `HUDDLE_MODE=aws` switches the agent to Strands on Amazon Bedrock.
- **CI:** GitHub Actions runs lint and unit tests, the Playwright browser tests, and a Docker build that starts the container and checks it serves the app.

## MCP server

Streamable HTTP at `/mcp`, protocol version 2025-11-25 (official `mcp` Python SDK). Every tool takes the caller's own signed token; none returns another person's raw answer or private limits.

**Family decisions**

| Tool | Purpose |
|---|---|
| `start_huddle` | Open a round (`care`, `everyday` or `trip`) for 2 to 6 people; returns a private token and link per person |
| `submit_private_answer` | Store or revise one person's validated answer; consent required |
| `get_group_result` | The aggregate result once the round closes, plus the caller's own share |
| `close_round` | Host only: close now; non-responders get stated defaults |
| `nudge_pending` | Host only: remind everyone who hasn't answered; per-channel delivery results |
| `submit_checkin` | The day-after private 1 to 5 check-in |
| `revisit_round` | Host only: the household's next round, same decision or a different one |

**Household chores**

| Tool | Purpose |
|---|---|
| `create_household` | 2 to 6 people (optional email for reminders); returns a private token per member |
| `get_household` | This week's shared plan and fairness report, plus only the caller's own private profile, offers and load |
| `set_my_profile` | Private: availability, preferences, skills, things to learn, keywords, and a capped weekly exemption |
| `add_chore` | Add a chore any time, from fields or plain words; if the week is planned the best-fit person is asked |
| `plan_week` | Plan a week fairly from everyone's private limits (redoing an existing plan is admin only) |
| `respond_to_assignment` | Accept or decline an offer made to the caller; a decline makes the agent ask someone else |
| `hand_back_chore` | The owner can't do it after all: the agent asks the next best person |
| `complete_chore` | The owner marks a planned chore done |
| `week_checkin` | Private: how the week felt; a heavy week lightens the next |
| `start_household_decision` | Start a care, weekend or trip decision for the whole household: the same people, each answering privately with their own link |
| `ask_household_agent` | Plain words: add a chore, "what's on my plate", "I did the bins", "who has the laundry" |

Try it from any MCP client:

```python
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

async def main():
    async with streamable_http_client("http://localhost:8000/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print(init.protocolVersion)                # 2025-11-25
            print([t.name for t in (await session.list_tools()).tools])

asyncio.run(main())
```

## Quickstart

Mock mode needs no AWS credentials.

```
make install   # Python 3.12 venv and web dependencies
make dev       # API and MCP on :8000, simulator on http://localhost:5173
```

Open `http://localhost:5173`. The **Home** tab is the product: create a household, press **Add a starter set of chores** then **Plan the week**, switch between members to set their private limits, and try the agent ("add fix the squeaky door"). From the same page, start **Share a parent's care** for the household: each member answers their part privately, and once the decision closes the care people have taken on counts in the chore plan. The **Try a decision** tab runs a one-off decision without a household.

```
make test      # unit, protocol and leak tests
make e2e       # Playwright browser tests (needs Google Chrome)
make docker    # or: docker compose up --build  ->  http://localhost:8000
make lint
```

Optional extras: `pip install '.[voice]'` (speaker ID and Whisper), `pip install '.[aws]'` (Strands and Bedrock).

### Configuration

| Setting | Default | Meaning |
|---|---|---|
| `HUDDLE_MODE` | `mock` | `mock` runs without AWS; `aws` runs the agent on Amazon Bedrock |
| `HUDDLE_DB_URL` | `sqlite:///huddle.db` | Database |
| `HUDDLE_SECRET` | dev value | Signs round tokens; set it in any shared deployment |
| `HUDDLE_PUBLIC_URL` | `http://localhost:8000` | Address used for links in reminder emails |
| `HUDDLE_TICK_SECONDS` | `15` | Scheduler interval for reminders and deadlines |
| `HUDDLE_SMTP_HOST`, `_PORT`, `_USER`, `_PASSWORD`, `_FROM`, `_STARTTLS` | unset | Turns on email reminders |
| `HUDDLE_BEDROCK_MODEL_ID`, `AWS_REGION` | unset | Bedrock model and region for `aws` mode |

## Repository layout

```
server/            FastAPI app, MCP server, engines, agent, voice, notifier
  engine/          privacy, rounds, care, everyday, trip, plan card, chores (fair planner), home (household service)
  agent/           answer parsing, voice-only dialogue, chore understanding, prompts, Strands agent
  voice/           speaker identification, transcription
web/               React + Vite simulator and private link pages; Playwright tests
deploy/            Dockerfile, AgentCore hosting notes
tests/             unit, protocol, leak and voice tests; synthetic audio fixtures
scripts/           helpers (audio fixtures, scripted rounds)
docs/              plan, architecture notes, accuracy reports, friction log, product feedback
```

## Verification

- 225 automated tests, including the privacy leak test across every REST route and MCP tool (with a full household lifecycle of profiles, plans, offers, declines and check-ins), a protocol test asserting the negotiated MCP version, the fairness engine's hard-limit, fairness, preference, rotation and ledger properties, the chore agent's parsing and intents, the scheduler, real SMTP delivery against a local mail sink, and an end-to-end run of a fictional family through speaker ID, Whisper, the voice-only dialogue and the MCP tools ([docs/family-simulation.md](docs/family-simulation.md)).
- 29 Playwright browser tests covering the flows, the household with decisions and chores together, reminders, voice-only privacy, phone width, and accessibility (axe, WCAG A and AA) in light and dark.
- Voice accuracy report: [docs/voice-accuracy.md](docs/voice-accuracy.md).

## Documentation

- [docs/alexa-fit.md](docs/alexa-fit.md): why a shared voice assistant, and how the voice-only mode handles privacy
- [docs/fairness-agent.md](docs/fairness-agent.md): how the household agent defines and keeps fairness, and what is private
- [docs/evidence-household-load.md](docs/evidence-household-load.md): sourced evidence on unequal household load
- [docs/novelty-search.md](docs/novelty-search.md): related work and how Huddle differs
- [docs/friction-log.md](docs/friction-log.md) and [docs/product-feedback.md](docs/product-feedback.md): developer-experience notes for the tools used
- [docs/development-plan.md](docs/development-plan.md): the build plan
- [THIRD_PARTY.md](THIRD_PARTY.md): libraries, models and licences

## Hackathon

- **Track:** Alexa+. A self-hosted MCP server (Streamable HTTP, 2025-11-25) that an Alexa+ agent calls, with a web simulator as the Alexa+ experience; both are in this repository.
- **AWS Builder:** Amazon Bedrock through the Strands Agents SDK, with hosting on Bedrock AgentCore Runtime (see [deploy/agentcore/README.md](deploy/agentcore/README.md)).
- **Open Source:** this repository, MIT licensed, created after Aug 31, 2026.

## Licence

MIT. See [LICENSE](LICENSE).
