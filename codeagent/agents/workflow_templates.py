"""Standard workflow templates and configurations for autonomous multi-agent execution."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from codeagent.agents.base_agent import AgentRole


class WorkflowType(str, Enum):
    """Supported workflow template categories."""

    BUILD_PROJECT = "BUILD_PROJECT"
    FIX_BUG = "FIX_BUG"
    CODE_REVIEW = "CODE_REVIEW"
    ADD_FEATURE = "ADD_FEATURE"
    REFACTOR_PROJECT = "REFACTOR_PROJECT"
    CUSTOM = "CUSTOM"


class StepDefinition(BaseModel):
    """Specification of an orchestrated workflow phase."""

    name: str
    role: AgentRole
    description: str
    requires_approval: bool = False
    is_optional: bool = False


class WorkflowTemplate(BaseModel):
    """Definition of a standard repeatable multi-agent workflow."""

    template_type: WorkflowType
    name: str
    description: str
    steps: List[StepDefinition]
    max_retries: int = 2
    max_revisions: int = 2


WORKFLOW_TEMPLATES: Dict[WorkflowType, WorkflowTemplate] = {
    WorkflowType.BUILD_PROJECT: WorkflowTemplate(
        template_type=WorkflowType.BUILD_PROJECT,
        name="Build Project Workflow",
        description="Plan components, implement code, verify tests, debug if needed, review, and validate completion.",
        steps=[
            StepDefinition(name="Plan", role=AgentRole.PLANNER, description="Analyze requirements and build task graph"),
            StepDefinition(name="Implement", role=AgentRole.CODER, description="Create and modify project source files"),
            StepDefinition(name="Debug", role=AgentRole.DEBUGGER, description="Diagnose and repair failed tests", is_optional=True),
            StepDefinition(name="Review", role=AgentRole.REVIEWER, description="Independent quality, security, and correctness evaluation"),
        ],
    ),
    WorkflowType.FIX_BUG: WorkflowTemplate(
        template_type=WorkflowType.FIX_BUG,
        name="Fix Bug Workflow",
        description="Analyze error traceback, determine root cause, generate fix, apply patch, retest, and review.",
        steps=[
            StepDefinition(name="Diagnose", role=AgentRole.DEBUGGER, description="Locate root cause and propose fix"),
            StepDefinition(name="ApplyFix", role=AgentRole.CODER, description="Apply approved code patch and retest"),
            StepDefinition(name="Review", role=AgentRole.REVIEWER, description="Inspect patch for regressions and safety"),
        ],
    ),
    WorkflowType.CODE_REVIEW: WorkflowTemplate(
        template_type=WorkflowType.CODE_REVIEW,
        name="Code Review Workflow",
        description="Inspect source files, verify security boundaries, audit quality, and generate findings report.",
        steps=[
            StepDefinition(name="Review", role=AgentRole.REVIEWER, description="Multi-category independent code evaluation"),
        ],
    ),
    WorkflowType.ADD_FEATURE: WorkflowTemplate(
        template_type=WorkflowType.ADD_FEATURE,
        name="Add Feature Workflow",
        description="Understand feature, plan incremental tasks, implement code, test, and perform review.",
        steps=[
            StepDefinition(name="Plan", role=AgentRole.PLANNER, description="Plan incremental feature architecture"),
            StepDefinition(name="Implement", role=AgentRole.CODER, description="Write new feature code and tests"),
            StepDefinition(name="Debug", role=AgentRole.DEBUGGER, description="Fix broken tests", is_optional=True),
            StepDefinition(name="Review", role=AgentRole.REVIEWER, description="Review feature code and test coverage"),
        ],
    ),
    WorkflowType.REFACTOR_PROJECT: WorkflowTemplate(
        template_type=WorkflowType.REFACTOR_PROJECT,
        name="Refactor Project Workflow",
        description="Analyze architecture, plan refactoring, backup files, apply changes, run regressions, and review.",
        steps=[
            StepDefinition(name="Plan", role=AgentRole.PLANNER, description="Map architectural refactoring steps"),
            StepDefinition(name="Implement", role=AgentRole.CODER, description="Apply clean-code modifications"),
            StepDefinition(name="Test", role=AgentRole.CODER, description="Run comprehensive regression tests"),
            StepDefinition(name="Review", role=AgentRole.REVIEWER, description="Review refactored modules"),
        ],
    ),
}


def get_template(workflow_type: WorkflowType) -> WorkflowTemplate:
    """Lookup workflow template by enum type."""
    if workflow_type in WORKFLOW_TEMPLATES:
        return WORKFLOW_TEMPLATES[workflow_type]
    raise ValueError(f"Unknown workflow template: '{workflow_type}'")

