import type { Result } from "../api";

/** Group result: aggregate only. Never shows anyone's answer or who set a limit. */
export default function Reveal({ result }: { result: Result }) {
  const care = result.mode === "care";
  return (
    <section className="reveal" aria-labelledby="reveal-h">
      <h2 id="reveal-h">{care ? "Here's a care plan that fits everyone" : "Here's the plan"}</h2>

      {(result.warnings as string[]).map((w) => <p key={w} className="banner warn">{w}</p>)}
      {result.defaults_applied && (
        <p className="banner note">
          {care ? result.defaults_note : "At least one person did not answer, so a middle-of-the-road default was used for them."}
        </p>
      )}

      {care ? <Care r={result} /> : <Everyday r={result} />}

      <p className="banner limits">{result.honest_limits}</p>
      {care && <p className="fine">{result.disclaimer}</p>}
    </section>
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
        <h3>Proposed split</h3>
        {r.assignments.length === 0 && <p>Nobody could take on any task with the limits given.</p>}
        {r.assignments.map((a: Result) => (
          <div key={a.name} className="who">
            <strong>{a.name}</strong>
            <ul>{a.tasks.map((t: Result) => <li key={t.task_id}>{t.label}, {t.hours} h/week</li>)}</ul>
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
      <p className="banner note">{r.assignment_caveat}</p>
    </>
  );
}
