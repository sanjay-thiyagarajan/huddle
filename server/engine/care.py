"""Care mode: siblings share care of an aging parent.

Each person privately gives hours/week, $/month and task types they cannot do. The engine
reports group-level, bucketed gaps and a task split that respects every private limit.
It is a decision aid, not medical, legal or financial advice, and collects no health data.
"""
import math
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field, field_validator
from scipy.optimize import Bounds, LinearConstraint, milp

from . import privacy

TaskType = Literal["checkin", "appointments", "meals", "finances", "overnight"]
Dealbreaker = Literal["nights", "transport", "appointments", "finances", "checkins", "far_away"]

# Which task types each dealbreaker rules out. "far_away" rules out in-person tasks;
# check-ins (phone/video) and paperwork can still be done remotely.
BLOCKS: dict[str, set[str]] = {
    "nights": {"overnight"},
    "transport": {"appointments"},
    "appointments": {"appointments"},
    "finances": {"finances"},
    "checkins": {"checkin"},
    "far_away": {"overnight", "appointments", "meals"},
}

# Task types that are physically demanding or tie someone to a place and time. The fairness record
# counts these so the next split can rotate them.
HEAVY_TYPES = {"overnight", "appointments"}
FAIRNESS_WEIGHT = 0.0005  # small: rotation breaks ties and never costs coverage

DEFAULT_NEED = {
    "tasks": [
        {"id": "checkin", "label": "Daily check-in", "type": "checkin", "hours": 7},
        {"id": "appointments", "label": "Appointments and transport", "type": "appointments", "hours": 6},
        {"id": "meals", "label": "Meals", "type": "meals", "hours": 8},
        {"id": "finances", "label": "Finances and paperwork", "type": "finances", "hours": 3},
        {"id": "overnight", "label": "Overnight cover", "type": "overnight", "hours": 6},
    ],
    "dollars_per_month": 1800,
}

RESPITE_RATE = 30  # assumed $/hour for paid respite: a placeholder, not a quote
WEEKS_PER_MONTH = 4.33

DISCLAIMER = "Decision aid, not medical, legal or financial advice."
ASSIGNMENT_CAVEAT = (
    "The split shows assignments, not anyone's limits. Still, an assignment can hint at what a "
    "person is able to do, so treat it as a proposal to discuss."
)


class Task(BaseModel):
    id: str = Field(min_length=1, max_length=30, pattern=r"^[a-z0-9_]+$")
    label: str = Field(min_length=1, max_length=60)
    type: TaskType
    hours: int = Field(ge=1, le=80)


class CareNeed(BaseModel):
    tasks: list[Task] = Field(min_length=1, max_length=20)
    dollars_per_month: int = Field(ge=0, le=100000)


class CareAnswer(BaseModel):
    hours_per_week: float = Field(ge=0, le=168)
    dollars_per_month: float = Field(ge=0, le=100000)
    dealbreakers: list[Dealbreaker] = Field(default_factory=list)

    @field_validator("dealbreakers")
    @classmethod
    def _dedupe(cls, v):
        return list(dict.fromkeys(v))


AnswerModel = CareAnswer


def validate_need(need: dict | None) -> dict:
    need = need or DEFAULT_NEED
    parsed = CareNeed.model_validate(need)
    ids = [t.id for t in parsed.tasks]
    if len(set(ids)) != len(ids):
        raise ValueError("task ids must be unique")
    for t in parsed.tasks:
        if privacy.looks_like_health_text(t.label):
            raise ValueError(f"task label '{t.label}': {privacy.HEALTH_WARNING}")
    return parsed.model_dump()


def default_answer(_answered: list[dict]) -> dict:
    """Non-responder default: 0 hours and $0, which makes the gap visible."""
    return CareAnswer(hours_per_week=0, dollars_per_month=0).model_dump()


def _blocked(answer: dict) -> set[str]:
    return set().union(*(BLOCKS[d] for d in answer["dealbreakers"])) if answer["dealbreakers"] else set()


def solve(tasks: list[dict], answers: list[dict],
          prior_heavy: list[int] | None = None) -> list[dict[str, int]]:
    """Integer-hour split. Stage 1 maximises hours covered; stage 2 spreads load evenly
    (minimises the largest share of anyone's own capacity). Returns, per person, {task_id: hours}.
    `prior_heavy` is each person's heavy-task hours from earlier rounds (public assignments only);
    among otherwise equal splits, heavy tasks go to whoever has taken fewer.
    """
    P, T = len(answers), len(tasks)
    caps = [int(math.floor(a["hours_per_week"])) for a in answers]
    blocked = [_blocked(a) for a in answers]
    n = P * T
    idx = lambda p, t: p * T + t  # noqa: E731

    ub = np.zeros(n)
    for p in range(P):
        for t, task in enumerate(tasks):
            if task["type"] not in blocked[p]:
                ub[idx(p, t)] = min(caps[p], task["hours"])

    rows, hi = [], []
    for t, task in enumerate(tasks):  # a task cannot be over-filled
        row = np.zeros(n + 1)
        row[[idx(p, t) for p in range(P)]] = 1
        rows.append(row)
        hi.append(task["hours"])
    for p in range(P):  # nobody exceeds their own hours
        row = np.zeros(n + 1)
        row[[idx(p, t) for t in range(T)]] = 1
        rows.append(row)
        hi.append(caps[p])
    A = np.array(rows)
    integrality = np.r_[np.ones(n), 0]
    bounds = Bounds(np.zeros(n + 1), np.r_[ub, 1e6])

    c1 = np.r_[-np.ones(n), 0]
    r1 = milp(c1, constraints=LinearConstraint(A, -np.inf, np.array(hi)),
              integrality=integrality, bounds=bounds)
    if not r1.success:
        return [{} for _ in answers]
    covered = int(round(-r1.fun))

    # Stage 2: keep coverage, minimise u where load_p <= u * cap_p.
    extra, extra_hi = [], []
    for p in range(P):
        if caps[p] > 0:
            row = np.zeros(n + 1)
            row[[idx(p, t) for t in range(T)]] = 1
            row[n] = -caps[p]
            extra.append(row)
            extra_hi.append(0)
    cover = np.r_[np.ones(n), 0]
    cons = [LinearConstraint(A, -np.inf, np.array(hi)), LinearConstraint(cover, covered, np.inf)]
    if extra:
        cons.append(LinearConstraint(np.array(extra), -np.inf, np.array(extra_hi)))
    c2 = np.zeros(n + 1)
    c2[n] = 1
    top = max(prior_heavy or [0])
    if top > 0:
        for p in range(P):
            for t, task in enumerate(tasks):
                if task["type"] in HEAVY_TYPES:
                    c2[idx(p, t)] = FAIRNESS_WEIGHT * prior_heavy[p] / top
    r2 = milp(c2, constraints=cons, integrality=integrality, bounds=bounds)
    x = (r2 if r2.success else r1).x

    return [{tasks[t]["id"]: int(round(x[idx(p, t)])) for t in range(T) if round(x[idx(p, t)]) > 0}
            for p in range(P)]


def _money_label(amount: float) -> str:
    return f"${amount:,.0f}"


def compute(named_answers: list[tuple[str, dict]], need: dict, defaults_applied: bool = False,
            history: dict | None = None) -> dict:
    names = [n for n, _ in named_answers]
    answers = [a for _, a in named_answers]
    n = len(answers)
    policy = privacy.reveal_policy(n)
    tasks = need["tasks"]
    by_id = {t["id"]: t for t in tasks}

    prior = history or {"rounds": 0, "heavy": {}}
    prior_heavy = [prior["heavy"].get(nm.lower(), 0) for nm in names]
    split = solve(tasks, answers, prior_heavy)
    assigned_by_task = {t["id"]: sum(s.get(t["id"], 0) for s in split) for t in tasks}
    need_hours = sum(t["hours"] for t in tasks)
    covered_hours = sum(assigned_by_task.values())
    gap_hours = need_hours - covered_hours
    money_have = sum(a["dollars_per_month"] for a in answers)
    gap_money = max(0.0, need["dollars_per_month"] - money_have)

    assignments = [
        {"name": names[p], "tasks": [{"task_id": tid, "label": by_id[tid]["label"], "hours": h}
                                     for tid, h in split[p].items()]}
        for p in range(n) if split[p]
    ]
    unfilled = [{"task_id": t["id"], "label": t["label"],
                 "unfilled_hours_bucket": privacy.hours_bucket(t["hours"] - assigned_by_task[t["id"]])}
                for t in tasks if assigned_by_task[t["id"]] < t["hours"]]

    options = []
    if gap_hours > 0:
        monthly = gap_hours * RESPITE_RATE * WEEKS_PER_MONTH
        options.append(
            f"Pay for paid respite hours to cover the {privacy.gap_label_hours(gap_hours)} weekly gap "
            f"(roughly {privacy.money_bucket(monthly)}/month at an assumed ${RESPITE_RATE}/h; "
            "a placeholder rate, not a quote).")
        if any(t["type"] == "overnight" for t in tasks):
            options.append("Reduce overnight cover and check whether a different arrangement works.")
        options.append("Shift tasks: ask whether a task someone ruled out could be shared differently.")
    if gap_money > 0:
        options.append("Close the monthly money gap by pooling more, or by trimming the monthly need.")
    if not options:
        options.append("The plan is covered. Review it together in a few weeks.")

    heavy_now = {names[p]: sum(h for tid, h in split[p].items() if by_id[tid]["type"] in HEAVY_TYPES)
                 for p in range(n)}
    fairness = None
    if prior["rounds"] > 0:
        fairness = {
            "plans": prior["rounds"] + 1,
            "heavy_hours": {nm: prior_heavy[i] + heavy_now[nm] for i, nm in enumerate(names)},
            "note": ("Heavy tasks (overnight cover, appointments and transport) are counted across plans for "
                     "this group. This split gave them to whoever had taken fewer, where limits allowed. "
                     "Based on past assignments only, never anyone's private limits."),
        }

    headline = (
        f"The plan needs {need_hours} h/week and {_money_label(need['dollars_per_month'])}/month. "
        f"After fitting everyone's private limits, the gap is {privacy.gap_label_hours(gap_hours)} "
        f"per week and {privacy.gap_label_money(gap_money)} per month."
    )
    return {
        "mode": "care",
        "headline": headline,
        "need": {"hours_per_week": need_hours, "dollars_per_month": need["dollars_per_month"]},
        "gap_hours_bucket": privacy.gap_label_hours(gap_hours),
        "gap_dollars_bucket": privacy.gap_label_money(gap_money),
        "assignments": assignments,
        "unfilled_tasks": unfilled,
        "options": options,
        "fairness": fairness,
        "heavy_hours_this_plan": heavy_now,
        "assignment_caveat": ASSIGNMENT_CAVEAT,
        "disclaimer": DISCLAIMER,
        "group_size": n,
        "defaults_applied": defaults_applied,
        "defaults_note": ("At least one person did not answer; 0 hours and $0 were assumed for them."
                          if defaults_applied else None),
        "warnings": [policy.warning] if policy.warning else [],
        "honest_limits": privacy.HONEST_LIMITS,
    }
