import { useCallback, useEffect, useState } from "react";
import AnswerForm from "../AnswerForm";
import { api } from "../api";
import type { Result, Status } from "../api";
import Reveal from "../reveal/Reveal";

/** /r/<token>: a private page for one person, usable from any phone. */
export default function LinkPage({ token }: { token: string }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const s = await api.status(token);
      setStatus(s);
      if (s.state === "closed") {
        const r = await api.result(token);
        if (r.ready && r.result) setResult(r.result);
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
      {result ? <Reveal result={result} />
        : status.me.answered ? <p className="banner note" role="status">Saved. Waiting for the others. This page updates by itself.</p>
        : status.state === "closed" ? <p className="banner note">This round has closed.</p>
        : <AnswerForm mode={status.mode} token={token} name={status.me.name}
            onSubmit={async (a) => { await api.submit(token, a); await refresh(); }} />}
    </main>
  );
}
