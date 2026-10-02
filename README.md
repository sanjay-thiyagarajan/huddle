# Huddle

**A private group-decision agent for the household.** Everyone answers in private. Huddle works out what fits all the limits and proposes one plan, with the trade-off explained, without saying who set which limit.

Built for the [Amazon Developer Hackathon](https://amazonappdev2026.devpost.com/): primary track **Alexa+**, mini-challenges **AWS Builder** and **Open Source**. A new project, started after Aug 31, 2026, released under the MIT licence.

---

## The problem

Some decisions depend on numbers people don't want to say out loud: what they can spend, how many hours they can give, what they simply can't do. When one person has to speak first, that person's limit becomes the group's limit, and everyone else stays quiet or resents it.

The clearest case is **siblings sharing the care of an ageing parent**. From [AARP and the National Alliance for Caregiving, *Caregiving in the U.S. 2025*](https://www.aarp.org/press/releases/2025-07-24-new-report-reveals-crisis-point-for-americas-63-million-family-caregivers.html):

- 63 million Americans (nearly 1 in 4 adults) provided ongoing care for an adult or a child in the past year.
- Caregivers pay roughly $7,200 a year out of pocket on average.
- Nearly 1 in 4 caregivers provide 40 or more hours of care a week, and nearly half had at least one major financial impact.

The same shape shows up in smaller decisions: a weekend plan, or a friends' trip where nobody wants to be the one with the smallest budget.

## What Huddle does

Huddle is built for a **household's stream of decisions**, hard and easy, handled one way: *private limits in, one unattributed plan out.*

1. **Asks each person privately**, in the way that suits them: by voice at a shared device, or on their own phone through a private one-time link.
2. **Works out what is compatible** and reports only group-level results, in coarse bands.
3. **Proposes one plan and explains the trade-off**, without naming anyone ("Picked X; some of you preferred Y, but the budget ruled it out").
4. **Reminds people who haven't answered**: a first reminder half-way and a final one near the deadline, plus a host nudge. In-app, optional email, and the device's share sheet. Then a stated default if someone still doesn't answer.
5. **Lets people change their mind** until the round closes.
6. **Checks in the day after**: each person privately rates how the plan sits with them, and the group sees an unattributed summary.
7. **Plans the next decision for the same family**, without retyping who's in it. It can be the same decision again or a different one. The care plan shapes what follows: whoever carries heavy care tasks gets an optional private hint when leisure plans are made, and a fair-share record rotates heavy tasks across care rounds.
8. **Hands over a plan card**: a copyable, printable summary that the assistant can also read aloud.

| Decision | Each person privately gives | The group gets |
|---|---|---|
| **Share care for a parent** (flagship) | hours/week, dollars/month, task types they can't do | the care need vs. what's covered (gap in bands), who owns which task, ways to close the gap. Each person sees their own hours privately. |
| **Plan a weekend** | budget, vibe, dealbreakers | one activity and the trade-off |
| **Plan a trip** | budget for the trip, vibe, dealbreakers | one trip and the trade-off |

Huddle decides; it doesn't book anything, split expenses, read calendars, or give medical, legal or financial advice. Care mode collects no health data.

### On a shared speaker
Answering a private number out loud can be overheard, so the **voice-only mode** (see [docs/alexa-fit.md](docs/alexa-fit.md)) starts by asking whether anyone is within earshot and offers the person's private phone link or the screen instead. The assistant never says an answer back unless asked, the draft stays on the server, it is saved through the MCP tool, and consent is spoken.

## Privacy model

- Private answers are stored server-side and returned only to their owner.
- The group sees aggregates in coarse bands, and who owns each task, never anyone's hours or limits, and never who set a limit. Each person's own hours are returned only for their own token.
- Matching is private, not cryptographic: with three or more people, who set a limit stays hidden; with two people, the other person can work out your number, and the app says so.
- Voice identification is a stand-in for Alexa person recognition. It separates profiles on a shared device; it does not authenticate anyone.
- An automated **leak test** seeds distinctive values and calls every route and MCP tool as every participant, failing if anyone else's value appears.

## How a round works

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

## Technical architecture

```mermaid
flowchart LR
  subgraph Clients["Clients"]
    direction TB
    SIM["Simulator<br/>React + Vite<br/>device screen, voice-only mode"]
    LINK["Private page /r/:token<br/>a remote person's phone"]
  end

  subgraph Edge["Interfaces and agent"]
    direction TB
    REST["REST API<br/>/api/*"]
    AGENT["Household agent<br/>parsing, voice-only dialogue"]
    MCP["MCP server<br/>Streamable HTTP /mcp<br/>spec 2025-11-25"]
  end

  subgraph Core["Services"]
    direction TB
    ROUNDS["Round service<br/>lifecycle, check-in, household,<br/>audit trail, plan card"]
    SCHED["Scheduler<br/>reminders, deadlines"]
    VOICE["Voice<br/>ECAPA speaker ID, Whisper"]
    NOTIFY["Notifier<br/>in-app, email"]
  end

  subgraph Logic["Decision logic"]
    direction TB
    ENGINE["Decision engines<br/>care (integer program),<br/>weekend, trip"]
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
  REST --> VOICE
  MCP --> ROUNDS
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
| MCP server | `server/mcp_server.py` | Seven tools over Streamable HTTP, called at runtime by the household agent |
| Privacy engine | `server/engine/privacy.py` | Bands, the k rule, the leak guard |
| Round service | `server/engine/rounds.py` | Lifecycle, answers, revision, check-in, household chain, reminders, audit trail |
| Decision engines | `server/engine/care.py`, `everyday.py`, `trip.py` | Care split via `scipy.optimize.milp`; weekend and trip matching |
| Household agent | `server/agent/` | Mock parser by default; Strands agent on Bedrock in `aws` mode; the voice-only dialogue |
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

Streamable HTTP at `/mcp`, protocol version 2025-11-25 (official `mcp` Python SDK). Every tool takes the caller's own signed token; none returns another person's raw answer.

| Tool | Purpose |
|---|---|
| `start_huddle` | Open a round (`care`, `everyday` or `trip`) for 2 to 6 people; returns a private token and link per person |
| `submit_private_answer` | Store or revise one person's validated answer; consent required |
| `get_group_result` | The aggregate result once the round closes, plus the caller's own share |
| `close_round` | Host only: close now; non-responders get stated defaults |
| `nudge_pending` | Host only: remind everyone who hasn't answered; per-channel delivery results |
| `submit_checkin` | The day-after private 1 to 5 check-in |
| `revisit_round` | Host only: the household's next round, same decision or a different one |

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

Open `http://localhost:5173`, keep "Share care for a parent" selected and press **Start the huddle**. Answer as Maya and Ben on the device (type or speak your answer, or turn on voice-only mode), open Chen's private link in a second tab, and watch the plan appear. Use the short 45-second deadline option to see the reminder and the stated defaults.

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
  engine/          privacy, rounds, care, everyday, trip, plan card
  agent/           answer parsing, voice-only dialogue, prompts, Strands agent
  voice/           speaker identification, transcription
web/               React + Vite simulator and private link pages; Playwright tests
deploy/            Dockerfile, AgentCore hosting notes
tests/             unit, protocol, leak and voice tests; synthetic audio fixtures
scripts/           helpers (audio fixtures, scripted rounds)
docs/              plan, architecture notes, accuracy reports, friction log, product feedback
```

## Verification

- 108 automated tests, including the privacy leak test across every REST route and MCP tool, a protocol test asserting the negotiated MCP version, and an end-to-end run of a fictional family through speaker ID, Whisper, the voice-only dialogue and the MCP tools ([docs/family-simulation.md](docs/family-simulation.md)).
- 18 Playwright browser tests covering the flows, reminders, voice-only privacy, phone width, and accessibility (axe, WCAG A and AA) in light and dark.
- Voice accuracy report: [docs/voice-accuracy.md](docs/voice-accuracy.md).

## Documentation

- [docs/alexa-fit.md](docs/alexa-fit.md): why a shared voice assistant, and how the voice-only mode handles privacy
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
