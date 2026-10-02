"""Friend-trip mode (stretch): the same private-matching engine with a trip catalogue.

Prices are mock per-person trip totals, not live prices. Huddle decides; it does not book.
"""
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from . import everyday

Attr = Literal["flights", "camping", "long_drive", "early_start", "strenuous", "nightlife"]
Vibe = Literal["beach", "city", "nature", "foodie", "relaxed", "adventurous"]
ATTRS = list(Attr.__args__)
VIBES = list(Vibe.__args__)

OPTIONS = [
    {"id": "cabin", "name": "Lake cabin weekend", "price": 140,
     "vibes": ["nature", "relaxed"], "attrs": ["long_drive"]},
    {"id": "camp", "name": "Mountain camping and hiking", "price": 90,
     "vibes": ["nature", "adventurous"], "attrs": ["camping", "strenuous", "early_start", "long_drive"]},
    {"id": "coast", "name": "Beach house on the coast", "price": 320,
     "vibes": ["beach", "relaxed", "foodie"], "attrs": ["long_drive"]},
    {"id": "citybreak", "name": "City break with food tours", "price": 520,
     "vibes": ["city", "foodie"], "attrs": ["flights", "nightlife"]},
    {"id": "island", "name": "Island resort week", "price": 1400,
     "vibes": ["beach", "relaxed", "adventurous"], "attrs": ["flights"]},
    {"id": "festival", "name": "Music festival weekend", "price": 380,
     "vibes": ["city", "adventurous"], "attrs": ["camping", "nightlife"]},
]


class TripAnswer(BaseModel):
    must_haves: list[Attr | Vibe] = Field(default_factory=list)
    dealbreakers: list[Attr] = Field(default_factory=list)
    budget_ceiling: float = Field(ge=0, le=100000)  # dollars per person for the whole trip
    vibe: list[Vibe] = Field(default_factory=list)

    @field_validator("must_haves", "dealbreakers", "vibe")
    @classmethod
    def _dedupe(cls, v):
        return list(dict.fromkeys(v))


AnswerModel = TripAnswer


def default_answer(answered: list[dict]) -> dict:
    out = everyday.default_answer(answered)
    return TripAnswer.model_validate({**out, "budget_ceiling": out["budget_ceiling"]}).model_dump()


def compute(named_answers, need=None, defaults_applied=False) -> dict:
    return everyday.compute(named_answers, need, defaults_applied, options=OPTIONS, mode="trip")
