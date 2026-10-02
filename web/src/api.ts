export type Mode = "everyday" | "care";
export type Channel = "voice" | "link";

export interface Person { name: string; channel: Channel; is_host: boolean; token: string; link: string }
export interface Status {
  round_id: string; mode: Mode; state: "collecting" | "reminded" | "closed";
  deadline_at: string; reminder_at: string;
  need: { tasks?: { id: string; label: string; hours: number }[]; dollars_per_month?: number };
  me: { name: string; is_host: boolean; answered: boolean };
  participants: { name: string; channel: Channel; answered: boolean }[];
}
export interface Holds { stored: { name: string; has_answer: boolean; value: string }[] }
export interface Draft { draft: Record<string, unknown>; missing: string[]; followup: string | null }
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Result = Record<string, any>;

async function parse<T>(res: Response): Promise<T> {
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.message ?? body.error ?? "Something went wrong. Try again.");
  if (body && typeof body === "object" && "error" in body && typeof body.error === "string")
    throw new Error(body.error.replace(/^Error executing tool \w+: /, ""));
  return body as T;
}

const post = (url: string, body: unknown) =>
  fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

/** The simulator's agent talks to Huddle's MCP server (Streamable HTTP) through this proxy. */
export const tool = <T,>(name: string, args: Record<string, unknown>) =>
  post("/api/agent/tool", { name, arguments: args }).then((r) => parse<T>(r));

export const api = {
  status: (token: string) => fetch(`/api/status?token=${encodeURIComponent(token)}`).then((r) => parse<Status>(r)),
  holds: (token: string) => fetch(`/api/server-holds?token=${encodeURIComponent(token)}`).then((r) => parse<Holds>(r)),
  submit: (token: string, answer: Record<string, unknown>) =>
    post("/api/answers", { token, answer }).then((r) => parse<{ stored: boolean; warnings: string[] }>(r)),
  result: (token: string) =>
    fetch(`/api/result?token=${encodeURIComponent(token)}`).then((r) => parse<{ ready: boolean; result?: Result }>(r)),
  parse: (token: string, text: string) => post("/api/agent/parse", { token, text }).then((r) => parse<Draft>(r)),
};

// Speech: the browser's Web Speech API (Chrome). Text input stays available as the fallback.
type Recognizer = { start(): void; stop(): void; onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null; onend: (() => void) | null; lang: string };
export function speechSupported(): boolean {
  const w = window as unknown as Record<string, unknown>;
  return Boolean(w.SpeechRecognition ?? w.webkitSpeechRecognition);
}
export function listen(onText: (t: string) => void, onEnd: () => void): () => void {
  const w = window as unknown as Record<string, new () => Recognizer>;
  const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
  const rec = new Ctor();
  rec.lang = "en-US";
  rec.onresult = (e) => onText(Array.from(e.results).map((r) => r[0].transcript).join(" "));
  rec.onend = onEnd;
  rec.start();
  return () => rec.stop();
}

export const EVERYDAY_ATTRS: [string, string][] = [
  ["outdoors", "Outdoors"], ["crowds", "Crowds"], ["long_drive", "Long drive"],
  ["early_start", "Early start"], ["physical", "Physical effort"], ["alcohol", "Alcohol"],
];
export const EVERYDAY_VIBES: [string, string][] = [
  ["active", "Active"], ["relaxed", "Relaxed"], ["foodie", "Food-focused"],
  ["cultural", "Cultural"], ["social", "Social"], ["adventurous", "Adventurous"],
];
export const CARE_DEALBREAKERS: [string, string][] = [
  ["nights", "Overnight cover"], ["transport", "Driving and transport"], ["appointments", "Appointments"],
  ["finances", "Finances and paperwork"], ["checkins", "Daily check-ins"], ["far_away", "I live far away"],
];
