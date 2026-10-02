import { useEffect, useState } from "react";
import { listen, speechSupported } from "../api";
import { CATEGORY_LABELS, homeApi, label } from "./homeApi";
import type { Category, HomeAssignment, HomeProfile, HomeState } from "./homeApi";

const PREF_LABELS: [string, string][] = [["love", "Love it"], ["ok", "Fine"], ["avoid", "Avoid"], ["cannot", "Can't do"]];
const SKILL_LABELS: [number, string][] = [[0, "New to it"], [1, "OK at it"], [2, "Good at it"]];
const REASONS: [string, string][] = [["busy", "I'm busy"], ["cannot", "I can't do it"], ["prefer_not", "I'd rather not"], ["other", "Other"]];
const fmtMin = (m: number) => (m >= 60 ? `${Math.floor(m / 60)} h${m % 60 ? ` ${m % 60} min` : ""}` : `${m} min`);

/** Private to the signed-in member. Availability, preferences and skills are only ever returned to their owner. */
export function ProfilePanel({ token, profile, onSaved }: { token: string; profile: HomeProfile; onSaved: () => void }) {
  const [hours, setHours] = useState(String(profile.availability / 60));
  const [prefs, setPrefs] = useState<Record<string, string>>(profile.prefs);
  const [skills, setSkills] = useState<Record<string, number>>(profile.skills);
  const [learn, setLearn] = useState<string[]>(profile.learn);
  const [keywords, setKeywords] = useState(profile.keywords.join(", "));
  const [exempt, setExempt] = useState(profile.exempt_this_week);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setHours(String(profile.availability / 60)); setPrefs(profile.prefs); setSkills(profile.skills);
    setLearn(profile.learn); setKeywords(profile.keywords.join(", ")); setExempt(profile.exempt_this_week);
  }, [profile]);

  async function save() {
    setError(null); setMsg(null);
    try {
      await homeApi.profile(token, {
        availability: Math.round(Number(hours) * 60), prefs, skills, learn,
        keywords: keywords.split(",").map((k) => k.trim()).filter(Boolean), exempt_this_week: exempt,
      });
      setMsg("Saved. Only you can see this.");
      onSaved();
    } catch (e) { setError((e as Error).message); }
  }

  return (
    <section className="home-panel" aria-labelledby="profile-h">
      <h3 id="profile-h">Your private limits</h3>
      <p className="fine">Only you can see these. The group sees who owns each chore, never why.</p>
      <label>Hours of chores you can take this week
        <input type="number" min={0} max={40} step={0.5} value={hours} onChange={(e) => setHours(e.target.value)} />
      </label>
      <label className="consent">
        <input type="checkbox" checked={exempt} onChange={(e) => setExempt(e.target.checked)} />
        <span>I'm exempt this week (ill, travelling). Limited to 2 weeks in any 8, so it stays fair. Used: {profile.exempt_weeks_used}.</span>
      </label>
      <details className="prefs">
        <summary>Preferences and skills</summary>
        <table>
          <caption className="sr-only">Your preference and skill for each kind of chore</caption>
          <thead><tr><th scope="col">Kind of chore</th><th scope="col">How you feel</th><th scope="col">Your skill</th><th scope="col">Want to learn</th></tr></thead>
          <tbody>
            {CATEGORY_LABELS.map(([k, text]) => (
              <tr key={k}>
                <th scope="row">{text}</th>
                <td>
                  <select aria-label={`How you feel about ${text}`} value={prefs[k] ?? "ok"} onChange={(e) => setPrefs({ ...prefs, [k]: e.target.value })}>
                    {PREF_LABELS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                </td>
                <td>
                  <select aria-label={`Your skill at ${text}`} value={skills[k] ?? 1} onChange={(e) => setSkills({ ...skills, [k]: Number(e.target.value) })}>
                    {SKILL_LABELS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                </td>
                <td>
                  <input type="checkbox" aria-label={`Want to learn ${text}`} checked={learn.includes(k)}
                    onChange={(e) => setLearn(e.target.checked ? [...learn, k] : learn.filter((x) => x !== k))} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <label>Things you know how to do (comma separated, like "plumbing, the car")
          <input value={keywords} onChange={(e) => setKeywords(e.target.value)} />
        </label>
      </details>
      {error && <p className="error" role="alert">{error}</p>}
      {msg && <p className="fine" role="status">{msg}</p>}
      <button className="primary" onClick={() => void save()}>Save my limits</button>
    </section>
  );
}

/** The signed-in member's offers, chores, load and week check-in. */
export function MyWeek({ token, st, onChange }: { token: string; st: HomeState; onChange: (s: HomeState) => void }) {
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState("busy");
  const [felt, setFelt] = useState<number | null>(null);
  const run = async (f: () => Promise<HomeState>) => { setError(null); try { onChange(await f()); } catch (e) { setError((e as Error).message); } };
  const pct = st.mine.load.vs_fair_share_pct;
  const used = st.mine.load.availability ? Math.round((st.mine.load.minutes / st.mine.load.availability) * 100) : 0;

  return (
    <section className="home-panel" aria-labelledby="week-h">
      <h3 id="week-h">Your week, {st.me.name}</h3>
      {st.mine.nudges.map((n) => <p key={n} className="banner note">{n}</p>)}
      {st.mine.proposals.length > 0 && (
        <div className="offers" role="region" aria-label="Requests waiting for you">
          {st.mine.proposals.map((p) => (
            <div key={p.id} className="offer">
              <p><strong>Can you take "{p.title}"?</strong> About {fmtMin(p.minutes)}. Nobody else can see who was asked.</p>
              <div className="row">
                <button className="primary" onClick={() => void run(() => homeApi.respond(token, p.id, true))}>Accept</button>
                <label className="inline">Or decline because
                  <select value={reason} onChange={(e) => setReason(e.target.value)}>{REASONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
                </label>
                <button className="ghost" onClick={() => void run(() => homeApi.respond(token, p.id, false, reason))}>Decline</button>
              </div>
            </div>
          ))}
        </div>
      )}
      {st.mine.assignments.length === 0 ? <p>No chores on your plate this week.</p> : (
        <ul className="mine">
          {st.mine.assignments.map((a) => (
            <li key={a.id}>
              <span className={`chip-status ${a.status}`}>{a.status}</span>
              <strong>{a.title}</strong> <span className="fine">{fmtMin(a.minutes)}{a.due ? `, due ${a.due}` : ""}</span>
              {a.why && <span className="fine why"> {a.why}</span>}
              {a.status === "planned" && (
                <span className="row">
                  <button className="ghost" onClick={() => void run(() => homeApi.complete(token, a.id))}>Done</button>
                  <button className="ghost" onClick={() => void run(() => homeApi.handBack(token, a.id, "busy"))}>Hand back</button>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      <p className="fine">
        You have {fmtMin(st.mine.load.minutes)} of {fmtMin(st.mine.load.availability)} you offered ({used}%).
        {pct !== null && ` That is ${Math.abs(pct)}% ${pct >= 0 ? "above" : "below"} your fair share.`}
      </p>
      <fieldset className="chips" aria-label="How did this week feel?">
        <legend>How did this week feel? Private. A heavy week lightens the next.</legend>
        {[1, 2, 3, 4, 5].map((n) => (
          <button key={n} className="chip" aria-pressed={felt === n}
            onClick={() => { setFelt(n); void homeApi.checkin(token, n).catch((e: Error) => setError(e.message)); }}>
            {n}{n === 1 ? ". Far too heavy" : n === 5 ? ". Comfortable" : ""}
          </button>
        ))}
      </fieldset>
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}

const STATUS_TEXT: Record<string, string> = { open: "Needs someone", pending: "Being offered", planned: "Planned", done: "Done", missed: "Missed", skipped: "Skipped" };

/** The shared board: the plan (who owns what) and the chores. Nothing private appears here. */
export function ChoreBoard({ token, st, onChange }: { token: string; st: HomeState; onChange: (s: HomeState) => void }) {
  const [text, setText] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ title: "", category: "other" as Category, minutes: "", cadence: "once", due: "", heaviness: "", people: "1" });
  const reload = async () => onChange(await homeApi.state(token));

  async function addText() {
    if (!text.trim()) return;
    setError(null); setNote(null);
    try {
      const out = await homeApi.addChore(token, { text });
      if (out.outcome === "need_more") { setNote(out.questions?.[0] ?? "Tell me a bit more."); return; }
      setText("");
      const guess = out.parsed?.assumed?.find((a) => a.startsWith("about"));
      setNote(`Added "${out.chore?.title}". ${out.outcome === "asked" ? "I've asked someone who fits." : "It will be in the plan when the week is planned."}${guess ? ` I guessed ${guess}.` : ""}`);
      await reload();
    } catch (e) { setError((e as Error).message); }
  }
  async function addForm(e: React.FormEvent) {
    e.preventDefault(); setError(null); setNote(null);
    try {
      const fields: Record<string, unknown> = { title: form.title, category: form.category, cadence: form.cadence, people_needed: Number(form.people) };
      if (form.minutes) fields.minutes = Number(form.minutes);
      if (form.due) fields.due = form.due;
      if (form.heaviness) fields.heaviness = Number(form.heaviness);
      const out = await homeApi.addChore(token, { fields });
      setNote(`Added "${out.chore?.title}". ${out.outcome === "asked" ? "I've asked someone who fits." : "It will be in the plan when the week is planned."}`);
      setForm({ ...form, title: "", minutes: "", due: "" });
      await reload();
    } catch (er) { setError((er as Error).message); }
  }
  async function plan(replan: boolean) {
    setError(null);
    try { onChange(await homeApi.plan(token, replan)); } catch (e) { setError((e as Error).message); }
  }

  const rows = st.plan.assignments;
  const [copied, setCopied] = useState(false);
  // Only what the whole household already sees: chores, owners and status. No private limits.
  const planText = () =>
    [`${st.home.name}: chores for ${st.home.week} to ${st.home.week_end}`, "", ...rows.map((a) => `${a.title} (${fmtMin(a.minutes)}): ${a.owner ?? "not yet"}${a.status === "done" ? ", done" : ""}`), "", st.plan.headline].join("\n");
  return (
    <section className="home-board" aria-labelledby="board-h">
      <h3 id="board-h">This week: {st.home.week} to {st.home.week_end}</h3>
      <form className="addchore" onSubmit={(e) => { e.preventDefault(); void addText(); }}>
        <label>Add a chore in your own words
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Clean the gutters by Saturday, about an hour" />
        </label>
        <button className="primary" disabled={!text.trim()}>Add chore</button>
      </form>
      <details className="prefs">
        <summary>Add a chore with details</summary>
        <form onSubmit={(e) => void addForm(e)} className="detailform">
          <label>Title<input required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></label>
          <label>Kind
            <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value as Category })}>
              {CATEGORY_LABELS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </label>
          <label>Minutes each time<input type="number" min={5} max={480} value={form.minutes} onChange={(e) => setForm({ ...form, minutes: e.target.value })} placeholder="I'll estimate" /></label>
          <label>How often
            <select value={form.cadence} onChange={(e) => setForm({ ...form, cadence: e.target.value })}>
              <option value="once">Once</option><option value="daily">Every day</option><option value="weekly">Every week</option>
              <option value="biweekly">Every other week</option><option value="monthly">Every month</option>
            </select>
          </label>
          <label>Due date<input type="date" value={form.due} onChange={(e) => setForm({ ...form, due: e.target.value })} /></label>
          <label>How heavy
            <select value={form.heaviness} onChange={(e) => setForm({ ...form, heaviness: e.target.value })}>
              <option value="">Usual for this kind</option><option value="1">Light</option><option value="2">Medium</option><option value="3">Heavy</option>
            </select>
          </label>
          <label>People needed<select value={form.people} onChange={(e) => setForm({ ...form, people: e.target.value })}><option>1</option><option>2</option><option>3</option></select></label>
          <button className="ghost">Add with details</button>
        </form>
      </details>
      {note && <p role="status" className="fine">{note}</p>}
      {error && <p className="error" role="alert">{error}</p>}

      {!st.plan.exists ? (
        <div className="banner note">
          <p>No plan for this week yet. {st.chores.length ? "Plan it and I'll split the chores fairly from everyone's private limits." : "Add some chores first."}</p>
          <button className="primary" disabled={!st.chores.length} onClick={() => void plan(false)}>Plan the week</button>
        </div>
      ) : (
        <>
          <table className="plan-table">
            <caption className="sr-only">This week's chores and who owns them</caption>
            <thead><tr><th scope="col">Chore</th><th scope="col">Kind</th><th scope="col">Time</th><th scope="col">Owner</th><th scope="col">Status</th></tr></thead>
            <tbody>
              {rows.map((a) => (
                <tr key={a.id}>
                  <th scope="row">{a.title}{a.mental ? " (mental load)" : ""}</th>
                  <td>{label(a.category)}</td><td>{fmtMin(a.minutes)}</td>
                  <td>{a.owner ?? "Not yet"}</td><td><span className={`chip-status ${a.status}`}>{STATUS_TEXT[a.status]}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="row">
            <button className="ghost" onClick={() => void navigator.clipboard.writeText(planText()).then(() => setCopied(true))}>{copied ? "Plan copied" : "Copy this week's plan"}</button>
            {st.me.is_admin && <button className="ghost" onClick={() => void plan(true)}>Redo the plan</button>}
          </div>
        </>
      )}
    </section>
  );
}

/** The aggregate fairness report. It shows how fair the split is, not why anyone got anything. */
export function FairnessCard({ st }: { st: HomeState }) {
  const r = st.plan.report;
  const total = Math.max(1, ...Object.values(st.plan.loads_minutes));
  if (!st.plan.exists) return null;
  return (
    <section className="home-panel fairness" aria-labelledby="fair-h">
      <h3 id="fair-h">How fair is this week?</h3>
      <p className={r.balanced ? "banner note" : "banner warn"}>{st.plan.headline}</p>
      <ul className="bars" aria-label="Time each person has this week">
        {st.members.map((m) => {
          const mins = st.plan.loads_minutes[m.name] ?? 0;
          return (
            <li key={m.name}>
              <span>{m.name}</span>
              <span className="bar" role="img" aria-label={`${m.name}: ${fmtMin(mins)}`}><i style={{ width: `${(mins / total) * 100}%` }} /></span>
              <span className="fine">{fmtMin(mins)}</span>
            </li>
          );
        })}
      </ul>
      <p className="fine">Fair means in proportion to what each person said they can give, privately, with chores weighted by how heavy they are and a premium for planning and admin. It also looks back over recent weeks, so a person who carried extra gets a lighter share.</p>
      {st.plan.attention.length > 0 && (
        <p className="banner warn" role="status">Needs a decision from the group: {st.plan.attention.join(", ")}. Nobody could take it. Talk it over, shrink it, or pay for help.</p>
      )}
    </section>
  );
}

/** Talk to the household agent in plain words, by typing or speaking. */
export function AgentBox({ token, onChanged }: { token: string; onChanged: () => void }) {
  const [text, setText] = useState("");
  const [lines, setLines] = useState<string[]>([]);
  const [listening, setListening] = useState(false);
  const [speak, setSpeak] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send(utterance: string) {
    setError(null);
    try {
      const out = await homeApi.say(token, utterance);
      setLines((l) => [...l.slice(-4), out.say]);
      if (speak && "speechSynthesis" in window) window.speechSynthesis.speak(new SpeechSynthesisUtterance(out.say));
      if (out.state_changed) onChanged();
    } catch (e) { setError((e as Error).message); }
  }
  return (
    <section className="home-panel" aria-labelledby="agent-h">
      <h3 id="agent-h">Ask the household agent</h3>
      <p className="fine">Try "what's on my plate", "I did the bins", "who has the laundry", or "add fix the squeaky door". Replies never mention anyone's private preferences.</p>
      <form className="row" onSubmit={(e) => { e.preventDefault(); const t = text.trim(); if (t) { setText(""); void send(t); } }}>
        <label className="grow">Say or type
          <input value={text} autoComplete="off" onChange={(e) => setText(e.target.value)} />
        </label>
        <button className="ghost" disabled={!text.trim()}>Send</button>
        {speechSupported() && (
          <button type="button" className="ghost" aria-pressed={listening} onClick={() => {
            setListening(true); let heard = "";
            listen((t) => { heard = t; }, () => { setListening(false); if (heard.trim()) void send(heard.trim()); });
          }}>{listening ? "Listening" : "Speak"}</button>
        )}
      </form>
      <label className="consent"><input type="checkbox" checked={speak} onChange={(e) => setSpeak(e.target.checked)} /><span>Speak the replies aloud</span></label>
      <div role="log" aria-live="polite" aria-label="What the agent says" className="captions">
        {lines.length === 0 ? <p className="fine">Replies appear here.</p> : lines.map((l, i) => <p key={i} className="caption">{l}</p>)}
      </div>
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}

export function Activity({ st }: { st: HomeState }) {
  return (
    <details className="voicebox">
      <summary>What happened so far</summary>
      <p className="fine">Who did what and when. It never says who was asked or why.</p>
      <ul className="audit" aria-label="Household activity">
        {st.events.map((e, i) => (
          <li key={i}>{new Date(e.at + "Z").toLocaleString()} {e.kind.replace(/_/g, " ")}{e.actor ? `, ${e.actor}` : ""}{e.detail ? ` (${e.detail})` : ""}</li>
        ))}
      </ul>
    </details>
  );
}

export type { HomeAssignment };
