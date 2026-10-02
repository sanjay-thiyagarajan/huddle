"""Buckets, the k rule and the leak guard.

This is no-attribution plus bucketing, not cryptographic secrecy. With two people the
other person can infer your number from a bucket.
"""
import re
from dataclasses import dataclass

K_MIN = 3

MONEY_EDGES = [0, 100, 250, 500, 1000]
HOURS_STEP = 5

TWO_PERSON_WARNING = "With two people, the other person may be able to infer your number."
HONEST_LIMITS = (
    "Answers are never shown or attributed, but this is bucketing, not cryptographic secrecy. "
    "In a group of two, the other person can infer your number."
)


def money_bucket(amount: float) -> str:
    """Fixed bands: $0-100, $100-250, $250-500, $500-1000, $1000+."""
    amount = max(0, amount)
    for lo, hi in zip(MONEY_EDGES, MONEY_EDGES[1:]):
        if amount < hi:
            return f"${lo}-{hi}"
    return f"${MONEY_EDGES[-1]}+"


def money_bucket_floor(amount: float) -> int:
    amount = max(0, amount)
    floor = 0
    for edge in MONEY_EDGES:
        if amount >= edge:
            floor = edge
    return floor


def hours_bucket(hours: float) -> str:
    """5-hour bands: 0-5, 5-10, ..."""
    hours = max(0, hours)
    lo = int(hours // HOURS_STEP) * HOURS_STEP
    return f"{lo}-{lo + HOURS_STEP} h"


def gap_label_hours(gap: float) -> str:
    return "none" if gap <= 0 else hours_bucket(gap)


def gap_label_money(gap: float) -> str:
    return "none" if gap <= 0 else money_bucket(gap)


@dataclass(frozen=True)
class RevealPolicy:
    group_size: int
    single_limit_detail: bool  # may we expose anything that hinges on one person's limit?
    warning: str | None


def reveal_policy(group_size: int) -> RevealPolicy:
    """k >= 3 for aggregates that depend on a single limiting value; k == 2 gets a warning."""
    return RevealPolicy(
        group_size=group_size,
        single_limit_detail=group_size >= K_MIN,
        warning=TWO_PERSON_WARNING if group_size < K_MIN else None,
    )


_HEALTH = re.compile(
    r"\b(diagnos\w*|dementia|alzheimer\w*|cancer|chemo\w*|stroke|diabet\w*|medicat\w*|"
    r"prescri\w*|surgery|dialysis|hospice|incontinen\w*|blood pressure|insulin|therapy|"
    r"disease|illness|symptom\w*)\b",
    re.I,
)
HEALTH_WARNING = (
    "That looks like health detail. Huddle collects no health data, so the note was not saved. "
    "Decision aid, not medical, legal or financial advice."
)


def looks_like_health_text(text: str | None) -> bool:
    return bool(text and _HEALTH.search(text))


# ---- leak guard (used by the automated leak test) ----------------------------------------

def _number_forms(value: float) -> list[str]:
    forms = {str(value), f"{value:g}"}
    if float(value).is_integer():
        i = int(value)
        forms |= {str(i), f"{i:,}", f"{i}.00"}
    return sorted(forms, key=len, reverse=True)


def find_leaks(body: str, sentinels: dict[str, list[float]], viewer: str) -> list[str]:
    """Return leak descriptions: any *other* participant's sentinel value in `body`.

    `sentinels` maps participant name -> distinctive raw values they submitted.
    Boundaries exclude [\\w.-] so random token characters do not cause false hits.
    """
    leaks = []
    for name, values in sentinels.items():
        if name == viewer:
            continue
        for v in values:
            for form in _number_forms(v):
                if re.search(rf"(?<![\w.\-]){re.escape(form)}(?![\w.\-]|\.\d)", body):
                    leaks.append(f"{name}'s value {form}")
                    break
    return leaks


def find_attributed_buckets(body: str, buckets: dict[str, list[str]], viewer: str) -> list[str]:
    """Flag another participant's name appearing within 40 chars of one of their buckets."""
    leaks = []
    for name, labels in buckets.items():
        if name == viewer:
            continue
        for label in labels:
            n, b = re.escape(name), re.escape(label)
            pat = rf"{n}.{{0,40}}{b}|{b}.{{0,40}}{n}"
            if re.search(pat, body, re.S):
                leaks.append(f"{name} near bucket {label}")
    return leaks
