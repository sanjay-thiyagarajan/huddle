# Third-party components

| Component | Use | Licence |
|---|---|---|
| mcp (Model Context Protocol Python SDK) | MCP server and client | MIT |
| FastAPI, Uvicorn, Pydantic, SQLModel | API, validation, storage | MIT / BSD-3 |
| SciPy, NumPy | Care-mode task split (`milp`) | BSD-3 |
| React, Vite, TypeScript | Simulator front end | MIT / Apache-2.0 |
| Playwright, axe-core (`@axe-core/playwright`) | Browser and accessibility tests (development only) | Apache-2.0 / MPL-2.0 |
| MCP Inspector (`@modelcontextprotocol/inspector`) | Interop check from a non-Python MCP client (development and CI only, run through `npx`) | Apache-2.0 / MIT (project in transition) |
| Bricolage Grotesque, Figtree (Google Fonts) | Typefaces | SIL OFL 1.1 |
| SpeechBrain, `speechbrain/spkrec-ecapa-voxceleb` | Speaker identification (optional `voice` extra) | Apache-2.0 |
| PyTorch, torchaudio, soundfile | Audio and model runtime (optional) | BSD-3 / BSD-3 / BSD-3 |
| faster-whisper, Whisper `base.en` (CTranslate2) | Local transcription fallback (optional) | MIT / MIT |
| macOS `say` voices | Generate the synthetic test clips in `tests/audio` (not redistributed as a voice) | Apple system TTS |
| Strands Agents SDK, boto3 | Agent in `aws` mode (optional `aws` extra); wired and unit-tested, not yet run against Bedrock | Apache-2.0 |

Planned (not yet run): Amazon Bedrock, Bedrock AgentCore Runtime.
