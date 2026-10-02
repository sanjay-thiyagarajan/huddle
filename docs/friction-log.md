# Friction log

Format per entry: task attempted, steps taken, expected vs actual, severity, workaround, actionable suggestion.

## F-001: `pip install mcp` now resolves to a 2.x major with a different server API
- **Task attempted:** Install the official MCP Python SDK and build a Streamable HTTP server (spec >= 2025-11-25).
- **Steps taken:** `uv pip install "mcp>=1.23"` in a fresh venv, then looked for `FastMCP` and the protocol-version constants.
- **Expected:** The `FastMCP` / `streamable_http_app()` API from the 1.x docs and examples.
- **Actual:** An unpinned install resolved to mcp 2.2.0 (`LATEST_PROTOCOL_VERSION = 2026-07-28`). `mcp.shared.version` is gone and `FastMCP` is replaced by `mcpserver.MCPServer`, so the 1.x tutorials do not apply.
- **Severity:** Medium (cost time; no blocker).
- **Workaround:** Pinned `mcp>=1.23,<2`. 1.30.0 reports `LATEST_PROTOCOL_VERSION = 2025-11-25` and lists `2025-11-25` in `SUPPORTED_PROTOCOL_VERSIONS`.
- **Suggestion:** Put a "1.x -> 2.x" migration note at the top of the README and quickstart, and make the docs site version-switchable so searchers land on the matching API.

## F-002: FastMCP session manager can only run once per instance
- **Task attempted:** Test the MCP endpoint over real HTTP, starting a fresh uvicorn server per test.
- **Steps taken:** Wrapped the FastAPI lifespan around `mcp.session_manager.run()` and started the app in a thread per test.
- **Expected:** Each server start works, or a clear error names the cause.
- **Actual:** The first test passed. Later ones failed with a bare `httpx.ConnectError`, because the server thread died on a `RuntimeError` inside the lifespan that never reached the test output.
- **Severity:** Low.
- **Workaround:** A session-scoped server fixture; the database is reset per test instead.
- **Suggestion:** Document the single-use constraint next to `streamable_http_app()`, or let `run()` be re-entered on a fresh manager.

## F-003: Tools returning bare `dict` give no structured output
- **Task attempted:** Read tool results from the MCP client as typed data.
- **Steps taken:** Declared tools with `-> dict`, then read `result.structuredContent`.
- **Expected:** `structuredContent` populated from the returned dict.
- **Actual:** `structuredContent` was `None`; the data was only in `content[0].text` as JSON. A `-> dict[str, Any]` annotation fixes it.
- **Severity:** Low.
- **Workaround:** Annotate returns as `dict[str, Any]`.
- **Suggestion:** Emit structured content for plain `dict` returns, or warn at registration that no output schema was inferred.

## F-004: scipy `milp` first import is slow and silent
- **Task attempted:** Integer-hour task split for care mode (maximise hours covered, then spread load).
- **Steps taken:** Used `scipy.optimize.milp` (HiGHS) in a unit-test suite.
- **Expected:** Tests on tiny problems finish in well under a second.
- **Actual:** The first test run took about 12 s with no output; later runs were 0.3 s for 80 solves. Cold-import and bytecode compilation, not the solver.
- **Severity:** Low.
- **Workaround:** None needed; noted so CI timing is not misread.
- **Suggestion:** None for the library; recording for honesty about the dev loop.

## F-005: Browser automation unavailable for UI verification
- **Task attempted:** Visually check the simulator UI in Chrome via the Claude in Chrome tools.
- **Steps taken:** Called `tabs_context_mcp` with `createIfEmpty`.
- **Expected:** A tab group to drive the app at localhost.
- **Actual:** "Browser extension is not connected."
- **Severity:** Medium (blocked the visual check until the extension was connected; resolved later in the session).
- **Workaround:** Scripted API round in `tests/e2e_mock_demo.py` meanwhile; once the extension connected, the UI was checked by hand in Chrome.
- **Suggestion:** Have the tool report which of "not installed", "not logged in" or "needs restart" applies.

## F-006: faster-whisper cannot decode audio files with the PyAV that pip resolves
- **Task attempted:** Transcribe a local 16 kHz WAV with `faster-whisper` (`base.en`, int8) as the server-side speech-to-text fallback.
- **Steps taken:** `pip install faster-whisper` alongside speechbrain/torch, then `WhisperModel(...).transcribe("clip.wav")`.
- **Expected:** A transcript.
- **Actual:** `TypeError: open() got an unexpected keyword argument 'metadata_errors'` raised from `av.container.core.open`, i.e. faster-whisper passes an option the installed PyAV does not support. The failure appears after the model has already downloaded, so the first run wastes minutes.
- **Severity:** Medium.
- **Workaround:** Decode the WAV ourselves (soundfile, resample to 16 kHz) and pass the float32 array to `transcribe()`, which skips PyAV.
- **Suggestion:** faster-whisper should declare a minimum `av` version that supports `metadata_errors`, so pip resolves a compatible pair.

## F-007: AgentCore MCP guide shows a single-file server; unclear how to host a composed app
- **Task attempted:** Work out how to host Huddle's MCP server on AgentCore Runtime (docs: "Deploy MCP servers in AgentCore Runtime").
- **Steps taken:** Read the guide end to end and compared it with Huddle, a FastAPI app with FastMCP mounted at `/mcp` plus REST routes.
- **Expected:** A statement of what the runtime launches (a command, an ASGI app, a container) so a mounted app is clearly fine.
- **Actual:** The contract (`0.0.0.0:8000/mcp`, stateless HTTP) is clear, but the scaffold step has you overwrite a generated `main.py` with a single FastMCP file run via `mcp.run(...)`. The guide doesn't say whether `uvicorn server.api:app` serving `/mcp` is equally supported.
- **Severity:** Low to medium. Unverified, since no AWS credentials were available to try it.
- **Workaround:** Documented both options in `deploy/agentcore/README.md` as an open question for the first real deploy.
- **Suggestion:** Add a "bring your own ASGI app / container" example next to the single-file one, and state which is supported.

## F-008: No default model id, so the agent cannot be tried without catalog lookup
- **Task attempted:** Build the Strands + Bedrock agent without hard-coding a model id from memory (the plan forbids it).
- **Steps taken:** Inspected `strands.models.BedrockModel`; its `model_id` is a required choice of the caller. The catalog is only visible with credentials.
- **Expected:** A documented current default, or a way to list usable ids offline.
- **Actual:** Cannot choose or validate an id without an AWS account and region. Huddle reads `HUDDLE_BEDROCK_MODEL_ID` and refuses to start the agent if unset (then falls back to the mock parser, labelled `mock-fallback`).
- **Severity:** Low.
- **Workaround:** Environment variable plus an explicit fallback.
- **Suggestion:** Publish the current recommended model id per region in the Strands Bedrock docs.
