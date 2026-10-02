import { useCallback, useEffect, useState } from "react";
import AnswerForm from "../AnswerForm";
import { api, listen, speechSupported, tool } from "../api";
import type { Channel, Holds, Mode, Person, Result, Status } from "../api";
import Reveal from "../reveal/Reveal";

const PRESETS: Record<Mode, { name: string; channel: Channel }[]> = {
  everyday: [{ name: "Maya", channel: "voice" }, { name: "Ben", channel: "voice" }],
  care: [{ name: "Maya", channel: "voice" }, { name: "Ben", channel: "voice" }, { name: "Chen", channel: "link" }],
};
const guessMode = (t: string): Mode => (/\b(care|mum|mom|dad|parent|mother|father|grand)/i.test(t) ? "care" : "everyday");

function Ring({ active, label }: { active: boolean; label: string }) {
  return <div className={`ring${active ? " on" : ""}`} role="img" aria-label={label}><span /></div>;
}

export default function Simulator() {
  const [utterance, setUtterance] = useState("Alexa, plan our Saturday");
  const [mode, setMode] = useState<Mode>("everyday");
  const [people, setPeople] = useState(PRESETS.everyday);
  const [demoClock, setDemoClock] = useState(false);
  const [round, setRound] = useState<Person[] | null>(null);
  const [active, setActive] = useState("");
  const [status, setStatus] = useState<Status | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [holds, setHolds] = useState<Holds | null>(null);
  const [showHolds, setShowHolds] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [listening, setListening] = useState(false);

  const host = round?.find((p) => p.is_host);

  const changeUtterance = (t: string) => {
    setUtterance(t);
    const m = guessMode(t);
    if (m !== mode) { setMode(m); setPeople(PRESETS[m]); }
  };
  const chooseMode = (m: Mode) => { setMode(m); setPeople(PRESETS[m]); setUtterance(m === "care" ? "Alexa, help us plan Mum's care" : "Alexa, plan our Saturday"); };

  async function start() {
    setError(null);
    try {
      const out = await tool<{ participants: Person[] }>("start_huddle", {
        mode, participants: people.filter((p) => p.name.trim()), deadline_seconds: demoClock ? 45 : 3600,
      });
      setRound(out.participants); setActive(out.participants[0].name); setResult(null); setNote(null);
    } catch (e) { setError((e as Error).message); }
  }

  const refresh = useCallback(async () => {
    if (!host) return;
    try {
      const s = await api.status(host.token);
      setStatus(s);
      if (showHolds) setHolds(await api.holds(host.token));
      if (s.state === "closed" && !result) {
        const r = await tool<{ ready: boolean; result?: Result }>("get_group_result", { token: host.token });
        if (r.ready && r.result) setResult(r.result);
      }
    } catch (e) { setError((e as Error).message); }
  }, [host, showHolds, result]);

  useEffect(() => {
    if (!round) return;
    void refresh();
    const id = setInterval(() => void refresh(), 2000);
    return () => clearInterval(id);
  }, [round, refresh]);

  async function nudge() {
    if (!host) return;
    const r = await tool<{ pending: string[]; message: string }>("nudge_pending", { token: host.token });
    setNote(r.pending.length ? `Reminder sent to ${r.pending.join(", ")}.` : r.message);
  }
  async function closeNow() {
    if (!host) return;
    const r = await tool<{ result?: Result }>("close_round", { token: host.token });
    if (r.result) setResult(r.result);
    void refresh();
  }
  function reset() { setRound(null); setStatus(null); setResult(null); setHolds(null); setNote(null); }

  const person = round?.find((p) => p.name === active);
  const answered = (n: string) => status?.participants.find((p) => p.name === n)?.answered ?? false;
  const state = status?.state;

  return (
    <div className="shell">
      <header className="device">
        <Ring active={listening || (!!round && !result)} label={listening ? "Listening" : "Idle"} />
        <p className="sim-tag">Simulated voice assistant. Not a real Alexa+ device.</p>
        {!round ? (
          <form className="wake" onSubmit={(e) => { e.preventDefault(); void start(); }}>
            <label>
              <span className="big">What should we sort out?</span>
              <input value={utterance} onChange={(e) => changeUtterance(e.target.value)} />
            </label>
            {speechSupported() && (
              <button type="button" className="ghost" aria-pressed={listening}
                onClick={() => { setListening(true); listen(changeUtterance, () => setListening(false)); }}>
                Speak instead
              </button>
            )}
            <div className="modes" role="group" aria-label="Kind of decision">
              {(["everyday", "care"] as Mode[]).map((m) => (
                <button type="button" key={m} className="chip" aria-pressed={mode === m} onClick={() => chooseMode(m)}>
                  {m === "everyday" ? "A weekend plan" : "Sharing care for a parent"}
                </button>
              ))}
            </div>
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
                <li key={p.name}>{p.name}<span>{p.channel === "link" ? "by link" : "by voice"}, {p.answered ? "answered" : "waiting"}</span></li>
              ))}
            </ul>
            {state === "reminded" && <p className="banner note" role="status">A reminder went out to anyone still waiting.</p>}
            {note && <p className="fine" role="status">{note}</p>}
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
            <button className="ghost" onClick={reset}>Start over</button>
          </div>
        )}
      </header>

      <main className="stage">
        {!round && (
          <section className="intro">
            <h1>Huddle</h1>
            <p className="lede">Ask everyone privately. Get one plan. Nobody has to say their number out loud.</p>
            <p className="fine">Answers are never shown or attributed. This is bucketing, not cryptographic secrecy, and with only two people the other person can work out your number.</p>
          </section>
        )}

        {round && result && <Reveal result={result} />}

        {round && !result && (
          <section className="booth" aria-label="Private answer">
            <div className="recognized" role="group" aria-label="Who is speaking">
              <span>Recognized: <strong>{active}</strong></span>
              <span className="fine">Profile switcher stands in for voice recognition. It separates profiles; it is not security.</span>
              <div className="modes">
                {round.map((p) => (
                  <button key={p.name} className="chip" aria-pressed={p.name === active} onClick={() => setActive(p.name)}>
                    {p.name}{answered(p.name) ? " (done)" : ""}
                  </button>
                ))}
              </div>
            </div>
            {person && (answered(person.name) ? (
              <p className="banner note" role="status">{person.name}'s answer is saved. It stays on the server and is not shown here.</p>
            ) : person.channel === "link" ? (
              <div className="linkbox">
                <p>{person.name} answers on their own phone. Send them this private link:</p>
                <code>{window.location.origin}{person.link}</code>
                <div className="row">
                  <button className="ghost" onClick={() => void navigator.clipboard?.writeText(window.location.origin + person.link)}>Copy link</button>
                  <a className="ghost" href={person.link} target="_blank" rel="noreferrer">Open their page</a>
                </div>
              </div>
            ) : (
              <AnswerForm key={person.token} mode={mode} token={person.token} name={person.name}
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
