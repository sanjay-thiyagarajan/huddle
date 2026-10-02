"""Everyday mode: pick one weekend plan that fits every private limit."""
from statistics import median
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from . import privacy

Attr = Literal["outdoors", "crowds", "long_drive", "early_start", "physical", "alcohol"]
Vibe = Literal["active", "relaxed", "foodie", "cultural", "social", "adventurous"]
ATTRS = list(Attr.__args__)
VIBES = list(Vibe.__args__)

# Mock catalogue for the demo (no live prices). price = per person, dollars.
OPTIONS = [
    {"id": "hike", "name": "Sunrise hike and picnic", "price": 15,
     "vibes": ["active", "adventurous"], "attrs": ["outdoors", "early_start", "physical"]},
    {"id": "market", "name": "Farmers market and long brunch", "price": 45,
     "vibes": ["relaxed", "foodie"], "attrs": ["crowds"]},
    {"id": "museum", "name": "Museum and a sit-down dinner", "price": 90,
     "vibes": ["cultural", "foodie", "relaxed"], "attrs": ["alcohol"]},
    {"id": "escape", "name": "Escape room and arcade", "price": 35,
     "vibes": ["social", "adventurous"], "attrs": ["crowds"]},
    {"id": "park", "name": "Theme park day", "price": 120,
     "vibes": ["active", "social", "adventurous"], "attrs": ["crowds", "physical", "long_drive"]},
    {"id": "class", "name": "Cooking class with wine", "price": 150,
     "vibes": ["foodie", "social", "cultural"], "attrs": ["alcohol"]},
]


class EverydayAnswer(BaseModel):
    must_haves: list[Attr | Vibe] = Field(default_factory=list)
    dealbreakers: list[Attr] = Field(default_factory=list)
    budget_ceiling: float = Field(ge=0, le=100000)  # dollars per person
    vibe: list[Vibe] = Field(default_factory=list)

    @field_validator("must_haves", "dealbreakers", "vibe")
    @classmethod
    def _dedupe(cls, v):
        return list(dict.fromkeys(v))


def default_answer(answered: list[dict]) -> dict:
    """Non-responder default: median budget of those who answered, no dealbreakers."""
    budgets = [a["budget_ceiling"] for a in answered]
    return EverydayAnswer(budget_ceiling=median(budgets) if budgets else 150).model_dump()


def _score(opt: dict, answers: list[dict]) -> int:
    tags = set(opt["vibes"]) | set(opt["attrs"])
    return sum(len(set(a["vibe"]) & tags) + 2 * len(set(a["must_haves"]) & tags) for a in answers)


def _supporters(opt: dict, answers: list[dict]) -> int:
    tags = set(opt["vibes"]) | set(opt["attrs"])
    return sum(1 for a in answers if (set(a["vibe"]) | set(a["must_haves"])) & tags)


AnswerModel = EverydayAnswer


def compute(named_answers: list[tuple[str, dict]], need: dict | None = None,
            defaults_applied: bool = False, options: list[dict] | None = None,
            mode: str = "everyday") -> dict:
    options = options or OPTIONS
    answers = [a for _, a in named_answers]  # names are deliberately dropped here
    n = len(answers)
    policy = privacy.reveal_policy(n)
    budget = min(a["budget_ceiling"] for a in answers)
    banned = {d for a in answers for d in a["dealbreakers"]}

    def reason(opt) -> str | None:
        if opt["price"] > budget:
            return "budget"
        if banned & set(opt["attrs"]):
            return "dealbreaker"
        return None

    ranked = sorted(options, key=lambda o: (-_score(o, answers), o["price"]))
    feasible = [o for o in ranked if reason(o) is None]
    wanted = ranked[0]
    chosen = feasible[0] if feasible else None

    if chosen is None:
        tradeoff = "No activity fit every private limit at once. Loosen a limit or try another day."
    elif chosen["id"] == wanted["id"]:
        tradeoff = f"Picked {chosen['name']}: it was the most-wanted option and fit every limit."
    else:
        why = reason(wanted)
        if policy.single_limit_detail:
            ruled = "the budget bucket" if why == "budget" else "a dealbreaker in the group"
            who = f"{_supporters(wanted, answers)} of you"
        else:
            ruled, who = "a group limit", "some of you"
        tradeoff = f"Picked {chosen['name']}; {who} preferred {wanted['name']}, but {ruled} ruled it out."

    return {
        "mode": mode,
        "plan": None if chosen is None else {
            "id": chosen["id"], "name": chosen["name"],
            "price_band": privacy.money_bucket(chosen["price"]),
        },
        "tradeoff": tradeoff,
        "group_budget_bucket": privacy.money_bucket(budget) if policy.single_limit_detail else None,
        "group_size": n,
        "defaults_applied": defaults_applied,
        "warnings": [policy.warning] if policy.warning else [],
        "honest_limits": privacy.HONEST_LIMITS,
    }
