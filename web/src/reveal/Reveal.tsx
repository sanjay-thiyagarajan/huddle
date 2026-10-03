import { useState } from "react";
import type { Explanation, PlanCard, Result } from "../api";

/** Group result: aggregate only. Never shows anyone's answer or who set a limit. */
export default function Reveal({ result, onExplain, onCard }: {
  result: Result; onExplain?: () => Promise<Explanation>; onCard?: () => Promise<PlanCard>;
}) {
  const care = result.mode === "care";
  const [explained, setExplained] = useState<Explanation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [speaking, setSpeaking] = useState(false);
  const [copied, setCopied] = useState(false);
  const canSpeak = typeof window !== "undefined" && "speechSynthesis" in window;

  async function readAloud() {
    if (!onCard) return;
    if (speaking) { window.speechSynthesis.cancel(); setSpeaking(false); return; }
    try {
      const card = await onCard();
      const u = new SpeechSynthesisUtterance(card.text);
      u.onend = () => setSpeaking(false);
      u.onerror = () => setSpeaking(false);
      setSpeaking(true);
      window.speechSynthesis.speak(u);
    } catch (e) { setError((e as Error).message); }
  }
  async function copyCard() {
    if (!onCard) return;
    try {
      await navigator.clipboard.writeText((await onCard()).text);
      setCopied(true);
    } catch (e) { setError((e as Error).message); }
  }

  const heading = care ? "Here's a care plan that fits everyone"
    : result.mode === "trip" ? "Here's a trip that works for the group"
    : result.mode === "when" ? "Here's a time that works" : "Here's the plan";
  return (
    <section className="reveal" aria-labelledby="reveal-h">
      <h2 id="reveal-h">{heading}</h2>

      {(result.warnings as string[]).map((w) => <p key={w} className="banner warn">{w}</p>)}
      {result.defaults_applied && (
        <p className="banner note">
          {care ? result.defaults_note : "At least one person did not answer, so a middle-of-the-road default was used for them."}
        </p>
      )}

      {care ? <Care r={result} /> : result.mode === "when" ? <When r={result} /> : <Everyday r={result} />}

      {onCard && (
        <div className="explain row">
          {canSpeak && <button className="ghost" aria-pressed={speaking} onClick={() => void readAloud()}>{speaking ? "Stop reading" : "Read it aloud"}</button>}
          <button className="ghost" onClick={() => void copyCard()}>{copied ? "Plan card copied" : "Copy plan card"}</button>
          <button className="ghost" onClick={() => window.print()}>Print</button>
        </div>
      )}
      {onExplain && (
        <div className="explain">
          <button className="ghost" onClick={() => { setError(null); onExplain().then(setExplained).catch((e: Error) => setError(e.message)); }}>
            Explain this in plain words
          </button>
          {explained && (
            <p role="status">{explained.text} <span className="fine">({explained.engine === "bedrock" ? "Amazon Bedrock" : "built-in explainer"}, {explained.latency_ms} ms)</span></p>
          )}
          {error && <p className="error" role="alert">{error}</p>}
        </div>
      )}

      <p className="banner limits">{result.honest_limits}</p>
      {care && <p className="fine">{result.disclaimer}</p>}
    </section>
  );
}

function When({ r }: { r: Result }) {
  return (
    <>
      <p className="plan"><strong>{r.plan.label}</strong><span> ({r.plan.span})</span></p>
      <p>{r.tradeoff}</p>
      {r.counts && <p className="fine">{r.counts.can} can, {r.counts.flex} could move things, {r.counts.cannot} can't.</p>}
      {r.alternatives.length > 0 && (
        <p className="fine">Next best: {r.alternatives.map((a: Result) => a.label).join("; ")}.</p>
      )}
    </>
  );
}

function Everyday({ r }: { r: Result }) {
  return (
    <>
      {r.plan ? (
        <p className="plan"><strong>{r.plan.name}</strong><span> around {r.plan.price_band} per person</span></p>
      ) : <p className="plan"><strong>No plan fit every limit</strong></p>}
      <p>{r.tradeoff}</p>
      {r.group_budget_bucket && <p className="fine">Group budget band: {r.group_budget_bucket} per person.</p>}
    </>
  );
}

function Care({ r }: { r: Result }) {
  return (
    <>
      <p className="lead">{r.headline}</p>
      <div className="split">
        <h3>Who owns what</h3>
        <p className="fine">Each person sees their own hours privately. The group sees ownership, not hours.</p>
        {r.assignments.length === 0 && <p>Nobody could take on any task with the limits given.</p>}
        {r.assignments.map((a: Result) => (
          <div key={a.name} className="who">
            <strong>{a.name}</strong>
            <ul>{a.tasks.map((t: Result) => <li key={t.task_id}>{t.label}{t.shared ? " (shared)" : ""}</li>)}</ul>
          </div>
        ))}
        {r.unfilled_tasks.length > 0 && (
          <div className="who open">
            <strong>Still open</strong>
            <ul>{r.unfilled_tasks.map((t: Result) => <li key={t.task_id}>{t.label}: {t.unfilled_hours_bucket} unfilled</li>)}</ul>
          </div>
        )}
      </div>
      <h3>Ways to close the gap</h3>
      <ul className="options">{r.options.map((o: string) => <li key={o}>{o}</li>)}</ul>
      {r.fairness && (
        <div className="fairness">
          <h3>Fair share over time</h3>
          <p>Plans in which each person held a heavy task (overnight cover, appointments and transport), across {r.fairness.plans} plans:{" "}
            {Object.entries(r.fairness.held_heavy as Record<string, number>).map(([n, c]) => `${n} ${c}`).join(", ")}.</p>
          <p className="fine">{r.fairness.note}</p>
        </div>
      )}
      <p className="banner note">{r.assignment_caveat}</p>
    </>
  );
}
