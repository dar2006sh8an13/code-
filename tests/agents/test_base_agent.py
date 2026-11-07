"""Unit tests for BaseAgent, status enums, validation, and lifecycle methods."""

import pytest
from pydantic import BaseModel, Field

from codeagent.agents.base_agent import (
    AgentContext,
    AgentRole,
    AgentStatus,
    BaseAgent,
)


class DummyInput(BaseModel):
    query: str
    count: int = 1


class DummyOutput(BaseModel):
    response: str
    success: bool = True


class ConcreteAgent(BaseAgent):
    """Concrete test implementation of BaseAgent."""

    def __init__(self, **kwargs):
        super().__init__(
            name="TestAgent",
            role=AgentRole.CODER,
            description="Test agent instance",
            input_schema=DummyInput,
            output_schema=DummyOutput,
            **kwargs,
        )

    def execute(self, input_data, context=None):
        validated = self.validate_input(input_data)
        assert isinstance(validated, DummyInput)
        self.status = AgentStatus.COMPLETED
        return DummyOutput(response=f"Echo: {validated.query} * {validated.count}")


def test_base_agent_initialization():
    agent = ConcreteAgent()
    assert agent.name == "TestAgent"
    assert agent.role == AgentRole.CODER
    assert agent.status == AgentStatus.IDLE
    assert agent.agent_id.startswith("coder_")
    assert agent.timeout_seconds == 300.0


def test_base_agent_input_validation():
    agent = ConcreteAgent()
    # Dict input
    valid_dict = agent.validate_input({"query": "hello", "count": 3})
    assert isinstance(valid_dict, DummyInput)
    assert valid_dict.query == "hello"
    assert valid_dict.count == 3

    # Model input
    valid_model = agent.validate_input(DummyInput(query="world"))
    assert valid_model.query == "world"

    # Invalid input
    with pytest.raises(Exception):
        agent.validate_input({"invalid_key": 123})


def test_base_agent_output_validation():
    agent = ConcreteAgent()
    # Valid output
    out = agent.validate_output({"response": "done", "success": True})
    assert isinstance(out, DummyOutput)
    assert out.response == "done"

    # Invalid output
    with pytest.raises(Exception):
        agent.validate_output(12345)


def test_base_agent_lifecycle_and_reset():
    agent = ConcreteAgent()
    agent.initialize()
    assert agent.status == AgentStatus.IDLE

    out = agent.execute({"query": "ping", "count": 2})
    assert out.response == "Echo: ping * 2"
    assert agent.get_status() == AgentStatus.COMPLETED

    agent.cancel()
    assert agent.get_status() == AgentStatus.CANCELLED

    agent.reset()
    assert agent.get_status() == AgentStatus.IDLE


def test_base_agent_metadata_dict():
    agent = ConcreteAgent()
    info = agent.to_info_dict()
    assert info["name"] == "TestAgent"
    assert info["role"] == "coder"
    assert info["input_schema"] == "DummyInput"
    assert info["output_schema"] == "DummyOutput"

