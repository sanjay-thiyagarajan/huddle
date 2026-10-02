"""Find a time: the same private-limits-in, one-unattributed-answer-out engine, applied to time.

Everyone sees the same candidate times. Each person privately says yes, maybe (I'd have to move something) or
no for each. Members answer from their own private schedule; guests (friends, colleagues) answer by a private
link. The group learns the time that works and how well it fits, never who was busy or why.
"""

from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from . import privacy
from . import schedule as sc

MAX_PEOPLE = 12  # a find-a-time can include a bigger circle than the other decisions
Choice = Literal["yes", "maybe", "no"]


class WhenAnswer(BaseModel):
    slots: dict[str, Choice] = Field(min_length=1, max_length=40)  # ISO start time -> answer


AnswerModel = WhenAnswer


def validate_need(need: dict | None) -> dict:
    need = need or {}
    title = str(need.get("title", "")).strip()
    if not 1 <= len(title) <= 80:
        raise ValueError("a find-a-time needs a title (up to 80 characters)")
    circle = need.get("circle", "friends")
    if circle not in ("family", "friends", "work"):
        raise ValueError("circle must be family, friends or work")
    duration = need.get("duration_minutes")
    if not isinstance(duration, int) or isinstance(duration, bool) or not 15 <= duration <= 600:
        raise ValueError("duration_minutes is 15 to 600")
    raw = need.get("slots") or []
    if not isinstance(raw, list) or not 1 <= len(raw) <= 40:
        raise ValueError("offer 1 to 40 candidate times")
    slots = []
    for s in raw:
        try:
            slots.append(datetime.fromisoformat(str(s)).replace(tzinfo=None).isoformat(timespec="minutes"))
        except ValueError:
            raise ValueError("candidate times look like 2026-10-08T19:00") from None
    if len(set(slots)) != len(slots):
        raise ValueError("candidate times must be different")
    return {"title": title, "circle": circle, "duration_minutes": duration, "slots": sorted(slots)}


def default_answer(answered: list[dict]) -> dict:
    """Someone who never answers is treated as 'maybe' on every time, and the result says so."""
    keys = sorted({k for a in answered for k in a["slots"]})
    return WhenAnswer(slots=dict.fromkeys(keys or ["unknown"], "maybe")).model_dump()


def _pretty(start: datetime, minutes: int) -> dict:
    end = start + timedelta(minutes=minutes)
    return {"start": start.isoformat(timespec="minutes"), "end": end.isoformat(timespec="minutes"),
            "label": sc.label(start), "span": sc.span_label(start, end)}


def tally(named_answers: list[tuple[str, dict]], need: dict) -> list[dict]:
    """Per candidate time: how many said yes, maybe, no (a missing answer counts as no), best first."""
    rows = []
    for slot in need["slots"]:
        votes = [a["slots"].get(slot, "no") for _, a in named_answers]
        rows.append({"slot": slot, "yes": votes.count("yes"), "maybe": votes.count("maybe"), "no": votes.count("no")})
    return sorted(rows, key=lambda r: (r["no"], -r["yes"], r["slot"]))


def compute(named_answers: list[tuple[str, dict]], need: dict, defaults_applied: bool = False) -> dict:
    n = len(named_answers)
    policy = privacy.reveal_policy(n)
    ranked = tally(named_answers, need)
    best = ranked[0]
    start = datetime.fromisoformat(best["slot"])
    dur = need["duration_minutes"]
    plan = _pretty(start, dur)
    if best["no"] == 0 and best["maybe"] == 0:
        fit, tradeoff = "everyone", f"{plan['label']} works for everyone."
    elif best["no"] == 0:
        fit = "flex"
        tradeoff = (
            f"{plan['label']} is the best fit: everyone can make it, but some of you would need to move something."
        )
    else:
        fit = "most"
        tradeoff = (
            f"No time works for everyone. {plan['label']} is the closest: "
            + (f"{best['no']} of {n} can't make it." if policy.single_limit_detail else "someone can't make it.")
        )
    alternatives = [
        {**_pretty(datetime.fromisoformat(r["slot"]), dur), "fit": "everyone" if r["no"] == 0 and r["maybe"] == 0
         else "flex" if r["no"] == 0 else "most"}
        for r in ranked[1:3]
    ]
    return {
        "mode": "when",
        "title": need["title"],
        "circle": need["circle"],
        "duration_minutes": dur,
        "plan": plan,
        "fit": fit,
        "tradeoff": tradeoff,
        "counts": ({"can": best["yes"], "flex": best["maybe"], "cannot": best["no"]}
                   if policy.single_limit_detail else None),
        "alternatives": alternatives,
        "group_size": n,
        "defaults_applied": defaults_applied,
        "warnings": [policy.warning] if policy.warning else [],
        "honest_limits": privacy.HONEST_LIMITS,
    }
