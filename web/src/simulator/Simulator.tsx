import { useCallback, useEffect, useState } from "react";
import AnswerForm from "../AnswerForm";
import Checkin from "../Checkin";
import MyShare from "../MyShare";
import NeedEditor, { DEFAULT_TASKS, needPayload } from "../NeedEditor";
import type { TaskDraft } from "../NeedEditor";
import { api, listen, speechSupported, tool } from "../api";
import { inviteText, shareOrCopy } from "../share";
import type { Channel, CheckinSummary, Delivery, Hint, Holds, HouseholdPlan, Mode, NudgeResult, Person, Result, ShareLine, Status } from "../api";
import Reveal from "../reveal/Reveal";
import VoiceSession from "../VoiceSession";
import { ENROL_PHRASES, enrolVoice, identifyVoice, recordWav } from "../voice";

interface Invitee { name: string; channel: Channel; email?: string }
const PRESETS: Record<Mode, Invitee[]> = {
  everyday: [{ name: "Maya", channel: "voice" }, { name: "Ben", channel: "voice" }],
  care: [{ name: "Maya", channel: "voice" }, { name: "Ben", channel: "voice" }, { name: "Chen", channel: "link" }],
  trip: [{ name: "Maya", channel: "voice" }, { name: "Ben", channel: "voice" }, { name: "Chen", channel: "link" }],
};
const WAKE: Record<Mode, string> = {
  everyday: "Alexa, plan our Saturday",
  care: "Alexa, help us plan Mum's care",
  trip: "Alexa, help us pick a trip",
};
const MODE_LABEL: Record<Mode, string> = {
  care: "Share care for a parent", everyday: "Plan a weekend", trip: "Plan a trip",
};
const NEXT_LABEL: Record<Mode, string> = {
  care: "Share care again", everyday: "Plan a weekend", trip: "Plan a trip",
};
const guessMode = (t: string): Mode =>
  /\b(care|mum|mom|dad|parent|mother|father|grand)/i.test(t) ? "care"
    : /\b(trip|travel|vacation|getaway|holiday)\b/i.test(t) ? "trip" : "everyday";

function Ring({ active, label }: { active: boolean; label: string }) {
  return <div className={`ring${active ? " on" : ""}`} role="img" aria-label={label}><span /></div>;
}

export default function Simulator() {
  const [utterance, setUtterance] = useState(WAKE.care);
  const [mode, setMode] = useState<Mode>("care");
  const [people, setPeople] = useState(PRESETS.care);
  const [tasks, setTasks] = useState<TaskDraft[]>(DEFAULT_TASKS);
  const [dollars, setDollars] = useState(1800);
  const [demoClock, setDemoClock] = useState(false);
  const [round, setRound] = useState<Person[] | null>(null);
  const [active, setActive] = useState("");
  const [status, setStatus] = useState<Status | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [checkin, setCheckin] = useState<CheckinSummary | null>(null);
  const [holds, setHolds] = useState<Holds | null>(null);
  const [showHolds, setShowHolds] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [shareMsg, setShareMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [listening, setListening] = useState(false);
  const [voiceMsg, setVoiceMsg] = useState<string | null>(null);
  const [editing, setEditing] = useState<Record<string, unknown> | null>(null);
  const [revisitBusy, setRevisitBusy] = useState(false);
  const [hints, setHints] = useState<Hint[]>([]);
  const [share, setShare] = useState<ShareLine[]>([]);
  const [plans, setPlans] = useState<HouseholdPlan[]>([]);
  const [voiceOnly, setVoiceOnly] = useState(false);
  const [onScreen, setOnScreen] = useState<string[]>([]); // people who chose the screen instead of voice
  const [onPhone, setOnPhone] = useState<string[]>([]); // people who chose their phone link
  const [revoice, setRevoice] = useState<string | null>(null);

  const host = round?.find((p) => p.is_host);

  const chooseMode = (m: Mode) => { setMode(m); setPeople(PRESETS[m]); setUtterance(WAKE[m]); };
  const changeUtterance = (t: string) => {
    setUtterance(t);
    const m = guessMode(t);
    if (m !== mode) { setMode(m); setPeople(PRESETS[m]); }
  };

  async function start() {
    setError(null);
    try {
      const need = mode === "care" ? needPayload(tasks, dollars) : undefined;
      const out = await tool<{ participants: Person[] }>("start_huddle", {
        mode, participants: people.filter((p) => p.name.trim()).map((p) => ({ ...p, email: p.email?.trim() || undefined })),
        deadline_seconds: demoClock ? 45 : 3600, need,
      });
      setRound(out.participants); setActive(out.participants[0].name); setResult(null); setCheckin(null); setNote(null); setPlans([]); setOnScreen([]); setOnPhone([]); setRevoice(null);
    } catch (e) { setError((e as Error).message); }
  }

  const refresh = useCallback(async () => {
    if (!host) return;
    try {
      const s = await api.status(host.token);
      setStatus(s);
      if (showHolds) setHolds(await api.holds(host.token));
      if (s.state === "closed") {
        const r = await tool<{ ready: boolean; result?: Result; checkin?: CheckinSummary }>("get_group_result", { token: host.token });
        if (r.ready && r.result) { setResult(r.result); setCheckin(r.checkin ?? null); }
      }
    } catch (e) { setError((e as Error).message); }
  }, [host, showHolds]);

  useEffect(() => {
    if (!round) return;
    void refresh();
    const id = setInterval(() => void refresh(), 2000);
    return () => clearInterval(id);
  }, [round, refresh]);

  // Optional private hint for whoever is at the device: from their own public care assignment only.
  useEffect(() => {
    const person = round?.find((p) => p.name === active);
    if (!person || result) { setHints([]); return; }
    let live = true;
    api.status(person.token).then((s) => { if (live) setHints(s.hints); }).catch(() => undefined);
    return () => { live = false; };
  }, [round, active, result]);

  // The selected profile's own hours, fetched with THEIR token (the group result carries none).
  useEffect(() => {
    const person = round?.find((p) => p.name === active);
    if (!person || !result || result.mode !== "care") { setShare([]); return; }
    let live = true;
    api.result(person.token).then((r) => { if (live) setShare(r.my_share ?? []); }).catch(() => undefined);
    return () => { live = false; };
  }, [round, active, result]);

  useEffect(() => {
    if (!host || !result) return;
    api.household(host.token).then((h) => setPlans(h.plans)).catch(() => undefined);
  }, [host, result]);

  async function nudge() {
    if (!host) return;
    const r = await tool<NudgeResult>("nudge_pending", { token: host.token });
    setNote(r.message);
    setDeliveries(r.deliveries);
  }
  async function closeNow() {
    if (!host) return;
    const r = await tool<{ result?: Result }>("close_round", { token: host.token });
    if (r.result) setResult(r.result);
    void refresh();
  }
  async function enrol(name: string) {
    try {
      for (const [i, phrase] of ENROL_PHRASES.entries()) {
        setVoiceMsg(`${name}, say ${i + 1} of ${ENROL_PHRASES.length}: "${phrase}"`);
        await enrolVoice(name, await recordWav(4000));
      }
      setVoiceMsg(`${name}'s voice profile is saved on this machine.`);
    } catch (e) { setVoiceMsg((e as Error).message); }
  }
  async function whoIsSpeaking() {
    try {
      setVoiceMsg("Listening for a few seconds");
      const r = await identifyVoice(await recordWav(4000));
      if (r.recognized && r.name && round?.some((p) => p.name === r.name)) {
        setActive(r.name);
        setVoiceMsg(`Recognized ${r.name}.`);
      } else setVoiceMsg("Not sure who that was. Pick a profile below.");
    } catch (e) { setVoiceMsg((e as Error).message); }
  }
  async function revisit(next: Mode = mode) {
    if (!host) return;
    setRevisitBusy(true);
    try {
      const out = await tool<{ participants: Person[] }>("revisit_round", {
        token: host.token, mode: next, need: next === "care" ? needPayload(tasks, dollars) : undefined,
        deadline_seconds: demoClock ? 45 : 3600,
      });
      setMode(next); setUtterance(WAKE[next]);
      setRound(out.participants); setActive(out.participants[0].name);
      setStatus(null); setResult(null); setCheckin(null); setHolds(null); setEditing(null);
      setOnScreen([]); setOnPhone([]); setRevoice(null);
      setNote(next === mode ? "A new round is open for the same people. Everyone answers again from scratch."
        : "The next decision is open for the same family. Everyone answers from scratch.");
    } catch (e) { setError((e as Error).message); } finally { setRevisitBusy(false); }
  }
  async function change(p: Person) {
    const mine = await api.myAnswers(p.token);
    setEditing(mine.answer);
  }
  function reset() { setPlans([]); setOnScreen([]); setOnPhone([]); setRevoice(null); setRound(null); setStatus(null); setResult(null); setCheckin(null); setHolds(null); setNote(null); }

  const person = round?.find((p) => p.name === active);
  const answered = (n: string) => status?.participants.find((p) => p.name === n)?.answered ?? false;
  const checkedIn = (n: string) => status?.events.some((e) => e.kind === "checked_in" && e.actor === n) ?? false;
  const state = status?.state;

  return (
    <div className="shell">
      <header className="device">
        <Ring active={listening || (!!round && !result)} label={listening ? "Listening" : "Idle"} />
        <p className="sim-tag">Simulated voice assistant. Not a real Alexa+ device.</p>
        {!round ? (
          <form className="wake" onSubmit={(e) => { e.preventDefault(); void start(); }}>
            <label>
              <span className="big">What does the family need to decide?</span>
              <input value={utterance} onChange={(e) => changeUtterance(e.target.value)} />
            </label>
            {speechSupported() && (
              <button type="button" className="ghost" aria-pressed={listening}
                onClick={() => { setListening(true); listen(changeUtterance, () => setListening(false)); }}>
                Speak instead
              </button>
            )}
            <div className="modes" role="group" aria-label="Kind of decision">
              {(["care", "everyday", "trip"] as Mode[]).map((m) => (
                <button type="button" key={m} className="chip" aria-pressed={mode === m} onClick={() => chooseMode(m)}>
                  {MODE_LABEL[m]}
                </button>
              ))}
            </div>
            {mode === "care" && (
              <NeedEditor tasks={tasks} dollars={dollars} onTasks={setTasks} onDollars={setDollars} summary="What the care plan needs" />
            )}
            <fieldset className="people">
              <legend>Who's in the huddle</legend>
              {people.map((p, i) => (
                <div className="person-row" key={i}>
                  <input aria-label={`Name ${i + 1}`} value={p.name} onChange={(e) => setPeople(people.map((q, j) => j === i ? { ...q, name: e.target.value } : q))} />
                  <select aria-label={`How ${p.name || "they"} answers`} value={p.channel}
                    onChange={(e) => setPeople(people.map((q, j) => j === i ? { ...q, channel: e.target.value as Channel } : q))}>
                    <option value="voice">Here, by voice</option>
                    <option value="link">Remote, by link</option>
                  </select>
                  {p.channel === "link" && (
                    <input className="email-input" type="email" aria-label={`Email for reminders for ${p.name || "this person"} (optional)`}
                      placeholder="Email for reminders (optional, only if they agreed)" value={p.email ?? ""}
                      onChange={(e) => setPeople(people.map((q, j) => j === i ? { ...q, email: e.target.value } : q))} />
                  )}
                </div>
              ))}
              {people.length < 6 && <button type="button" className="ghost" onClick={() => setPeople([...people, { name: "", channel: "voice" }])}>Add a person</button>}
            </fieldset>
            <label className="consent">
              <input type="checkbox" checked={demoClock} onChange={(e) => setDemoClock(e.target.checked)} />
              <span>Short 45-second deadline, to see the reminder and defaults</span>
            </label>
            {error && <p className="error" role="alert">{error}</p>}
            <button className="primary" disabled={people.filter((p) => p.name.trim()).length < 2}>Start the huddle</button>
          </form>
        ) : (
          <div className="running">
            <p className="big">{utterance}</p>
            <p className="fine">Huddle is asking each person privately. Nobody sees anyone else's answer.</p>
            <ul className="roster">
              {status?.participants.map((p) => (
                <li key={p.name}>{p.name}<span>{p.channel === "link" ? "by link" : "by voice"}, {p.answered ? "answered" : state === "closed" ? "no answer, default used" : "waiting"}</span></li>
              ))}
            </ul>
            {state === "reminded" && <p className="banner note" role="status">A reminder went out to anyone still waiting.</p>}
            {note && <p className="fine" role="status">{note}</p>}
            {deliveries.length > 0 && (
              <ul className="audit" aria-label="Reminder delivery">
                {deliveries.map((d, i) => <li key={i}>{d.name}: {d.channel === "in_app" ? "in-app" : d.channel} {d.status}{d.detail ? ` (${d.detail})` : ""}</li>)}
              </ul>
            )}
            {!result && (
              <div className="row">
                <button className="ghost" onClick={() => void nudge()}>Remind people</button>
                <button className="ghost" onClick={() => void closeNow()}>Close now</button>
              </div>
            )}
            <label className="consent">
              <input type="checkbox" checked={showHolds} onChange={(e) => { setShowHolds(e.target.checked); if (!e.target.checked) setHolds(null); }} />
              <span>Show what the server holds</span>
            </label>
            {showHolds && holds && (
              <ul className="holds" aria-label="What the server holds">
                {holds.stored.map((h) => <li key={h.name}>{h.name}: {h.has_answer ? "answer stored" : "nothing yet"}<span>{h.value}</span></li>)}
              </ul>
            )}
            <label className="consent">
              <input type="checkbox" checked={voiceOnly} onChange={(e) => setVoiceOnly(e.target.checked)} />
              <span>Voice-only mode (like a speaker with no screen)</span>
            </label>
            <details className="voicebox">
              <summary>What happened so far</summary>
              <p className="fine">Who did what and when. Never what anyone answered.</p>
              <ul className="audit" aria-label="Audit trail">
                {status?.events.map((e, i) => (
                  <li key={i}>{new Date(e.at + "Z").toLocaleTimeString()} {e.kind.replace("_", " ")}{e.actor ? `, ${e.actor}` : ""}{e.detail ? ` (${e.detail})` : ""}</li>
                ))}
              </ul>
            </details>
            {plans.length > 0 && (
              <details className="voicebox" open>
                <summary>Family plans so far</summary>
                <ul className="audit" aria-label="Family plans so far">
                  {plans.map((p) => <li key={p.round_id}><strong>{p.title}:</strong> {p.summary}{p.checkin ? ` (${p.checkin})` : ""}</li>)}
                </ul>
              </details>
            )}
            <details className="voicebox">
              <summary>Voice recognition setup</summary>
              <p className="fine">Optional stand-in for Alexa person recognition. It separates profiles and is not security. Only a voice fingerprint is kept, not the recording.</p>
              <div className="row">
                {round.filter((p) => p.channel === "voice").map((p) => (
                  <button key={p.name} className="ghost" onClick={() => void enrol(p.name)}>Enrol {p.name}</button>
                ))}
              </div>
              {voiceMsg && <p role="status">{voiceMsg}</p>}
            </details>
            <button className="ghost" onClick={reset}>Start over</button>
          </div>
        )}
      </header>

      <main className="stage">
        {!round && (
          <section className="intro">
            <h1>Try a decision</h1>
            <p className="fine">A one-off family decision without setting up a household. For your own home, with chores and decisions together, use the Home tab.</p>
            <p className="lede">Some decisions stall because nobody wants to say their real number out loud. Huddle asks each person privately and proposes one plan.</p>
            <p>It's built for a family's decisions, hard and easy, with one way of working. Take three siblings sharing a parent's care: one can give 12 hours a week but not nights, one lives far away and can send money, one can only drive on weekdays. Nobody wants their limit to be the one that decides. Huddle collects each limit privately, works out what fits everyone, and shows a plan and the trade-off without saying who set which limit.</p>
            <p>Then the same family can plan a weekend or a trip the same way, without retyping who's in it. And the care plan shapes what comes next: whoever carries the heavy care tasks gets an optional, private hint when leisure plans are made.</p>
            <p className="fine">Answers are never shown or attributed. This is bucketing, not cryptographic secrecy, and with only two people the other person can work out your number. Huddle decides; it does not book, split expenses or give medical, legal or financial advice.</p>
          </section>
        )}

        {round && result && (
          <>
            <Reveal result={result} onExplain={host ? () => api.explain(host.token) : undefined}
              onCard={host ? () => api.planCard(host.token) : undefined} />
            <div className="recognized" role="group" aria-label="Who is checking in">
              <div className="modes">
                {round.map((p) => (
                  <button key={p.name} className="chip" aria-pressed={p.name === active} onClick={() => { setActive(p.name); setEditing(null); }}>{p.name}</button>
                ))}
              </div>
            </div>
            {person && result.mode === "care" && person.channel === "voice" && (
              <MyShare name={person.name} share={share} shared />
            )}
            {person && (person.channel === "link" && !checkedIn(person.name) ? (
              <p className="fine">{person.name} checks in on their own page: <a href={person.link} target="_blank" rel="noreferrer">open it</a>.</p>
            ) : (
              <Checkin name={person?.name ?? ""} summary={checkin} done={person ? checkedIn(person.name) : false}
                onSubmit={async (score) => { await tool("submit_checkin", { token: person!.token, score }); void refresh(); }} />
            ))}
            {host && (
              <section className="nextround" aria-labelledby="next-h">
                <h3 id="next-h">{checkin?.revisit ? "Someone isn't comfortable. Try another round?" : "What should the family decide next?"}</h3>
                <p className="fine">Same people, answering again from scratch. Nothing private carries over.{mode === "care" ? " Heavy care tasks are rotated across rounds using past assignments only." : " If someone carries heavy care tasks, they get an optional private hint."}</p>
                {mode === "care" && (
                  <NeedEditor tasks={tasks} dollars={dollars} onTasks={setTasks} onDollars={setDollars} summary="Care need for the next round" />
                )}
                <div className="row">
                  <button className={checkin?.revisit ? "primary" : "ghost"} disabled={revisitBusy} onClick={() => void revisit(mode)}>Start the next round of this decision</button>
                  {(["care", "everyday", "trip"] as Mode[]).filter((m) => m !== mode).map((m) => (
                    <button key={m} className="ghost" disabled={revisitBusy} onClick={() => void revisit(m)}>{NEXT_LABEL[m]}</button>
                  ))}
                </div>
              </section>
            )}
          </>
        )}

        {round && !result && (
          <section className="booth" aria-label="Private answer">
            <div className="recognized" role="group" aria-label="Who is speaking">
              <span>Recognized: <strong>{active}</strong></span>
              <span className="fine">Profile switcher stands in for voice recognition. It separates profiles; it is not security.</span>
              <button className="ghost" onClick={() => void whoIsSpeaking()}>Who's speaking? Listen</button>
              <div className="modes">
                {round.map((p) => (
                  <button key={p.name} className="chip" aria-pressed={p.name === active} onClick={() => { setActive(p.name); setEditing(null); }}>
                    {p.name}{answered(p.name) ? " (done)" : ""}
                  </button>
                ))}
              </div>
            </div>
            {person && (editing && person.channel === "voice" ? (
              <AnswerForm key={`${person.token}-edit`} mode={mode} token={person.token} name={person.name} initial={editing}
                onSubmit={async (answer) => {
                  await tool("submit_private_answer", { token: person.token, answer });
                  setEditing(null); void refresh();
                }} />
            ) : answered(person.name) && revoice !== person.name ? (
              <>
                <p className="banner note" role="status">{person.name}'s answer is saved. It stays on the server and is not shown here. It can be changed until everyone has answered.</p>
                {person.channel === "voice" && (voiceOnly && !onScreen.includes(person.name)
                  ? <button className="ghost" onClick={() => setRevoice(person.name)}>Change my answer by voice</button>
                  : <button className="ghost" onClick={() => void change(person)}>Change my answer</button>)}
              </>
            ) : person.channel === "link" || onPhone.includes(person.name) ? (
              <div className="linkbox">
                <p>{person.name} answers on their own phone, so nobody hears it. Send them this private link:</p>
                <code>{window.location.origin}{person.link}</code>
                <div className="row">
                  <button className="ghost" onClick={() => void navigator.clipboard?.writeText(window.location.origin + person.link)}>Copy link</button>
                  <button className="ghost" onClick={() => void shareOrCopy({ title: "Huddle", text: inviteText(person.name), url: window.location.origin + person.link })
                    .then((r) => setShareMsg(r === "failed" ? "Couldn't open sharing. Copy the link instead." : r === "copied" ? "Invite copied. Paste it into a message." : "Invite ready to send."))}>Share invite</button>
                  <a className="ghost" href={person.link} target="_blank" rel="noreferrer">Open their page</a>
                </div>
                {shareMsg && <p className="fine" role="status">{shareMsg}</p>}
              </div>
            ) : voiceOnly && !onScreen.includes(person.name) ? (
              <VoiceSession key={person.token} token={person.token} name={person.name}
                onSaved={() => { setRevoice(null); void refresh(); }}
                onHandoff={(kind) => {
                  if (kind === "link") setOnPhone((l) => [...l, person.name]);
                  else setOnScreen((l) => [...l, person.name]);
                }} />
            ) : (
              <AnswerForm key={person.token} mode={mode} token={person.token} name={person.name} hints={hints}
                onSubmit={async (answer) => {
                  const out = await tool<{ warnings: string[] }>("submit_private_answer", { token: person.token, answer });
                  void refresh();
                  return out.warnings;
                }} />
            ))}
          </section>
        )}
        {error && round && <p className="error" role="alert">{error}</p>}
      </main>
    </div>
  );
}
