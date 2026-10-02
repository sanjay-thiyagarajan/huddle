import { useState } from "react";
import type { CheckinSummary } from "./api";

const LABELS = ["Not comfortable", "Uneasy", "Okay", "Comfortable", "Very comfortable"];

/** Day-after check-in: one private 1-5 answer. The group only sees an unattributed summary. */
export default function Checkin({ name, summary, done, onSubmit }: {
  name: string; summary: CheckinSummary | null; done: boolean;
  onSubmit: (score: number) => Promise<void>;
}) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function pick(score: number) {
    setBusy(true); setError(null);
    try { await onSubmit(score); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return (
    <section className="checkin" aria-labelledby="checkin-h">
      <h3 id="checkin-h">The day after: how does the plan sit with you?</h3>
      {summary?.complete ? (
        <>
          <p className={`banner ${summary.revisit ? "warn" : "note"}`} role="status">{summary.message}</p>
          {summary.warning && <p className="fine">{summary.warning}</p>}
        </>
      ) : done ? (
        <p className="banner note" role="status">
          Thanks, {name}. {summary ? `${summary.checked_in} of ${summary.of} have checked in.` : ""} The group sees a summary once everyone has answered, never who said what.
        </p>
      ) : (
        <>
          <p className="fine">Private. Only an unattributed summary is shared, once everyone has answered.</p>
          <div className="row" role="group" aria-label={`Check-in for ${name}`}>
            {LABELS.map((l, i) => (
              <button key={l} className="chip" disabled={busy} onClick={() => void pick(i + 1)}>{i + 1}. {l}</button>
            ))}
          </div>
        </>
      )}
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}
