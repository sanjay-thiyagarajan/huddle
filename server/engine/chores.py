"""Household chores: a fair, preference-aware weekly planner that works from PRIVATE limits.

Pure logic (no database). The planner takes each person's private availability, preferences, skills and
exemption, plus the chores, and returns who owns what. Order of priority, each stage never undoing the last:

  1. Hard limits: nobody gets a chore in a category they can't do, nobody exceeds their own availability,
     exempt people get nothing. Cover as much of the work as possible.
  2. Fairness: minimise the largest gap between what each person carries and their fair share. A fair
     share is proportional to the person's own availability (with a floor so claiming almost nothing
     doesn't erase your share), adjusted by what people carried over recent weeks and by how last week felt.
  3. Preferences: among equally fair splits, honour what people love, know, or want to learn, and avoid
     what they dislike.
  4. Rotation: heavy chores don't sit with the same person week after week when someone else could take them.

Burden is minutes weighted by how heavy the chore is, plus a premium for mental load (planning, booking,
remembering), which is real work even though it's invisible.
"""

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

CATEGORIES = [
    "cooking",
    "dishes",
    "cleaning",
    "laundry",
    "tidying",
    "shopping",
    "kids",
    "pets",
    "yard",
    "repairs",
    "admin",
    "planning",
    "other",
]
PREF_VALUES = ("love", "ok", "avoid", "cannot")
MENTAL_CATEGORIES = {"planning", "admin"}  # anticipating, booking, remembering, paperwork

# Occurrences of a chore in a week in which it is active.
CADENCES = {"once": 1, "daily": 7, "weekly": 1, "biweekly": 1, "monthly": 1}
DEFAULT_MINUTES = {
    "cooking": 45,
    "dishes": 20,
    "cleaning": 40,
    "laundry": 30,
    "tidying": 15,
    "shopping": 60,
    "kids": 45,
    "pets": 15,
    "yard": 60,
    "repairs": 60,
    "admin": 30,
    "planning": 20,
    "other": 30,
}
DEFAULT_HEAVINESS = {
    "cooking": 2,
    "dishes": 1,
    "cleaning": 2,
    "laundry": 1,
    "tidying": 1,
    "shopping": 2,
    "kids": 2,
    "pets": 1,
    "yard": 3,
    "repairs": 3,
    "admin": 1,
    "planning": 1,
    "other": 1,
}

HEAVY_WEIGHT = {1: 1.0, 2: 1.25, 3: 1.5}
MENTAL_BONUS = 0.25
FLOOR_FRACTION = 0.4  # a fair share is never based on less than 40% of the household's mean availability
ALPHA = 0.5  # how strongly past over/under-carrying shifts this week's fair share
FELT_FACTOR = {1: 0.8, 2: 0.9}  # last week felt overloaded -> a lighter share this week
BALANCED_WITHIN = 0.10  # "balanced" means no one is more than 10% of an average share from their fair share


def burden_of(minutes_week: float, heaviness: int, mental: bool) -> float:
    return minutes_week * (HEAVY_WEIGHT[heaviness] + (MENTAL_BONUS if mental else 0.0))


@dataclass
class ChoreIn:
    id: str
    title: str
    category: str
    minutes: int  # minutes this week (already multiplied by occurrences)
    heaviness: int = 1
    mental: bool = False
    people_needed: int = 1

    @property
    def burden(self) -> float:
        return burden_of(self.minutes, self.heaviness, self.mental)


@dataclass
class MemberIn:
    id: str
    availability: int  # minutes of chores they can take this week (private)
    prefs: dict = field(default_factory=dict)  # category -> love | ok | avoid | cannot (private)
    skills: dict = field(default_factory=dict)  # category -> 0 none, 1 ok, 2 good (private)
    learn: list = field(default_factory=list)  # categories they'd like to learn (private)
    keywords: list = field(default_factory=list)  # "plumbing", "the car": things they know (private)
    exempt: bool = False
    felt: int | None = None  # how last week felt, 1 to 5 (private)
    prior_dev: float = 0.0  # burden carried minus fair share over recent weeks


@dataclass
class PlanOut:
    assign: dict  # chore_id -> [member_id]
    shares: dict  # member_id -> fraction of the total (fair-share weights, after adjustments)
    targets: dict  # member_id -> burden this week
    loads: dict  # member_id -> burden assigned
    deviation_pct: float
    why: dict  # (chore_id, member_id) -> reason code, private to that member
    report: dict


def member_weights(members: list[MemberIn]) -> dict:
    active = [m for m in members if not m.exempt]
    if not active:
        return {}
    mean = sum(m.availability for m in active) / len(active)
    return {
        m.id: max(m.availability, FLOOR_FRACTION * mean) * FELT_FACTOR.get(m.felt or 0, 1.0) for m in active
    }


def fair_targets(total: float, weights: dict, prior_dev: dict) -> dict:
    """Each person's fair share of `total`, shifted away from people who carried extra recently."""
    if not weights or total <= 0:
        return {k: 0.0 for k in weights}
    s = sum(weights.values())
    t = {k: total * v / s - ALPHA * prior_dev.get(k, 0.0) for k, v in weights.items()}
    for _ in range(5):  # clip at zero and renormalise so the targets still add up to the total
        t = {k: max(v, 0.0) for k, v in t.items()}
        got = sum(t.values())
        if got <= 0:
            return {k: total * v / s for k, v in weights.items()}
        t = {k: v * total / got for k, v in t.items()}
    return t


def eligible(m: MemberIn, c: ChoreIn, used_minutes: int = 0) -> bool:
    return (
        not m.exempt
        and m.prefs.get(c.category, "ok") != "cannot"
        and c.minutes <= m.availability - used_minutes
    )


def pref_score(m: MemberIn, c: ChoreIn) -> tuple[float, str]:
    """How good a match this chore is for this person, and why (the reason is shown only to them)."""
    p = m.prefs.get(c.category, "ok")
    s = {"love": 3.0, "ok": 0.0, "avoid": -4.0}[p]
    skill = m.skills.get(c.category, 1)
    s += skill - 1
    known = any(k.strip() and k.strip().lower() in c.title.lower() for k in m.keywords)
    if known:
        s += 2
    learn = c.category in m.learn and skill < 2
    if learn:
        s += 1
    reason = "love" if p == "love" else "knows" if (known or skill >= 2) else "learn" if learn else "fair"
    return s, reason


def plan(
    chores: list[ChoreIn],
    members: list[MemberIn],
    last_owner: dict | None = None,
    history_dev: dict | None = None,
    rotation_penalty: float = 1.5,
    base_load: dict | None = None,
    base_minutes: dict | None = None,
) -> PlanOut:
    """`base_load` / `base_minutes` are work already assigned or done this week (burden and minutes per
    member). They count toward each person's fair share and use up their availability, so adding chores
    mid-week stays fair relative to what people already have."""
    last_owner = last_owner or {}
    base_load = base_load or {}
    base_minutes = base_minutes or {}
    prior = {m.id: (history_dev or {}).get(m.id, m.prior_dev) for m in members}
    weights = member_weights(members)
    active = [m for m in members if not m.exempt]
    pairs = [(m, c) for c in chores for m in active if eligible(m, c, base_minutes.get(m.id, 0))]
    n = len(pairs)
    assign: dict = {c.id: [] for c in chores}
    why: dict = {}
    loads = {m.id: 0.0 for m in members}

    def finish(x, targets):
        for k, (m, c) in enumerate(pairs):
            if x[k] > 0.5:
                assign[c.id].append(m.id)
                loads[m.id] += c.burden
                why[(c.id, m.id)] = (
                    pref_score(m, c)[1]
                    if (c.heaviness < 2 or c.id not in last_owner or m.id not in last_owner[c.id])
                    else "rotation"
                )
        mean_t = (sum(targets.values()) / len(targets)) if targets else 0.0
        dev = max(
            (abs(loads[k] + base_load.get(k, 0.0) - targets.get(k, 0.0)) for k in loads if k in targets),
            default=0.0,
        )
        return dev / mean_t if mean_t > 0 else 0.0

    if n == 0 or not weights:
        return PlanOut(assign, {}, {}, loads, 0.0, why, _report(chores, assign, last_owner, 0.0))

    A_rows, hi = [], []
    for c in chores:  # a chore can be staffed by at most `people_needed` different people
        row = np.zeros(n + 1)
        for k, (m, cc) in enumerate(pairs):
            if cc.id == c.id:
                row[k] = 1
        A_rows.append(row)
        hi.append(c.people_needed)
    for m in active:  # nobody exceeds their own availability
        row = np.zeros(n + 1)
        for k, (mm, c) in enumerate(pairs):
            if mm.id == m.id:
                row[k] = c.minutes
        A_rows.append(row)
        hi.append(
            max(0, m.availability - base_minutes.get(m.id, 0))
        )  # never negative: it would sink the whole plan
    base_A, base_hi = np.array(A_rows), np.array(hi, dtype=float)
    integrality = np.r_[np.ones(n), 0]
    burden = np.array([c.burden for _, c in pairs])

    # Stage 1: cover as much of the work as possible.
    r1 = milp(
        np.r_[-burden, 0],
        constraints=LinearConstraint(base_A, -np.inf, base_hi),
        integrality=integrality,
        bounds=Bounds(np.zeros(n + 1), np.r_[np.ones(n), 1e9]),
    )
    if not r1.success:
        return PlanOut(assign, {}, {}, loads, 0.0, why, _report(chores, assign, last_owner, 0.0))
    covered = float(-r1.fun)
    targets = fair_targets(covered + sum(base_load.get(m.id, 0.0) for m in active), weights, prior)

    # Stage 2: leximin. Minimise the largest gap from anyone's fair share without covering less, then lock in
    # whoever is stuck at that gap (for example a person already carrying more than their share, whose gap no
    # split can shrink) and minimise the largest gap among everyone else, and so on. Minimising only one
    # largest gap would be blind to the rest of the household whenever one person's gap can't be reduced.
    P = len(active)
    nv = n + P + 1  # x (one per eligible person and chore), e_i (gap of person i), D (the largest gap)
    iD = n + P
    mean_t = sum(targets.values()) / len(targets)
    dev_rows, dev_hi = [], []
    for i, m in enumerate(active):
        row = np.zeros(nv)
        for k, (mm, c) in enumerate(pairs):
            if mm.id == m.id:
                row[k] = c.burden
        up = row.copy()
        up[n + i] = -1
        lo = -row
        lo[n + i] = -1
        gap = targets[m.id] - base_load.get(m.id, 0.0)
        dev_rows += [up, lo]
        dev_hi += [gap, -gap]
    A_base = np.hstack([base_A, np.zeros((base_A.shape[0], nv - base_A.shape[1]))])
    cover_row = np.zeros(nv)
    cover_row[:n] = burden
    integrality_v = np.r_[np.ones(n), np.zeros(P + 1)]

    def run(objective, ub_e, extra=None):
        cons = [
            LinearConstraint(A_base, -np.inf, base_hi),
            LinearConstraint(np.array(dev_rows), -np.inf, np.array(dev_hi)),
            LinearConstraint(cover_row, covered - 1e-6, np.inf),
            *(extra or []),
        ]
        ub = np.r_[np.ones(n), ub_e, 1e9]
        return milp(objective, constraints=cons, integrality=integrality_v, bounds=Bounds(np.zeros(nv), ub))

    tol_dev = max(0.01 * mean_t, 0.5)
    fixed: dict[int, float] = {}
    sol = None
    while len(fixed) < P:
        free = [i for i in range(P) if i not in fixed]
        rows = []
        for i in free:
            r = np.zeros(nv)
            r[n + i] = 1
            r[iD] = -1
            rows.append(r)
        ub_e = np.array([fixed[i] + 1e-6 if i in fixed else 1e9 for i in range(P)])
        c_obj = np.zeros(nv)
        c_obj[iD] = 1
        r2 = run(c_obj, ub_e, [LinearConstraint(np.array(rows), -np.inf, np.zeros(len(rows)))])
        if not r2.success:
            break
        sol, d_level = r2, float(r2.x[iD])
        stuck = []
        for i in free:
            if r2.x[n + i] < d_level - tol_dev:
                continue  # already below the largest gap in this solution
            c_i = np.zeros(nv)
            c_i[n + i] = 1
            ub_i = np.array([fixed[j] + 1e-6 if j in fixed else d_level + 1e-6 for j in range(P)])
            r_i = run(c_i, ub_i)
            if r_i.success and float(r_i.x[n + i]) >= d_level - tol_dev:
                stuck.append(i)
        if not stuck:  # numerical safety: lock the largest so the loop always finishes
            stuck = [max(free, key=lambda i: r2.x[n + i])]
        for i in stuck:
            fixed[i] = d_level
    if sol is None:
        finish(r1.x[:n], targets)
        return PlanOut(
            assign,
            _shares(targets, sum(targets.values())),
            targets,
            loads,
            0.0,
            why,
            _report(chores, assign, last_owner, 0.0),
        )

    # Stage 3: among equally fair splits, the best match for people and the most rotation.
    tol = max(0.02 * mean_t, 1.0)
    score = np.zeros(nv)
    for k, (m, c) in enumerate(pairs):
        s = pref_score(m, c)[0]
        if c.heaviness >= 2 and m.id in last_owner.get(c.id, ()):
            s -= rotation_penalty
        score[k] = s
    r3 = run(-score, np.array([fixed.get(i, 1e9) + tol for i in range(P)]))
    x = (r3 if r3.success else sol).x[:n]
    deviation = finish(x, targets)
    return PlanOut(
        assign,
        _shares(targets, sum(targets.values())),
        targets,
        loads,
        deviation,
        why,
        _report(chores, assign, last_owner, deviation),
    )


def _shares(targets: dict, total: float) -> dict:
    return {k: (v / total if total > 0 else 0.0) for k, v in targets.items()}


def _report(chores: list[ChoreIn], assign: dict, last_owner: dict, deviation: float) -> dict:
    heavy = [c for c in chores if c.heaviness >= 2 and assign.get(c.id)]
    rotated = [c for c in heavy if last_owner.get(c.id) and not (set(assign[c.id]) & set(last_owner[c.id]))]
    mental = [c for c in chores if c.mental and assign.get(c.id)]
    mental_owners = {o for c in mental for o in assign[c.id]}
    staffed = sum(len(assign[c.id]) for c in chores)
    wanted = sum(c.people_needed for c in chores)
    return {
        "deviation_pct": round(deviation * 100, 1),
        "balanced": deviation <= BALANCED_WITHIN,
        "slots_filled": staffed,
        "slots_total": wanted,
        "unstaffed": [c.id for c in chores if len(assign[c.id]) < c.people_needed],
        "heavy_chores": len(heavy),
        "heavy_rotated": len(rotated),
        # rotation only means something when there was a previous owner to rotate away from
        "rotation_applies": any(last_owner.get(c.id) for c in heavy),
        "mental_chores": len(mental),
        "mental_owners": len(mental_owners),
    }


def rank_candidates(
    chore: ChoreIn,
    members: list[MemberIn],
    loads: dict,
    shares: dict,
    total: float,
    exclude: set | None = None,
    last_owner: set | None = None,
    used_minutes: dict | None = None,
) -> list[str]:
    """Best first: who should be ASKED to take an extra chore. Fairest resulting split, then best match."""
    exclude = exclude or set()
    last_owner = last_owner or set()
    total_after = total + chore.burden
    active = [m for m in members if not m.exempt]
    if not active:
        return []
    weights = member_weights(members)
    wsum = sum(weights.values())
    sh = shares if shares and sum(shares.values()) > 0 else {k: v / wsum for k, v in weights.items()}
    targets = {k: total_after * sh.get(k, 0.0) for k in weights}
    scored = []
    for m in active:
        if m.id in exclude or not eligible(m, chore, (used_minutes or {}).get(m.id, 0)):
            continue
        new_load = dict(loads)
        new_load[m.id] = new_load.get(m.id, 0.0) + chore.burden
        worst = max(abs(new_load.get(k, 0.0) - targets.get(k, 0.0)) for k in targets)
        s = pref_score(m, chore)[0] - (rotation_penalty_for(chore, m, last_owner))
        scored.append((round(worst, 6), -s, new_load[m.id], m.id))
    scored.sort()
    return [mid for *_, mid in scored]


def rotation_penalty_for(chore: ChoreIn, m: MemberIn, last_owner: set) -> float:
    return 1.5 if chore.heaviness >= 2 and m.id in last_owner else 0.0
