import { defineConfig } from "@playwright/test";

// Serves the built simulator + API + MCP from one in-memory mock-mode server on :8001.
export default defineConfig({
  testDir: "e2e",
  timeout: 120_000,
  workers: 1,
  use: { baseURL: "http://127.0.0.1:8001", channel: "chrome" }, // installed Chrome; no browser download
  webServer: {
    command:
      "npm run build && cd .. && rm -f e2e.db && HUDDLE_MODE=mock HUDDLE_PORT=8001 HUDDLE_DB_URL=sqlite:///e2e.db .venv/bin/uvicorn server.api:app --port 8001",
    url: "http://127.0.0.1:8001/api/health",
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
