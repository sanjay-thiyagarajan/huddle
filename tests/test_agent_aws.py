"""aws-mode agent behaviour, with the Bedrock call faked (no credentials in CI)."""
import pytest

from server import config
from server.agent import huddle_agent as ha


class FakeResult:
    def __init__(self, structured_output):
        self.structured_output = structured_output


class FakeAgent:
    """Records every prompt it is given and returns a canned structured output."""
    prompts: list[str] = []

    def __init__(self, system_prompt, output):
        self.system_prompt, self.output = system_prompt, output

    def __call__(self, prompt, structured_output_model=None):
        FakeAgent.prompts.append(prompt)
        out = self.output
        if callable(out):
            out = out()
        return FakeResult(out)


@pytest.fixture
def aws(monkeypatch):
    monkeypatch.setattr(config, "MODE", "aws")
    FakeAgent.prompts = []
    return monkeypatch


def test_parse_uses_bedrock_and_sees_only_this_persons_words(aws):
    aws.setattr(ha, "_make_agent", lambda system: FakeAgent(
        system, ha.CareParse(hours_per_week=10, dollars_per_month=400, dealbreakers=["nights"])))
    out = ha.parse_with_engine("care", "ten hours, 400 a month, not nights")
    assert out["engine"] == "bedrock" and out["draft"]["hours_per_week"] == 10
    assert out["missing"] == [] and out["followup"] is None and "latency_ms" in out
    assert len(FakeAgent.prompts) == 1 and "ten hours" in FakeAgent.prompts[0]


def test_missing_fields_are_recomputed_not_trusted(aws):
    aws.setattr(ha, "_make_agent", lambda system: FakeAgent(
        system, ha.CareParse(hours_per_week=10, dollars_per_month=None, followup=None)))
    out = ha.parse_with_engine("care", "about ten hours")
    assert out["missing"] == ["dollars_per_month"] and out["followup"]  # code supplies the question


def test_each_call_gets_a_fresh_agent(aws):
    made = []
    aws.setattr(ha, "_make_agent", lambda system: made.append(1) or FakeAgent(
        system, ha.EverydayParse(budget_ceiling=50)))
    ha.parse_with_engine("everyday", "fifty dollars")
    ha.parse_with_engine("everyday", "fifty dollars")
    assert len(made) == 2  # no shared conversation memory between people


def test_bedrock_failure_falls_back_to_mock_and_says_so(aws):
    def boom(system):
        raise RuntimeError("no credentials")
    aws.setattr(ha, "_make_agent", boom)
    out = ha.parse_with_engine("care", "I can do maybe ten hours and $400 a month")
    assert out["engine"] == "mock-fallback" and "no credentials" in out["engine_error"]
    assert out["draft"]["hours_per_week"] == 10


def test_invalid_model_output_falls_back(aws):
    aws.setattr(ha, "_make_agent", lambda system: FakeAgent(system, None))
    assert ha.parse_with_engine("care", "ten hours and $400")["engine"] == "mock-fallback"


def test_explain_sends_only_the_aggregate_result(aws):
    result = {"mode": "everyday", "tradeoff": "Picked X.", "plan": {"name": "X"}, "warnings": [],
              "honest_limits": "never shown or attributed"}
    aws.setattr(ha, "_make_agent", lambda system: FakeAgent(system, ha.Explanation(text="Plain words.")))
    out = ha.explain(result)
    assert out == {"text": "Plain words.", "engine": "bedrock", "latency_ms": out["latency_ms"]}
    assert "budget_ceiling" not in FakeAgent.prompts[0] and "dollars_per_month" not in FakeAgent.prompts[0]


def test_mock_mode_never_touches_the_agent(monkeypatch):
    monkeypatch.setattr(config, "MODE", "mock")
    monkeypatch.setattr(ha, "_make_agent", lambda s: pytest.fail("must not build an agent in mock mode"))
    assert ha.parse_with_engine("care", "ten hours and $400")["engine"] == "mock"
    assert ha.explain({"tradeoff": "Picked X."})["engine"] == "mock"


def test_model_id_is_required_and_real_strands_agent_builds(monkeypatch):
    pytest.importorskip("strands")
    monkeypatch.delenv("HUDDLE_BEDROCK_MODEL_ID", raising=False)
    with pytest.raises(ha.AgentConfigError):
        ha._make_agent("x")
    monkeypatch.setenv("HUDDLE_BEDROCK_MODEL_ID", "example.model-id-not-called")
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    agent = ha._make_agent("system")  # builds Agent + BedrockModel; makes no AWS call
    assert type(agent).__name__ == "Agent"


def test_strands_mcp_client_discovers_and_calls_huddle_tools(live_server):
    """The Strands side of the AWS path, without Bedrock: its MCP client reaches Huddle's server over
    Streamable HTTP, sees every tool, and gets structured content back from a real call."""
    pytest.importorskip("strands")  # the optional `aws` extra
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "aws_mcp_host", Path(__file__).parent.parent / "scripts" / "aws_mcp_host.py")
    host = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(host)

    url = f"{live_server}/mcp"
    names = host.discover(url)
    assert len(names) == 25 and {"ask_household_agent", "submit_private_answer"} <= set(names)
    with host.connect(url) as client:
        name, token = host._household(client)
        state = client.call_tool_sync("t-1", "get_household", {"token": token})
    assert name == "Maya" and state["status"] == "success"
    assert state["structuredContent"]["me"]["name"] == "Maya"
