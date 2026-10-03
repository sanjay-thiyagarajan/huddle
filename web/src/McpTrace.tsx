import { useSyncExternalStore } from "react";
import { toolCalls } from "./api";

/** The MCP tools this assistant called, so the protocol is visible. Names and timing only. */
export default function McpTrace() {
  const calls = useSyncExternalStore(toolCalls.subscribe, toolCalls.get);
  return (
    <details className="voicebox">
      <summary>MCP tool calls</summary>
      <p className="fine">What this assistant asked Huddle's MCP server (Streamable HTTP). Tool names and timing only, never what was sent.</p>
      <ol className="audit" aria-label="MCP tool calls">
        {calls.map((c, i) => <li key={i}><code>{c.name}</code> {c.ok ? "ok" : "refused"}, {c.ms} ms</li>)}
      </ol>
    </details>
  );
}
