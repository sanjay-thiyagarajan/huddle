# Third-party components

| Component | Use | Licence |
|---|---|---|
| mcp (Model Context Protocol Python SDK) | MCP server and client | MIT |
| FastAPI, Uvicorn, Pydantic, SQLModel | API, validation, storage | MIT / BSD-3 |
| SciPy, NumPy | Care-mode task split (`milp`) | BSD-3 |
| React, Vite, TypeScript | Simulator front end | MIT / Apache-2.0 |
| Bricolage Grotesque, Figtree (Google Fonts) | Typefaces | SIL OFL 1.1 |
| SpeechBrain, `speechbrain/spkrec-ecapa-voxceleb` | Speaker identification (optional `voice` extra) | Apache-2.0 |
| PyTorch, torchaudio, soundfile | Audio and model runtime (optional) | BSD-3 / BSD-3 / BSD-3 |
| faster-whisper, Whisper `base.en` (CTranslate2) | Local transcription fallback (optional) | MIT / MIT |
| macOS `say` voices | Generate the synthetic test clips in `tests/audio` (not redistributed as a voice) | Apple system TTS |

Planned (not yet used): Strands Agents SDK, Amazon Bedrock, Bedrock AgentCore.
