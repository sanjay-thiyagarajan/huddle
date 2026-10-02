"""Voice-only dialogue for collecting ONE person's private answer on a shared device (no screen).

Design rule: the assistant never says a private value aloud unless the person explicitly asks
("read it back"), because on a shared speaker anyone nearby can hear it. Stages:

    privacy  -> is anyone close enough to hear? offer a phone link or the screen instead
    consent  -> adults only, answer stays private
    collect  -> ask for what's missing, one question at a time (never repeating what was said)
    confirm  -> "save it" / "change it" / "read it back" (opt-in)

The draft lives only in this server-side object. Callers receive `say` text and a stage, never the draft.
`submit` (the answer to store) is returned separately for the server to send through the MCP tool.
"""
import re
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field

TTL_SECONDS = 900
MAX_MISUNDERSTOOD = 3

_REQUIRED = {"care": ("hours_per_week", "dollars_per_month"), "everyday": ("budget_ceiling",),
             "trip": ("budget_ceiling",)}
_LIST_FIELDS = ("vibe", "must_haves", "dealbreakers")

_CANCEL = re.compile(r"\b(cancel|stop|never ?mind|forget it)\b", re.I)
_LINK = re.compile(r"\b(link|phone|text me|send me)\b", re.I)
_SCREEN = re.compile(r"\bscreen\b", re.I)
_NEARBY = re.compile(r"\b(someone|somebody|people|everyone|they)\b.*\b(here|there|listening|coming|nearby|close)\b"
                     r"|\b(can hear|listening)\b", re.I)
_ALONE = re.compile(r"\b(just me|only me|alone|nobody|no one|no[- ]one|it'?s private|it'?s fine|"
                    r"nobody'?s (here|around|close)|go ahead|no)\b", re.I)
_YES = re.compile(r"\b(yes|yeah|yep|sure|okay|ok|i agree|i consent|agree|fine)\b", re.I)
_NO = re.compile(r"\b(no|nope|i don'?t|do not|don'?t)\b", re.I)
_SAVE = re.compile(r"\b(save( it)?|yes|that'?s right|correct|looks good|confirm|keep it)\b", re.I)
_CHANGE = re.compile(r"\b(change( it)?|redo|start over|again|wrong|no)\b", re.I)
_READBACK = re.compile(r"\b(read (it )?back|say it back|repeat( it)?)\b", re.I)

_FIRST_QUESTION = {
    "care": "Roughly how many hours a week could you give, and how many dollars a month could you put in? "
            "Tell me anything you can't do as well.",
    "everyday": "What's the most you'd comfortably spend per person? Tell me anything you'd enjoy, "
                "or can't stand, too.",
    "trip": "What's the most you'd comfortably spend for the whole trip? Tell me what you'd enjoy, "
            "or can't stand, too.",
}
_LABELS = {
    "nights": "overnight cover", "transport": "driving and transport", "appointments": "appointments",
    "finances": "finances and paperwork", "checkins": "daily check-ins", "far_away": "being far away",
}


@dataclass
class Turn:
    say: str
    stage: str  # privacy | consent | collect | confirm | saved | handoff | cancelled
    done: bool = False
    handoff: str | None = None  # "link" | "screen"
    spoke_values: bool = False  # True only for an explicit "read it back"
    submit: dict | None = field(default=None, repr=False)  # internal: for the server, never sent to clients


class DialogueSession:
    def __init__(self, mode: str, name: str, parse: Callable[[str, str], dict]):
        if mode not in _REQUIRED:
            raise ValueError(f"unknown mode {mode}")
        self.mode, self.name, self._parse = mode, name, parse
        self.stage = "privacy"
        self.draft: dict = {}
        self.misses = 0
        self.consented = False

    # -- helpers ----------------------------------------------------------------------------
    def _missing(self) -> list[str]:
        return [k for k in _REQUIRED[self.mode] if self.draft.get(k) is None]

    def _merge(self, parsed: dict) -> bool:
        """Fold a parse into the draft. True if it taught us anything."""
        learned = False
        for k, v in parsed["draft"].items():
            if k in _LIST_FIELDS:
                new = [x for x in v if x not in self.draft.get(k, [])]
                if new:
                    self.draft[k] = [*self.draft.get(k, []), *new]
                    learned = True
            elif v is not None and self.draft.get(k) != v:
                self.draft[k] = v
                learned = True
        return learned

    def _readback(self) -> str:
        d = self.draft
        if self.mode == "care":
            parts = [f"{d.get('hours_per_week'):g} hours a week", f"{d.get('dollars_per_month'):g} dollars a month"]
            if d.get("dealbreakers"):
                parts.append("you can't do " + ", ".join(_LABELS.get(x, x) for x in d["dealbreakers"]))
        else:
            parts = [f"at most {d.get('budget_ceiling'):g} dollars"]
            if d.get("vibe"):
                parts.append("you'd enjoy " + ", ".join(x.replace("_", " ") for x in d["vibe"]))
            if d.get("dealbreakers"):
                parts.append("you can't stand " + ", ".join(x.replace("_", " ") for x in d["dealbreakers"]))
        return "You said " + "; ".join(parts) + "."

    def _ask(self, prefix: str = "") -> Turn:
        self.stage = "collect"
        question = _FIRST_QUESTION[self.mode] if not self.draft else self._followup(self._missing())
        return Turn(prefix + question, "collect")

    def _followup(self, missing: list[str]) -> str:
        ask = {
            "hours_per_week": "About how many hours a week could you give?",
            "dollars_per_month": "And roughly how many dollars a month could you put in?",
            "budget_ceiling": ("What's the most you'd comfortably spend for the whole trip?"
                               if self.mode == "trip" else "What's the most you'd comfortably spend per person?"),
        }
        return ask[missing[0]]

    # -- the conversation -----------------------------------------------------------------------
    def start(self) -> Turn:
        return Turn(f"{self.name}, before we start: is anyone close enough to hear you? You can also say "
                    "send me a link to answer on your phone, or use the screen.", "privacy")

    def step(self, utterance: str) -> Turn:
        u = (utterance or "").strip()
        if not u:
            return Turn("I didn't hear anything. Say that again whenever you're ready.", self.stage)
        if _CANCEL.search(u):
            self.draft, self.stage = {}, "cancelled"
            return Turn("No problem. Nothing was saved.", "cancelled", done=True)
        if _LINK.search(u) and not (self.stage == "collect" and self._looks_like_answer(u)):
            self.draft, self.stage = {}, "handoff"
            return Turn(f"Okay, {self.name}. I'll stop here. Open your private link on your phone to answer there.",
                        "handoff", done=True, handoff="link")
        if _SCREEN.search(u):
            self.draft, self.stage = {}, "handoff"
            return Turn("Okay. Please use the screen to answer. I've deleted anything I'd heard.",
                        "handoff", done=True, handoff="screen")
        if self.stage != "privacy" and _NEARBY.search(u):  # someone walked in: stop collecting aloud
            self.stage = "privacy"
            return Turn("Okay, pausing. You can say send me a link to finish on your phone, or use the screen, "
                        "or just me if it's safe to go on here.", "privacy")
        handler = {"privacy": self._privacy, "consent": self._consent, "collect": self._collect,
                   "confirm": self._confirm}[self.stage]
        return handler(u)

    def _looks_like_answer(self, u: str) -> bool:
        return bool(re.search(r"\d|\b(hours?|dollars?|bucks|budget)\b", u, re.I))

    def _privacy(self, u: str) -> Turn:
        if _NEARBY.search(u) or (_YES.search(u) and not _NO.search(u) and not _ALONE.search(u)):
            return Turn("Okay. You can say send me a link to answer on your phone, or use the screen. "
                        "Or say just me if you'd rather go ahead here.", "privacy")
        if _ALONE.search(u):
            self.stage = "consent"
            return Turn("Thanks. This is for adults only. Your answer stays private: it's never shown to anyone "
                        "else or attributed to you. Do you agree to answer?", "consent")
        return Turn("Sorry, is anyone close enough to hear you? Say just me, send me a link, or use the screen.",
                    "privacy")

    def _consent(self, u: str) -> Turn:
        if _YES.search(u) and not _NO.search(u):
            self.consented = True
            return self._ask("Great. ")
        if _NO.search(u):
            self.stage = "cancelled"
            return Turn("No problem. Nothing was saved.", "cancelled", done=True)
        return Turn("Sorry, do you agree to answer privately? Say yes or no.", "consent")

    def _collect(self, u: str) -> Turn:
        learned = self._merge(self._parse(self.mode, u))
        if not learned:
            self.misses += 1
            if self.misses >= MAX_MISUNDERSTOOD:
                self.draft, self.stage = {}, "handoff"
                return Turn("I'm having trouble hearing that. Let's finish on your phone or the screen instead.",
                            "handoff", done=True, handoff="link")
            question = _FIRST_QUESTION[self.mode] if not self.draft else self._followup(self._missing() or [])
            return Turn("Sorry, I didn't catch that. " + question, "collect")
        self.misses = 0
        missing = self._missing()
        if missing:
            return Turn(self._followup(missing), "collect")
        self.stage = "confirm"
        return Turn(f"Thanks, {self.name}. I have what I need. Say save it to keep it, change it to start over, "
                    "or read it back if you want me to say it out loud, which anyone nearby could hear.",
                    "confirm")

    def _confirm(self, u: str) -> Turn:
        if _READBACK.search(u):
            return Turn(self._readback() + " Say save it or change it.", "confirm", spoke_values=True)
        wants_save, wants_change = bool(_SAVE.search(u)), bool(_CHANGE.search(u))
        if wants_save and not wants_change:
            answer = {**self.draft, "consent": self.consented}
            self.stage = "saved"
            return Turn(f"Saved, {self.name}. You can change it until everyone has answered.", "saved",
                        done=True, submit=answer)
        if wants_change:
            self.draft, self.misses = {}, 0
            return self._ask("Okay, starting over. ")
        return Turn("Say save it, change it, or read it back.", "confirm")


# ---- server-side session store (draft never leaves this process) ---------------------------------

@dataclass
class _Held:
    token: str
    session: DialogueSession
    created: float


_SESSIONS: dict[str, _Held] = {}


class DialogueError(Exception):
    pass


def open_session(token: str, mode: str, name: str, parse: Callable[[str, str], dict]) -> tuple[str, Turn]:
    _expire()
    sid = secrets.token_urlsafe(9)
    s = DialogueSession(mode, name, parse)
    _SESSIONS[sid] = _Held(token, s, time.monotonic())
    return sid, s.start()


def take_turn(sid: str, token: str, utterance: str) -> Turn:
    _expire()
    held = _SESSIONS.get(sid)
    if held is None:
        raise DialogueError("This voice session has expired. Start again.")
    if held.token != token:
        raise DialogueError("This voice session belongs to someone else.")
    turn = held.session.step(utterance)
    if turn.done:
        _SESSIONS.pop(sid, None)
    return turn


def _expire() -> None:
    now = time.monotonic()
    for sid in [k for k, v in _SESSIONS.items() if now - v.created > TTL_SECONDS]:
        _SESSIONS.pop(sid, None)
