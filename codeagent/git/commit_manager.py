"""Controlled Git commit workflow enforcing explicit staging, secret scanning, approval gates, and commit hash verification."""

from pathlib import Path
import re
from typing import Callable, List, Optional, Union
from pydantic import BaseModel, Field

from codeagent.execution.audit_logger import SECRET_PATTERNS
from codeagent.git.diff_manager import DiffManager, GitDiffResult
from codeagent.git.repo_detector import GitExecutionError, NotAGitRepositoryError, RepoDetector
from codeagent.git.status_manager import GitStatusReport, StatusManager


class CommitValidationError(Exception):
    """Raised when commit prerequisites or validations fail."""
    pass


class SecretDetectedInCommitError(CommitValidationError):
    """Raised when sensitive secrets or credentials are found in staged changes."""
    pass


class CommitNotApprovedError(CommitValidationError):
    """Raised when human user approval is rejected for a commit."""
    pass


class CommitResult(BaseModel):
    """Verified outcome of a Git commit operation."""

    success: bool
    commit_hash: str
    branch: str
    message: str
    files_committed: List[str] = Field(default_factory=list)
    insertions: int = 0
    deletions: int = 0
    audit_id: Optional[str] = None

    def to_summary(self) -> str:
        """Format an informative summary of the verified commit."""
        short_hash = self.commit_hash[:8]
        return (
            f"Commit Successful: [{self.branch} {short_hash}]\n"
            f"Message: {self.message}\n"
            f"Files ({len(self.files_committed)}): {', '.join(self.files_committed)}\n"
            f"Diff: +{self.insertions}, -{self.deletions}"
        )


class CommitManager:
    """Orchestrates controlled Git commits with safety gates and verification."""

    def __init__(
        self,
        workspace_root: Optional[Union[str, Path]] = None,
        detector: Optional[RepoDetector] = None,
        status_manager: Optional[StatusManager] = None,
        diff_manager: Optional[DiffManager] = None,
        approval_callback: Optional[Callable[[str, dict], bool]] = None,
        scan_secrets: bool = True,
    ) -> None:
        """Initialize CommitManager."""
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        self.detector = detector or RepoDetector(self.workspace_root)
        self.status_manager = status_manager or StatusManager(self.workspace_root, self.detector)
        self.diff_manager = diff_manager or DiffManager(self.workspace_root, self.detector)
        self.approval_callback = approval_callback
        self.scan_secrets = scan_secrets

    def stage_explicit_files(
        self,
        files: List[str],
        cwd: Optional[Path] = None,
    ) -> List[str]:
        """Stage only explicitly named files. Rejects wildcards, '.', and '-A'."""
        if not files:
            raise CommitValidationError("No files specified for staging.")

        target_dir = Path(cwd or self.workspace_root).resolve()
        for f in files:
            clean_f = f.strip()
            if clean_f in (".", "-A", "--all", "*"):
                raise CommitValidationError(
                    f"Refusing to stage wildcard or entire tree '{f}'. "
                    "CodeAgent strictly requires explicit file paths."
                )

        cmd = ["add", "--"] + [f.strip() for f in files]
        res = self.detector.run_git_command(cmd, cwd=target_dir)
        if res.returncode != 0:
            raise GitExecutionError(f"Failed to stage files: {res.stderr.strip()}")

        return files

    def scan_staged_for_secrets(self, diff_text: str) -> List[str]:
        """Inspect staged diff lines for potential secret or token leaks."""
        violations: List[str] = []
        for line in diff_text.splitlines():
            # Only scan added lines in diff
            if line.startswith("+") and not line.startswith("+++"):
                added_content = line[1:].strip()
                for pattern, _ in SECRET_PATTERNS:
                    if pattern.search(added_content):
                        violations.append(f"Secret matched pattern: {pattern.pattern} in line: '{added_content[:60]}...'")
                        break
                if "[REDACTED" in added_content:
                    violations.append(f"Secret placeholder or token detected in line: '{added_content[:60]}...'")
        return violations

    def generate_commit_message_suggestion(self, staged_diff: GitDiffResult) -> str:
        """Generate a conventional commit message proposal based on changed files and diff."""
        if not staged_diff.file_diffs:
            return "chore: update project files"

        first_file = staged_diff.file_diffs[0].file_path
        ext = Path(first_file).suffix.lower()

        if "test" in first_file.lower():
            prefix = "test"
        elif ext in (".md", ".txt", ".rst"):
            prefix = "docs"
        elif any(f in first_file.lower() for f in ("setting", "config", ".env", "pyproject", "package.json")):
            prefix = "chore"
        else:
            prefix = "feat" if staged_diff.total_insertions > staged_diff.total_deletions else "fix"

        file_count = len(staged_diff.file_diffs)
        if file_count == 1:
            return f"{prefix}: update {first_file}"
        return f"{prefix}: update {file_count} files including {first_file}"

    def commit_changes(
        self,
        files_to_stage: Optional[List[str]] = None,
        commit_message: Optional[str] = None,
        cwd: Optional[Path] = None,
    ) -> CommitResult:
        """Execute full controlled commit workflow.

        Steps:
        1. Read status.
        2. Explicitly stage files if provided.
        3. Read staged diff.
        4. Secret scan.
        5. Formulate commit message.
        6. Request explicit human approval.
        7. Execute commit.
        8. Verify commit hash.
        """
        target_dir = Path(cwd or self.workspace_root).resolve()
        repo_info = self.detector.detect_repository(target_dir)
        if not repo_info.is_git_repo:
            raise NotAGitRepositoryError(f"Directory '{target_dir}' is not inside a Git repository.")

        # 1. Stage explicit files if provided
        if files_to_stage:
            self.stage_explicit_files(files_to_stage, cwd=target_dir)

        # 2. Inspect staged diff (unredacted for security scanning)
        staged_diff = self.diff_manager.get_diff(staged=True, cwd=target_dir, redact_secrets=False)
        if not staged_diff.file_diffs and staged_diff.total_files_changed == 0:
            raise CommitValidationError("No staged changes to commit. Use stage_explicit_files first.")

        # 3. Secret scan
        if self.scan_secrets:
            secret_violations = self.scan_staged_for_secrets(staged_diff.raw_diff)
            if secret_violations:
                details = "\n".join(f" - {v}" for v in secret_violations[:3])
                raise SecretDetectedInCommitError(
                    f"Refusing to commit: Staged changes contain potential secrets or credentials:\n{details}"
                )

        # 4. Message formulation
        final_message = (commit_message or "").strip()
        if not final_message:
            final_message = self.generate_commit_message_suggestion(staged_diff)

        # 5. Approval gate
        staged_names = [f.file_path for f in staged_diff.file_diffs]
        if self.approval_callback:
            approved = self.approval_callback(
                "git_commit",
                {
                    "message": final_message,
                    "staged_files": staged_names,
                    "insertions": staged_diff.total_insertions,
                    "deletions": staged_diff.total_deletions,
                    "diff_summary": staged_diff.stat_summary,
                },
            )
            if not approved:
                raise CommitNotApprovedError(f"User rejected commit with message: '{final_message}'.")

        # 6. Execute git commit
        res_commit = self.detector.run_git_command(["commit", "-m", final_message], cwd=target_dir)
        if res_commit.returncode != 0:
            raise GitExecutionError(f"git commit failed: {res_commit.stderr.strip()}")

        # 7. Verify resulting commit hash
        res_hash = self.detector.run_git_command(["rev-parse", "HEAD"], cwd=target_dir)
        if res_hash.returncode != 0 or not res_hash.stdout.strip():
            raise GitExecutionError("Commit was created but failed to verify resulting commit hash.")

        verified_hash = res_hash.stdout.strip()
        active_branch = repo_info.current_branch or "HEAD"

        return CommitResult(
            success=True,
            commit_hash=verified_hash,
            branch=active_branch,
            message=final_message,
            files_committed=staged_names,
            insertions=staged_diff.total_insertions,
            deletions=staged_diff.total_deletions,
        )
