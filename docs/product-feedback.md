# Product feedback

One section per tool/API/SDK used. Updated as each phase lands; finalized in P8.

## MCP Python SDK (`mcp`, pinned to 1.30.x)
- **Purpose:** Huddle's self-hosted MCP server (Streamable HTTP, protocol 2025-11-25) exposing `start_huddle`, `submit_private_answer`, `get_group_result`, `close_round`, `nudge_pending`; the same package's client is used in tests.
- **What worked:** `FastMCP` with `stateless_http=True, json_response=True` mounts cleanly into FastAPI at `/mcp`. Tool schemas come from type hints. The client (`streamable_http_client` + `ClientSession`) negotiated `2025-11-25` on the first try, so the protocol-version assertion is simple.
- **What to improve:** An unpinned install now gives 2.x with a different server API (see friction log F-001). Tools annotated `-> dict` return no `structuredContent`; only `dict[str, Any]` does, which is easy to miss. `FastMCP.session_manager.run()` can be entered only once per instance, which breaks per-test server fixtures. The old `streamablehttp_client` is deprecated in favour of `streamable_http_client` with no migration hint in the error text.
- **Zero to hello world:** about 20 minutes, most of it spent on the 1.x/2.x split.
- **Would build again:** Yes. Tool schemas, typed results and the official client made a protocol-level test straightforward.
