"""Agent factory instantiating and configuring specialized agents with scoped permissions."""

from pathlib import Path
from typing import Optional
from codeagent.agents.agent_messages import MessageBus
from codeagent.agents.agent_registry import AgentRegistry
from codeagent.agents.coder_agent import CoderAgent
from codeagent.agents.coordinator_agent import CoordinatorAgent
from codeagent.agents.debugger_agent import DebuggerAgent
from codeagent.agents.file_locks import FileLockManager
from codeagent.agents.planner_agent import PlannerAgent
from codeagent.agents.reviewer_agent import ReviewerAgent
from codeagent.agents.workflow_state import WorkflowStateManager
from codeagent.config.settings import Settings, get_settings
from codeagent.debugging.debugger import AutonomousDebugger
from codeagent.execution.manager import ExecutionManager
from codeagent.filesystem.manager import FilesystemManager
from codeagent.git.git_manager import GitManager
from codeagent.intelligence.project_manager import ProjectManager
from codeagent.llm.client import LLMClient
from codeagent.safety.backup_manager import SafetyBackupManager
from codeagent.safety.permission_manager import SafetyPermissionManager
from codeagent.safety.protected_paths import ProtectedPathsManager


class AgentFactory:
    """Factory creating fully wired autonomous agents configured with role-scoped tools."""

    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        settings: Optional[Settings] = None,
        llm_client: Optional[LLMClient] = None,
        message_bus: Optional[MessageBus] = None,
        registry: Optional[AgentRegistry] = None,
        state_manager: Optional[WorkflowStateManager] = None,
        file_locks: Optional[FileLockManager] = None,
    ) -> None:
        """Initialize the agent factory."""
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.settings = settings or get_settings()
        self.llm_client = llm_client
        self.message_bus = message_bus or MessageBus()
        self.registry = registry or AgentRegistry()
        self.state_manager = state_manager or WorkflowStateManager(
            workspace_root=self.workspace_root,
            storage_path=self.settings.workflow_storage_path,
        )
        self.file_locks = file_locks or FileLockManager(workspace_root=self.workspace_root)

        # Core subsystems
        self.fs_manager = FilesystemManager(settings=self.settings)
        self.exec_manager = ExecutionManager(
            settings=self.settings,
            workspace_root=self.workspace_root,
        )
        self.protected_paths = ProtectedPathsManager(workspace_root=self.workspace_root)
        self.safety_perm = SafetyPermissionManager(workspace_root=self.workspace_root)
        self.safety_backup = SafetyBackupManager(
            workspace_root=self.workspace_root,
            backup_storage_path=self.settings.backup_storage_path,
            protected_paths_mgr=self.protected_paths,
        )
        self.project_mgr = ProjectManager(settings=self.settings)
        self.git_mgr = GitManager(workspace_root=self.workspace_root, settings=self.settings)
        self.debugger = AutonomousDebugger(
            workspace_root=self.workspace_root,
            settings=self.settings,
            llm_client=self.llm_client,
            execution_manager=self.exec_manager,
            backup_manager=self.fs_manager.backup_manager,
        )

    def create_planner(self) -> PlannerAgent:
        """Create and register PlannerAgent."""
        agent = PlannerAgent(
            llm_client=self.llm_client,
            project_manager=self.project_mgr,
            settings=self.settings,
        )
        self.registry.register(agent, allow_override=True)
        return agent

    def create_coder(self) -> CoderAgent:
        """Create and register CoderAgent."""
        agent = CoderAgent(
            filesystem_manager=self.fs_manager,
            execution_manager=self.exec_manager,
            backup_manager=self.safety_backup,
            protected_paths_manager=self.protected_paths,
            file_lock_manager=self.file_locks,
            llm_client=self.llm_client,
            settings=self.settings,
        )
        self.registry.register(agent, allow_override=True)
        return agent

    create_code = create_coder

    def create_debugger(self) -> DebuggerAgent:
        """Create and register DebuggerAgent."""
        agent = DebuggerAgent(
            debugger=self.debugger,
            filesystem_manager=self.fs_manager,
            execution_manager=self.exec_manager,
            llm_client=self.llm_client,
            settings=self.settings,
        )
        self.registry.register(agent, allow_override=True)
        return agent

    def create_reviewer(self) -> ReviewerAgent:
        """Create and register ReviewerAgent."""
        agent = ReviewerAgent(
            filesystem_manager=self.fs_manager,
            git_manager=self.git_mgr,
            protected_paths_manager=self.protected_paths,
            llm_client=self.llm_client,
            settings=self.settings,
        )
        self.registry.register(agent, allow_override=True)
        return agent

    def create_coordinator(self) -> CoordinatorAgent:
        """Create CoordinatorAgent with all 4 specialized agents registered."""
        planner = self.create_planner()
        coder = self.create_coder()
        debugger = self.create_debugger()
        reviewer = self.create_reviewer()

        agent = CoordinatorAgent(
            registry=self.registry,
            message_bus=self.message_bus,
            state_manager=self.state_manager,
            file_lock_manager=self.file_locks,
            settings=self.settings,
            workspace_root=self.workspace_root,
        )
        self.registry.register(agent, allow_override=True)
        return agent

    create_code = create_coder

    def build_full_system(self) -> CoordinatorAgent:
        """Convenience method to instantiate the complete 5-agent system."""
        return self.create_coordinator()

    def create_all_agents(self) -> AgentRegistry:
        """Instantiate all 5 agents and return the populated registry."""
        self.create_coordinator()
        return self.registry


