import { post } from "../api";

async function parse<T>(res: Response): Promise<T> {
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.message ?? body.error ?? "Something went wrong. Try again.");
  return body as T;
}

export type Circle = "family" | "friends" | "work" | "personal";
export const CIRCLES: [Circle, string][] = [["family", "Family"], ["friends", "Friends"], ["work", "Work"], ["personal", "Personal"]];
export const circleLabel = (c: string) => CIRCLES.find(([k]) => k === c)?.[1] ?? c;

export interface TimeItem {
  id: string; title: string; circle: Circle; start: string; end: string; minutes: number;
  flexibility: "fixed" | "movable" | "optional"; importance: number; shared: boolean; tentative: boolean;
  repeat: string; date: string;
}
export interface ConflictOption { key: string; label: string; detail: string; alternatives?: string[] }
export interface Options { recommended: string; reason: string; options: ConflictOption[] }
export interface Clash extends TimeItem { options: Options }
export interface TimeRules {
  circle_rank: Circle[]; protected: { days: number[]; start: string; end: string; label?: string }[];
  work_start: string | null; work_end: string | null; max_evenings: number | null; buffer_minutes: number; learned: Record<string, number>;
}
export interface Summary {
  minutes_by_circle: Record<string, number>; committed_minutes: number; free_minutes: number; evenings_out: number;
  overbooked: boolean; notes: string[]; suggested_chore_minutes: number;
}
export interface GatherSlot { start: string; label: string; suggested: "yes" | "maybe" | "no"; reason: string; given: string | null }
export interface Gathering {
  round_id: string; title: string; circle: string; duration_minutes: number; state: string; answered: boolean;
  token: string; answered_count: number; of: number; slots: GatherSlot[]; result: Record<string, unknown> | null;
}
export interface MyTime {
  week: string; items: TimeItem[]; conflicts: { a: TimeItem; b: TimeItem; options: Options }[]; tentative: TimeItem[];
  summary: Summary; rules: TimeRules; gatherings: Gathering[];
}
export interface AddOut {
  created: boolean; commitment?: TimeItem; rule_suggestion?: { prefer: string; over: string } | null;
  analysis?: { clashes: Clash[]; rule_flags: string[]; notes: string[] } | null;
}
export interface SayOut { say: string; intent: string; state_changed: boolean; quick_replies: string[] }
export interface GatherStarted { round_id: string; my_token: string; guests: { name: string; link: string }[] }

const q = encodeURIComponent;
export const timeApi = {
  get: (token: string, week?: string) =>
    fetch(`/api/time?token=${q(token)}${week ? `&week=${q(week)}` : ""}`).then((r) => parse<MyTime>(r)),
  add: (token: string, fields: Record<string, unknown>, resolution?: Record<string, unknown>) =>
    post("/api/time/commitments", { token, fields, resolution }).then((r) => parse<AddOut>(r)),
  update: (token: string, commitment_id: string, changes: Record<string, unknown>, occurrence?: string) =>
    post("/api/time/update", { token, commitment_id, changes, occurrence }).then((r) => parse<unknown>(r)),
  confirm: (token: string, commitment_id: string, keep: boolean) =>
    post("/api/time/confirm", { token, commitment_id, keep }).then((r) => parse<unknown>(r)),
  rules: (token: string, changes: Record<string, unknown>) => post("/api/time/rules", { token, changes }).then((r) => parse<TimeRules>(r)),
  gather: (token: string, fields: Record<string, unknown>) => post("/api/time/gathering", { token, fields }).then((r) => parse<GatherStarted>(r)),
  answer: (token: string, round_id: string, body: { answers?: Record<string, string>; accept_suggestions?: boolean }) =>
    post("/api/time/answer", { token, round_id, ...body }).then((r) => parse<unknown>(r)),
  say: (token: string, utterance: string) =>
    post("/api/time/say", { token, utterance, today: new Date().toLocaleDateString("sv") }).then((r) => parse<SayOut>(r)),
};
