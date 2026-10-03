"""A Strands agent on Amazon Bedrock acting as the MCP host, the way an Alexa+ agent would.

It is given nothing but the server's address. It discovers Huddle's tools over Streamable HTTP
(Strands' own MCP client), reads the server's instructions, and then speaks for ONE household
member with that member's own token. It never holds anyone else's token or private answer.

    make dev                                  # a server on :8000
    python scripts/aws_mcp_host.py            # discovery only: no AWS needed, no model call
    HUDDLE_BEDROCK_MODEL_ID=<id> AWS_REGION=<region> python scripts/aws_mcp_host.py --bedrock

Prints the tools the agent discovered, then (with --bedrock) each tool the model chose to call and
its reply. Without --bedrock it proves the Strands-to-MCP path only, and says so.
"""
import argparse
import os
import sys

from mcp.client.streamable_http import streamable_http_client
from strands.tools.mcp import MCPClient

TURNS = [
    "What's on my plate this week?",
    "Add a chore: fix the squeaky door, about half an hour, by Saturday.",
    "Privately: I can give about three hours to chores a week, and I'd like to avoid cooking.",
]

SYSTEM = (
    "You are a household voice assistant. You speak for one person, {name}, whose private token is "
    "{token}. Use only that token. Follow the Huddle server's rules: never say a private limit back "
    "unless asked, and never guess who set a limit. Answer in one or two short spoken sentences."
)


def connect(url: str) -> MCPClient:
    return MCPClient(lambda: streamable_http_client(url))


def discover(url: str) -> list[str]:
    """The tool names a Strands agent sees on Huddle's MCP server."""
    with connect(url) as client:
        return [t.tool_name for t in client.list_tools_sync()]


def _household(client: MCPClient) -> tuple[str, str]:
    """Set the scene with direct tool calls: a household, starter chores, a planned week."""
    made = client.call_tool_sync(
        "setup-1", "create_household",
        {"name": "Demo home", "members": [{"name": "Maya"}, {"name": "Ben"}, {"name": "Chen"}]},
    )
    me = made["structuredContent"]["members"][0]
    for i, text in enumerate(("take out the bins, 10 minutes, weekly", "cook dinner, 45 minutes, daily")):
        client.call_tool_sync(f"setup-chore-{i}", "add_chore", {"token": me["token"], "text": text})
    client.call_tool_sync("setup-plan", "plan_week", {"token": me["token"]})
    return me["name"], me["token"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("HUDDLE_MCP_URL", "http://127.0.0.1:8000/mcp"))
    ap.add_argument("--bedrock", action="store_true", help="run the model turns (needs AWS credentials)")
    args = ap.parse_args()

    with connect(args.url) as client:
        tools = client.list_tools_sync()
        print(f"Discovered {len(tools)} tools over Streamable HTTP at {args.url}:")
        print("  " + ", ".join(t.tool_name for t in tools))
        if not args.bedrock:
            print("Discovery only: no model was called. Pass --bedrock to run the agent on Amazon Bedrock.")
            return 0

        model_id = os.environ.get("HUDDLE_BEDROCK_MODEL_ID")
        if not model_id:
            print("Set HUDDLE_BEDROCK_MODEL_ID to a model id enabled in your account.", file=sys.stderr)
            return 2
        from strands import Agent
        from strands.models import BedrockModel

        name, token = _household(client)
        agent = Agent(
            model=BedrockModel(model_id=model_id, region_name=os.environ.get("AWS_REGION"), temperature=0.0),
            tools=tools,
            system_prompt=SYSTEM.format(name=name, token=token),
            callback_handler=None,
        )
        for say in TURNS:
            before = len(agent.messages)
            reply = agent(say)
            called = [
                block["toolUse"]["name"]
                for msg in agent.messages[before:]
                for block in msg.get("content", [])
                if "toolUse" in block
            ]
            print(f"\n{name}: {say}\n  tools called: {called or 'none'}\n  assistant: {str(reply).strip()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
