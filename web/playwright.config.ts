import { defineConfig } from "@playwright/test";

// Serves the built simulator + API + MCP from one in-memory mock-mode server on :8001.
// Works the same on Linux, macOS and Windows: no shell-only syntax (no `rm`, no inline env vars).
const uvicorn =
  process.env.HUDDLE_UVICORN ?? (process.platform === "win32" ? ".venv\\Scripts\\uvicorn.exe" : ".venv/bin/uvicorn"); // CI sets this to plain `uvicorn`

export default defineConfig({
  testDir: "e2e",
  timeout: 120_000,
  workers: 1,
  use: { baseURL: "http://127.0.0.1:8001", channel: "chrome" }, // installed Chrome; no browser download
  webServer: {
    command: `npm run build --prefix web && node -e "require('fs').rmSync('e2e.db',{force:true})" && ${uvicorn} server.api:app --port 8001`,
    cwd: "..", // the repository root
    env: { HUDDLE_MODE: "mock", HUDDLE_TICK_SECONDS: "2", HUDDLE_PORT: "8001", HUDDLE_DB_URL: "sqlite:///e2e.db" },
    url: "http://127.0.0.1:8001/api/health",
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
