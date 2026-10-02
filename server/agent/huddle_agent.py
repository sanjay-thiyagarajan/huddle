"""The household agent (Alexa+ stand-in).

* `call_tool` reaches Huddle's MCP server over Streamable HTTP, at runtime, like any MCP host.
* `parse_utterance` turns one person's words into a structured draft. In HUDDLE_MODE=mock it is
  a deterministic keyword parser (no credentials); the Bedrock/Strands version replaces it in aws mode.
  It is invoked per person with only that person's input, and never sees other answers.
"""
import os
import re
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

TOOLS = {"start_huddle", "submit_private_answer", "get_group_result", "close_round", "nudge_pending"}


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

_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen twenty".split())}
_NEG = re.compile(r"\b(not|no|can'?t|cannot|won'?t|never|avoid|hate|dislike|without|nothing)\b", re.I)

_EVERYDAY_WORDS = {
    "outdoors": r"outdoor|outside|hik", "crowds": r"crowd", "long_drive": r"long drive|far drive",
    "early_start": r"early", "physical": r"physical|strenuous", "alcohol": r"alcohol|drink|wine",
    "active": r"active|sport", "relaxed": r"relax|chill|easy", "foodie": r"food|eat|brunch|dinner",
    "cultural": r"museum|culture|art", "social": r"social|friends|group", "adventurous": r"advent|thrill",
}
_CARE_WORDS = {
    "nights": r"night|overnight", "transport": r"transport|driv", "appointments": r"appointment",
    "finances": r"financ|paperwork|bills", "checkins": r"check-?in|phone call|calls",
    "far_away": r"far away|live far|another city|out of town|different city",
}


def _num(token: str) -> float | None:
    token = token.lower().replace(",", "")
    if re.fullmatch(r"\d+(\.\d+)?", token):
        return float(token)
    return float(_WORDS[token]) if token in _WORDS else None


_NUMBER = r"(\d[\d,]*(?:\.\d+)?|" + "|".join(sorted(_WORDS, key=len, reverse=True)) + r")"


def _clauses(text: str) -> list[str]:
    return [c.strip() for c in re.split(r"[,.;]|\bbut\b|\band\b(?= (?:not|no|never|can))", text) if c.strip()]


def parse_utterance(mode: str, text: str) -> dict:
    """Return {draft, missing, followup}. Negated clauses become dealbreakers, others preferences."""
    if mode == "care":
        return _parse_care(text)
    return _parse_everyday(text)


def _parse_everyday(text: str) -> dict:
    draft: dict = {"budget_ceiling": None, "vibe": [], "must_haves": [], "dealbreakers": []}
    pattern = (rf"\$\s*{_NUMBER}|{_NUMBER}\s*(?:dollars|bucks)"
               rf"|(?:under|up to|max|budget(?: of)?)\s*\$?{_NUMBER}")
    m = re.search(pattern, text, re.I)
    if m:
        draft["budget_ceiling"] = _num(next(g for g in m.groups() if g))
    for clause in _clauses(text):
        neg = bool(_NEG.search(clause))
        for key, pat in _EVERYDAY_WORDS.items():
            if re.search(pat, clause, re.I):
                if neg and key in {"outdoors", "crowds", "long_drive", "early_start", "physical", "alcohol"}:
                    draft["dealbreakers"].append(key)
                elif not neg:
                    (draft["must_haves"] if re.search(r"must|need|have to", clause, re.I)
                     else draft["vibe"]).append(key)
    for k in ("vibe", "must_haves", "dealbreakers"):
        draft[k] = list(dict.fromkeys(draft[k]))
    missing = [] if draft["budget_ceiling"] is not None else ["budget_ceiling"]
    return {"draft": draft, "missing": missing,
            "followup": "What's the most you'd comfortably spend per person?" if missing else None}


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


def explain(result: dict) -> str:
    """Two plain sentences about an aggregate result. Mock mode: derived from the result itself."""
    # aws mode: replaced by the Strands agent on Bedrock (P5)
    return result.get("tradeoff") or result.get("headline", "")
