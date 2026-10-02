"""The household agent (Alexa+ stand-in).

* `call_tool` reaches Huddle's MCP server over Streamable HTTP, at runtime, like any MCP host.
* `parse_utterance` turns one person's words into a structured draft. In HUDDLE_MODE=mock it is
  a deterministic keyword parser (no credentials); the Bedrock/Strands version replaces it in aws mode.
  It is invoked per person with only that person's input, and never sees other answers.
"""
import json
import logging
import os
import re
import time
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import BaseModel, Field

from .. import config
from ..engine import care, everyday, trip
from . import prompts

log = logging.getLogger("huddle.agent")

TOOLS = {"start_huddle", "submit_private_answer", "get_group_result", "close_round", "nudge_pending",
         "submit_checkin", "revisit_round",
         # the household
         "create_household", "get_household", "set_my_profile", "add_chore", "plan_week",
         "respond_to_assignment", "hand_back_chore", "complete_chore", "week_checkin", "ask_household_agent"}


def mcp_url() -> str:
    return os.environ.get("HUDDLE_MCP_URL", f"http://127.0.0.1:{os.environ.get('HUDDLE_PORT', '8000')}/mcp")


async def call_tool(name: str, arguments: dict, url: str | None = None) -> dict[str, Any]:
    if name not in TOOLS:
        raise ValueError(f"unknown tool {name}")
    async with streamable_http_client(url or mcp_url()) as (rd, wr, _):
        async with ClientSession(rd, wr) as sess:
            await sess.initialize()
            res = await sess.call_tool(name, arguments)
            if res.isError:
                text = " ".join(getattr(c, "text", "") for c in res.content)
                return {"error": text or "tool error"}
            return res.structuredContent or {}


# ---- mock parser -----------------------------------------------------------------------------

_ONES = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen".split())}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
         "eighty": 80, "ninety": 90}
_WORDS = {**_ONES, **_TENS, "hundred": 100}
_WORD_ALT = "|".join(sorted(_WORDS, key=len, reverse=True))
_NEG = re.compile(r"\b(not|no|can'?t|cannot|won'?t|never|avoid|hate|dislike|without|nothing)\b", re.I)

_EVERYDAY_WORDS = {
    "outdoors": r"outdoor|outside|hik", "crowds": r"crowd", "long_drive": r"long drive|far drive",
    "early_start": r"early", "physical": r"physical|strenuous", "alcohol": r"alcohol|drink|wine",
    "active": r"active|sport", "relaxed": r"relax|chill|easy", "foodie": r"food|eat|brunch|dinner",
    "cultural": r"museum|culture|art", "social": r"social|friends|group", "adventurous": r"advent|thrill",
}
_TRIP_WORDS = {
    "flights": r"flight|fly|plane", "camping": r"camp|tent", "long_drive": r"long drive|far drive",
    "early_start": r"early", "strenuous": r"strenuous|hard hik|intense",
    "nightlife": r"nightlife|clubs?|party",
    "beach": r"beach|coast|sea", "city": r"city|urban", "nature": r"nature|mountain|lake|hik",
    "foodie": r"food|eat|restaurant", "relaxed": r"relax|chill|easy", "adventurous": r"advent|thrill",
}
_TRIP_NEGATABLE = {"flights", "camping", "long_drive", "early_start", "strenuous", "nightlife"}
_CARE_WORDS = {
    "nights": r"night|overnight", "transport": r"transport|driv", "appointments": r"appointment",
    "finances": r"financ|paperwork|bills", "checkins": r"check-?in|phone call|calls",
    "far_away": r"far away|live far|another city|out of town|different city",
}


def _num(phrase: str) -> float | None:
    """'600', '1,200', 'twelve', 'sixty five', 'six hundred', 'a hundred and fifty' -> number.

    Returns None for phrases it cannot read (for example a bare 'hundred'), so the agent asks again
    instead of guessing.
    """
    phrase = phrase.lower().replace(",", "").strip()
    if re.fullmatch(r"\d+(\.\d+)?", phrase):
        return float(phrase)
    total, seen = 0, False
    for w in re.split(r"[ -]+", phrase):
        if w in ("and", "a"):
            seen = seen or w == "a"
        elif w == "hundred":
            if total == 0 and not seen:
                return None
            total = max(total, 1) * 100
            seen = True
        elif w in _ONES or w in _TENS:
            total += _ONES.get(w, _TENS.get(w, 0))
            seen = True
        else:
            return None
    return float(total)


# One number: digits, or number words ("sixty five", "a hundred and fifty"), on word boundaries.
_NW = rf"\b(?:{_WORD_ALT})\b"
_NUMBER = rf"(\d[\d,]*(?:\.\d+)?|(?:\ba\s+(?=hundred\b))?{_NW}(?:[ -]+(?:and[ -]+)?{_NW})*)"


def _clauses(text: str) -> list[str]:
    return [c.strip() for c in re.split(r"[,.;]|\bbut\b|\band\b(?= (?:not|no|never|can))", text) if c.strip()]


def parse_utterance(mode: str, text: str) -> dict:
    """Return {draft, missing, followup}. Negated clauses become dealbreakers, others preferences."""
    if mode == "care":
        return _parse_care(text)
    if mode == "trip":
        return _parse_everyday(text, _TRIP_WORDS, _TRIP_NEGATABLE, "for the whole trip")
    return _parse_everyday(text)


def _parse_everyday(text: str, words: dict[str, str] | None = None, negatable: set[str] | None = None,
                    unit: str = "per person") -> dict:
    draft: dict = {"budget_ceiling": None, "vibe": [], "must_haves": [], "dealbreakers": []}
    pattern = (rf"\$\s*{_NUMBER}|{_NUMBER}\s*(?:dollars|bucks)"
               rf"|(?:under|up to|max|budget(?: of)?)\s*\$?{_NUMBER}")
    m = re.search(pattern, text, re.I)
    if m:
        draft["budget_ceiling"] = _num(next(g for g in m.groups() if g))
    for clause in _clauses(text):
        neg = bool(_NEG.search(clause))
        for key, pat in (words or _EVERYDAY_WORDS).items():
            if re.search(pat, clause, re.I):
                if neg and key in (negatable or {"outdoors", "crowds", "long_drive", "early_start",
                                                 "physical", "alcohol"}):
                    draft["dealbreakers"].append(key)
                elif not neg:
                    (draft["must_haves"] if re.search(r"must|need|have to", clause, re.I)
                     else draft["vibe"]).append(key)
    for k in ("vibe", "must_haves", "dealbreakers"):
        draft[k] = list(dict.fromkeys(draft[k]))
    missing = [] if draft["budget_ceiling"] is not None else ["budget_ceiling"]
    return {"draft": draft, "missing": missing,
            "followup": f"What's the most you'd comfortably spend {unit}?" if missing else None}


def _parse_care(text: str) -> dict:
    draft: dict = {"hours_per_week": None, "dollars_per_month": None, "dealbreakers": []}
    h = re.search(rf"{_NUMBER}\s*(?:h\b|hrs?\b|hours?)", text, re.I)
    if h:
        draft["hours_per_week"] = _num(h.group(1))
    d = re.search(rf"\$\s*{_NUMBER}|{_NUMBER}\s*(?:dollars|bucks)", text, re.I)
    if d:
        draft["dollars_per_month"] = _num(next(g for g in d.groups() if g))
    if re.search(r"no (?:time|hours)|zero hours|nothing", text, re.I) and draft["hours_per_week"] is None:
        draft["hours_per_week"] = 0
    for clause in _clauses(text):
        if _NEG.search(clause) or re.search(r"live far|far away|another city", clause, re.I):
            for key, pat in _CARE_WORDS.items():
                if re.search(pat, clause, re.I):
                    draft["dealbreakers"].append(key)
    draft["dealbreakers"] = list(dict.fromkeys(draft["dealbreakers"]))
    missing = [k for k in ("hours_per_week", "dollars_per_month") if draft[k] is None]
    ask = {"hours_per_week": "About how many hours a week could you give?",
           "dollars_per_month": "And roughly how many dollars a month could you put in?"}
    return {"draft": draft, "missing": missing, "followup": ask[missing[0]] if missing else None}


# ---- aws mode: Strands Agents SDK on Amazon Bedrock ----------------------------------------------


class AgentConfigError(RuntimeError):
    pass


class EverydayParse(BaseModel):
    budget_ceiling: float | None = Field(default=None, ge=0, le=100000)
    vibe: list[everyday.Vibe] = Field(default_factory=list)
    must_haves: list[everyday.Vibe | everyday.Attr] = Field(default_factory=list)
    dealbreakers: list[everyday.Attr] = Field(default_factory=list)
    followup: str | None = Field(default=None, max_length=200)


class TripParse(BaseModel):
    budget_ceiling: float | None = Field(default=None, ge=0, le=100000)
    vibe: list[trip.Vibe] = Field(default_factory=list)
    must_haves: list[trip.Vibe | trip.Attr] = Field(default_factory=list)
    dealbreakers: list[trip.Attr] = Field(default_factory=list)
    followup: str | None = Field(default=None, max_length=200)


class CareParse(BaseModel):
    hours_per_week: float | None = Field(default=None, ge=0, le=168)
    dollars_per_month: float | None = Field(default=None, ge=0, le=100000)
    dealbreakers: list[care.Dealbreaker] = Field(default_factory=list)
    followup: str | None = Field(default=None, max_length=200)


class Explanation(BaseModel):
    text: str = Field(max_length=600)


def _make_agent(system_prompt: str):
    """A fresh Strands agent per call, so it carries no memory of anyone else's answers.

    The model id comes from HUDDLE_BEDROCK_MODEL_ID: check the Bedrock model catalog for a current
    id enabled in your account and region. Nothing is hard-coded on purpose.
    """
    model_id = os.environ.get("HUDDLE_BEDROCK_MODEL_ID")
    if not model_id:
        raise AgentConfigError("Set HUDDLE_BEDROCK_MODEL_ID to a Bedrock model id enabled in your account.")
    from strands import Agent
    from strands.models import BedrockModel

    model = BedrockModel(model_id=model_id, region_name=os.environ.get("AWS_REGION"), temperature=0.0)
    return Agent(model=model, system_prompt=system_prompt, callback_handler=None)


def _structured(agent, prompt: str, model_cls: type[BaseModel]) -> BaseModel:
    out = agent(prompt, structured_output_model=model_cls).structured_output
    if not isinstance(out, model_cls):
        raise ValueError("model returned no structured output")
    return out


def _bedrock_parse(mode: str, text: str) -> dict:
    cls = {"care": CareParse, "trip": TripParse}.get(mode, EverydayParse)
    out = _structured(_make_agent(prompts.PARSE_SYSTEM), f"Mode: {mode}\nThe person said: {text}", cls)
    draft = out.model_dump(exclude={"followup"})
    required = ("hours_per_week", "dollars_per_month") if mode == "care" else ("budget_ceiling",)
    missing = [k for k in required if draft[k] is None]  # recomputed here, never trusted from the model
    fallback = parse_utterance(mode, text)["followup"]
    return {"draft": draft, "missing": missing, "followup": (out.followup or fallback) if missing else None}


def parse_with_engine(mode: str, text: str) -> dict:
    """Parse one person's words. Adds `engine` and `latency_ms`; Bedrock failures fall back to mock."""
    start = time.perf_counter()
    engine, error = "mock", None
    if config.MODE == "aws":
        try:
            out = _bedrock_parse(mode, text)
            engine = "bedrock"
        except Exception as e:  # noqa: BLE001  any Bedrock/credential failure falls back to mock
            error = f"{type(e).__name__}: {e}"[:200]
            log.warning("bedrock parse failed, using mock parser: %s", error)
            out, engine = parse_utterance(mode, text), "mock-fallback"
    else:
        out = parse_utterance(mode, text)
    out = {**out, "engine": engine, "latency_ms": round((time.perf_counter() - start) * 1000)}
    if error:
        out["engine_error"] = error
    log.info("parse engine=%s latency_ms=%s", engine, out["latency_ms"])
    return out


def explain(result: dict) -> dict:
    """Two plain sentences about an AGGREGATE result; the agent never sees raw answers."""
    start = time.perf_counter()
    engine, error, text = "mock", None, result.get("tradeoff") or result.get("headline", "")
    if config.MODE == "aws":
        try:
            prompt = "Explain this group result:\n" + json.dumps(
                {k: result[k] for k in result if k not in {"honest_limits"}})
            text = _structured(_make_agent(prompts.EXPLAIN_SYSTEM), prompt, Explanation).text
            engine = "bedrock"
        except Exception as e:  # noqa: BLE001
            error = f"{type(e).__name__}: {e}"[:200]
            log.warning("bedrock explain failed, using mock text: %s", error)
            engine = "mock-fallback"
    out = {"text": text, "engine": engine, "latency_ms": round((time.perf_counter() - start) * 1000)}
    if error:
        out["engine_error"] = error
    return out
