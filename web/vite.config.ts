import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const api = process.env.HUDDLE_API ?? "http://127.0.0.1:8000";
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": api, "/me": api, "/mcp": api } },
});
