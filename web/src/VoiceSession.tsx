import { useEffect, useRef, useState } from "react";
import { api, listen, speechSupported } from "./api";
import type { VoiceTurn } from "./api";

/**
 * Voice-only answering, as it would work on a screenless speaker. The screen shows captions of what the
 * ASSISTANT says, never what the person says, and the assistant never says their answer back unless they
 * ask. If anyone is nearby it offers the phone link or the screen instead.
 */
export default function VoiceSession({ token, name, onSaved, onHandoff }: {
  token: string; name: string; onSaved: () => void; onHandoff: (kind: "link" | "screen") => void;
}) {
  const [sid, setSid] = useState<string | null>(null);
  const [lines, setLines] = useState<{ text: string; warn: boolean }[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [listening, setListening] = useState(false);
  const [speakAloud, setSpeakAloud] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const stop = useRef<(() => void) | null>(null);

  useEffect(() => { // a new person at the device starts a new session
    setSid(null); setLines([]); setInput(""); setDone(false); setError(null);
    return () => { window.speechSynthesis?.cancel(); };
  }, [token]);

  function say(turn: VoiceTurn) {
    setLines((l) => [...l, { text: turn.say, warn: turn.spoke_values }]);
    if (speakAloud && "speechSynthesis" in window) window.speechSynthesis.speak(new SpeechSynthesisUtterance(turn.say));
  }

  async function send(utterance: string | null) {
    setBusy(true); setError(null);
    try {
      const turn = await api.turn(token, sid, utterance ?? "");
      setSid(turn.session_id);
      say(turn);
      if (turn.done) {
        setDone(true);
        if (turn.saved) onSaved();
        if (turn.handoff) onHandoff(turn.handoff);
      }
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  function submitText() {
    const text = input.trim();
    if (!text) return;
    setInput(""); // what the person says is never shown back
    void send(text);
  }
  function mic() {
    if (listening) { stop.current?.(); return; }
    window.speechSynthesis?.cancel();
    setListening(true);
    let heard = "";
    stop.current = listen((t) => { heard = t; }, () => { setListening(false); if (heard.trim()) void send(heard.trim()); });
  }

  return (
    <section className="voice-only" aria-label={`Voice-only answer for ${name}`}>
      <p className="fine">Voice-only mode: this works like a speaker with no screen. The captions show only what the assistant says. What you say isn't shown, and your answer is never read back unless you ask.</p>
      <div className="captions" role="log" aria-live="polite" aria-label="What the assistant says">
        {lines.length === 0 && <p className="fine">Press Start to begin.</p>}
        {lines.map((l, i) => <p key={i} className={l.warn ? "caption warn" : "caption"}>{l.text}</p>)}
      </div>
      {!sid ? (
        <button className="primary" disabled={busy} onClick={() => void send(null)}>Start voice session for {name}</button>
      ) : !done ? (
        <div className="say-row">
          <label>Say it (typed here as a stand-in for speaking)
            <input value={input} autoComplete="off" onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") submitText(); }} />
          </label>
          <div className="row">
            <button className="ghost" disabled={busy || !input.trim()} onClick={submitText}>Send</button>
            {speechSupported() && <button className="ghost" aria-pressed={listening} disabled={busy} onClick={mic}>{listening ? "Stop listening" : "Speak"}</button>}
          </div>
        </div>
      ) : (
        <button className="ghost" onClick={() => { setSid(null); setLines([]); setDone(false); }}>Start again</button>
      )}
      <label className="consent">
        <input type="checkbox" checked={speakAloud} onChange={(e) => { setSpeakAloud(e.target.checked); window.speechSynthesis?.cancel(); }} />
        <span>Speak the replies aloud</span>
      </label>
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}
