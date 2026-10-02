import { useCallback, useEffect, useState } from "react";
import AnswerForm from "../AnswerForm";
import Checkin from "../Checkin";
import { api } from "../api";
import type { CheckinSummary, Result, Status } from "../api";
import Reveal from "../reveal/Reveal";

/** /r/<token>: a private page for one person, usable from any phone. */
export default function LinkPage({ token }: { token: string }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [checkin, setCheckin] = useState<CheckinSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Record<string, unknown> | null>(null);

  const refresh = useCallback(async () => {
    try {
      const s = await api.status(token);
      setStatus(s);
      if (s.state === "closed") {
        const r = await api.result(token);
        if (r.ready && r.result) { setResult(r.result); setCheckin(r.checkin ?? null); }
      }
    } catch (e) { setError((e as Error).message); }
  }, [token]);

  useEffect(() => {
    void refresh();
    const id = setInterval(() => void refresh(), 3000);
    return () => clearInterval(id);
  }, [refresh]);

  if (error) return <main className="solo"><h1>This link doesn't work</h1><p className="error">{error}</p><p>Ask the person who started the huddle for a new link.</p></main>;
  if (!status) return <main className="solo"><p>Loading</p></main>;

  const care = status.mode === "care";
  return (
    <main className="solo">
      <h1>Hi {status.me.name}, this page is just for you</h1>
      <p className="lede">
        {care ? "Your family is working out how to share care. " : "Your group is picking a plan. "}
        Your answer is never shown to anyone else or attributed to you.
      </p>
      {care && status.need.tasks && (
        <p className="fine">The plan needs {status.need.tasks.reduce((n, t) => n + t.hours, 0)} h/week and ${status.need.dollars_per_month?.toLocaleString()}/month. Decision aid, not medical, legal or financial advice.</p>
      )}
      {result ? (
        <>
          <Reveal result={result} onExplain={() => api.explain(token)} onCard={() => api.planCard(token)} />
          <Checkin name={status.me.name} summary={checkin} done={status.events.some((e) => e.kind === "checked_in" && e.actor === status.me.name)}
            onSubmit={async (score) => { await api.checkin(token, score); await refresh(); }} />
        </>
      )
        : editing ? <AnswerForm mode={status.mode} token={token} name={status.me.name} initial={editing}
            onSubmit={async (a) => { await api.submit(token, a); setEditing(null); await refresh(); }} />
        : status.me.answered ? (
          <>
            <p className="banner note" role="status">Saved. Waiting for the others. This page updates by itself. You can change your answer until everyone has answered.</p>
            <button className="ghost" onClick={() => void api.myAnswers(token).then((r) => setEditing(r.answer))}>Change my answer</button>
          </>
        )
        : status.state === "closed" ? <p className="banner note">This round has closed.</p>
        : <AnswerForm mode={status.mode} token={token} name={status.me.name}
            onSubmit={async (a) => { await api.submit(token, a); await refresh(); }} />}
    </main>
  );
}
