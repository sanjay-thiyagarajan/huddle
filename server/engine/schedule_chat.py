"""Talk to the scheduling agent: add things in plain words, and settle clashes by conversation.

The half-finished conversation (a draft missing its time, or a clash waiting for an answer) is kept in
server memory per person, so a restart only costs them repeating their last sentence. Replies speak only
about the caller's own schedule."""

import re
from datetime import date, datetime, timedelta

from sqlmodel import Session, select

from ..agent import chore_agent as ca
from ..agent import schedule_agent as sa
from ..db import Member
from . import schedule as sc
from . import schedule_service as ss
from .rounds import HuddleError, now_utc

_PENDING: dict[str, dict] = {}
_MAX_PENDING = 500


def _aiso(x) -> str:
    return x.isoformat(timespec="minutes") if isinstance(x, datetime) else str(x)[:16]


def label(x) -> str:
    d = x if isinstance(x, datetime) else datetime.fromisoformat(str(x))
    hour = d.strftime("%I:%M %p").lstrip("0").lower()
    return f"{d.strftime('%A %b')} {d.day}, {hour}"


def _remember(member_id: str, state: dict | None) -> None:
    if state is None:
        _PENDING.pop(member_id, None)
        return
    if len(_PENDING) >= _MAX_PENDING:
        _PENDING.pop(next(iter(_PENDING)))
    _PENDING[member_id] = state


def _reply(text: str, kind: str, changed: bool = False, quick: list[str] | None = None, **extra) -> dict:
    return {"say": text, "intent": kind, "state_changed": changed, "quick_replies": quick or [], **extra}


def _clash_text(f: dict, clash: dict) -> tuple[str, list[str], list[dict]]:
    opts = clash["options"]
    lines = [
        f"'{f['title']}' at {label(f['start'])} clashes with '{clash['title']}' "
        f"({clash['circle']}, {label(clash['start'])})."
    ]
    rec = next((o for o in opts["options"] if o["key"] == opts["recommended"]), opts["options"][0])
    lines.append(f"I'd suggest: {rec['label'].lower()}. {opts['reason']}")
    shown = opts["options"][:4]
    lines.append("Your options: " + "; ".join(f"{i}. {o['label']}" for i, o in enumerate(shown, 1)) + ".")
    quick = ["Yes, do that", "Keep both", "Skip the new one"]
    if any(o["key"] == "move_new" for o in shown) and rec["key"] != "move_new":
        quick.insert(1, "Move the new one")
    return " ".join(lines), quick, shown


def _first_alt(options: list[dict], key: str, text: str, fields: dict | None) -> str | None:
    day, tm = sa._day(text, date.today()), sa._time(text)
    if tm and fields:
        base = (
            datetime.fromisoformat(fields["start"])
            if day is None
            else datetime.combine(day, datetime.min.time())
        )
        return _aiso(base.replace(hour=tm[0], minute=tm[1]))
    for o in options:
        if o["key"] == key and o.get("alternatives"):
            return _aiso(o["alternatives"][0])
    return None


def _finish(s: Session, token: str, fields: dict, resolution: dict, now: datetime, today: str | None) -> dict:
    out = ss.add_commitment(s, token, fields, resolution, now, today)
    sug = out.get("rule_suggestion")
    tail = ""
    if sug:
        tail = f" You've chosen {sug['prefer']} over {sug['over']} twice. Want that as a rule? Say 'make it a rule'."
        me = ss._auth(s, token, now)[0]
        _remember(me.id, {"kind": "rule", "suggestion": sug})
    return out | {"tail": tail}


def say(
    s: Session, token: str, utterance: str, now: datetime | None = None, today: str | None = None
) -> dict:
    now = now or now_utc()
    me, home = ss._auth(s, token, now)
    td = ss._today(now, today)
    text = (utterance or "").strip()[:300]
    if not text:
        raise HuddleError("empty", "Say something.")
    pending = _PENDING.get(me.id)

    if pending and pending["kind"] == "rule":
        _remember(me.id, None)
        if re.match(r"\s*(yes|yeah|ok|okay|sure|make it a rule|do it)", text, re.I):
            sug = pending["suggestion"]
            rank = ss.rules_view(s, me.id)["circle_rank"]
            rank = [sug["prefer"], *[c for c in rank if c != sug["prefer"]]]
            ss.set_rules(s, token, {"circle_rank": rank}, now)
            return _reply(
                f"Done. {sug['prefer'].capitalize()} now comes before {sug['over']} when things clash.",
                "rule",
                True,
            )
        pending = None

    if pending and pending["kind"] == "draft":
        _remember(me.id, None)
        merged = f"{pending['text']} {text}"
        parsed = sa.parse_commitment(merged, td)
        if sa.interpret(text)["intent"] in ("week", "free", "cancel", "find") and parsed["questions"]:
            pending = None
        else:
            return _propose(s, token, me, parsed, merged, now, today)

    if pending and pending["kind"] == "clash":
        choice = sa.reply_choice(text)
        fields, options = pending["fields"], pending["options"]
        if choice and choice.startswith("option:"):
            word = choice.split(":")[1]
            idx = {
                "1": 0,
                "one": 0,
                "first": 0,
                "2": 1,
                "two": 1,
                "second": 1,
                "3": 2,
                "three": 2,
                "third": 2,
            }[word]
            choice = options[idx]["key"] if idx < len(options) else None
        if choice == "recommended":
            choice = pending["recommended"]
        if choice is None:
            parsed = sa.parse_commitment(text, td)
            if not parsed["questions"] and sa.interpret(text)["intent"] == "add":
                _remember(me.id, None)
                return _propose(s, token, me, parsed, text, now, today)
            return _reply(
                "Tell me what you'd like: say 'yes' for my suggestion, 'keep both', 'skip the new one', or a number.",
                "clash",
                quick=["Yes, do that", "Keep both", "Skip the new one"],
            )
        res: dict = {"choice": choice}
        if choice == "move_new":
            alt = _first_alt(options, "move_new", text, fields)
            if not alt:
                return _reply("Which time should I move it to? Say something like 'Friday 7pm'.", "clash")
            res["new_start"] = alt
        elif choice == "move_existing":
            alt = _first_alt(options, "move_existing", text, None)
            if not alt:
                return _reply("I can't find a good time to move the other one to.", "clash")
            res["existing_new_start"] = alt
        _remember(me.id, None)
        out = _finish(s, token, fields, res, now, today)
        title = fields["title"]
        said = {
            "move_new": f"Moved '{title}' to {label(res.get('new_start', fields['start']))}.",
            "move_existing": f"Added '{title}' and moved the other one to {label(res.get('existing_new_start', fields['start']))}.",
            "drop_new": f"Okay, I've skipped '{title}'.",
            "drop_existing": f"Added '{title}' and cancelled the other one.",
            "keep_both": f"Kept both. '{title}' overlaps; I'll keep it on your list as a clash.",
            "decide_later": f"Added '{title}' and I'll keep the clash flagged until you decide.",
            "ask_others": f"Added '{title}'. To ask the others for another time, use Find a time.",
        }[choice]
        return _reply(said + out["tail"], "clash_resolved", out["created"], next=out.get("next"))

    intent = sa.interpret(text)
    kind = intent["intent"]
    if kind == "week":
        return _week(s, token, me, now, today)
    if kind == "free":
        return _free(s, me, td)
    if kind == "cancel":
        return _cancel(s, token, me, intent["target"], now, td)
    if kind == "find":
        return _find(s, token, home, text, now, td)
    if kind == "rule":
        return _reply("Open My time and set it under Rules, so I keep it for every week.", "rule")
    return _propose(s, token, me, sa.parse_commitment(text, td), text, now, today)


def _propose(s, token, me, parsed: dict, text: str, now: datetime, today: str | None) -> dict:
    if parsed["questions"]:
        _remember(me.id, {"kind": "draft", "text": text})
        return _reply(" ".join(parsed["questions"]), "draft")
    f = parsed["fields"]
    out = ss.add_commitment(s, token, f, None, now, today)
    guess = f" (I assumed {parsed['assumed'][0]})" if parsed["assumed"] else ""
    if out["created"]:
        c = out["commitment"]
        flags = out["analysis"]["rule_flags"] if out.get("analysis") else []
        note = f" Heads up: {flags[0]}" if flags else ""
        return _reply(
            f"Added '{c['title']}' ({c['circle']}) on {label(c['start'])}{guess}.{note}", "add", True
        )
    clash = out["analysis"]["clashes"][0]
    f = {**f, "start": f["start"]}
    said, quick, shown = _clash_text(f, clash)
    _remember(
        me.id,
        {"kind": "clash", "fields": f, "options": shown, "recommended": clash["options"]["recommended"]},
    )
    return _reply(
        said + guess, "clash", quick=quick, options=[{"key": o["key"], "label": o["label"]} for o in shown]
    )


def _week(s, token, me, now, today) -> dict:
    t = ss.get_my_time(s, token, None, now, today)
    sm = t["summary"]
    if not t["items"]:
        return _reply("Nothing on your calendar this week.", "week")
    parts = [f"{c} {round(m / 60, 1)}h" for c, m in sm["minutes_by_circle"].items() if m]
    text = f"This week: {', '.join(parts)}. About {round(sm['free_minutes'] / 60)}h free."
    if t["conflicts"]:
        text += f" {len(t['conflicts'])} clash{'es' if len(t['conflicts']) > 1 else ''} to settle."
    text += f" Evenings out: {sm['evenings_out']}."
    return _reply(text, "week")


def _free(s, me, td: date) -> dict:
    items, rules = ss._items(s, me.id), ss._rules(s, me.id)
    slots = sc.free_slots(items, rules, td, td + timedelta(days=6), 120, limit=40)
    evenings = [x for x in slots if x.hour >= 17][:3] or slots[:3]
    if not evenings:
        return _reply("I can't find a free two-hour window in the next week.", "free")
    return _reply("You're free for two hours on " + "; ".join(label(x) for x in evenings) + ".", "free")


def _cancel(s, token, me, target: str, now, td) -> dict:
    t = ss.get_my_time(s, token, None, now, str(td))
    items = t["items"]
    i = ca.best_match(target, [x["title"] for x in items]) if items else None
    if i is None:
        return _reply(f"I couldn't find '{target}' this week.", "cancel")
    ss.update_commitment(s, token, items[i]["id"], {"status": "cancelled"}, items[i]["start"][:10], now)
    return _reply(f"Cancelled '{items[i]['title']}' on {label(items[i]['start'])}.", "cancel", True)


def _find(s, token, home, text: str, now, td: date) -> dict:
    names = {m.name.lower(): m.name for m in s.exec(select(Member).where(Member.home_id == home.id))}
    after = re.split(r"\bwith\b", text, maxsplit=1, flags=re.I)
    people = [p.strip(" .") for p in re.split(r",|\band\b|&", after[1])] if len(after) > 1 else []
    members, guests = [], []
    for p in people:
        if p and p.lower() in names:
            members.append(names[p.lower()])
        elif p:
            guests.append({"name": p.title()[:40]})
    title = re.sub(
        r"(?i)\b(find|pick|suggest|work out|arrange)\b|\b(a )?(time|day|slot|date)\b|\bfor\b", " ", after[0]
    )
    title = re.sub(r"\s+", " ", title).strip(" ,.") or "Get-together"
    fields = {
        "title": title.capitalize()[:80],
        "circle": sa.circle_of(text) if sa.circle_of(text) in ("family", "friends", "work") else "friends",
        "duration_minutes": sa._minutes(text) or 120,
        "windows": [
            {
                "date_from": (td + timedelta(days=1)).isoformat(),
                "date_to": (td + timedelta(days=7)).isoformat(),
                "from": "18:00",
                "to": "22:00",
            }
        ],
        "members": [m for m in members if m.lower() != _me_name(s, token, now)],
        "guests": guests,
    }
    out = ss.start_gathering(s, token, fields, now)
    links = " Share each guest's link from the Find a time card." if out["guests"] else ""
    return _reply(
        f"I've asked {len(fields['members']) + len(guests)} people about evenings next week. "
        f"Your suggested answers are ready in My time.{links}",
        "find",
        True,
        round_id=out["round_id"],
    )


def _me_name(s: Session, token: str, now) -> str:
    return ss._auth(s, token, now)[0].name.lower()
