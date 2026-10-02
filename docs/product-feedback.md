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
