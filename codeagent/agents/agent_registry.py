"""Agent registry enabling discovery, lifecycle tracking, and role-based lookup."""

from typing import Dict, List, Optional
from codeagent.agents.base_agent import AgentRole, AgentStatus, BaseAgent


class AgentRegistrationError(Exception):
    """Raised when registering an agent fails."""
    pass


class AgentRegistry:
    """Central directory for discovering, registering, and managing autonomous agents."""

    def __init__(self) -> None:
        """Initialize empty AgentRegistry."""
        self._agents: Dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent, allow_override: bool = False) -> None:
        """Register an agent instance.

        Args:
            agent: Agent instance deriving from BaseAgent.
            allow_override: If True, overwrite existing agent with same ID.

        Raises:
            AgentRegistrationError: If an agent with the same ID already exists and allow_override is False.
        """
        if agent.agent_id in self._agents and not allow_override:
            raise AgentRegistrationError(
                f"Agent with ID '{agent.agent_id}' is already registered in the system."
            )
        self._agents[agent.agent_id] = agent

    def unregister(self, agent_id: str) -> bool:
        """Remove an agent by ID."""
        if agent_id in self._agents:
            del self._agents[agent_id]
            return True
        return False

    def get(self, agent_id: str) -> Optional[BaseAgent]:
        """Lookup an agent by ID."""
        return self._agents.get(agent_id)

    def get_by_role(self, role: AgentRole) -> List[BaseAgent]:
        """Find all agents matching a specialized role."""
        if role in (AgentRole.CODE, AgentRole.CODER):
            return [a for a in self._agents.values() if a.role in (AgentRole.CODE, AgentRole.CODER)]
        return [a for a in self._agents.values() if a.role == role]

    def get_primary_agent(self, role: AgentRole) -> Optional[BaseAgent]:
        """Get the primary (first registered) agent for a role."""
        matches = self.get_by_role(role)
        return matches[0] if matches else None

    def list_agents(self) -> List[BaseAgent]:
        """Return all registered agents."""
        return list(self._agents.values())

    def reset_all(self) -> None:
        """Reset all registered agents to IDLE state."""
        for agent in self._agents.values():
            agent.reset()

    def cancel_all(self) -> None:
        """Cancel execution on all registered agents."""
        for agent in self._agents.values():
            agent.cancel()

    def get_status_overview(self) -> List[Dict[str, str]]:
        """Return human-readable status summary of all agents."""
        return [
            {
                "agent_id": a.agent_id,
                "name": a.name,
                "role": a.role.value,
                "status": a.get_status().value,
                "description": a.description,
            }
            for a in self._agents.values()
        ]

