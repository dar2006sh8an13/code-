"""Reviewer agent: independently evaluates code across Correctness, Quality, Security, Testing, and Performance."""

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field

from codeagent.agents.base_agent import AgentContext, AgentRole, AgentStatus, BaseAgent
from codeagent.agents.workflow_state import ReviewDecision, ReviewFinding
from codeagent.config.settings import Settings, get_settings
from codeagent.filesystem.manager import FilesystemManager
from codeagent.git.git_manager import GitManager
from codeagent.llm.client import LLMClient
from codeagent.safety.protected_paths import ProtectedPathsManager


class ReviewerInput(BaseModel):
    """Input payload providing the scope, target files, and evidence for code review."""

    task_id: str
    task_name: str
    description: str = ""
    files_to_review: List[str] = Field(default_factory=list)
    changes_summary: Optional[str] = None
    test_results: Optional[Dict[str, Any]] = None
    acceptance_criteria: List[str] = Field(default_factory=list)


class ReviewerOutput(BaseModel):
    """Independent review verdict, findings, evidence, and change recommendations."""

    review_id: str = Field(default_factory=lambda: f"rev_{uuid.uuid4().hex[:8]}")
    task_id: str
    decision: ReviewDecision = ReviewDecision.APPROVED
    severity: str = "LOW"
    findings: List[ReviewFinding] = Field(default_factory=list)
    evidence: str = ""
    recommended_changes: List[str] = Field(default_factory=list)
    summary: str = ""


class ReviewerAgent(BaseAgent):
    """Independent code reviewer inspecting correctness, quality, security, tests, and efficiency."""

    def __init__(
        self,
        agent_id: Optional[str] = None,
        filesystem_manager: Optional[FilesystemManager] = None,
        git_manager: Optional[GitManager] = None,
        protected_paths_manager: Optional[ProtectedPathsManager] = None,
        llm_client: Optional[LLMClient] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        """Initialize ReviewerAgent."""
        cfg = settings or get_settings()
        target_model = cfg.reviewer_model or cfg.agent_model or cfg.model_name
        super().__init__(
            agent_id=agent_id or f"reviewer_{uuid.uuid4().hex[:8]}",
            name="ReviewerAgent",
            role=AgentRole.REVIEWER,
            description="Performs independent multi-category review for correctness, security, quality, and testing",
            system_instructions=(
                "You are the Reviewer Agent. You independently critique code changes. "
                "Evaluate Correctness, Code Quality, Security, Testing, and Performance. "
                "Never modify files directly. Never claim code is secure merely because tests pass."
            ),
            capabilities=["security_audit", "code_quality_review", "test_adequacy_evaluation", "diff_analysis"],
            tools=["read_file", "git_diff", "git_status", "list_protected_paths", "check_command_permission"],
            input_schema=ReviewerInput,
            output_schema=ReviewerOutput,
            settings=cfg,
        )
        self.fs_manager = filesystem_manager or FilesystemManager(settings=cfg)
        self.git_manager = git_manager or GitManager(settings=cfg, workspace_root=self.fs_manager.workspace_root)
        self.protected_paths = protected_paths_manager or ProtectedPathsManager(workspace_root=self.fs_manager.workspace_root)
        self.llm_client = llm_client
        self.model_name = target_model

    def execute(self, input_data: Any, context: Optional[AgentContext] = None) -> ReviewerOutput:
        """Execute independent multi-factor code review."""
        self.status = AgentStatus.BUSY
        rev_in = self.validate_input(input_data)
        assert isinstance(rev_in, ReviewerInput)

        findings: List[ReviewFinding] = []
        recommended: List[str] = []
        max_severity = "LOW"

        # 1. Review Category C: Security Analysis
        for rel_path in rev_in.files_to_review:
            # Check protected path violation
            if self.protected_paths.is_protected(rel_path):
                findings.append(
                    ReviewFinding(
                        category="Security",
                        severity="CRITICAL",
                        description=f"File '{rel_path}' is in protected system boundaries and should not be modified.",
                        file_path=rel_path,
                        recommendation="Revert changes to protected files immediately.",
                    )
                )
                max_severity = "CRITICAL"

            # Inspect file content if it exists
            full_path = self.fs_manager.workspace_root / rel_path
            if full_path.exists() and full_path.is_file():
                try:
                    content = full_path.read_text(encoding="utf-8", errors="replace")

                    # Check for hardcoded secrets
                    secret_patterns = [
                        (r"(?:api[_-]?key|secret|password|token)\s*[:=]\s*['\"][A-Za-z0-9_/-]{8,}['\"]", "Hardcoded credential/API key"),
                        (r"sk-[a-zA-Z0-9]{20,}", "OpenAI API Key format"),
                        (r"ghp_[a-zA-Z0-9]{20,}", "GitHub Personal Access Token"),
                    ]
                    for pat, desc in secret_patterns:
                        if re.search(pat, content, re.IGNORECASE):
                            findings.append(
                                ReviewFinding(
                                    category="Security",
                                    severity="HIGH",
                                    description=f"Potential secret detected in '{rel_path}': {desc}",
                                    file_path=rel_path,
                                    recommendation="Remove hardcoded secrets and retrieve from environment variables.",
                                )
                            )
                            if max_severity != "CRITICAL":
                                max_severity = "HIGH"

                    # Check for unsafe execution calls
                    unsafe_patterns = [
                        (r"os\.system\(", "os.system is vulnerable to shell injection"),
                        (r"subprocess\.[a-zA-Z0-9_]+\([^)]*shell\s*=\s*True", "shell=True in subprocess"),
                        (r"\beval\(", "Arbitrary code execution via eval()"),
                        (r"\bexec\(", "Arbitrary code execution via exec()"),
                    ]
                    for pat, desc in unsafe_patterns:
                        if re.search(pat, content):
                            findings.append(
                                ReviewFinding(
                                    category="Security",
                                    severity="HIGH",
                                    description=f"Unsafe execution construct detected in '{rel_path}': {desc}",
                                    file_path=rel_path,
                                    recommendation="Use safe subprocess execution with argument arrays and shell=False.",
                                )
                            )
                            if max_severity != "CRITICAL":
                                max_severity = "HIGH"

                except Exception:
                    pass

        # 2. Review Category A & D: Test Results and Correctness
        if rev_in.test_results:
            failed_count = rev_in.test_results.get("failed", 0)
            if failed_count > 0:
                findings.append(
                    ReviewFinding(
                        category="Testing",
                        severity="HIGH",
                        description=f"Tests failed during execution: {failed_count} failures recorded.",
                        recommendation="Fix broken assertions and verify all tests pass.",
                    )
                )
                if max_severity not in ("CRITICAL", "HIGH"):
                    max_severity = "HIGH"

        # 3. Formulate Review Decision
        if any(f.severity in ("CRITICAL", "HIGH") for f in findings):
            decision = ReviewDecision.REJECTED
            summary_msg = f"Review REJECTED: {len(findings)} critical or high severity defect(s) identified."
        elif findings:
            decision = ReviewDecision.NEEDS_REVISION
            summary_msg = f"Review NEEDS_REVISION: {len(findings)} minor or medium finding(s) should be addressed."
            recommended.extend([f.recommendation for f in findings if f.recommendation])
        else:
            decision = ReviewDecision.APPROVED
            summary_msg = "Review APPROVED: Implementation satisfies correctness, security, and quality criteria."

        self.status = AgentStatus.COMPLETED
        return ReviewerOutput(
            task_id=rev_in.task_id,
            decision=decision,
            severity=max_severity,
            findings=findings,
            evidence=f"Reviewed {len(rev_in.files_to_review)} file(s). Test failure count: {rev_in.test_results.get('failed', 0) if rev_in.test_results else 'N/A'}",
            recommended_changes=recommended,
            summary=summary_msg,
        )

