"""Unified Git coordinator facade connecting detection, status, diff, branch, and commit managers."""

from pathlib import Path
from typing import Callable, List, Optional, Union

from codeagent.config.settings import Settings, get_settings
from codeagent.git.branch_manager import BranchManager, BranchOperationResult, GitBranchListResult
from codeagent.git.commit_manager import CommitManager, CommitResult
from codeagent.git.diff_manager import DiffManager, GitDiffResult
from codeagent.git.repo_detector import GitRepoInfo, RepoDetector
from codeagent.git.status_manager import GitStatusReport, StatusManager


class GitManager:
    """Central coordinator for Git operations with security boundary enforcement."""

    def __init__(
        self,
        workspace_root: Optional[Union[str, Path]] = None,
        settings: Optional[Settings] = None,
        approval_callback: Optional[Callable[[str, dict], bool]] = None,
    ) -> None:
        """Initialize GitManager."""
        self.settings = settings or get_settings()
        self.workspace_root = Path(workspace_root or self.settings.workspace_root or Path.cwd()).resolve()
        self.approval_callback = approval_callback

        self.detector = RepoDetector(self.workspace_root)
        self.status_mgr = StatusManager(self.workspace_root, self.detector)
        self.diff_mgr = DiffManager(self.workspace_root, self.detector)
        self.branch_mgr = BranchManager(
            self.workspace_root,
            self.detector,
            self.status_mgr,
            approval_callback=self.approval_callback,
        )
        self.commit_mgr = CommitManager(
            self.workspace_root,
            self.detector,
            self.status_mgr,
            self.diff_mgr,
            approval_callback=self.approval_callback,
            scan_secrets=self.settings.secret_scan_before_commit,
        )

    def is_git_enabled(self) -> bool:
        """Check whether Git integration is enabled in settings."""
        return self.settings.git_enabled

    def get_repository_info(self, target_path: Optional[Union[str, Path]] = None) -> GitRepoInfo:
        """Inspect repository status at target path."""
        return self.detector.detect_repository(target_path)

    def get_status(self, cwd: Optional[Path] = None) -> GitStatusReport:
        """Retrieve structured Git status."""
        return self.status_mgr.get_status(cwd)

    def get_diff(
        self,
        staged: bool = False,
        file_path: Optional[str] = None,
        cwd: Optional[Path] = None,
    ) -> GitDiffResult:
        """Generate structured Git diff with secret scrubbing."""
        return self.diff_mgr.get_diff(staged=staged, file_path=file_path, cwd=cwd)

    def list_branches(self, cwd: Optional[Path] = None) -> GitBranchListResult:
        """List local branches."""
        return self.branch_mgr.list_branches(cwd)

    def create_branch(
        self,
        branch_name: str,
        switch: bool = False,
        cwd: Optional[Path] = None,
    ) -> BranchOperationResult:
        """Create a new branch with validation and approval."""
        return self.branch_mgr.create_branch(branch_name, switch=switch, cwd=cwd)

    def switch_branch(
        self,
        branch_name: str,
        cwd: Optional[Path] = None,
    ) -> BranchOperationResult:
        """Switch branches with dirty-tree safety checks."""
        return self.branch_mgr.switch_branch(branch_name, cwd=cwd)

    def stage_files(
        self,
        files: List[str],
        cwd: Optional[Path] = None,
    ) -> List[str]:
        """Stage explicit files."""
        return self.commit_mgr.stage_explicit_files(files, cwd=cwd)

    def commit_changes(
        self,
        files_to_stage: Optional[List[str]] = None,
        commit_message: Optional[str] = None,
        cwd: Optional[Path] = None,
    ) -> CommitResult:
        """Execute full controlled commit workflow with secret scan and hash verification."""
        return self.commit_mgr.commit_changes(
            files_to_stage=files_to_stage,
            commit_message=commit_message,
            cwd=cwd,
        )
