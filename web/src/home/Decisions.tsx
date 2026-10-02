import { useEffect, useState } from "react";
import AnswerForm from "../AnswerForm";
import Checkin from "../Checkin";
import MyShare from "../MyShare";
import NeedEditor, { DEFAULT_TASKS, needPayload } from "../NeedEditor";
import type { TaskDraft } from "../NeedEditor";
import { api } from "../api";
import type { CheckinSummary, Hint, Result, ShareLine, Status } from "../api";
import Reveal from "../reveal/Reveal";
import { homeApi } from "./homeApi";
import type { HomeDecision, HomeState } from "./homeApi";

const KINDS: [HomeDecision["mode"], string][] = [
  ["care", "Share a parent's care"], ["everyday", "Plan a weekend"], ["trip", "Plan a trip"],
];

/** Shared: start a family decision for everyone in the household, and see the plans made so far. */
export function StartDecision({ token, st, onStarted }: { token: string; st: HomeState; onStarted: () => void }) {
  const [tasks, setTasks] = useState<TaskDraft[]>(DEFAULT_TASKS);
  const [dollars, setDollars] = useState(1800);
  const [choosing, setChoosing] = useState<HomeDecision["mode"] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const open = st.mine.decisions.filter((d) => d.state !== "closed");

  async function start(mode: HomeDecision["mode"]) {
    setBusy(true); setError(null);
    try { await homeApi.decision(token, mode, mode === "care" ? needPayload(tasks, dollars) : undefined); setChoosing(null); onStarted(); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  return (
    <section className="home-panel" aria-labelledby="decide-h">
      <h3 id="decide-h">Family decisions</h3>
      <p className="fine">For the bigger questions: a parent's care, a weekend, a trip. Everyone in the household answers privately and gets one plan, with nobody told who set which limit. Same people, no retyping.</p>
      <div className="modes" role="group" aria-label="Start a decision">
        {KINDS.map(([mode, text]) => (
          <button key={mode} className="chip" aria-pressed={choosing === mode} disabled={open.some((d) => d.mode === mode)}
            onClick={() => (mode === "care" ? setChoosing(choosing === mode ? null : mode) : void start(mode))}>
            {text}
          </button>
        ))}
      </div>
      {choosing === "care" && (
        <div className="care-start">
          <p className="fine">
            Here, care means the family sharing a parent's care between them: the hours each person can give (check-ins, appointments and transport,
            meals, paperwork, overnight cover), the money each can put in each month, and the tasks they can't do. Huddle doesn't hire or pay anyone. If
            the family can't cover the need, it suggests paid help as one option.
          </p>
          <NeedEditor tasks={tasks} dollars={dollars} onTasks={setTasks} onDollars={setDollars} summary="What the care plan needs" />
          <button className="primary" disabled={busy} onClick={() => void start("care")}>Ask everyone privately</button>
        </div>
      )}
      {error && <p className="error" role="alert">{error}</p>}
      {open.length > 0 && (
        <ul className="audit" aria-label="Open decisions">
          {open.map((d) => <li key={d.round_id}><strong>{d.title}</strong>: {d.answered_count} of {d.of} have answered</li>)}
        </ul>
      )}
      {st.plans_so_far.length > 0 && (
        <>
          <h4>Plans so far</h4>
          <ul className="audit" aria-label="Family plans so far">
            {st.plans_so_far.map((p) => <li key={p.round_id}><strong>{p.title}:</strong> {p.summary}{p.checkin ? ` (${p.checkin})` : ""}</li>)}
          </ul>
        </>
      )}
    </section>
  );
}

/** Private to the signed-in member: answer your part, see the result, your own share, and check in. */
export function MyDecisions({ st, onChanged }: { st: HomeState; onChanged: () => void }) {
  const decisions = st.mine.decisions;
  if (decisions.length === 0) return null;
  return (
    <section aria-label="Your family decisions">
      {decisions.map((d) => <DecisionCard key={d.round_id} d={d} name={st.me.name} onChanged={onChanged} />)}
    </section>
  );
}

function DecisionCard({ d, name, onChanged }: { d: HomeDecision; name: string; onChanged: () => void }) {
  const [hints, setHints] = useState<Hint[]>([]);
  const [result, setResult] = useState<Result | null>(null);
  const [checkin, setCheckin] = useState<CheckinSummary | null>(null);
  const [share, setShare] = useState<ShareLine[]>([]);
  const [status, setStatus] = useState<Status | null>(null);

  const load = async () => {
    try {
      const s = await api.status(d.token);
      setStatus(s); setHints(s.hints);
      if (s.state === "closed") {
        const r = await api.result(d.token);
        if (r.ready && r.result) { setResult(r.result); setCheckin(r.checkin ?? null); setShare(r.my_share ?? []); }
      }
    } catch { /* the token may have expired: nothing to show */ }
  };
  useEffect(() => { void load(); }, [d.token, d.state, d.answered]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="home-panel decision-card" role="region" aria-label={`Decision: ${d.title}`}>
      <h3>{d.title[0].toUpperCase() + d.title.slice(1)}</h3>
      {d.state !== "closed" && (
        d.answered ? (
          <p className="banner note" role="status">Your answer is saved and private. {d.answered_count} of {d.of} have answered. You can change it until everyone has.</p>
        ) : (
          <AnswerForm mode={d.mode} token={d.token} name={name} hints={hints}
            onSubmit={async (a) => { await api.submit(d.token, a); onChanged(); }} />
        )
      )}
      {d.state === "closed" && result && (
        <>
          <Reveal result={result} onExplain={() => api.explain(d.token)} onCard={() => api.planCard(d.token)} />
          {result.mode === "care" && <MyShare name={name} share={share} shared />}
          <Checkin name={name} summary={checkin} done={Boolean(status?.events.some((e) => e.kind === "checked_in" && e.actor === name))}
            onSubmit={async (score) => { await api.checkin(d.token, score); await load(); onChanged(); }} />
        </>
      )}
    </div>
  );
}
