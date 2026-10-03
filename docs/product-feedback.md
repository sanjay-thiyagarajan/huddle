# Product feedback

One section per tool/API/SDK used. Updated as each phase lands; finalized in P8.

## MCP Python SDK (`mcp`, pinned to 1.30.x)
- **Purpose:** Huddle's self-hosted MCP server (Streamable HTTP, protocol 2025-11-25): 25 tools in three groups (7 for family decisions, 11 for the household, 7 for a person's own schedule). The same package's client is the simulator agent's way to reach the server at runtime (`server/agent/huddle_agent.py`) and is used in the tests.
- **What worked:** `FastMCP` with `stateless_http=True, json_response=True` mounts cleanly into FastAPI at `/mcp`. Tool schemas come from type hints, and a `TypedDict` parameter gives the host a real input schema while the tool still receives a plain dict. `title=` and `annotations=ToolAnnotations(...)` on `@mcp.tool` reach the client unchanged. Server `instructions` arrive in the initialize result, which is where Huddle puts its rules for a voice host (ask who can hear, never say an answer back). The client (`streamable_http_client` + `ClientSession`) negotiated `2025-11-25` on the first try, so the protocol-version assertion is simple.
- **What to improve:** An unpinned install now gives 2.x with a different server API (friction log F-001). Tools annotated `-> dict` return no `structuredContent`; only `dict[str, Any]` does (F-003). A `dict` parameter becomes `{"type": "object", "additionalProperties": true}` with no warning, so a host gets no shape at all, and a tool with no annotations is read by the protocol's defaults as destructive and open-world (F-011). `FastMCP.session_manager.run()` can be entered only once per instance, which breaks per-test server fixtures (F-002). The old `streamablehttp_client` is deprecated in favour of `streamable_http_client` with no migration hint in the error text.
- **Zero to hello world:** about 20 minutes, most of it spent on the 1.x/2.x split.
- **Would build again:** Yes. Tool schemas, typed results and the official client made a protocol-level test straightforward.

## MCP Inspector (`@modelcontextprotocol/inspector` 2.9, CLI mode)
- **Purpose:** an interoperability check from a client that is not Huddle's own and not Python: `make mcp-inspect` lists the tools over Streamable HTTP, and CI runs the same call against the built container.
- **What worked:** `npx -y @modelcontextprotocol/inspector --cli <url> --transport http --method tools/list` printed the full tool list as JSON on the first try, including titles, annotations and output schemas. `--method tools/call --tool-name ... --tool-arg key=value` accepted a JSON array as an argument value and returned `structuredContent`.
- **What to improve:** the CLI flags are easy to miss next to the browser UI in the README; the transport has to be named (`--transport http`) for a plain `http://.../mcp` address.
- **Zero to hello world:** a few minutes; no install beyond `npx`.
- **Would build again:** Yes. It is the cheapest proof that a host other than ours can use the server.

## SpeechBrain ECAPA-TDNN (`speechbrain/spkrec-ecapa-voxceleb`)
- **Purpose:** stand-in for Alexa person recognition: map a voice to a household profile so several people at one device keep separate private answers.
- **What worked:** `EncoderClassifier.from_hparams` plus `encode_batch` gave usable embeddings with a few lines. On 5 synthetic voices it identified 25/25 held-out clips and rejected 5/5 clips from an unenrolled voice (genuine scores 0.75-0.93, unknown best 0.30). Runs on CPU.
- **What to improve:** the model card gives no guidance on a cosine threshold or on how many seconds of enrolment audio are enough. The first-run download is silent for minutes. These numbers are synthetic voices only; real-voice behaviour is untested.
- **Zero to hello world:** about 30 minutes, almost all of it installing torch and downloading the model.
- **Would build again:** Yes for a stand-in. No for anything security-related; the plan already says it is not authentication.

## faster-whisper (Whisper `base.en`, local)
- **Purpose:** server-side transcription fallback for browsers without the Web Speech API.
- **What worked:** int8 on CPU transcribed all 30 synthetic clips with 0% word error after number normalisation.
- **What to improve:** it failed on first use with a PyAV `metadata_errors` TypeError (friction log F-006).
- **Zero to hello world:** about 20 minutes plus the failure above.
- **Would build again:** Yes.

## Strands Agents SDK (`strands-agents` 1.57)
**Honesty note: written before any run against Bedrock. No AWS credentials were available, so what follows covers installing, reading the API and wiring only. Update after the first real run.**
- **Purpose:** the conversational agent: turn one person's spoken answer into a structured private answer (Pydantic-validated, one follow-up if a field is missing), and explain an aggregate result in two sentences.
- **What worked (so far):** `Agent(..., structured_output_model=PydanticModel)` returns a validated object on `result.structured_output`, which fits the "validate before storage" rule. A fresh `Agent` per call gives a clean way to guarantee the agent never carries one person's answer into another's call. `BedrockModel(...)` and `Agent(...)` construct without network access, so the wiring is unit-tested with a fake agent.
- **What to improve:** `Agent.__init__` has a very long signature, and `structured_output()` and `agent(..., structured_output_model=)` both exist, which made it hard to tell which is current without reading the source.
- **Also wired, model call not yet run:** `scripts/aws_mcp_host.py` makes a Strands agent the MCP host. `strands.tools.mcp.MCPClient` wraps the MCP SDK's `streamable_http_client`, and `list_tools_sync()` hands the agent all 25 of Huddle's tools with no adapter code. A test runs that discovery and a real tool call against the live test server; only the Bedrock model step is untested.
- **Zero to hello world:** install took a few minutes; not yet run against a model.
- **Would build again:** Undecided until it has run for real.

## Amazon Bedrock
- **Purpose:** the model behind the Strands agent (`HUDDLE_MODE=aws`). The model id is read from `HUDDLE_BEDROCK_MODEL_ID` and never hard-coded.
- **What worked / what to improve:** **not exercised yet** (no credentials). In `aws` mode any Bedrock failure falls back to the mock parser and the API reports `engine: "mock-fallback"` with the error, so a failed AWS call can never be mistaken for a Bedrock result. See friction log F-008.
- **Would build again:** Not yet known.

## Amazon Bedrock AgentCore Runtime
- **Purpose:** host Huddle's MCP server for the demo and judging window, then tear it down.
- **What worked (reading only):** the MCP contract (`0.0.0.0:8000/mcp`, stateless Streamable HTTP) matches what Huddle already serves, so no server changes are needed. Steps and open questions are in `deploy/agentcore/README.md`.
- **What to improve:** see friction log F-007. I also expect SQLite state not to survive across sessions, an inference to test.
- **Not yet done:** deployment. AgentCore Memory and Identity are not used.
- **Would build again:** Not yet known.

## FastAPI, Uvicorn and Pydantic
- **Purpose:** the REST API for the simulator and the private link pages, the host for the mounted MCP app, and validation of every private answer before it is stored.
- **What worked:** mounting FastMCP's Streamable HTTP app next to the REST routes on one port; Pydantic models double as the validation layer and as the Strands agent's structured-output types.
- **What to improve:** nothing specific to report. The one wrinkle was on the MCP side (the session manager has to be run inside the FastAPI lifespan, F-002).
- **Zero to hello world:** not timed.
- **Would build again:** Yes.

## SQLModel and SQLite
- **Purpose:** rounds, private answers, households, chores, commitments and the audit trail, in one local file so a fresh clone runs with no services.
- **What worked:** an in-memory database per test (`sqlite://`) keeps the suite fast and isolated.
- **What to improve:** nothing specific to report. SQLite on local disk is the reason hosted state on AgentCore is an open question (see below).
- **Zero to hello world:** not timed.
- **Would build again:** Yes for a locally runnable demo; a managed store for anything hosted.

## SciPy `optimize.milp` (HiGHS)
- **Purpose:** the care split and the weekly chore plan, both small integer programs (the chore plan is several solves in strict order: hard limits, fair share, preferences, rotation).
- **What worked:** problems of this size solve in milliseconds, and results were correct in every test.
- **What to improve:** the first import is slow and silent (F-004), and HiGHS once printed an internal line that bypassed Python logging and hid the pytest summary (F-009).
- **Zero to hello world:** not timed.
- **Would build again:** Yes.

## React, Vite and TypeScript
- **Purpose:** the simulator (the Alexa+ stand-in) and the private link pages.
- **What worked:** one build output served by the same container as the API, so there is a single port to run.
- **What to improve:** nothing specific to report.
- **Zero to hello world:** not timed.
- **Would build again:** Yes.

## Browser Web Speech API (speech recognition and speech synthesis)
- **Purpose:** the microphone and the spoken replies in the simulator, standing in for a voice device.
- **What worked:** no key, no cost, works in Chrome.
- **What to improve:** recognition is not available in every browser, which is why a typed input is always present and local Whisper exists as a fallback. It has not been measured on real voices here.
- **Zero to hello world:** not timed.
- **Would build again:** Yes for a simulator, with the typed fallback kept.

## Playwright and axe-core
- **Purpose:** browser tests of the full flows, the failure path, phone width, and an accessibility audit (WCAG A and AA) in light and dark.
- **What worked:** driving the installed Chrome; `@axe-core/playwright` made the accessibility check one assertion per page.
- **What to improve:** one test raced the page load once in CI (it decided nobody had been asked before the offer had loaded) and needed an explicit wait.
- **Zero to hello world:** not timed.
- **Would build again:** Yes.

## Docker and GitHub Actions
- **Purpose:** one image that serves the simulator, the REST API and `/mcp`; CI runs lint, the unit, protocol and leak tests, the browser tests, a container smoke test and the Inspector interop check.
- **What worked:** the same image runs locally and matches what AgentCore Runtime expects of an MCP server (port 8000, `/mcp`).
- **What to improve:** nothing specific to report.
- **Zero to hello world:** not timed.
- **Would build again:** Yes.

## uv, ruff, pytest and aiosmtpd
- **Purpose:** environment and installs (uv), lint (ruff), tests (pytest, pytest-asyncio), and a local mail sink (aiosmtpd) so reminder emails are tested against a real SMTP conversation.
- **What worked:** `uv venv` plus `uv pip install` kept a clean install to seconds without the optional extras.
- **What to improve:** `ruff format` over a whole directory rewrote files that were not being changed (F-010).
- **Zero to hello world:** not timed.
- **Would build again:** Yes.

## Claude Code
- **Purpose:** the development tool: the code, tests and documents in this repository were written with it, phase by phase from `docs/development-plan.md`.
- **What worked:** keeping the plan, the honesty rules and the friction log in the repository gave it standing instructions to work from.
- **What to improve:** its browser tools could not be used until the Chrome extension connected, and the error did not say which step was missing (F-005).
- **Would build again:** Yes.

### AWS services used, and how (for the AWS Builder mini-challenge)
Planned: Amazon Bedrock (model inference through Strands) and Bedrock AgentCore Runtime (hosting the MCP server). **Neither has been run yet**; this section must be updated with real results, latencies from `scripts/aws_scripted_rounds.py` and the deployed runtime ARN before submission.
