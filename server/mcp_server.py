"""Huddle's self-hosted MCP server (Streamable HTTP, protocol 2025-11-25).

The household voice agent (Alexa+ stand-in) calls these tools. Every tool takes a signed
participant token; none returns another participant's raw answer.
"""
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from .db import get_session
from .engine import rounds

mcp = FastMCP(
    "huddle",
    instructions=(
        "Huddle asks each person privately and proposes one plan. Answers are never shown or "
        "attributed. Pass each person's own token when submitting their answer."
    ),
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
    # Local demo server: the simulator and test clients call it on localhost.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


def _run(fn, *args, **kwargs) -> dict[str, Any]:
    try:
        with get_session() as s:
            return fn(s, *args, **kwargs)
    except rounds.HuddleError as e:
        raise ValueError(f"{e.code}: {e.message}") from None


@mcp.tool()
def start_huddle(mode: str, participants: list[dict], deadline_seconds: int = 3600,
                 need: dict | None = None) -> dict[str, Any]:
    """Open a round. mode: 'everyday' or 'care'. participants: [{name, channel: voice|link}];
    the first is the host. Returns a private token (and link) per participant."""
    return _run(rounds.create_round, mode, participants, deadline_seconds, need)


@mcp.tool()
def submit_private_answer(token: str, answer: dict) -> dict[str, Any]:
    """Store one participant's private answer (validated, single-use). Include consent: true.
    Returns only whether it was stored, never any other participant's data."""
    return _run(rounds.submit_answer, token, answer)


@mcp.tool()
def get_group_result(token: str) -> dict[str, Any]:
    """Aggregate, unattributed result once the round is closed; otherwise {ready: false}."""
    return _run(rounds.get_result, token)


@mcp.tool()
def close_round(token: str) -> dict[str, Any]:
    """Host only: close now. Non-responders get defaults and the result says so."""
    return _run(rounds.close_round, token)


@mcp.tool()
def nudge_pending(token: str) -> dict[str, Any]:
    """Host only: names of people who have not answered yet (never their values)."""
    return _run(rounds.nudge_pending, token)


@mcp.tool()
def submit_checkin(token: str, score: int) -> dict[str, Any]:
    """Day-after check-in once the round is closed: how comfortable are you with the plan (1-5)?
    Private and single-use. The group only ever sees an unattributed summary."""
    return _run(rounds.submit_checkin, token, score)
