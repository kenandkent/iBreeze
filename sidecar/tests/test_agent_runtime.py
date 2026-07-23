"""Agent Runtime domain service tests."""
import pytest
from ibreeze.agent_runtime import (
    register_agent,
    list_agents,
    get_agent_status,
    run_agent,
    stop_agent,
    get_run_history,
)


@pytest.fixture
def registered_agent():
    register_agent(agent_id="agent-1", name="Helper", model="gpt-4")
    return "agent-1"


def test_run_agent(registered_agent):
    run = run_agent(agent_id=registered_agent, user_id="user-1", message="Hello")
    assert run.agent_id == "agent-1"
    assert run.user_id == "user-1"
    assert run.response is not None
    assert "Hello" in run.response
    assert run.status == "completed"


def test_run_nonexistent_agent():
    with pytest.raises(KeyError, match="Agent 不存在"):
        run_agent(agent_id="no-such-agent", user_id="u1", message="Hi")


def test_list_agents(registered_agent):
    agents = list_agents()
    ids = [a.id for a in agents]
    assert "agent-1" in ids


def test_get_agent(registered_agent):
    agent = get_agent_status(registered_agent)
    assert agent.id == "agent-1"
    assert agent.name == "Helper"
    assert agent.model == "gpt-4"
    assert agent.status == "idle"


def test_get_agent_not_found():
    with pytest.raises(KeyError, match="Agent 不存在"):
        get_agent_status("no-such-agent")


def test_stop_agent(registered_agent):
    import ibreeze.agent_runtime as rt
    rt._agents[registered_agent]["status"] = "running"
    stop_agent(registered_agent)
    agent = get_agent_status(registered_agent)
    assert agent.status == "idle"


def test_stop_nonexistent_agent():
    with pytest.raises(KeyError, match="Agent 不存在"):
        stop_agent("no-such-agent")
