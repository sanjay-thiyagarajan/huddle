import { useEffect, useRef, useState } from "react";
import { api, CARE_DEALBREAKERS, EVERYDAY_ATTRS, EVERYDAY_VIBES, listen, speechSupported, TRIP_ATTRS, TRIP_VIBES } from "./api";
import type { Mode } from "./api";

type Draft = Record<string, unknown>;
const blank = (mode: Mode): Draft =>
  mode === "care"
    ? { hours_per_week: "", dollars_per_month: "", dealbreakers: [] }
    : { budget_ceiling: "", vibe: [], must_haves: [], dealbreakers: [] };

function Chips({ options, value, onChange, label }: {
  options: [string, string][]; value: string[]; onChange: (v: string[]) => void; label: string;
}) {
  const toggle = (k: string) => onChange(value.includes(k) ? value.filter((x) => x !== k) : [...value, k]);
  return (
    <fieldset className="chips">
      <legend>{label}</legend>
      {options.map(([k, text]) => (
        <button type="button" key={k} className="chip" aria-pressed={value.includes(k)} onClick={() => toggle(k)}>
          {text}
        </button>
      ))}
    </fieldset>
  );
}

/** One person's private answer: say it or fill it in, check it, then save. */
export default function AnswerForm({ mode, token, name, onSubmit, initial }: {
  mode: Mode; token: string; name: string; initial?: Record<string, unknown>;
  onSubmit: (answer: Record<string, unknown>) => Promise<unknown>;
}) {
  const start = (): Draft => (initial ? Object.fromEntries(Object.entries(initial).map(([k, v]) => [k, typeof v === "number" ? String(v) : v])) : blank(mode));
  const [draft, setDraft] = useState<Draft>(start);
  const [said, setSaid] = useState("");
  const [consent, setConsent] = useState(Boolean(initial)); // already agreed when revising
  const [followup, setFollowup] = useState<string | null>(null);
  const [engine, setEngine] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [listening, setListening] = useState(false);
  const stop = useRef<(() => void) | null>(null);

  useEffect(() => { setDraft(start()); setSaid(""); setConsent(Boolean(initial)); setFollowup(null); setEngine(null); setError(null); }, [token, mode]);

  const set = (k: string, v: unknown) => setDraft((d) => ({ ...d, [k]: v }));
  const list = (k: string) => (draft[k] as string[]) ?? [];

  async function understand() {
    setError(null);
    try {
      const out = await api.parse(token, said);
      setDraft((d) => {
        const next = { ...d };
        for (const [k, v] of Object.entries(out.draft)) if (v !== null && !(Array.isArray(v) && !v.length)) next[k] = v;
        return next;
      });
      setFollowup(out.followup);
      setEngine(out.engine);
    } catch (e) { setError((e as Error).message); }
  }

  function mic() {
    if (listening) { stop.current?.(); return; }
    setListening(true);
    stop.current = listen(setSaid, () => setListening(false));
  }

  async function save() {
    setBusy(true); setError(null);
    const answer: Record<string, unknown> = { ...draft, consent };
    for (const k of ["budget_ceiling", "hours_per_week", "dollars_per_month"])
      if (k in answer) answer[k] = answer[k] === "" ? null : Number(answer[k]);
    try { await onSubmit(answer); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  return (
    <form className="answer" onSubmit={(e) => { e.preventDefault(); void save(); }}>
      <label className="say">
        <span>Say it in your own words, {name}</span>
        <textarea rows={2} value={said} onChange={(e) => setSaid(e.target.value)}
          placeholder={mode === "care" ? "I can do maybe ten hours a week and $400 a month, but not nights."
                                       : mode === "trip" ? "Up to $400 for the trip, I love the beach, and no flights."
                                       : "Under $60 each, I'd love good food, and no crowds."} />
      </label>
      <div className="row">
        <button type="button" className="ghost" onClick={() => void understand()} disabled={!said.trim()}>Fill in from what I said</button>
        {speechSupported() && (
          <button type="button" className="ghost" aria-pressed={listening} onClick={mic}>{listening ? "Stop listening" : "Use microphone"}</button>
        )}
      </div>
      {engine && <p className="fine" role="status">Understood by: {engine === "bedrock" ? "Amazon Bedrock" : engine === "mock-fallback" ? "built-in parser (Bedrock was unavailable)" : "built-in parser"}. Check the fields below.</p>}
      {followup && <p className="followup" role="status">{followup}</p>}

      {mode === "care" ? (
        <>
          <div className="pair">
            <label>Hours per week you can give
              <input type="number" min={0} max={168} step={0.5} inputMode="decimal" required
                value={String(draft.hours_per_week ?? "")} onChange={(e) => set("hours_per_week", e.target.value)} />
            </label>
            <label>Dollars per month you can put in
              <input type="number" min={0} step={1} inputMode="numeric" required
                value={String(draft.dollars_per_month ?? "")} onChange={(e) => set("dollars_per_month", e.target.value)} />
            </label>
          </div>
          <Chips label="Things you can't do" options={CARE_DEALBREAKERS} value={list("dealbreakers")} onChange={(v) => set("dealbreakers", v)} />
        </>
      ) : (
        <>
          <label>{mode === "trip" ? "Most you'd spend per person for the whole trip (dollars)" : "Most you'd spend per person (dollars)"}
            <input type="number" min={0} step={1} inputMode="numeric" required
              value={String(draft.budget_ceiling ?? "")} onChange={(e) => set("budget_ceiling", e.target.value)} />
          </label>
          <Chips label="What you'd enjoy" options={mode === "trip" ? TRIP_VIBES : EVERYDAY_VIBES} value={list("vibe")} onChange={(v) => set("vibe", v)} />
          <Chips label="Dealbreakers" options={mode === "trip" ? TRIP_ATTRS : EVERYDAY_ATTRS} value={list("dealbreakers")} onChange={(v) => set("dealbreakers", v)} />
        </>
      )}

      <label className="consent">
        <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
        <span>I'm an adult and I agree to answer. Others never see my answer, and it is never attributed to me.</span>
      </label>
      {error && <p className="error" role="alert">{error}</p>}
      <button className="primary" disabled={!consent || busy}>{busy ? "Saving" : initial ? "Update my private answer" : "Save my private answer"}</button>
    </form>
  );
}
