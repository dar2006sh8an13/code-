"""Unit tests for AgentMessage, MessageBus, subscriptions, and security checks."""

import pytest
from codeagent.agents.agent_messages import (
    AgentMessage,
    MessageBus,
    MessageSecurityError,
    MessageType,
)


def test_agent_message_creation_and_defaults():
    msg = AgentMessage(
        sender_agent_id="agent_1",
        receiver_agent_id="agent_2",
        workflow_id="wf_100",
        message_type=MessageType.TASK_ASSIGNMENT,
        payload={"task": "implement feature"},
    )
    assert msg.message_id is not None
    assert msg.correlation_id is not None
    assert msg.timestamp is not None
    assert "[TASK_ASSIGNMENT]" in msg.to_summary()


def test_message_bus_direct_routing():
    bus = MessageBus()
    received = []

    def callback(m: AgentMessage):
        received.append(m)

    bus.subscribe("agent_b", callback)

    msg = AgentMessage(
        sender_agent_id="agent_a",
        receiver_agent_id="agent_b",
        workflow_id="wf_1",
        message_type=MessageType.TASK_STARTED,
    )
    bus.publish(msg)

    assert len(received) == 1
    assert received[0].message_id == msg.message_id


def test_message_bus_broadcast_routing():
    bus = MessageBus()
    received_a = []
    received_b = []

    bus.subscribe("agent_a", lambda m: received_a.append(m))
    bus.subscribe("agent_b", lambda m: received_b.append(m))

    bcast = AgentMessage(
        sender_agent_id="coord",
        receiver_agent_id="*",
        workflow_id="wf_1",
        message_type=MessageType.WORKFLOW_UPDATE,
    )
    bus.publish(bcast)

    assert len(received_a) == 1
    assert len(received_b) == 1


def test_message_bus_impersonation_detection():
    bus = MessageBus()
    msg = AgentMessage(
        sender_agent_id="agent_a",
        receiver_agent_id="agent_b",
        workflow_id="wf_1",
        message_type=MessageType.TASK_ASSIGNMENT,
    )

    # Calling publish claiming authenticated sender is 'imposter'
    with pytest.raises(MessageSecurityError) as exc_info:
        bus.publish(msg, authenticated_sender_id="imposter")
    assert "Agent impersonation rejected" in str(exc_info.value)


def test_message_bus_history_and_filtering():
    bus = MessageBus()
    m1 = AgentMessage(
        sender_agent_id="a",
        receiver_agent_id="b",
        workflow_id="wf_1",
        task_id="t1",
        message_type=MessageType.TASK_STARTED,
    )
    m2 = AgentMessage(
        sender_agent_id="b",
        receiver_agent_id="a",
        workflow_id="wf_2",
        task_id="t2",
        message_type=MessageType.TASK_COMPLETED,
    )
    bus.publish(m1)
    bus.publish(m2)

    hist_wf1 = bus.get_history(workflow_id="wf_1")
    assert len(hist_wf1) == 1
    assert hist_wf1[0].task_id == "t1"

    hist_t2 = bus.get_history(task_id="t2")
    assert len(hist_t2) == 1
    assert hist_t2[0].workflow_id == "wf_2"

