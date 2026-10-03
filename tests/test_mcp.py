"""F1: official MCP SDK client over Streamable HTTP completes a full everyday round."""

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

MIN_PROTOCOL = "2025-11-25"  # ISO dates compare correctly as strings


def ans(budget, **kw):
    return {
        "consent": True,
        "budget_ceiling": budget,
        "vibe": kw.get("vibe", []),
        "must_haves": [],
        "dealbreakers": kw.get("deal", []),
    }


async def test_protocol_version_tools_and_full_round(live_server):
    async with streamable_http_client(f"{live_server}/mcp") as (rd, wr, _):
        async with ClientSession(rd, wr) as sess:
            init = await sess.initialize()
            assert init.protocolVersion >= MIN_PROTOCOL, init.protocolVersion
            assert init.serverInfo.name == "huddle"

            tools = {t.name for t in (await sess.list_tools()).tools}
            assert tools == {
                "start_huddle",
                "submit_private_answer",
                "get_group_result",
                "close_round",
                "nudge_pending",
                "submit_checkin",
                "revisit_round",
                "create_household",
                "get_household",
                "set_my_profile",
                "add_chore",
                "plan_week",
                "respond_to_assignment",
                "hand_back_chore",
                "complete_chore",
                "week_checkin",
                "ask_household_agent",
                "start_household_decision",
                "get_my_time",
                "add_commitment",
                "update_commitment",
                "set_schedule_rules",
                "start_gathering",
                "answer_gathering",
                "ask_schedule_agent",
            }

            r = (
                await sess.call_tool(
                    "start_huddle",
                    {
                        "mode": "everyday",
                        "participants": [
                            {"name": "Maya", "channel": "voice"},
                            {"name": "Ben", "channel": "link"},
                            {"name": "Chen"},
                        ],
                    },
                )
            ).structuredContent
            toks = {p["name"]: p["token"] for p in r["participants"]}

            pend = (await sess.call_tool("nudge_pending", {"token": toks["Maya"]})).structuredContent
            assert sorted(pend["pending"]) == ["Ben", "Chen", "Maya"]
            denied = await sess.call_tool("nudge_pending", {"token": toks["Ben"]})
            assert denied.isError  # host only

            early = (await sess.call_tool("get_group_result", {"token": toks["Ben"]})).structuredContent
            assert early["ready"] is False

            for name, a in [
                ("Maya", ans(200, vibe=["foodie"])),
                ("Ben", ans(300, vibe=["relaxed"])),
                ("Chen", ans(150, vibe=["foodie"], deal=["crowds"])),
            ]:
                out = await sess.call_tool("submit_private_answer", {"token": toks[name], "answer": a})
                assert out.structuredContent["stored"] is True

            final = (await sess.call_tool("get_group_result", {"token": toks["Ben"]})).structuredContent
            assert final["ready"] and final["result"]["plan"]["name"]
            assert final["result"]["defaults_applied"] is False


async def test_close_round_applies_defaults(live_server):
    async with streamable_http_client(f"{live_server}/mcp") as (rd, wr, _):
        async with ClientSession(rd, wr) as sess:
            await sess.initialize()
            r = (
                await sess.call_tool(
                    "start_huddle",
                    {"mode": "everyday", "participants": [{"name": "A"}, {"name": "B"}, {"name": "C"}]},
                )
            ).structuredContent
            toks = {p["name"]: p["token"] for p in r["participants"]}
            await sess.call_tool("submit_private_answer", {"token": toks["A"], "answer": ans(200)})
            res = (await sess.call_tool("close_round", {"token": toks["A"]})).structuredContent
            assert res["result"]["defaults_applied"] is True


async def test_host_guidance_titles_and_behaviour_hints(live_server):
    """What a host sees before it calls anything: instructions, a title and explicit hints per tool."""
    from typing import get_args

    from server.engine import care, everyday, trip

    async with streamable_http_client(f"{live_server}/mcp") as (rd, wr, _):
        async with ClientSession(rd, wr) as sess:
            init = await sess.initialize()
            assert "can hear" in init.instructions and "consent" in init.instructions
            tools = {t.name: t for t in (await sess.list_tools()).tools}

    assert len(tools) == 25
    hints = ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")
    for name, t in tools.items():
        assert t.title and t.description, name
        # The protocol defaults are destructive and open-world, so every hint is set explicitly.
        assert all(getattr(t.annotations, h) is not None for h in hints), name
        assert t.outputSchema, name  # structured results, not JSON in a text block
    assert {n for n, t in tools.items() if t.annotations.readOnlyHint} == {"get_household", "get_my_time"}
    assert {n for n, t in tools.items() if t.annotations.destructiveHint} == {
        "close_round",
        "plan_week",
        "update_commitment",
    }
    # Anything that can notify a person may send email (when SMTP is set and they gave an address).
    assert {n for n, t in tools.items() if t.annotations.openWorldHint} == {
        "nudge_pending",
        "add_chore",
        "plan_week",
        "respond_to_assignment",
        "hand_back_chore",
        "ask_household_agent",
        "start_household_decision",
        "start_gathering",
        "ask_schedule_agent",
    }

    # The answer shape a host needs is in the tool description, with the engines' own vocabulary.
    shape = tools["submit_private_answer"].description
    for literal in (care.Dealbreaker, everyday.Vibe, everyday.Attr, trip.Vibe, trip.Attr):
        assert all(word in shape for word in get_args(literal))
    assert "consent: true" in shape
