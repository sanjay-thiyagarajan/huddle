import { post, tool } from "../api";

async function parse<T>(res: Response): Promise<T> {
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.message ?? body.error ?? "Something went wrong. Try again.");
  if (body && typeof body === "object" && "error" in body && typeof body.error === "string") throw new Error(body.error);
  return body as T;
}

export type Category = "cooking" | "dishes" | "cleaning" | "laundry" | "tidying" | "shopping" | "kids" | "pets" | "yard" | "repairs" | "admin" | "planning" | "other";
export const CATEGORY_LABELS: [Category, string][] = [
  ["cooking", "Cooking"], ["dishes", "Dishes"], ["cleaning", "Cleaning"], ["laundry", "Laundry"], ["tidying", "Tidying and bins"],
  ["shopping", "Shopping"], ["kids", "Kids"], ["pets", "Pets"], ["yard", "Yard and garden"], ["repairs", "Repairs and fixing"],
  ["admin", "Bills and paperwork"], ["planning", "Planning and booking"], ["other", "Other"],
];
export const label = (c: string) => CATEGORY_LABELS.find(([k]) => k === c)?.[1] ?? c;

export interface HomeChore {
  id: string; title: string; category: Category; minutes: number; cadence: string; due: string | null;
  heaviness: number; people_needed: number; mental: boolean; status: string; estimated: boolean;
}
export interface HomeAssignment {
  id: number; chore_id: string; title: string; category: string; minutes: number; due: string | null;
  slot: number; status: "open" | "pending" | "planned" | "done" | "missed" | "skipped"; owner: string | null;
  heaviness: number; mental: boolean; why?: string | null;
}
export interface HomeProfile {
  availability: number; prefs: Record<string, string>; skills: Record<string, number>; learn: string[];
  keywords: string[]; exempt_this_week: boolean; exempt_weeks_used: number;
}
export interface HomeReport {
  deviation_pct?: number; balanced?: boolean; slots_filled?: number; slots_total?: number; unstaffed?: string[];
  heavy_chores?: number; heavy_rotated?: number; mental_chores?: number; mental_owners?: number; exempt_count?: number;
}
export interface HomeDecision {
  round_id: string; mode: "care" | "everyday" | "trip" | "when"; title: string; state: "collecting" | "reminded" | "closed";
  deadline_at: string; answered: boolean; answered_count: number; of: number; token: string; link: string; created: string;
}
export interface HomePlanSummary { round_id: string; mode: string; title: string; summary: string; at: string; checkin: string | null }
export interface HomeState {
  home: { name: string; week: string; week_end: string };
  me: { name: string; is_admin: boolean };
  members: { name: string; is_admin: boolean }[];
  chores: HomeChore[];
  plan: { exists: boolean; assignments: HomeAssignment[]; loads_minutes: Record<string, number>; report: HomeReport; headline: string; attention: string[] };
  mine: {
    assignments: HomeAssignment[]; proposals: { id: number; title: string; minutes: number; category: string }[];
    profile: HomeProfile; load: { minutes: number; availability: number; care_minutes: number; vs_fair_share_pct: number | null };
    nudges: string[]; decisions: HomeDecision[];
  };
  plans_so_far: HomePlanSummary[];
  events: { at: string; kind: string; actor: string | null; detail: string | null }[];
}
export interface HomeMember { name: string; is_admin: boolean; token: string; link: string }
export interface AddResult {
  outcome: "held" | "asked" | "need_more"; chore?: HomeChore; proposed_to_you?: number[]; questions?: string[];
  parsed?: { assumed: string[]; questions: string[]; engine: string };
}
export interface SayResult { say: string; intent: string; state_changed: boolean }

const q = (t: string) => encodeURIComponent(t);
export const homeApi = {
  create: (name: string, members: { name: string; email?: string }[]) =>
    post("/api/home", { name, members }).then((r) => parse<{ home_id: string; name: string; members: HomeMember[] }>(r)),
  state: (token: string) => fetch(`/api/home/state?token=${q(token)}`).then((r) => parse<HomeState>(r)),
  profile: (token: string, changes: Record<string, unknown>) => post("/api/home/profile", { token, changes }).then((r) => parse<HomeProfile>(r)),
  addChore: (token: string, body: { fields?: Record<string, unknown>; text?: string }) =>
    post("/api/home/chores", { token, ...body }).then((r) => parse<AddResult>(r)),
  plan: (token: string, replan = false) => post("/api/home/plan", { token, replan }).then((r) => parse<HomeState>(r)),
  respond: (token: string, assignment_id: number, accept: boolean, reason?: string) =>
    post("/api/home/respond", { token, assignment_id, accept, reason }).then((r) => parse<HomeState>(r)),
  handBack: (token: string, assignment_id: number, reason?: string) =>
    post("/api/home/handback", { token, assignment_id, reason }).then((r) => parse<HomeState>(r)),
  complete: (token: string, assignment_id: number) => post("/api/home/complete", { token, assignment_id }).then((r) => parse<HomeState>(r)),
  decision: (token: string, mode: string, need?: unknown) =>
    post("/api/home/decision", { token, mode, need }).then((r) => parse<{ round_id: string; my_link: string }>(r)),
  checkin: (token: string, score: number) => post("/api/home/checkin", { token, score }).then((r) => parse<{ stored: boolean }>(r)),
  // The agent box is the assistant speaking: it goes through the MCP tool, not a REST route.
  say: (token: string, utterance: string) => tool<SayResult>("ask_household_agent", { token, utterance }),
};
