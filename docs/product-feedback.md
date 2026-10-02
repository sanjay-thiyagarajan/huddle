# Product feedback

One section per tool/API/SDK used. Updated as each phase lands; finalized in P8.

## MCP Python SDK (`mcp`, pinned to 1.30.x)
- **Purpose:** Huddle's self-hosted MCP server (Streamable HTTP, protocol 2025-11-25) exposing `start_huddle`, `submit_private_answer`, `get_group_result`, `close_round`, `nudge_pending`; the same package's client is used in tests.
- **What worked:** `FastMCP` with `stateless_http=True, json_response=True` mounts cleanly into FastAPI at `/mcp`. Tool schemas come from type hints. The client (`streamable_http_client` + `ClientSession`) negotiated `2025-11-25` on the first try, so the protocol-version assertion is simple.
- **What to improve:** An unpinned install now gives 2.x with a different server API (see friction log F-001). Tools annotated `-> dict` return no `structuredContent`; only `dict[str, Any]` does, which is easy to miss. `FastMCP.session_manager.run()` can be entered only once per instance, which breaks per-test server fixtures. The old `streamablehttp_client` is deprecated in favour of `streamable_http_client` with no migration hint in the error text.
- **Zero to hello world:** about 20 minutes, most of it spent on the 1.x/2.x split.
- **Would build again:** Yes. Tool schemas, typed results and the official client made a protocol-level test straightforward.

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

### AWS services used, and how (for the AWS Builder mini-challenge)
Planned: Amazon Bedrock (model inference through Strands) and Bedrock AgentCore Runtime (hosting the MCP server). **Neither has been run yet**; this section must be updated with real results, latencies from `scripts/aws_scripted_rounds.py` and the deployed runtime ARN before submission.
