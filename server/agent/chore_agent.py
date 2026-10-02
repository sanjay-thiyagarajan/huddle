"""The household chore agent: understands plain words about chores.

* `parse_chore` turns "clean the gutters by Saturday, about an hour" into a structured chore: title,
  category, minutes, recurrence, due date, how heavy it is, whether it takes two people, and whether it is
  mental load (planning, booking, remembering). Anything it had to guess is reported, so nothing is silent.
* `interpret` routes what someone says ("what's on my plate", "I did the bins", "who has the laundry") to
  an intent. The service performs it and replies in words that never reveal anyone's private preferences.

In HUDDLE_MODE=mock both are deterministic (no credentials). In aws mode `parse_chore_engine` asks a
Strands agent on Bedrock first and falls back to the deterministic parser, saying so.
"""

import re
import time
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from .. import config
from ..engine import chores as ch
from . import huddle_agent, prompts

_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]

_LEAD = re.compile(
    r"^\s*(?:please\s+)?(?:add(?:\s+a)?(?:\s+new)?(?:\s+chore)?|new chore|chore|remind us(?:\s+to)?|"
    r"we (?:need|have) to|we should|someone (?:needs to|has to|should)|can (?:someone|somebody)|"
    r"somebody (?:needs to|has to|should)|i need someone to)\s*[:,-]?\s*",
    re.I,
)

_CATEGORY_WORDS = [  # first match wins, so the more specific kinds come first
    ("dishes", r"dish|washing[- ]up|dishwasher"),
    ("laundry", r"laundry|wash(?:ing)? (?:the )?clothes|ironing|\biron\b|fold"),
    ("cooking", r"cook|dinner|lunch|breakfast|meal prep|\bbake|baking"),
    ("pets", r"\bdog\b|\bcat\b|\bpet\b|litter|walk the|feed the"),
    ("yard", r"garden|lawn|\bmow|\byard\b|gutter|\bweed|hedge|\bleaves\b"),
    ("repairs", r"\bfix\b|repair|replace|install|assemble|plumb|\bleak|\bpaint|bulb|\bbike\b"),
    ("kids", r"school|\bkids?\b|children|homework|bath ?time|pick ?up|drop ?off|childcare|nappy|diaper"),
    ("shopping", r"grocer|shopping|supermarket|\bbuy\b|\bshop\b"),
    (
        "planning",
        r"\bplan\b|\bbook\b|schedule|organi[sz]e|appointment|\bcall\b|research|arrange|reservation|remind",
    ),
    ("admin", r"\bbill|\btax|insurance|paperwork|\bform\b|renew|passport|\bbank|council|rent\b"),
    ("cleaning", r"clean|\bmop|vacuum|hoover|bathroom|toilet|scrub|\bdust"),
    ("tidying", r"tidy|declutter|\bbins?\b|trash|rubbish|garbage|recycl|take out"),
]
_HEAVY = re.compile(
    r"deep[- ]clean|garage|\bmove\b|haul|heavy|whole house|spring[- ]clean|\bpaint|attic|basement", re.I
)
_LIGHT = re.compile(r"\bquick\b|\bsmall\b|\blittle\b|\bjust\b", re.I)
_TWO = re.compile(
    r"two people|2 people|together|both of us|with (?:someone|somebody|a hand)|needs? two|\bhelp lifting",
    re.I,
)
_MENTAL = re.compile(
    r"remember|\bplan\b|\bbook\b|organi[sz]e|\bcall\b|schedule|research|arrange|appointment", re.I
)


class ChoreParse(BaseModel):
    """What the Bedrock agent returns (validated before use)."""

    title: str = Field(min_length=1, max_length=80)
    category: Literal[tuple(ch.CATEGORIES)] = "other"  # type: ignore[valid-type]
    minutes: int | None = Field(default=None, ge=5, le=480)
    cadence: Literal["once", "daily", "weekly", "biweekly", "monthly"] = "once"
    due: str | None = None
    heaviness: int | None = Field(default=None, ge=1, le=3)
    people_needed: int | None = Field(default=None, ge=1, le=3)
    mental: bool | None = None


# ---- understanding a chore --------------------------------------------------------------------------------------


def _duration(text: str) -> tuple[int | None, str]:
    """(minutes, text without the duration phrase)."""
    t = text
    for pat, mins in (
        (r"half an? hour", 30),
        (r"(?:a )?quarter of an hour", 15),
        (r"(?:about |around )?an hour", 60),
        (r"(?:about |around )?(?:a )?couple of hours", 120),
    ):
        m = re.search(pat, t, re.I)
        if m:
            return mins, (t[: m.start()] + t[m.end() :])
    m = re.search(
        rf"(?:about |around |roughly )?{huddle_agent._NUMBER}\s*(minutes?|mins?|hours?|hrs?|h)\b", t, re.I
    )
    if m:
        n = huddle_agent._num(m.group(1))
        if n:
            mins = int(round(n * (60 if m.group(2).lower().startswith("h") else 1)))
            return mins, (t[: m.start()] + t[m.end() :])
    return None, t


def _cadence(text: str) -> tuple[str, str]:
    for pat, cad in (
        (r"every other week|fortnightly|bi-?weekly|every two weeks", "biweekly"),
        (r"every ?day|daily|each day", "daily"),
        (r"every month|monthly|each month|once a month", "monthly"),
        (
            r"every (?:week|monday|tuesday|wednesday|thursday|friday|saturday|sunday)|weekly|each week|"
            r"once a week",
            "weekly",
        ),
    ):
        m = re.search(pat, text, re.I)
        if m:
            return cad, (text[: m.start()] + text[m.end() :])
    return "once", text


def _due(text: str, today: date) -> tuple[str | None, str]:
    t = text
    m = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", t)
    if m:
        return m.group(1), t[: m.start()] + t[m.end() :]
    m = re.search(
        rf"\b(?:by|before|on|until)?\s*({'|'.join(_MONTHS)})[a-z]*\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b",
        t,
        re.I,
    )
    if m:
        month, day = _MONTHS.index(m.group(1).lower()[:3]) + 1, int(m.group(2))
        year = today.year if (month, day) >= (today.month, today.day) else today.year + 1
        try:
            return date(year, month, day).isoformat(), t[: m.start()] + t[m.end() :]
        except ValueError:
            pass
    for pat, resolve in (
        (r"\b(?:by |before |for )?today\b", lambda: today),
        (r"\b(?:by |before |for )?tomorrow\b", lambda: today + timedelta(days=1)),
        (
            r"\b(?:by |before |on |for )?(?:this |the )?weekend\b",
            lambda: today + timedelta(days=(5 - today.weekday()) % 7),
        ),
        (
            r"\b(?:by |before |for )?next week\b",
            lambda: today + timedelta(days=(4 - today.weekday()) % 7 + 7),
        ),
    ):
        m = re.search(pat, t, re.I)
        if m:
            return resolve().isoformat(), t[: m.start()] + t[m.end() :]
    m = re.search(rf"\b(?:by|before|on|until|this|next)\s+({'|'.join(_WEEKDAYS)})\b", t, re.I)
    if m:
        target = _WEEKDAYS.index(m.group(1).lower())
        ahead = (target - today.weekday()) % 7
        if m.group(0).lower().startswith("next") and ahead == 0:
            ahead = 7
        return (today + timedelta(days=ahead)).isoformat(), t[: m.start()] + t[m.end() :]
    return None, t


def parse_chore(text: str, today: date) -> dict:
    """Plain words to a chore. Returns {fields, assumed, questions}; `assumed` lists what was guessed."""
    raw = text.strip()
    body = _LEAD.sub("", raw)
    minutes, body = _duration(body)
    cadence, body = _cadence(body)
    due, body = _due(body, today)
    title = body.strip(" ,.;:-!?")
    trailing = re.compile(
        r"\s+(?:for|in|at|about|around|roughly|by|before|on|until|every|each|and|please|thanks)$", re.I
    )
    while trailing.search(title):
        title = trailing.sub("", title).strip(" ,.;:-!?")
    title = re.sub(r"\s+", " ", title)
    title = title[:1].upper() + title[1:] if title else ""
    category = next((c for c, pat in _CATEGORY_WORDS if re.search(pat, raw, re.I)), "other")
    heaviness = 3 if _HEAVY.search(raw) else 1 if _LIGHT.search(raw) else None
    people = 2 if _TWO.search(raw) else None
    fields: dict = {"title": title, "category": category, "cadence": cadence}
    assumed: list[str] = []
    if minutes is not None:
        fields["minutes"] = minutes
    else:
        assumed.append(f"about {ch.DEFAULT_MINUTES[category]} minutes")
    if due:
        fields["due"] = due
    if heaviness:
        fields["heaviness"] = heaviness
    if people:
        fields["people_needed"] = people
    if _MENTAL.search(raw) or category in ch.MENTAL_CATEGORIES:
        fields["mental"] = True
    if category == "other":
        assumed.append("the kind of chore")
    questions = []
    if not title:
        questions.append("What's the chore?")
    return {"fields": fields, "assumed": assumed, "questions": questions}


def parse_chore_engine(text: str, today: date) -> dict:
    """Parse with Bedrock in aws mode (validated), otherwise or on any failure with the built-in parser."""
    start = time.perf_counter()
    out, engine, error = None, "mock", None
    if config.MODE == "aws":
        try:
            agent = huddle_agent._make_agent(prompts.CHORE_SYSTEM)
            got = huddle_agent._structured(
                agent, f"Today is {today.isoformat()}. The household said: {text}", ChoreParse
            )
            fields = {k: v for k, v in got.model_dump().items() if v is not None}
            out = {
                "fields": fields,
                "assumed": [] if fields.get("minutes") else ["the time it takes"],
                "questions": [],
            }
            engine = "bedrock"
        except Exception as e:  # noqa: BLE001  any Bedrock failure falls back to the built-in parser
            error = f"{type(e).__name__}: {e}"[:200]
            engine = "mock-fallback"
    if out is None:
        out = parse_chore(text, today)
    out = {**out, "engine": engine, "latency_ms": round((time.perf_counter() - start) * 1000)}
    if error:
        out["engine_error"] = error
    return out


# ---- what someone says ------------------------------------------------------------------------------------------

_ADD = re.compile(
    r"^\s*(?:please\s+)?(?:add\b|new chore|chore\s*:|remind us|we (?:need|have) to|we should|"
    r"someone (?:needs to|has to|should)|can (?:someone|somebody)|somebody (?:needs to|has to|should)|"
    r"i need someone to)",
    re.I,
)
_MINE = re.compile(
    r"what'?s on my plate|my chores|what do i (?:have|need) to do|my week|what am i (?:doing|on)|"
    r"what'?s (?:left|on) for me|my list",
    re.I,
)
_DONE = re.compile(
    r"\b(?:i(?:'ve| have)?|we(?:'ve| have)?)\s*(?:just\s*)?(?:did|done|finished|completed)\b|"
    r"\bmark\b.*\bdone\b|\b(?:is|are)\s+done\b|\bdone with\b",
    re.I,
)
_WHO = re.compile(r"\bwho(?:'s| is| has| does| owns| is doing| does the)?\b", re.I)
_BACK = re.compile(
    r"hand (?:it |that |the )?back|give (?:it |that |the )?back|can'?t do|cannot do|pass on|swap out", re.I
)
_PLAN = re.compile(
    r"what'?s the plan|who does what|this week'?s plan|how'?s the split|is (?:it|the split) fair", re.I
)
_MAKE_PLAN = re.compile(r"\bplan (?:the|this|our) week\b|make (?:the|a) plan", re.I)
_ACCEPT = re.compile(r"\b(?:accept|i'?ll take it|i can take it|yes,? (?:i|please)|sure,? i'?ll)\b", re.I)
_DECLINE = re.compile(
    r"\b(?:decline|i can'?t take it|no,? (?:thanks|i can'?t)|pass(?: on it)?|not this time)\b", re.I
)

_STOP = {
    "the",
    "a",
    "an",
    "my",
    "our",
    "i",
    "did",
    "done",
    "finished",
    "completed",
    "have",
    "ive",
    "just",
    "with",
    "mark",
    "as",
    "who",
    "is",
    "has",
    "does",
    "doing",
    "hand",
    "back",
    "give",
    "it",
    "that",
    "can",
    "cant",
    "cannot",
    "do",
    "pass",
    "on",
    "swap",
    "out",
    "of",
    "to",
    "for",
    "please",
    "whos",
}


def interpret(text: str) -> dict:
    """{intent, target}: what the person wants. `target` is the rest of the sentence for matching a chore."""
    t = text.strip()
    if _ADD.search(t):
        return {"intent": "add", "target": t}
    if _MAKE_PLAN.search(t):
        return {"intent": "make_plan", "target": ""}
    if _PLAN.search(t):
        return {"intent": "plan", "target": ""}
    if _MINE.search(t):
        return {"intent": "mine", "target": ""}
    if _BACK.search(t):
        return {"intent": "handback", "target": t}
    if _DONE.search(t):
        return {"intent": "done", "target": t}
    if _WHO.search(t) and re.search(r"\bwho\b", t, re.I):
        return {"intent": "who", "target": t}
    if _DECLINE.search(t):
        return {"intent": "decline", "target": ""}
    if _ACCEPT.search(t):
        return {"intent": "accept", "target": ""}
    return {"intent": "unknown", "target": t}


def _variants(word: str) -> set[str]:
    """Spellings a word may take: dishes -> dish, bins -> bin, bikes -> bike."""
    out = {word, word.rstrip("s")}
    if word.endswith("es") and len(word) > 4:
        out.add(word[:-2])
    if word.endswith("ies"):
        out.add(word[:-3] + "y")
    return out


def best_match(target: str, titles: list[str]) -> int | None:
    """Index of the chore title that shares the most words with what was said, or None."""
    words = [w for w in re.findall(r"[a-z]+", target.lower()) if w not in _STOP and len(w) > 2]
    best, score = None, 0
    for i, title in enumerate(titles):
        tw = [_variants(w) for w in re.findall(r"[a-z]+", title.lower()) if len(w) > 2]
        s = sum(1 for w in words if any(_variants(w) & v for v in tw))
        if s > score:
            best, score = i, s
    return best
