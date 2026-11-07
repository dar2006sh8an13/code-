"""Git repository detection and workspace boundary validation."""

import os
from pathlib import Path
import shutil
import subprocess
from typing import Optional, Union
from pydantic import BaseModel, Field

from codeagent.filesystem.path_validator import PathValidator, WorkspaceSecurityError


class GitExecutionError(Exception):
    """Base exception for Git command execution failures."""
    pass


class GitNotInstalledError(GitExecutionError):
    """Raised when the git executable cannot be located on system PATH."""
    pass


class NotAGitRepositoryError(GitExecutionError):
    """Raised when an operation targets a path that is not a Git repository."""
    pass


class GitSecurityError(GitExecutionError):
    """Raised when a Git operation attempts to breach workspace boundaries."""
    pass


class GitRepoInfo(BaseModel):
    """Structured information describing a detected Git repository."""

    is_git_repo: bool = False
    repo_root: Optional[str] = None
    current_branch: Optional[str] = None
    is_detached_head: bool = False
    has_commits: bool = False
    head_commit_hash: Optional[str] = None
    git_version: Optional[str] = None
    is_clean: bool = True

    def to_summary(self) -> str:
        """Format an informative summary of repository state."""
        if not self.is_git_repo:
            return "Not a Git repository."
        status_line = "clean" if self.is_clean else "dirty (uncommitted changes)"
        head_str = self.head_commit_hash[:8] if self.head_commit_hash else "None (initial commit pending)"
        branch_str = self.current_branch or ("Detached HEAD" if self.is_detached_head else "Unknown")
        return (
            f"Git Repository: {self.repo_root}\n"
            f"Branch: {branch_str} | HEAD: {head_str} | Working Tree: {status_line}\n"
            f"Git Version: {self.git_version or 'Unknown'}"
        )


class RepoDetector:
    """Detects Git repository status, current branch, and enforces workspace confinement."""

    def __init__(self, workspace_root: Optional[Union[str, Path]] = None) -> None:
        """Initialize RepoDetector with workspace boundary."""
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        self.path_validator = PathValidator(self.workspace_root)

    def check_git_available(self) -> bool:
        """Check whether the git executable exists on PATH."""
        return shutil.which("git") is not None

    def get_git_version(self) -> str:
        """Retrieve the installed Git version string."""
        if not self.check_git_available():
            raise GitNotInstalledError("Git executable 'git' not found on system PATH.")
        try:
            res = subprocess.run(
                ["git", "--version"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            if res.returncode == 0:
                return res.stdout.strip()
            return "Unknown Git version"
        except Exception as e:
            raise GitExecutionError(f"Failed to query git version: {e}") from e

    def run_git_command(
        self,
        args: list[str],
        cwd: Optional[Path] = None,
        timeout: int = 30,
    ) -> subprocess.CompletedProcess:
        """Execute a git command using argument array with shell=False.

        Args:
            args: Command arguments starting after 'git' (e.g. ['status', '--porcelain']).
            cwd: Working directory (must be inside authorized workspace).
            timeout: Subprocess timeout in seconds.

        Returns:
            CompletedProcess result.
        """
        if not self.check_git_available():
            raise GitNotInstalledError("Git executable is not installed or not available on PATH.")

        target_dir = cwd or self.workspace_root
        target_dir = self.validate_within_workspace(target_dir)

        full_cmd = ["git"] + args
        try:
            res = subprocess.run(
                full_cmd,
                cwd=str(target_dir),
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
            return res
        except subprocess.TimeoutExpired as e:
            raise GitExecutionError(f"Git command timed out after {timeout}s: {' '.join(full_cmd)}") from e
        except Exception as e:
            raise GitExecutionError(f"Failed executing git command: {e}") from e

    def validate_within_workspace(self, path: Path) -> Path:
        """Ensure the target directory is within the authorized workspace."""
        resolved = path.resolve()
        try:
            resolved.relative_to(self.workspace_root)
            return resolved
        except ValueError:
            # Check if workspace_root is within resolved (e.g. when checking if workspace is inside repo)
            if self.workspace_root.is_relative_to(resolved):
                return resolved
            raise GitSecurityError(
                f"Path '{resolved}' is outside authorized workspace boundary '{self.workspace_root}'."
            )

    def detect_repository(self, target_path: Optional[Union[str, Path]] = None) -> GitRepoInfo:
        """Inspect directory and build structured GitRepoInfo."""
        dir_path = Path(target_path or self.workspace_root).resolve()
        dir_path = self.validate_within_workspace(dir_path)

        if not self.check_git_available():
            return GitRepoInfo(is_git_repo=False, git_version=None)

        git_ver = None
        try:
            git_ver = self.get_git_version()
        except GitNotInstalledError:
            return GitRepoInfo(is_git_repo=False)

        # Check if inside work tree
        res = self.run_git_command(["rev-parse", "--is-inside-work-tree"], cwd=dir_path)
        if res.returncode != 0 or res.stdout.strip() != "true":
            return GitRepoInfo(is_git_repo=False, git_version=git_ver)

        # Get repo toplevel root
        res_root = self.run_git_command(["rev-parse", "--show-toplevel"], cwd=dir_path)
        repo_root = res_root.stdout.strip() if res_root.returncode == 0 else str(dir_path)

        # Check current branch or detached HEAD
        current_branch: Optional[str] = None
        is_detached = False

        res_branch = self.run_git_command(["branch", "--show-current"], cwd=dir_path)
        if res_branch.returncode == 0 and res_branch.stdout.strip():
            current_branch = res_branch.stdout.strip()
        else:
            # Could be detached HEAD or empty repo
            res_ref = self.run_git_command(["rev-parse", "--abbrev-ref", "HEAD"], cwd=dir_path)
            ref_out = res_ref.stdout.strip()
            if ref_out == "HEAD":
                is_detached = True
                current_branch = None
            elif ref_out and res_ref.returncode == 0:
                current_branch = ref_out

        # Check if repository has commits
        has_commits = False
        head_commit_hash: Optional[str] = None

        res_head = self.run_git_command(["rev-parse", "HEAD"], cwd=dir_path)
        if res_head.returncode == 0 and res_head.stdout.strip():
            has_commits = True
            head_commit_hash = res_head.stdout.strip()

        # Check cleanliness via porcelain status
        res_status = self.run_git_command(["status", "--porcelain=v1"], cwd=dir_path)
        is_clean = (res_status.returncode == 0 and len(res_status.stdout.strip()) == 0)

        return GitRepoInfo(
            is_git_repo=True,
            repo_root=repo_root,
            current_branch=current_branch,
            is_detached_head=is_detached,
            has_commits=has_commits,
            head_commit_hash=head_commit_hash,
            git_version=git_ver,
            is_clean=is_clean,
        )
