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
