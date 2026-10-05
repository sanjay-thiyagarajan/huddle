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
export type ReminderKind = "starting_soon" | "digest";
export interface DueReminder { id: string; title: string; start: string; minutes_away: number }
export interface Reminders { kinds: ReminderKind[]; quiet_start: string | null; quiet_end: string | null; utc_offset_minutes: number; due: DueReminder[] }
export interface FeedView { subscribed: boolean; circle?: string; last_status?: string; last_fetched?: string | null }
export interface MyTime {
  week: string; items: TimeItem[]; conflicts: { a: TimeItem; b: TimeItem; options: Options }[]; tentative: TimeItem[];
  summary: Summary; rules: TimeRules; gatherings: Gathering[]; reminders: Reminders; feed: FeedView;
}
export interface Briefing {
  day: string; items: TimeItem[]; clashes: { a: TimeItem; b: TimeItem }[];
  chores_due: { id: number; title: string; due: string; minutes: number }[]; offers: number;
  decisions_waiting: { round_id: string; title: string; deadline_at: string }[]; next_free: string | null; say: string;
}
export interface ImportOut { imported: number; updated: number; unchanged: number; skipped: number; skipped_reasons?: Record<string, number>; clashes: number; notes: string[] }
export interface ExportOut { filename: string; ics: string; count: number }
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
  briefing: (token: string, day?: string) =>
    fetch(`/api/time/briefing?token=${q(token)}&today=${q(new Date().toLocaleDateString("sv"))}${day ? `&day=${q(day)}` : ""}`).then((r) => parse<Briefing>(r)),
  importIcs: (token: string, ics: string, circle: Circle) =>
    post("/api/time/import", { token, ics, circle, today: new Date().toLocaleDateString("sv") }).then((r) => parse<ImportOut>(r)),
  exportIcs: (token: string, kind: "my_time" | "chore_plan") =>
    post("/api/time/export", { token, kind, today: new Date().toLocaleDateString("sv") }).then((r) => parse<ExportOut>(r)),
  subscribe: (token: string, url: string | null, circle: Circle) =>
    post("/api/time/subscribe", { token, url, circle, today: new Date().toLocaleDateString("sv") }).then((r) => parse<ImportOut & { subscribed: boolean }>(r)),
  refreshFeed: (token: string) =>
    post("/api/time/subscribe", { token, url: null, refresh: true, today: new Date().toLocaleDateString("sv") }).then((r) => parse<ImportOut & { subscribed: boolean }>(r)),
  reminders: (token: string, changes: Partial<Reminders>) =>
    post("/api/time/reminders", { token, changes }).then((r) => parse<Reminders>(r)),
  say: (token: string, utterance: string) =>
    post("/api/time/say", { token, utterance, today: new Date().toLocaleDateString("sv") }).then((r) => parse<SayOut>(r)),
};
