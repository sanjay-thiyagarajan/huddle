import { useState } from "react";
import { inviteText, shareOrCopy } from "../share";
import HomeView from "./HomeView";
import { homeApi } from "./homeApi";
import type { HomeMember } from "./homeApi";

const KEY = "huddle-household-v1";
const load = (): { name: string; members: HomeMember[] } | null => {
  try { return JSON.parse(localStorage.getItem(KEY) ?? "null"); } catch { return null; }
};
const store = (v: unknown) => { try { v ? localStorage.setItem(KEY, JSON.stringify(v)) : localStorage.removeItem(KEY); } catch { /* storage unavailable */ } };

const STARTER = [
  "add do the dishes every day, 10 minutes", "add do the laundry every week, 40 minutes",
  "add take out the bins every week, 10 minutes", "add cook dinners every week, 90 minutes",
  "add plan the meals every week, 30 minutes", "add pay the bills every week, 30 minutes",
  "add clean the bathroom every week, 45 minutes",
];

/** The household on a shared device: set it up, then switch between members' private panels. */
export default function HomeApp() {
  const [home, setHome] = useState(load);
  const [active, setActive] = useState(() => load()?.members[0]?.name ?? "");
  const [name, setName] = useState("Our home");
  const [people, setPeople] = useState([{ name: "Maya", email: "" }, { name: "Ben", email: "" }, { name: "Chen", email: "" }]);
  const [error, setError] = useState<string | null>(null);
  const [shareMsg, setShareMsg] = useState<string | null>(null);
  const [seeding, setSeeding] = useState(false);

  async function create(e: React.FormEvent) {
    e.preventDefault(); setError(null);
    try {
      const out = await homeApi.create(name, people.filter((p) => p.name.trim()).map((p) => ({ name: p.name, email: p.email.trim() || undefined })));
      const v = { name: out.name, members: out.members };
      store(v); setHome(v); setActive(out.members[0].name);
    } catch (er) { setError((er as Error).message); }
  }
  async function seed(token: string) {
    setSeeding(true);
    try { for (const text of STARTER) await homeApi.addChore(token, { text }); } catch (e) { setError((e as Error).message); }
    setSeeding(false);
  }

  if (!home) {
    return (
      <main className="home-setup">
        <h1>Share the household load</h1>
        <p className="lede">Housework is a stream of small decisions, and it's easy for one person to end up doing most of it. Everyone tells Huddle privately what they can take on and what they'd rather not. The agent splits the chores fairly, week after week, and never says who set which limit.</p>
        <form onSubmit={(e) => void create(e)}>
          <label>Household name<input value={name} onChange={(e) => setName(e.target.value)} /></label>
          <fieldset className="people">
            <legend>Who lives here (2 to 6 adults)</legend>
            {people.map((p, i) => (
              <div className="person-row" key={i}>
                <input aria-label={`Name ${i + 1}`} value={p.name} onChange={(e) => setPeople(people.map((q, j) => (j === i ? { ...q, name: e.target.value } : q)))} />
                <input className="email-input" type="email" aria-label={`Email for reminders for ${p.name || "this person"} (optional)`}
                  placeholder="Email for reminders (optional, only if they agreed)" value={p.email}
                  onChange={(e) => setPeople(people.map((q, j) => (j === i ? { ...q, email: e.target.value } : q)))} />
              </div>
            ))}
            {people.length < 6 && <button type="button" className="ghost" onClick={() => setPeople([...people, { name: "", email: "" }])}>Add a person</button>}
          </fieldset>
          {error && <p className="error" role="alert">{error}</p>}
          <button className="primary" disabled={people.filter((p) => p.name.trim()).length < 2}>Create the household</button>
        </form>
      </main>
    );
  }

  const me = home.members.find((m) => m.name === active) ?? home.members[0];
  return (
    <main className="home-app">
      <header className="home-head">
        <h1>{home.name}</h1>
        <div className="recognized" role="group" aria-label="Whose private panels to show">
          <div className="modes">
            {home.members.map((m) => (
              <button key={m.name} className="chip" aria-pressed={m.name === me.name} onClick={() => setActive(m.name)}>{m.name}{m.is_admin ? " (admin)" : ""}</button>
            ))}
          </div>
        </div>
        <div className="row">
          <button className="ghost" onClick={() => void shareOrCopy({ title: "Huddle", text: inviteText(me.name), url: window.location.origin + me.link })
            .then((r) => setShareMsg(r === "failed" ? "Couldn't open sharing." : r === "copied" ? `${me.name}'s private link copied.` : "Link ready to send."))}>
            Share {me.name}'s private link
          </button>
          <button className="ghost" disabled={seeding} onClick={() => void seed(home.members[0].token)}>{seeding ? "Adding" : "Add a starter set of chores"}</button>
          <button className="ghost" onClick={() => { store(null); setHome(null); }}>Forget this household on this device</button>
        </div>
        {shareMsg && <p className="fine" role="status">{shareMsg}</p>}
        {error && <p className="error" role="alert">{error}</p>}
      </header>
      <HomeView key={me.token} token={me.token} sharedScreen />
    </main>
  );
}
