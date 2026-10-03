import { useState } from "react";

export const slotLabel = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

const CHOICES: ["yes" | "maybe" | "no", string][] = [["yes", "Works"], ["maybe", "Could move things"], ["no", "Can't"]];

/** One person's private answer to a find-a-time: for each candidate time, works, could move things, or can't. */
export default function WhenAnswer({ title, slots, suggestions, onSubmit }: {
  title: string; slots: string[]; suggestions?: Record<string, string>; onSubmit: (answer: Record<string, unknown>) => Promise<unknown>;
}) {
  const [picked, setPicked] = useState<Record<string, string>>(() => ({ ...(suggestions ?? {}) }));
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const complete = slots.every((s) => picked[s]);

  async function save() {
    setBusy(true); setError(null);
    try { await onSubmit({ consent: true, slots: picked }); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return (
    <section className="answer" aria-labelledby="when-h">
      <h2 id="when-h">When can you do "{title}"?</h2>
      <p className="fine">Answer for each time. Nobody sees which times you ruled out or why.</p>
      {slots.map((s) => (
        <fieldset key={s} className="chips">
          <legend>{slotLabel(s)}</legend>
          {CHOICES.map(([k, text]) => (
            <button type="button" key={k} className="chip" aria-pressed={picked[s] === k} onClick={() => setPicked((p) => ({ ...p, [s]: k }))}>{text}</button>
          ))}
        </fieldset>
      ))}
      <label className="consent"><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} /><span>Use my answers for this decision. They stay private and are never attributed to me.</span></label>
      <button className="primary" disabled={!consent || !complete || busy} onClick={() => void save()}>Save my private answer</button>
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}
