"""Huddle's self-hosted MCP server (Streamable HTTP, protocol 2025-11-25).

The household voice agent (Alexa+ stand-in) calls these tools. Every tool takes a signed
participant token; none returns another participant's raw answer.
"""

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from .db import get_session
from .engine import home, rounds, schedule_service

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
def start_huddle(
    mode: str, participants: list[dict], deadline_seconds: int = 3600, need: dict | None = None
) -> dict[str, Any]:
    """Open a round. mode: 'care', 'everyday' or 'trip'. participants: [{name, channel: voice|link,
    email (optional, for reminders; only add it if they agreed)}]; the first is the host. Returns a
    private token (and link) per participant. Emails are never returned."""
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
    """Host only: remind everyone who hasn't answered, now. Delivery is reported per person and channel
    (in-app always; email only if configured and given). Nobody is nudged twice within 10 minutes."""
    return _run(rounds.nudge_pending, token)


@mcp.tool()
def submit_checkin(token: str, score: int) -> dict[str, Any]:
    """Day-after check-in once the round is closed: how comfortable are you with the plan (1-5)?
    Private and single-use. The group only ever sees an unattributed summary."""
    return _run(rounds.submit_checkin, token, score)


@mcp.tool()
def revisit_round(
    token: str, need: dict | None = None, deadline_seconds: int = 3600, mode: str | None = None
) -> dict[str, Any]:
    """Host only, after a round closes: open the household's next round for the same people.
    mode defaults to the same decision (a follow-up); pass another mode (care, everyday, trip) to
    start a different decision for the same family. Nothing private carries over. Returns fresh tokens."""
    return _run(rounds.revisit_round, token, need, deadline_seconds, None, mode)


# ---- the household: chores planned fairly, week after week ----------------------------------------------------


@mcp.tool()
def create_household(name: str, members: list[dict]) -> dict[str, Any]:
    """Create a household of 2 to 6 people: [{name, email (optional, for reminders; only if they agreed)}].
    The first member is the admin. Returns a private token per member. Availability, preferences and skills
    are each member's own and stay private."""
    return _run(home.create_household, name, members)


@mcp.tool()
def get_household(token: str) -> dict[str, Any]:
    """This week's picture for the caller: the shared chores and plan (who owns what, an aggregate fairness
    report) plus only the caller's own private profile, offers and load."""
    return _run(home.get_state, token)


@mcp.tool()
def set_my_profile(token: str, changes: dict) -> dict[str, Any]:
    """Private to the caller: availability (minutes of chores a week), prefs ({category: love|ok|avoid|cannot}),
    skills ({category: 0|1|2}), learn (categories), keywords (things they know, like 'plumbing'),
    exempt_this_week (limited to 2 weeks in any 8, so the load stays fair)."""
    return _run(home.set_profile, token, changes)


@mcp.tool()
def add_chore(token: str, fields: dict | None = None, text: str | None = None) -> dict[str, Any]:
    """Add a chore any time. Give fields {title, category, minutes, cadence once|daily|weekly|biweekly|monthly,
    due, heaviness, people_needed} or plain text ('clean the gutters by Saturday, about an hour') for the agent
    to understand. If this week is planned the agent asks the best-fit person; otherwise it is held for the plan."""
    return _run(home.add_chore_any, token, fields, text)


@mcp.tool()
def plan_week(token: str, week: str | None = None, replan: bool = False) -> dict[str, Any]:
    """Plan a week (Monday date; default this week) fairly from everyone's private limits. replan=true redoes
    everything not yet done and is admin-only."""
    return _run(home.plan_week, token, week, replan)


@mcp.tool()
def respond_to_assignment(
    token: str, assignment_id: int, accept: bool, reason: str | None = None
) -> dict[str, Any]:
    """Answer an offer made to the caller. Declining (reason: cannot|busy|prefer_not|other, private) makes the
    agent ask someone else."""
    return _run(home.respond, token, assignment_id, accept, reason)


@mcp.tool()
def hand_back_chore(token: str, assignment_id: int, reason: str | None = None) -> dict[str, Any]:
    """The owner can't do a planned chore after all: the agent asks the next best person."""
    return _run(home.hand_back, token, assignment_id, reason)


@mcp.tool()
def complete_chore(token: str, assignment_id: int) -> dict[str, Any]:
    """The owner marks a planned chore done."""
    return _run(home.complete, token, assignment_id)


@mcp.tool()
def week_checkin(token: str, score: int) -> dict[str, Any]:
    """Private: how did this week feel, 1 (far too heavy) to 5 (comfortable)? A heavy week lightens the next."""
    return _run(home.checkin_week, token, score)


@mcp.tool()
def ask_household_agent(token: str, utterance: str) -> dict[str, Any]:
    """Talk to the household agent in plain words: add a chore, 'what's on my plate', 'I did the bins', 'who has
    the laundry', 'hand back the laundry'. Replies never speak anyone's private preferences."""
    return _run(home.say, token, utterance)


@mcp.tool()
def start_household_decision(
    token: str,
    mode: str,
    deadline_seconds: int = 3600,
    need: dict | None = None,
    remote: list[str] | None = None,
) -> dict[str, Any]:
    """Start a family decision (mode: care, everyday or trip) for the whole household: the same people, each
    answering privately with their own link. The caller's own round token is returned; everyone else finds
    theirs in their own get_household. For care, `need` is the task list and monthly money needed."""
    return _run(home.start_decision, token, mode, deadline_seconds, need, remote)


# ---- my time: personal and family commitments in one private schedule ------------------------------------------


@mcp.tool()
def get_my_time(token: str, week: str | None = None) -> dict[str, Any]:
    """The caller's own week across family, friends, work and personal (private to them), with clashes and
    smart options for each, tentative items, their rules and any find-a-time they are invited to."""
    return _run(schedule_service.get_my_time, token, week)


@mcp.tool()
def add_commitment(token: str, fields: dict, resolution: dict | None = None) -> dict[str, Any]:
    """Add a private commitment {title, circle family|friends|work|personal, start, minutes, flexibility
    fixed|movable|optional, importance 1-3, repeat none|daily|weekly}. If it clashes, the reply lists options with
    a recommendation; call again with resolution {choice: keep_both|decide_later|drop_new|move_new|move_existing|
    drop_existing|ask_others, new_start / existing_new_start}."""
    return _run(schedule_service.add_commitment, token, fields, resolution)


@mcp.tool()
def update_commitment(
    token: str, commitment_id: str, changes: dict, occurrence: str | None = None
) -> dict[str, Any]:
    """Change or cancel one of the caller's own commitments (for a repeating one, `occurrence` is a date)."""
    return _run(schedule_service.update_commitment, token, commitment_id, changes, occurrence)


@mcp.tool()
def set_schedule_rules(token: str, changes: dict) -> dict[str, Any]:
    """Private: how the agent weighs and protects the caller's time (circle_rank, protected windows, work hours,
    max_evenings, buffer_minutes)."""
    return _run(schedule_service.set_rules, token, changes)


@mcp.tool()
def start_gathering(token: str, fields: dict) -> dict[str, Any]:
    """Find a time with household members and outside guests: {title, circle, duration_minutes, windows
    [{date_from, date_to, from, to}], members [names], guests [{name}]}. Members answer from their own schedule;
    guests get a link. The result shows the best time, never who could not make which."""
    return _run(schedule_service.start_gathering, token, fields)


@mcp.tool()
def answer_gathering(
    token: str, round_id: str, answers: dict | None = None, accept_suggestions: bool = False
) -> dict[str, Any]:
    """Answer a find-a-time privately from the caller's own schedule (accept_suggestions) or by hand."""
    return _run(schedule_service.answer_gathering, token, round_id, answers, accept_suggestions)
