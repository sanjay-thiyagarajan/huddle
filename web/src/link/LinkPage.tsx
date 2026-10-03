import { useCallback, useEffect, useState } from "react";
import AnswerForm from "../AnswerForm";
import WhenAnswer from "../WhenAnswer";
import Checkin from "../Checkin";
import MyShare from "../MyShare";
import { api } from "../api";
import type { CheckinSummary, Mode, Result, ShareLine, Status } from "../api";
import Reveal from "../reveal/Reveal";
import { Brand } from "../Logo";

/** /r/<token>: a private page for one person, usable from any phone. */
export default function LinkPage({ token }: { token: string }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [checkin, setCheckin] = useState<CheckinSummary | null>(null);
  const [share, setShare] = useState<ShareLine[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Record<string, unknown> | null>(null);
  const [perm, setPerm] = useState<NotificationPermission | "unsupported">(
    typeof Notification === "undefined" ? "unsupported" : Notification.permission);

  const refresh = useCallback(async () => {
    try {
      const s = await api.status(token);
      setStatus(s);
      if (s.state === "closed") {
        const r = await api.result(token);
        if (r.ready && r.result) { setResult(r.result); setCheckin(r.checkin ?? null); setShare(r.my_share ?? []); }
      }
    } catch (e) { setError((e as Error).message); }
  }, [token]);

  // A new reminder while the page is open: show a browser notification if the person allowed it.
  const reminderAt = status?.reminder?.at;
  useEffect(() => {
    if (!reminderAt || perm !== "granted") return;
    const key = `huddle-reminder-${token.slice(0, 12)}`;
    try {
      if (sessionStorage.getItem(key) === reminderAt) return;
      sessionStorage.setItem(key, reminderAt);
    } catch { /* storage unavailable: notify once per page load */ }
    new Notification("Huddle", { body: "Your private answer is still needed. It takes about two minutes." });
  }, [reminderAt, perm, token]);

  useEffect(() => {
    void refresh();
    const id = setInterval(() => void refresh(), 3000);
    return () => clearInterval(id);
  }, [refresh]);

  if (error) return <main className="solo"><Brand /><h1>This link doesn't work</h1><p className="error">{error}</p><p>Ask the person who started the huddle for a new link.</p></main>;
  if (!status) return <main className="solo"><p>Loading</p></main>;

  const care = status.mode === "care";
  return (
    <main className="solo">
      <Brand />
      <h1>Hi {status.me.name}, this page is just for you</h1>
      <p className="lede">
        {care ? "Your family is working out how to share care. " : "Your group is picking a plan. "}
        Your answer is never shown to anyone else or attributed to you.
      </p>
      {care && status.need.tasks && (
        <p className="fine">The plan needs {status.need.tasks.reduce((n, t) => n + t.hours, 0)} h/week and ${status.need.dollars_per_month?.toLocaleString()}/month. Decision aid, not medical, legal or financial advice.</p>
      )}
      {status.reminder && !status.me.answered && status.state !== "closed" && (
        <p className="banner warn" role="alert">
          {status.reminder.kind === "final" ? "Reminder: the deadline is close. Your answer is still needed."
            : "Reminder: your private answer is still needed."}
        </p>
      )}
      {perm === "default" && !status.me.answered && (
        <p className="fine">
          <button className="ghost" onClick={() => void Notification.requestPermission().then(setPerm)}>Notify me on this device</button>{" "}
          Get a notification here if a reminder comes while this page is open.
        </p>
      )}
      {result ? (
        <>
          <Reveal result={result} onExplain={() => api.explain(token)} onCard={() => api.planCard(token)} />
          {result.mode === "care" && <MyShare name={status.me.name} share={share} shared={false} />}
          <Checkin name={status.me.name} summary={checkin} done={status.events.some((e) => e.kind === "checked_in" && e.actor === status.me.name)}
            onSubmit={async (score) => { await api.checkin(token, score); await refresh(); }} />
        </>
      )
        : status.mode === "when" && !status.me.answered && status.state !== "closed" ? (
          <WhenAnswer title={status.need.title ?? "this"} slots={status.need.slots ?? []}
            onSubmit={async (a) => { await api.submit(token, a); await refresh(); }} />
        )
        : editing ? <AnswerForm mode={status.mode as Mode} token={token} name={status.me.name} initial={editing}
            onSubmit={async (a) => { await api.submit(token, a); setEditing(null); await refresh(); }} />
        : status.me.answered ? (
          <>
            <p className="banner note" role="status">Saved. Waiting for the others. This page updates by itself. You can change your answer until everyone has answered.</p>
            <button className="ghost" onClick={() => void api.myAnswers(token).then((r) => setEditing(r.answer))}>Change my answer</button>
          </>
        )
        : status.state === "closed" ? <p className="banner note">This round has closed.</p>
        : <AnswerForm mode={status.mode as Mode} token={token} name={status.me.name} hints={status.hints}
            onSubmit={async (a) => { await api.submit(token, a); await refresh(); }} />}
    </main>
  );
}
