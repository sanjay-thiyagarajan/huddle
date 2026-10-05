export type Mode = "everyday" | "care" | "trip";
export type RoundMode = Mode | "when";
export type Channel = "voice" | "link";

export interface Person { name: string; channel: Channel; is_host: boolean; token: string; link: string }
export interface AuditEvent { at: string; kind: string; actor: string | null; detail: string | null }
export interface CheckinSummary {
  checked_in: number; of: number; complete: boolean; revisit?: boolean; message?: string;
  comfortable_count?: number; warning?: string;
}
export interface ShareLine { task_id: string; label: string; hours: number }
export interface Delivery { name: string; channel: string; status: string; detail: string }
export interface NudgeResult { pending: string[]; deliveries: Delivery[]; message: string }
export interface Hint { message: string; suggested_dealbreakers: string[] }
export interface HouseholdPlan { round_id: string; mode: Mode; title: string; summary: string; at: string; checkin: string | null }
export interface Status {
  round_id: string; mode: RoundMode; state: "collecting" | "reminded" | "closed";
  deadline_at: string; reminder_at: string;
  need: {
    tasks?: { id: string; label: string; hours: number }[]; dollars_per_month?: number;
    slots?: string[]; title?: string; circle?: string; duration_minutes?: number;
  };
  me: { name: string; is_host: boolean; answered: boolean };
  participants: { name: string; channel: Channel; answered: boolean }[];
  events: AuditEvent[];
  hints: Hint[];
  reminder: { at: string; kind: string } | null;
}
export interface Holds { stored: { name: string; has_answer: boolean; value: string }[] }
export interface Draft {
  draft: Record<string, unknown>; missing: string[]; followup: string | null;
  engine: string; latency_ms: number; engine_error?: string;
}
export interface PlanCard { title: string; text: string; markdown: string }
export interface VoiceTurn {
  session_id: string; say: string; stage: string; done: boolean; handoff: "link" | "screen" | null;
  spoke_values: boolean; saved: boolean;
}
export interface Explanation { text: string; engine: string; latency_ms: number }
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Result = Record<string, any>;

async function parse<T>(res: Response): Promise<T> {
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.message ?? body.error ?? "Something went wrong. Try again.");
  if (body && typeof body === "object" && "error" in body && typeof body.error === "string")
    throw new Error(body.error.replace(/^Error executing tool \w+: /, ""));
  return body as T;
}

export const post = (url: string, body: unknown) =>
  fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

/** One MCP tool call the simulator's agent made. Names and timing only, never arguments or results. */
export interface ToolCall { name: string; ok: boolean; ms: number }
let calls: ToolCall[] = [];
const watchers = new Set<() => void>();
export const toolCalls = {
  get: () => calls,
  subscribe: (fn: () => void) => { watchers.add(fn); return () => { watchers.delete(fn); }; },
};
const record = (name: string, ok: boolean, since: number) => {
  calls = [...calls, { name, ok, ms: Math.round(performance.now() - since) }].slice(-30);
  watchers.forEach((fn) => fn());
};

/** The simulator's agent talks to Huddle's MCP server (Streamable HTTP) through this proxy. */
export const tool = <T,>(name: string, args: Record<string, unknown>) => {
  const since = performance.now();
  return post("/api/agent/tool", { name, arguments: args }).then((r) => parse<T>(r)).then(
    (out) => { record(name, true, since); return out; },
    (e) => { record(name, false, since); throw e; },
  );
};

export const api = {
  status: (token: string) => fetch(`/api/status?token=${encodeURIComponent(token)}`).then((r) => parse<Status>(r)),
  holds: (token: string) => fetch(`/api/server-holds?token=${encodeURIComponent(token)}`).then((r) => parse<Holds>(r)),
  submit: (token: string, answer: Record<string, unknown>) =>
    post("/api/answers", { token, answer }).then((r) => parse<{ stored: boolean; warnings: string[] }>(r)),
  result: (token: string) =>
    fetch(`/api/result?token=${encodeURIComponent(token)}`)
      .then((r) => parse<{ ready: boolean; result?: Result; checkin?: CheckinSummary; my_share?: ShareLine[] }>(r)),
  turn: (token: string, sessionId: string | null, utterance: string) =>
    post("/api/agent/turn", { token, session_id: sessionId, utterance }).then((r) => parse<VoiceTurn>(r)),
  myAnswers: (token: string) =>
    fetch(`/me/answers?token=${encodeURIComponent(token)}`).then((r) => parse<{ answered: boolean; answer: Record<string, unknown> | null }>(r)),
  household: (token: string) => fetch(`/api/household?token=${encodeURIComponent(token)}`).then((r) => parse<{ plans: HouseholdPlan[] }>(r)),
  planCard: (token: string) => fetch(`/api/plan-card?token=${encodeURIComponent(token)}`).then((r) => parse<PlanCard>(r)),
  explain: (token: string) => fetch(`/api/agent/explain?token=${encodeURIComponent(token)}`).then((r) => parse<Explanation>(r)),
  checkin: (token: string, score: number) =>
    post("/api/checkin", { token, score }).then((r) => parse<{ stored: boolean; summary: CheckinSummary }>(r)),
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

/** Say something with the browser's voice (a stand-in for the assistant's). Replaces anything still being said. */
export function speechOutSupported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}
export function speak(text: string): void {
  if (!speechOutSupported() || !text) return;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
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

export const TRIP_ATTRS: [string, string][] = [
  ["flights", "Flying"], ["camping", "Camping"], ["long_drive", "Long drive"],
  ["early_start", "Early start"], ["strenuous", "Strenuous activity"], ["nightlife", "Nightlife"],
];
export const TRIP_VIBES: [string, string][] = [
  ["beach", "Beach"], ["city", "City"], ["nature", "Nature"],
  ["foodie", "Food-focused"], ["relaxed", "Relaxed"], ["adventurous", "Adventurous"],
];
export const TASK_TYPES: [string, string][] = [
  ["checkin", "Check-in"], ["appointments", "Appointments and transport"], ["meals", "Meals"],
  ["finances", "Finances and paperwork"], ["overnight", "Overnight cover"],
];
