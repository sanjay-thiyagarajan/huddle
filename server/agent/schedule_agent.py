"""Plain-words scheduling: understand 'dinner with Priya Thursday 7pm for 2 hours' and the person's replies
when something clashes. Deterministic (works with no AWS credentials); nothing here calls a model."""

import re
from datetime import date, timedelta

_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]

_CIRCLES = [  # first match wins
    (
        "work",
        r"\b(meeting|standup|stand-up|client|colleague|coworker|office|boss|work|interview|deadline|1:1|review)\b",
    ),
    (
        "family",
        r"\b(mom|mum|dad|kids?|son|daughter|school|family|grandma|grandpa|grandparents?|sister|brother|"
        r"cousin|aunt|uncle|parent|pta|recital|concert)\b",
    ),
    (
        "friends",
        r"\b(friends?|dinner|drinks?|party|movie|game night|brunch|lunch|coffee|catch up|hangout|beer|"
        r"birthday|wedding|with)\b",
    ),
]
_FIXED = re.compile(r"\b(can'?t move|cannot move|fixed|must|have to|non-?negotiable)\b", re.I)
_OPTIONAL = re.compile(r"\b(if i can|maybe|optional|if there'?s time|might)\b", re.I)
_IMPORTANT = re.compile(r"\b(important|really matters|big deal|key)\b", re.I)
_UNIMPORTANT = re.compile(r"\b(whenever|not important|no rush|casual)\b", re.I)

_TIME = re.compile(r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)", re.I)
_TIME24 = re.compile(r"\b(?:at\s+)?([01]?\d|2[0-3]):([0-5]\d)\b")
_AT = re.compile(r"\bat\s+(\d{1,2})\b(?!\s*(?:min|hour|hr))", re.I)
_PART = {
    "morning": 9,
    "noon": 12,
    "lunchtime": 12,
    "afternoon": 15,
    "evening": 18,
    "tonight": 19,
    "night": 20,
}
_DUR = re.compile(
    r"\bfor\s+(?:about\s+)?(\d+(?:\.\d+)?|an?|half an)\s*(hours?|hrs?|h|minutes?|mins?)\b", re.I
)
_DUR2 = re.compile(r"\b(\d+)\s*(hours?|hrs?|minutes?|mins?)\b", re.I)


def _day(text: str, today: date) -> date | None:
    low = text.lower()
    m = re.search(r"\b(20\d\d)-(\d\d)-(\d\d)\b", low)
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
    if re.search(r"\b(today|tonight)\b", low):
        return today
    if "tomorrow" in low:
        return today + timedelta(days=1)
    for i, name in enumerate(_WEEKDAYS):
        if re.search(rf"\b(?:next\s+|this\s+|on\s+)?{name}\b|\b{name[:3]}\b", low):
            ahead = (i - today.weekday()) % 7
            if "next " + name in low and ahead < 7:
                ahead += 7 if ahead else 7
            return today + timedelta(days=ahead)
    m = re.search(rf"\b({'|'.join(_MONTHS)})[a-z]*\.?\s+(\d{{1,2}})\b", low)
    if m:
        month, d = _MONTHS.index(m[1]) + 1, int(m[2])
        for year in (today.year, today.year + 1):
            try:
                cand = date(year, month, d)
            except ValueError:
                return None
            if cand >= today:
                return cand
    return None


def _time(text: str) -> tuple[int, int] | None:
    m = _TIME.search(text)
    if m:
        h, mi, ap = int(m[1]), int(m[2] or 0), m[3].lower()[0]
        if not 1 <= h <= 12:
            return None
        return (h % 12) + (12 if ap == "p" else 0), mi
    m = _TIME24.search(text)
    if m:
        return int(m[1]), int(m[2])
    low = text.lower()
    for word, h in _PART.items():
        if re.search(rf"\b{word}\b", low):
            return h, 0
    m = _AT.search(text)
    if m and 1 <= int(m[1]) <= 12:  # 'at 7' with no am/pm: assume the likelier daytime reading
        h = int(m[1])
        return (h if 7 <= h <= 11 else (h % 12) + 12), 0
    return None


def _minutes(text: str) -> int | None:
    m = _DUR.search(text) or _DUR2.search(text)
    if not m:
        return None
    q = m[1].lower()
    n = 0.5 if q.startswith("half") else 1.0 if q in ("a", "an") else float(q)
    return round(n * (60 if m[2].lower().startswith(("h")) else 1))


def _repeat(text: str) -> str:
    low = text.lower()
    if re.search(r"\b(every day|daily|each day)\b", low):
        return "daily"
    if re.search(r"\b(every week|weekly|each week|every (?:" + "|".join(_WEEKDAYS) + r"))\b", low):
        return "weekly"
    return "none"


def _title(text: str) -> str:
    t = re.sub(
        r"^\s*(?:please\s+)?(?:add|put|schedule|book|set up|i have|i've got|i have got|i'm|im)\s+",
        "",
        text,
        flags=re.I,
    )
    t = re.sub(r"\b(?:every|each)\s+(?:day|week|" + "|".join(_WEEKDAYS) + r")\b", " ", t, flags=re.I)
    t = _DUR.sub(" ", t)
    t = _TIME.sub(" ", t)
    t = _TIME24.sub(" ", t)
    t = _AT.sub(" ", t)
    t = re.sub(r"\b(?:on|this|next)\s+(?=" + "|".join(_WEEKDAYS) + r")", " ", t, flags=re.I)
    t = re.sub(
        r"\b(?:"
        + "|".join(_WEEKDAYS)
        + r"|today|tomorrow|tonight|morning|afternoon|evening|noon|weekly|daily)\b",
        " ",
        t,
        flags=re.I,
    )
    t = re.sub(r"\b20\d\d-\d\d-\d\d\b", " ", t)
    t = re.sub(rf"\b(?:{'|'.join(_MONTHS)})[a-z]*\.?\s+\d{{1,2}}\b", " ", t, flags=re.I)
    t = re.sub(r"\b(?:can'?t move|cannot move|fixed|if i can|optional|important)\b", " ", t, flags=re.I)
    t = re.sub(r"\b(?:at|on|for|from|in|to)\s*$", "", re.sub(r"\s+", " ", t).strip(" ,.;"), flags=re.I)
    t = re.sub(r"\s+(?:at|on|for)\b(?=\s|$)", "", t, flags=re.I).strip(" ,.;")
    return t[:80]


def circle_of(text: str) -> str:
    for name, pat in _CIRCLES:
        if re.search(pat, text, re.I):
            return name
    return "personal"


def parse_commitment(text: str, today: date) -> dict:
    """Returns {fields, assumed[], questions[]}. Missing day or time becomes a question, not a guess."""
    day, tm = _day(text, today), _time(text)
    minutes = _minutes(text)
    fields = {"title": _title(text) or "Something", "circle": circle_of(text), "repeat": _repeat(text)}
    if _FIXED.search(text):
        fields["flexibility"] = "fixed"
    elif _OPTIONAL.search(text):
        fields["flexibility"] = "optional"
    if _IMPORTANT.search(text):
        fields["importance"] = 3
    elif _UNIMPORTANT.search(text):
        fields["importance"] = 1
    assumed, questions = [], []
    if fields["repeat"] != "none" and day is None:
        day = today  # 'every Monday' anchors on the next Monday
        for i, name in enumerate(_WEEKDAYS):
            if name in text.lower():
                day = today + timedelta(days=(i - today.weekday()) % 7)
    if day is None:
        questions.append("Which day?")
    if tm is None:
        questions.append("What time does it start?")
    if minutes is None:
        minutes = 60
        assumed.append("about an hour")
    fields["minutes"] = minutes
    if not questions:
        fields["start"] = f"{day.isoformat()}T{tm[0]:02d}:{tm[1]:02d}"
    return {"fields": fields, "assumed": assumed, "questions": questions}


# ---- what the person means ------------------------------------------------------------------------------------------

_WEEK = re.compile(
    r"\b(what'?s|what is|show|how'?s|how is)\b.*\b(my|the)\b.*\b(week|day|schedule|calendar|today|tomorrow)\b|\bmy (week|schedule)\b",
    re.I,
)
_FREE = re.compile(r"\bwhen (am i|are we|can i)\b.*\b(free|available)\b|\bfree time\b", re.I)
_CANCEL = re.compile(r"\b(cancel|remove|delete|drop|scrap)\b\s+(?:my\s+|the\s+)?(.+)", re.I)
_FIND = re.compile(
    r"\b(find|pick|suggest|work out|arrange)\s+(?:a\s+)?(?:time|day|slot|date)\b|\bwhen (?:should|can) we\b",
    re.I,
)
_RULES = re.compile(r"\b(always|never|protect|keep .* free|no more than|at most)\b", re.I)

REPLIES = [  # (choice, pattern), most specific first
    ("keep_both", r"\b(both|double[- ]?book|keep (?:them )?both)\b"),
    (
        "ask_others",
        r"\bask (?:them|the others|everyone|him|her|the group|people)\b|\bfind another time with\b",
    ),
    ("decide_later", r"\b(later|not sure|undecided|hold on|think about it|leave it)\b"),
    (
        "move_existing",
        r"\bmove (?:the )?(?:other|existing|old|first one)\b|\bmove (?!it\b|the new\b|new\b|this\b).+",
    ),
    ("drop_existing", r"\b(drop|cancel|skip) (?:the )?(?:other|existing|old)\b|\bcancel .* instead\b"),
    ("drop_new", r"\b(skip|drop|cancel|forget|never mind|nevermind|no thanks|pass)\b"),
    (
        "move_new",
        r"\b(move|shift|reschedule|change)\b(?: it| the new| this)?\b|\banother time\b|\bdifferent time\b",
    ),
    (
        "recommended",
        r"^\s*(yes|yeah|yep|ok|okay|sure|do that|go ahead|sounds good|that works|go with that|please)\b",
    ),
]


def reply_choice(text: str) -> str | None:
    low = text.lower()
    for choice, pat in REPLIES:
        if re.search(pat, low):
            return choice
    m = re.search(r"\b(?:option\s*)?(1|2|3|first|second|third|one|two|three)\b", low)
    return f"option:{m[1]}" if m else None


def interpret(text: str) -> dict:
    """The person's intent when nothing is waiting on an answer."""
    if _FIND.search(text):
        return {"intent": "find"}
    if _FREE.search(text):
        return {"intent": "free"}
    if _WEEK.search(text):
        return {"intent": "week"}
    m = _CANCEL.match(text.strip())
    if m:
        return {"intent": "cancel", "target": m[2].strip(" .")}
    if _RULES.search(text) and not (_day(text, date.today()) or _time(text)):
        return {"intent": "rule"}
    return {"intent": "add"}
