import { useCallback, useEffect, useRef, useState } from "react";
import { listen, speak, speechOutSupported, speechSupported } from "../api";
import { homeApi } from "../home/homeApi";
import { slotLabel } from "../WhenAnswer";
import { CIRCLES, circleLabel, timeApi } from "./timeApi";
import type { AddOut, Briefing, Circle, Clash, DueReminder, Gathering, ImportOut, MyTime as MyTimeData, Options, ReminderKind, Reminders as RemindersData, TimeItem, TimeRules } from "./timeApi";

const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" });
const hhmm = (iso: string) => new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
const hours = (m: number) => `${Math.round((m / 60) * 10) / 10} h`;
const isoDay = (d: Date) => d.toLocaleDateString("sv");

/** The signed-in member's own time: family, friends, work and personal in one private schedule. */
export default function MyTime({ token }: { token: string }) {
  const [data, setData] = useState<MyTimeData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [week, setWeek] = useState<string | undefined>(undefined);
  const [perm, setPerm] = useState<NotificationPermission | "unsupported">(
    typeof Notification === "undefined" ? "unsupported" : Notification.permission);
  const [aloud, setAloud] = useState<boolean>(() => {
    try { return localStorage.getItem("huddle-speak-time") === "1"; } catch { return false; }
  });
  const changeAloud = (on: boolean) => {
    setAloud(on);
    if (!on && speechOutSupported()) window.speechSynthesis.cancel();
    try { localStorage.setItem("huddle-speak-time", on ? "1" : "0"); } catch { /* storage unavailable: the choice lasts for this page only */ }
  };
  const refresh = useCallback(async () => {
    try { setData(await timeApi.get(token, week)); setError(null); } catch (e) { setError((e as Error).message); }
  }, [token, week]);
  useEffect(() => { void refresh(); const id = setInterval(() => void refresh(), 5000); return () => clearInterval(id); }, [refresh]);
  useEffect(() => { setData(null); setWeek(undefined); }, [token]);
  const shift = (days: number) => {
    if (!data) return;
    const d = new Date(`${data.week}T12:00:00`); d.setDate(d.getDate() + days); setWeek(isoDay(d));
  };

  if (error && !data) return <p className="error" role="alert">{error}</p>;
  if (!data) return <p>Loading</p>;
  return (
    <div className="home-layout">
      <div className="home-private">
        <p className="fine">Only you can see this page: what you've committed to, your rules, and how you'd answer. Others only ever see a result, never your schedule.</p>
        {speechOutSupported() && (
          <label className="consent">
            <input type="checkbox" checked={aloud} onChange={(e) => changeAloud(e.target.checked)} />
            <span>Speak replies and reminders aloud. This is your browser's voice standing in for the assistant, it works only while this page is open, and people nearby may hear your commitments.</span>
          </label>
        )}
        <StartingSoon due={data.reminders.due} perm={perm} aloud={aloud} />
        <Today token={token} refreshKey={data.items.length} />
        <TimeAgent token={token} aloud={aloud} onChanged={() => void refresh()} />
        <div className="modes" role="group" aria-label="Which week">
          <button className="chip" onClick={() => shift(-7)}>Previous week</button>
          <button className="chip" onClick={() => setWeek(undefined)}>This week</button>
          <button className="chip" onClick={() => shift(7)}>Next week</button>
          <span className="fine">Week of {day(data.week)}</span>
        </div>
        <Week token={token} data={data} onChanged={() => void refresh()} />
        <AddForm token={token} onChanged={() => void refresh()} />
      </div>
      <div className="home-shared">
        <Summary token={token} data={data} />
        <CalendarFiles token={token} feed={data.feed} onChanged={() => void refresh()} />
        <Reminders token={token} reminders={data.reminders} perm={perm} onAllow={() => void Notification.requestPermission().then(setPerm)} onChanged={() => void refresh()} />
        <FindTime token={token} data={data} onChanged={() => void refresh()} />
        <Rules token={token} rules={data.rules} onChanged={() => void refresh()} />
      </div>
    </div>
  );
}

function TimeAgent({ token, aloud, onChanged }: { token: string; aloud: boolean; onChanged: () => void }) {
  const [text, setText] = useState("");
  const [lines, setLines] = useState<{ who: "you" | "agent"; text: string }[]>([]);
  const [quick, setQuick] = useState<string[]>([]);
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function send(utterance: string) {
    setError(null);
    setLines((l) => [...l.slice(-7), { who: "you", text: utterance }]);
    try {
      const out = await timeApi.say(token, utterance);
      setLines((l) => [...l.slice(-7), { who: "agent", text: out.say }]);
      if (aloud) speak(out.say);
      setQuick(out.quick_replies);
      if (out.state_changed) onChanged();
    } catch (e) { setError((e as Error).message); }
  }
  return (
    <section className="home-panel" aria-labelledby="tagent-h">
      <h3 id="tagent-h">Tell the scheduling agent</h3>
      <p className="fine">Try "dinner with Priya Thursday 7pm for 2 hours", "what's my week", "when am I free" or "find a time for drinks with Ben". If something clashes, I'll suggest a way out and you decide.</p>
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
      <div role="log" aria-live="polite" aria-label="What the scheduling agent says" className="captions">
        {lines.length === 0 ? <p className="fine">Replies appear here.</p> : lines.map((l, i) => <p key={i} className="caption"><strong>{l.who === "you" ? "You" : "Agent"}:</strong> {l.text}</p>)}
      </div>
      {quick.length > 0 && (
        <div className="modes" role="group" aria-label="Quick replies">
          {quick.map((qr) => <button key={qr} className="chip" onClick={() => { setQuick([]); void send(qr); }}>{qr}</button>)}
        </div>
      )}
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}

function Week({ token, data, onChanged }: { token: string; data: MyTimeData; onChanged: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const byDay = new Map<string, TimeItem[]>();
  data.items.forEach((i) => byDay.set(i.date, [...(byDay.get(i.date) ?? []), i]));
  async function act(fn: () => Promise<unknown>) {
    setError(null);
    try { await fn(); onChanged(); } catch (e) { setError((e as Error).message); }
  }
  return (
    <section className="home-panel" aria-labelledby="week-t-h">
      <h3 id="week-t-h">Your week</h3>
      {data.items.length === 0 && <p className="fine">Nothing yet. Add something below, or tell the agent.</p>}
      {[...byDay.entries()].map(([d, list]) => (
        <div key={d}>
          <h4>{day(d)}</h4>
          <ul className="audit" aria-label={`Commitments on ${day(d)}`}>
            {list.map((i) => (
              <li key={`${i.id}-${i.start}`}>
                <strong>{hhmm(i.start)}</strong> {i.title} <span className="fine">({circleLabel(i.circle)}{i.flexibility === "fixed" ? ", fixed" : ""}{i.tentative ? ", tentative" : ""}{i.repeat !== "none" ? `, ${i.repeat}` : ""})</span>{" "}
                {i.tentative && <button className="ghost" onClick={() => void act(() => timeApi.confirm(token, i.id, true))}>Keep</button>}{" "}
                <button className="ghost" aria-label={`Cancel ${i.title}`} onClick={() => void act(() => timeApi.update(token, i.id, { status: "cancelled" }, i.repeat !== "none" ? i.date : undefined))}>
                  {i.tentative ? "Drop" : "Cancel"}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}
      {data.conflicts.length > 0 && (
        <div role="region" aria-label="Clashes">
          <h4>Clashes to settle</h4>
          {data.conflicts.map((c) => (
            <p key={`${c.a.id}-${c.b.id}-${c.a.start}`} className="banner warn">
              {c.a.title} and {c.b.title} overlap on {day(c.a.start)}. {c.options.reason}{" "}
              <button className="ghost" onClick={() => void act(() => timeApi.update(token, c.a.id, { status: "cancelled" }, c.a.repeat !== "none" ? c.a.date : undefined))}>Cancel {c.a.title}</button>{" "}
              <button className="ghost" onClick={() => void act(() => timeApi.update(token, c.b.id, { status: "cancelled" }, c.b.repeat !== "none" ? c.b.date : undefined))}>Cancel {c.b.title}</button>
            </p>
          ))}
        </div>
      )}
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}

function AddForm({ token, onChanged }: { token: string; onChanged: () => void }) {
  const [title, setTitle] = useState("");
  const [circle, setCircle] = useState<Circle>("friends");
  const [date, setDate] = useState(isoDay(new Date()));
  const [time, setTime] = useState("19:00");
  const [minutes, setMinutes] = useState(60);
  const [flex, setFlex] = useState("movable");
  const [repeat, setRepeat] = useState("none");
  const [pending, setPending] = useState<{ fields: Record<string, unknown>; clash: Clash } | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fields = () => ({ title, circle, start: `${date}T${time}`, minutes, flexibility: flex, repeat });
  async function submit(resolution?: Record<string, unknown>) {
    setError(null); setNote(null);
    try {
      const out: AddOut = await timeApi.add(token, pending?.fields ?? fields(), resolution);
      if (!out.created && out.analysis?.clashes.length) { setPending({ fields: pending?.fields ?? fields(), clash: out.analysis.clashes[0] }); return; }
      setPending(null);
      if (out.created) { setTitle(""); setNote(`Added ${out.commitment?.title}.${out.rule_suggestion ? ` You've chosen ${out.rule_suggestion.prefer} over ${out.rule_suggestion.over} twice. You can make that a rule below.` : ""}`); onChanged(); }
      else setNote("Skipped.");
    } catch (e) { setError((e as Error).message); }
  }
  const resolve = (o: Options["options"][number]) => {
    const alt = o.alternatives?.[0];
    const start = alt ? String(alt).slice(0, 16) : undefined;
    void submit({ choice: o.key, ...(o.key === "move_new" ? { new_start: start } : {}), ...(o.key === "move_existing" ? { existing_new_start: start } : {}) });
  };
  return (
    <section className="home-panel" aria-labelledby="add-t-h">
      <h3 id="add-t-h">Add something</h3>
      <form className="grid" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
        <label>What<input value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={80} /></label>
        <label>Who it's with
          <select value={circle} onChange={(e) => setCircle(e.target.value as Circle)}>{CIRCLES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
        </label>
        <label>Day<input type="date" value={date} onChange={(e) => setDate(e.target.value)} required /></label>
        <label>Starts<input type="time" value={time} onChange={(e) => setTime(e.target.value)} required /></label>
        <label>Minutes<input type="number" min={5} step={5} value={minutes} onChange={(e) => setMinutes(Number(e.target.value))} /></label>
        <label>Can it move?
          <select value={flex} onChange={(e) => setFlex(e.target.value)}><option value="fixed">No, it's fixed</option><option value="movable">If needed</option><option value="optional">It's optional</option></select>
        </label>
        <label>Repeats
          <select value={repeat} onChange={(e) => setRepeat(e.target.value)}><option value="none">Once</option><option value="daily">Daily</option><option value="weekly">Weekly</option></select>
        </label>
        <button className="primary" disabled={!title.trim() || Boolean(pending)}>Add</button>
      </form>
      {pending && (
        <div className="banner warn" role="alert">
          <p><strong>{String(pending.fields.title)}</strong> clashes with <strong>{pending.clash.title}</strong> ({circleLabel(pending.clash.circle)}, {hhmm(pending.clash.start)}). {pending.clash.options.reason}</p>
          <div className="modes" role="group" aria-label="How to settle the clash">
            {pending.clash.options.options.map((o) => (
              <button key={o.key} className={o.key === pending.clash.options.recommended ? "chip primary" : "chip"} title={o.detail} onClick={() => resolve(o)}>
                {o.label}{o.key === pending.clash.options.recommended ? " (suggested)" : ""}
              </button>
            ))}
          </div>
        </div>
      )}
      {note && <p className="banner note" role="status">{note}</p>}
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}

function Summary({ token, data }: { token: string; data: MyTimeData }) {
  const s = data.summary;
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <section className="home-panel" aria-labelledby="sum-h">
      <h3 id="sum-h">How your week looks</h3>
      <ul className="audit" aria-label="Hours by circle">
        {CIRCLES.map(([k, v]) => <li key={k}>{v}: {hours(s.minutes_by_circle[k] ?? 0)}</li>)}
        <li>Free: about {hours(s.free_minutes)}. Evenings out: {s.evenings_out}.</li>
      </ul>
      {s.notes.map((n) => <p key={n} className="fine">{n}</p>)}
      <p>After everything else, a realistic chore and care load for you is about <strong>{hours(s.suggested_chore_minutes)}</strong> a week.</p>
      <button className="ghost" disabled={done} onClick={() => { setError(null); homeApi.profile(token, { availability: s.suggested_chore_minutes }).then(() => setDone(true)).catch((e: Error) => setError(e.message)); }}>
        {done ? "Saved as your chore availability" : "Use this as my chore availability"}
      </button>
      <p className="fine">Only a suggestion, and still private: the household planner never sees your calendar, just the number you save.</p>
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}

function FindTime({ token, data, onChanged }: { token: string; data: MyTimeData; onChanged: () => void }) {
  const [members, setMembers] = useState<string[]>([]);
  const [names, setNames] = useState<string[] | null>(null);
  const [title, setTitle] = useState("");
  const [circle, setCircle] = useState("friends");
  const [minutes, setMinutes] = useState(120);
  const [from, setFrom] = useState(isoDay(new Date(Date.now() + 86400000)));
  const [to, setTo] = useState(isoDay(new Date(Date.now() + 5 * 86400000)));
  const [begin, setBegin] = useState("18:00");
  const [end, setEnd] = useState("22:00");
  const [guests, setGuests] = useState("");
  const [started, setStarted] = useState<{ guests: { name: string; link: string }[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { homeApi.state(token).then((s) => setNames(s.members.map((m) => m.name).filter((n) => n !== s.me.name))).catch(() => setNames([])); }, [token]);

  async function start() {
    setError(null); setStarted(null);
    try {
      const out = await timeApi.gather(token, {
        title, circle, duration_minutes: minutes, members,
        guests: guests.split(",").map((g) => g.trim()).filter(Boolean).map((name) => ({ name })),
        windows: [{ date_from: from, date_to: to, from: begin, to: end }],
      });
      setStarted(out); setTitle(""); onChanged();
    } catch (e) { setError((e as Error).message); }
  }
  return (
    <section className="home-panel" aria-labelledby="find-h">
      <h3 id="find-h">Find a time</h3>
      <p className="fine">For friends, colleagues or family. People in your household answer from their own schedule; guests get a link. Everyone sees the same candidate times, and the result never says who couldn't make which.</p>
      <form className="grid" onSubmit={(e) => { e.preventDefault(); void start(); }}>
        <label>What<input value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={80} /></label>
        <label>With
          <select value={circle} onChange={(e) => setCircle(e.target.value)}><option value="friends">Friends</option><option value="family">Family</option><option value="work">Work</option></select>
        </label>
        <label>Minutes<input type="number" min={15} step={15} value={minutes} onChange={(e) => setMinutes(Number(e.target.value))} /></label>
        <label>From day<input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></label>
        <label>To day<input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></label>
        <label>Earliest<input type="time" value={begin} onChange={(e) => setBegin(e.target.value)} /></label>
        <label>Latest end<input type="time" value={end} onChange={(e) => setEnd(e.target.value)} /></label>
        <fieldset className="chips">
          <legend>People in your household</legend>
          {(names ?? []).map((n) => (
            <button type="button" key={n} className="chip" aria-pressed={members.includes(n)} onClick={() => setMembers((m) => (m.includes(n) ? m.filter((x) => x !== n) : [...m, n]))}>{n}</button>
          ))}
        </fieldset>
        <label>Guests outside the household (names, separated by commas)<input value={guests} onChange={(e) => setGuests(e.target.value)} /></label>
        <button className="primary" disabled={!title.trim() || (members.length === 0 && !guests.trim())}>Ask them</button>
      </form>
      {started && (
        <div className="banner note" role="status">
          <p>Asked. Your suggested answers are ready below.</p>
          {started.guests.length > 0 && (
            <ul className="audit" aria-label="Guest links">
              {started.guests.map((g) => <li key={g.name}>{g.name}: <code>{window.location.origin}{g.link}</code></li>)}
            </ul>
          )}
        </div>
      )}
      {error && <p className="error" role="alert">{error}</p>}
      {data.gatherings.map((g) => <GatheringCard key={g.round_id} token={token} g={g} onChanged={onChanged} />)}
    </section>
  );
}

function GatheringCard({ token, g, onChanged }: { token: string; g: Gathering; onChanged: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const r = g.result as { plan?: { label: string; span: string }; tradeoff?: string } | null;
  async function accept() {
    setBusy(true); setError(null);
    try { await timeApi.answer(token, g.round_id, { accept_suggestions: true }); onChanged(); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return (
    <div className="decision-card" role="region" aria-label={`Find a time: ${g.title}`}>
      <h4>{g.title}</h4>
      {g.state === "closed" && r?.plan ? (
        <p><strong>{r.plan.label}</strong> ({r.plan.span}). {r.tradeoff}</p>
      ) : g.answered ? (
        <p className="banner note" role="status">Your answer is saved and private. {g.answered_count} of {g.of} have answered.</p>
      ) : (
        <>
          <p className="fine">From your own schedule, only you see these reasons:</p>
          <ul className="audit" aria-label="Your suggested answers">
            {g.slots.map((s) => <li key={s.start}><strong>{slotLabel(s.start)}</strong>: {s.suggested === "yes" ? "works" : s.suggested === "maybe" ? "could move things" : "can't"}. <span className="fine">{s.reason}</span></li>)}
          </ul>
          <button className="primary" disabled={busy} onClick={() => void accept()}>Use my suggested answers</button>
        </>
      )}
      {error && <p className="error" role="alert">{error}</p>}
    </div>
  );
}

/** Today at a glance: the same sentences the assistant reads aloud for "what's my day". */
function Today({ token, refreshKey }: { token: string; refreshKey: number }) {
  const [b, setB] = useState<Briefing | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { timeApi.briefing(token).then((x) => { setB(x); setError(null); }).catch((e: Error) => setError(e.message)); }, [token, refreshKey]);
  return (
    <section className="home-panel" aria-labelledby="today-h">
      <h3 id="today-h">Today</h3>
      {b && <p role="status">{b.say}</p>}
      {b && b.items.length > 0 && (
        <ul className="audit" aria-label="Today's commitments">
          {b.items.map((i) => <li key={`${i.id}-${i.start}`}><strong>{hhmm(i.start)}</strong> {i.title} <span className="fine">({circleLabel(i.circle)})</span></li>)}
        </ul>
      )}
      {b && speechOutSupported() && <button className="ghost" onClick={() => speak(b.say)}>Read my day aloud</button>}
      <p className="fine">Ask the assistant "what's my day" and it reads this aloud. It only ever covers your own things.</p>
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}

function download(filename: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/calendar" }));
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

/** Read an .ics file (or follow a calendar address), and hand your commitments or chores back as .ics. */
function CalendarFiles({ token, feed, onChanged }: { token: string; feed: MyTimeData["feed"]; onChanged: () => void }) {
  const [circle, setCircle] = useState<Circle>("personal");
  const [address, setAddress] = useState("");
  const [result, setResult] = useState<ImportOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  async function run(fn: () => Promise<ImportOut | void>) {
    setError(null); setResult(null);
    try {
      const out = await fn();
      if (out && typeof out.imported === "number") setResult({ ...out, notes: out.notes ?? [] });
      onChanged();
    } catch (e) { setError((e as Error).message); }
  }
  async function readFile(file: File | undefined) {
    if (!file) return;
    if (file.size > 2_000_000) { setError("That calendar file is too large (limit 2 MB)."); return; }
    await run(async () => timeApi.importIcs(token, await file.text(), circle));
  }
  async function save(kind: "my_time" | "chore_plan") {
    setError(null);
    try { const out = await timeApi.exportIcs(token, kind); download(out.filename, out.ics); } catch (e) { setError((e as Error).message); }
  }
  return (
    <section className="home-panel" aria-labelledby="cal-h">
      <h3 id="cal-h">Calendar files</h3>
      <p className="fine">Export your calendar from Outlook, Google or Apple as an .ics file and read it in here. It becomes your own private commitments; nobody else sees it, and the file itself isn't kept.</p>
      <div className="row">
        <label>These are mostly
          <select value={circle} onChange={(e) => setCircle(e.target.value as Circle)}>{CIRCLES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
        </label>
        <label className="grow">Calendar file (.ics)
          <input type="file" accept=".ics,text/calendar" onChange={(e) => { void readFile(e.target.files?.[0]); e.target.value = ""; }} />
        </label>
      </div>
      {result && (
        <div className="banner note" role="status">
          <p>Read {result.imported} new, {result.updated} updated, {result.unchanged} unchanged.</p>
          {result.notes.map((n) => <p key={n} className="fine">{n}</p>)}
        </div>
      )}
      <h4>Follow a calendar address</h4>
      <p className="fine">Outlook and Google can publish a read-only calendar link. Paste it and Huddle re-reads it about once an hour. Treat the link like a password: it's never shown again.</p>
      {feed.subscribed ? (
        <p role="status">Following a calendar ({feed.last_status}{feed.last_fetched ? `, last read ${feed.last_fetched.replace("T", " ")}` : ""}).{" "}
          <button className="ghost" onClick={() => void run(() => timeApi.refreshFeed(token))}>Read it again now</button>{" "}
          <button className="ghost" onClick={() => void run(async () => { await timeApi.subscribe(token, null, circle); })}>Stop following</button></p>
      ) : (
        <form className="row" onSubmit={(e) => { e.preventDefault(); const u = address.trim(); if (u) { setAddress(""); void run(() => timeApi.subscribe(token, u, circle)); } }}>
          <label className="grow">Calendar address (https:// or webcal://)
            <input type="password" autoComplete="off" value={address} onChange={(e) => setAddress(e.target.value)} />
          </label>
          <button className="ghost" disabled={!address.trim()}>Follow</button>
        </form>
      )}
      <h4>Take it with you</h4>
      <div className="row">
        <button className="ghost" onClick={() => void save("my_time")}>Export my commitments</button>
        <button className="ghost" onClick={() => void save("chore_plan")}>Export my chores this week</button>
      </div>
      <p className="fine">Chores are added as all-day entries, because a chore has a due date but no time of day. Times are kept as written, with no time zone.</p>
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}

const soonText = (d: DueReminder) =>
  `${d.title} ${d.minutes_away === 0 ? "starts now" : `starts in ${d.minutes_away} minute${d.minutes_away === 1 ? "" : "s"}`} (${hhmm(d.start)})`;

/** The "starting soon" reminder, shown while this page is open: a banner, and a browser pop-up if allowed. */
function StartingSoon({ due, perm, aloud }: { due: DueReminder[]; perm: NotificationPermission | "unsupported"; aloud: boolean }) {
  const told = useRef(new Set<string>());
  const spoken = useRef(new Set<string>());
  useEffect(() => {
    if (!aloud) return;
    for (const d of due) {
      const key = `${d.id}:${d.start}`;
      if (spoken.current.has(key)) continue;
      spoken.current.add(key);
      speak(`Reminder: ${soonText(d)}.`);
    }
  }, [due, aloud]);
  useEffect(() => {
    if (perm !== "granted") return;
    for (const d of due) {
      const key = `huddle-soon-${d.id}:${d.start}`;
      if (told.current.has(key)) continue;
      told.current.add(key);
      try { if (sessionStorage.getItem(key)) continue; sessionStorage.setItem(key, "1"); } catch { /* storage unavailable: the in-memory set still stops repeats */ }
      new Notification("Huddle", { body: soonText(d) });
    }
  }, [due, perm]);
  if (due.length === 0) return null;
  return (
    <div className="banner warn" role="alert" aria-label="Starting soon">
      {due.map((d) => <p key={`${d.id}-${d.start}`}><strong>{soonText(d)}</strong></p>)}
    </div>
  );
}

/** Opt-in reminders: a banner (and pop-up) while this page is open, and email only if the host set it up. */
function Reminders({ token, reminders, perm, onAllow, onChanged }: { token: string; reminders: RemindersData; perm: NotificationPermission | "unsupported"; onAllow: () => void; onChanged: () => void }) {
  const [start, setStart] = useState(reminders.quiet_start ?? "22:00");
  const [end, setEnd] = useState(reminders.quiet_end ?? "07:00");
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const offset = -new Date().getTimezoneOffset();
  async function save(changes: Partial<RemindersData>) {
    setError(null); setSaved(false);
    try { await timeApi.reminders(token, { utc_offset_minutes: offset, ...changes }); setSaved(true); onChanged(); } catch (e) { setError((e as Error).message); }
  }
  const toggle = (k: ReminderKind) => save({ kinds: reminders.kinds.includes(k) ? reminders.kinds.filter((x) => x !== k) : [...reminders.kinds, k] });
  return (
    <section className="home-panel" aria-labelledby="rem-h">
      <h3 id="rem-h">Reminders</h3>
      <p className="fine">Off until you turn them on. "Starting soon" shows as a banner at the top of this page (and a pop-up if you allow it) <strong>only while this page is open</strong>. It also arrives by email, but only if the host set up email and gave Huddle your address. Nothing is sent to a speaker.</p>
      <fieldset className="chips">
        <legend>Remind me</legend>
        <button type="button" className="chip" aria-pressed={reminders.kinds.includes("starting_soon")} onClick={() => void toggle("starting_soon")}>When something starts soon</button>
        <button type="button" className="chip" aria-pressed={reminders.kinds.includes("digest")} onClick={() => void toggle("digest")}>A week-ahead note on Sunday evening</button>
      </fieldset>
      <div className="row">
        <label>Quiet from<input type="time" value={start} onChange={(e) => setStart(e.target.value)} /></label>
        <label>until<input type="time" value={end} onChange={(e) => setEnd(e.target.value)} /></label>
        <button className="ghost" onClick={() => void save({ quiet_start: start, quiet_end: end })}>Set quiet hours</button>
        <button className="ghost" disabled={!reminders.quiet_start} onClick={() => void save({ quiet_start: null, quiet_end: null })}>No quiet hours</button>
      </div>
      {reminders.kinds.includes("starting_soon") && perm === "default" && (
        <p className="fine"><button className="ghost" onClick={onAllow}>Notify me on this device</button> Get a pop-up too, while this page is open in a tab.</p>
      )}
      {reminders.kinds.includes("starting_soon") && perm === "denied" && <p className="fine">Pop-ups are blocked for this site in your browser; the banner still shows.</p>}
      {reminders.quiet_start && <p className="fine">Quiet from {reminders.quiet_start} until {reminders.quiet_end}.</p>}
      <p className="fine">Your times are floating, so Huddle uses your browser's clock to work out "soon" (UTC{offset >= 0 ? "+" : ""}{offset / 60}).</p>
      {saved && <p className="banner note" role="status">Saved.</p>}
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
function Rules({ token, rules, onChanged }: { token: string; rules: TimeRules; onChanged: () => void }) {
  const [rank, setRank] = useState<Circle[]>(rules.circle_rank);
  const [evenings, setEvenings] = useState<string>(rules.max_evenings == null ? "" : String(rules.max_evenings));
  const [days, setDays] = useState<number[]>([]);
  const [from, setFrom] = useState("08:00");
  const [to, setTo] = useState("12:00");
  const [label, setLabel] = useState("");
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { setRank(rules.circle_rank); }, [rules.circle_rank]);

  const move = (i: number, d: number) => setRank((r) => { const n = [...r]; const j = i + d; if (j < 0 || j >= n.length) return r; [n[i], n[j]] = [n[j], n[i]]; return n; });
  async function save(extra: Record<string, unknown> = {}) {
    setError(null); setSaved(false);
    try {
      await timeApi.rules(token, { circle_rank: rank, max_evenings: evenings === "" ? null : Number(evenings), ...extra });
      setSaved(true); onChanged();
    } catch (e) { setError((e as Error).message); }
  }
  return (
    <section className="home-panel" aria-labelledby="rules-h">
      <h3 id="rules-h">Your rules</h3>
      <p className="fine">How I weigh and protect your time when things clash. Private to you.</p>
      <ol aria-label="Which circle wins a clash">
        {rank.map((c, i) => (
          <li key={c}>{circleLabel(c)}{" "}
            <button className="ghost" aria-label={`Move ${circleLabel(c)} up`} disabled={i === 0} onClick={() => move(i, -1)}>Up</button>{" "}
            <button className="ghost" aria-label={`Move ${circleLabel(c)} down`} disabled={i === rank.length - 1} onClick={() => move(i, 1)}>Down</button>
          </li>
        ))}
      </ol>
      <label>Most evenings out in a week (blank for no limit)
        <input type="number" min={0} max={7} value={evenings} onChange={(e) => setEvenings(e.target.value)} />
      </label>
      {rules.protected.length > 0 && (
        <ul className="audit" aria-label="Protected times">
          {rules.protected.map((p, i) => <li key={i}>{p.days.map((d) => DAYS[d]).join(", ")} {p.start} to {p.end}{p.label ? `: ${p.label}` : ""}</li>)}
        </ul>
      )}
      <fieldset className="chips">
        <legend>Protect a time</legend>
        {DAYS.map((d, i) => <button type="button" key={d} className="chip" aria-pressed={days.includes(i)} onClick={() => setDays((x) => (x.includes(i) ? x.filter((v) => v !== i) : [...x, i]))}>{d}</button>)}
      </fieldset>
      <div className="row">
        <label>From<input type="time" value={from} onChange={(e) => setFrom(e.target.value)} /></label>
        <label>To<input type="time" value={to} onChange={(e) => setTo(e.target.value)} /></label>
        <label className="grow">Called<input value={label} maxLength={40} onChange={(e) => setLabel(e.target.value)} /></label>
      </div>
      <div className="row">
        <button className="primary" onClick={() => void save()}>Save rules</button>
        <button className="ghost" disabled={days.length === 0} onClick={() => void save({ protected: [...rules.protected, { days, start: from, end: to, label }] }).then(() => setDays([]))}>Protect this time</button>
      </div>
      {saved && <p className="banner note" role="status">Saved.</p>}
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}
