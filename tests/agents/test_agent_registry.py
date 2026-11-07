"""Unit tests for AgentRegistry registration, duplicate detection, and lookup."""

import pytest
from codeagent.agents.agent_registry import AgentRegistrationError, AgentRegistry
from codeagent.agents.base_agent import AgentRole, BaseAgent


class SimpleTestAgent(BaseAgent):
    def __init__(self, agent_id: str, role: AgentRole):
        super().__init__(agent_id=agent_id, name=f"Agent_{agent_id}", role=role)

    def execute(self, input_data, context=None):
        return input_data


def test_agent_registry_crud():
    registry = AgentRegistry()
    a1 = SimpleTestAgent("planner_1", AgentRole.PLANNER)
    a2 = SimpleTestAgent("coder_1", AgentRole.CODER)

    registry.register(a1)
    registry.register(a2)

    assert registry.get("planner_1") == a1
    assert registry.get("coder_1") == a2
    assert len(registry.list_agents()) == 2

    # Unregister
    assert registry.unregister("planner_1") is True
    assert registry.get("planner_1") is None
    assert registry.unregister("planner_1") is False


def test_agent_registry_duplicate_rejection():
    registry = AgentRegistry()
    a1 = SimpleTestAgent("agent_dup", AgentRole.CODER)
    registry.register(a1)

    a2 = SimpleTestAgent("agent_dup", AgentRole.PLANNER)
    with pytest.raises(AgentRegistrationError):
        registry.register(a2, allow_override=False)

    # Allowed with override
    registry.register(a2, allow_override=True)
    assert registry.get("agent_dup").role == AgentRole.PLANNER


def test_agent_registry_role_lookup():
    registry = AgentRegistry()
    c1 = SimpleTestAgent("coder_1", AgentRole.CODER)
    c2 = SimpleTestAgent("coder_2", AgentRole.CODER)
    p1 = SimpleTestAgent("planner_1", AgentRole.PLANNER)

    registry.register(c1)
    registry.register(c2)
    registry.register(p1)

    coders = registry.get_by_role(AgentRole.CODER)
    assert len(coders) == 2
    assert registry.get_primary_agent(AgentRole.CODER) == c1

    assert registry.get_primary_agent(AgentRole.REVIEWER) is None


def test_agent_registry_status_overview():
    registry = AgentRegistry()
    c1 = SimpleTestAgent("coder_1", AgentRole.CODER)
    registry.register(c1)

    overview = registry.get_status_overview()
    assert len(overview) == 1
    assert overview[0]["role"] == "coder"
    assert overview[0]["status"] == "idle"

