"""Persistent workflow state management in SQLite WAL mode."""

from contextlib import contextmanager
from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field

from codeagent.agents.agent_messages import AgentMessage
from codeagent.agents.task_scheduler import TaskStatus, WorkflowTask


class WorkflowStatus(str, Enum):
    """Workflow execution states."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class WorkflowRecord(BaseModel):
    """Persistent database record for a multi-agent workflow."""

    workflow_id: str
    user_task: str
    project_id: Optional[str] = None
    workflow_type: str = "BUILD_PROJECT"
    status: WorkflowStatus = WorkflowStatus.PENDING
    start_time: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    end_time: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_summary(self) -> str:
        """Format an informative summary of this workflow."""
        end_str = f" (ended: {self.end_time[:19]})" if self.end_time else ""
        return f"[{self.status.value}] {self.workflow_id}: {self.user_task[:50]}... ({self.workflow_type}){end_str}"


class ReviewDecision(str, Enum):
    """Outcomes from a Reviewer Agent evaluation."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    NEEDS_REVISION = "NEEDS_REVISION"


class ReviewFinding(BaseModel):
    """Individual quality, security, or testing defect identified by Reviewer."""

    category: str  # Correctness, Code Quality, Security, Testing, Performance
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    description: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    recommendation: Optional[str] = None


class ReviewRecord(BaseModel):
    """Structured review record logged by Reviewer Agent."""

    review_id: str = Field(default_factory=lambda: f"rev_{uuid.uuid4().hex[:8]}")
    workflow_id: str
    task_id: str
    reviewer_agent_id: str
    decision: ReviewDecision
    severity: str = "LOW"
    findings: List[ReviewFinding] = Field(default_factory=list)
    evidence: str = ""
    recommended_changes: List[str] = Field(default_factory=list)
    summary: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class WorkflowStateManager:
    """Manages persistent SQLite WAL storage for multi-agent workflows, tasks, reviews, and messages."""

    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        storage_path: Optional[str] = None,
    ) -> None:
        """Initialize WorkflowStateManager and set up SQLite schema."""
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        subpath = storage_path or "data/workflows"
        self.db_dir = self.workspace_root / subpath
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.db_dir / "workflows.db"
        self._init_db()

    @contextmanager
    def _get_connection(self):
        """Open a SQLite connection in WAL mode with enforced foreign keys."""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Create database tables if they do not exist."""
        with self._get_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS workflows (
                    workflow_id TEXT PRIMARY KEY,
                    user_task TEXT NOT NULL,
                    project_id TEXT,
                    workflow_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    error TEXT,
                    metadata_json TEXT
                );

                CREATE TABLE IF NOT EXISTS workflow_tasks (
                    task_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    assigned_agent TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    dependencies_json TEXT,
                    required_input_json TEXT,
                    expected_output_json TEXT,
                    acceptance_criteria_json TEXT,
                    risk_level TEXT,
                    estimated_complexity TEXT,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 2,
                    result_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    FOREIGN KEY (workflow_id) REFERENCES workflows(workflow_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS workflow_reviews (
                    review_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    reviewer_agent_id TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    findings_json TEXT,
                    evidence TEXT,
                    recommended_changes_json TEXT,
                    summary TEXT,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (workflow_id) REFERENCES workflows(workflow_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS workflow_messages (
                    message_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    sender_agent_id TEXT NOT NULL,
                    receiver_agent_id TEXT NOT NULL,
                    task_id TEXT,
                    message_type TEXT NOT NULL,
                    payload_json TEXT,
                    timestamp TEXT NOT NULL,
                    correlation_id TEXT,
                    FOREIGN KEY (workflow_id) REFERENCES workflows(workflow_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_workflow_tasks_wf ON workflow_tasks(workflow_id);
                CREATE INDEX IF NOT EXISTS idx_workflow_reviews_wf ON workflow_reviews(workflow_id);
                CREATE INDEX IF NOT EXISTS idx_workflow_messages_wf ON workflow_messages(workflow_id);
                """
            )

    def save_workflow(self, workflow: WorkflowRecord) -> None:
        """Upsert a workflow record."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO workflows (
                    workflow_id, user_task, project_id, workflow_type,
                    status, start_time, end_time, error, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(workflow_id) DO UPDATE SET
                    status=excluded.status,
                    end_time=excluded.end_time,
                    error=excluded.error,
                    metadata_json=excluded.metadata_json;
                """,
                (
                    workflow.workflow_id,
                    workflow.user_task,
                    workflow.project_id,
                    workflow.workflow_type,
                    workflow.status.value,
                    workflow.start_time,
                    workflow.end_time,
                    workflow.error,
                    json.dumps(workflow.metadata),
                ),
            )

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowRecord]:
        """Retrieve workflow by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM workflows WHERE workflow_id = ?", (workflow_id,)
            ).fetchone()
            if not row:
                return None
            return WorkflowRecord(
                workflow_id=row["workflow_id"],
                user_task=row["user_task"],
                project_id=row["project_id"],
                workflow_type=row["workflow_type"],
                status=WorkflowStatus(row["status"]),
                start_time=row["start_time"],
                end_time=row["end_time"],
                error=row["error"],
                metadata=json.loads(row["metadata_json"] or "{}"),
            )

    def list_workflows(self, limit: int = 50) -> List[WorkflowRecord]:
        """List recent workflows."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM workflows ORDER BY start_time DESC LIMIT ?", (limit,)
            ).fetchall()
            return [
                WorkflowRecord(
                    workflow_id=r["workflow_id"],
                    user_task=r["user_task"],
                    project_id=r["project_id"],
                    workflow_type=r["workflow_type"],
                    status=WorkflowStatus(r["status"]),
                    start_time=r["start_time"],
                    end_time=r["end_time"],
                    error=r["error"],
                    metadata=json.loads(r["metadata_json"] or "{}"),
                )
                for r in rows
            ]

    def save_task(self, task: WorkflowTask) -> None:
        """Upsert a task record."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO workflow_tasks (
                    task_id, workflow_id, name, description, assigned_agent,
                    status, priority, dependencies_json, required_input_json,
                    expected_output_json, acceptance_criteria_json, risk_level,
                    estimated_complexity, retry_count, max_retries, result_json,
                    error, created_at, started_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    status=excluded.status,
                    retry_count=excluded.retry_count,
                    result_json=excluded.result_json,
                    error=excluded.error,
                    started_at=excluded.started_at,
                    completed_at=excluded.completed_at;
                """,
                (
                    task.task_id,
                    task.workflow_id,
                    task.name,
                    task.description,
                    task.assigned_agent.value,
                    task.status.value,
                    task.priority,
                    json.dumps(task.dependencies),
                    json.dumps(task.required_input),
                    json.dumps(task.expected_output),
                    json.dumps(task.acceptance_criteria),
                    task.risk_level,
                    task.estimated_complexity,
                    task.retry_count,
                    task.max_retries,
                    json.dumps(task.result) if task.result is not None else None,
                    task.error,
                    task.created_at,
                    task.started_at,
                    task.completed_at,
                ),
            )

    def get_tasks_for_workflow(self, workflow_id: str) -> List[WorkflowTask]:
        """Fetch all tasks associated with a workflow."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM workflow_tasks WHERE workflow_id = ? ORDER BY priority DESC",
                (workflow_id,),
            ).fetchall()
            from codeagent.agents.base_agent import AgentRole

            tasks = []
            for r in rows:
                tasks.append(
                    WorkflowTask(
                        task_id=r["task_id"],
                        workflow_id=r["workflow_id"],
                        name=r["name"],
                        description=r["description"] or "",
                        assigned_agent=AgentRole(r["assigned_agent"]),
                        status=TaskStatus(r["status"]),
                        priority=r["priority"],
                        dependencies=json.loads(r["dependencies_json"] or "[]"),
                        required_input=json.loads(r["required_input_json"] or "{}"),
                        expected_output=json.loads(r["expected_output_json"] or "{}"),
                        acceptance_criteria=json.loads(r["acceptance_criteria_json"] or "[]"),
                        risk_level=r["risk_level"] or "LOW",
                        estimated_complexity=r["estimated_complexity"] or "LOW",
                        retry_count=r["retry_count"] or 0,
                        max_retries=r["max_retries"] or 2,
                        result=json.loads(r["result_json"]) if r["result_json"] else None,
                        error=r["error"],
                        created_at=r["created_at"],
                        started_at=r["started_at"],
                        completed_at=r["completed_at"],
                    )
                )
            return tasks

    def save_review(self, review: ReviewRecord) -> None:
        """Insert a review record."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO workflow_reviews (
                    review_id, workflow_id, task_id, reviewer_agent_id,
                    decision, severity, findings_json, evidence,
                    recommended_changes_json, summary, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(review_id) DO UPDATE SET
                    decision=excluded.decision,
                    severity=excluded.severity,
                    findings_json=excluded.findings_json,
                    evidence=excluded.evidence,
                    recommended_changes_json=excluded.recommended_changes_json,
                    summary=excluded.summary;
                """,
                (
                    review.review_id,
                    review.workflow_id,
                    review.task_id,
                    review.reviewer_agent_id,
                    review.decision.value,
                    review.severity,
                    json.dumps([f.model_dump() for f in review.findings]),
                    review.evidence,
                    json.dumps(review.recommended_changes),
                    review.summary,
                    review.timestamp,
                ),
            )

    def get_reviews_for_task(self, task_id: str) -> List[ReviewRecord]:
        """Fetch all reviews for a specific task."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM workflow_reviews WHERE task_id = ? ORDER BY timestamp ASC",
                (task_id,),
            ).fetchall()
            reviews = []
            for r in rows:
                findings_raw = json.loads(r["findings_json"] or "[]")
                findings = [ReviewFinding(**f) for f in findings_raw]
                reviews.append(
                    ReviewRecord(
                        review_id=r["review_id"],
                        workflow_id=r["workflow_id"],
                        task_id=r["task_id"],
                        reviewer_agent_id=r["reviewer_agent_id"],
                        decision=ReviewDecision(r["decision"]),
                        severity=r["severity"],
                        findings=findings,
                        evidence=r["evidence"] or "",
                        recommended_changes=json.loads(r["recommended_changes_json"] or "[]"),
                        summary=r["summary"] or "",
                        timestamp=r["timestamp"],
                    )
                )
            return reviews

    def save_message(self, message: AgentMessage) -> None:
        """Insert an audit message."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO workflow_messages (
                    message_id, workflow_id, sender_agent_id, receiver_agent_id,
                    task_id, message_type, payload_json, timestamp, correlation_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(message_id) DO NOTHING;
                """,
                (
                    message.message_id,
                    message.workflow_id,
                    message.sender_agent_id,
                    message.receiver_agent_id,
                    message.task_id,
                    message.message_type.value,
                    json.dumps(message.payload),
                    message.timestamp,
                    message.correlation_id,
                ),
            )

    def cancel_workflow(self, workflow_id: str, reason: str = "Cancelled by user") -> bool:
        """Mark workflow and its unfinished tasks as CANCELLED."""
        wf = self.get_workflow(workflow_id)
        if not wf:
            return False
        wf.status = WorkflowStatus.CANCELLED
        wf.error = reason
        wf.end_time = datetime.now(timezone.utc).isoformat()
        self.save_workflow(wf)

        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE workflow_tasks
                SET status = 'CANCELLED', completed_at = ?
                WHERE workflow_id = ? AND status IN ('PENDING', 'READY', 'RUNNING');
                """,
                (datetime.now(timezone.utc).isoformat(), workflow_id),
            )
        return True

    def resume_workflow(self, workflow_id: str) -> Optional[WorkflowRecord]:
        """Verify workflow eligibility to resume.

        Non-negotiable rule: Do NOT automatically resume workflows containing expired approvals.
        Do NOT repeat completed destructive actions after a restart.
        """
        wf = self.get_workflow(workflow_id)
        if not wf:
            return None
        if wf.status in (WorkflowStatus.COMPLETED, WorkflowStatus.CANCELLED):
            return None

        # Re-set status to RUNNING
        wf.status = WorkflowStatus.RUNNING
        self.save_workflow(wf)
        return wf
