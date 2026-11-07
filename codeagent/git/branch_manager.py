"""Git branch management ensuring ref name validation, collision checks, and dirty-tree safety."""

from pathlib import Path
import re
from typing import Callable, List, Optional, Union
from pydantic import BaseModel, Field

from codeagent.git.repo_detector import GitExecutionError, NotAGitRepositoryError, RepoDetector
from codeagent.git.status_manager import StatusManager


class BranchValidationError(Exception):
    """Raised when a proposed Git branch name violates ref naming rules."""
    pass


class BranchCollisionError(Exception):
    """Raised when attempting to create a branch that already exists."""
    pass


class DirtyWorkingTreeError(Exception):
    """Raised when switching branches is refused due to uncommitted changes."""
    pass


class BranchNotApprovedError(Exception):
    """Raised when branch creation or switching is rejected by user approval."""
    pass


class GitBranchInfo(BaseModel):
    """Information regarding a local branch."""

    name: str
    is_current: bool = False
    commit_hash: Optional[str] = None
    commit_subject: Optional[str] = None


class GitBranchListResult(BaseModel):
    """Structured list of repository branches."""

    current_branch: Optional[str] = None
    is_detached_head: bool = False
    branches: List[GitBranchInfo] = Field(default_factory=list)

    def to_summary(self) -> str:
        """Textual summary of branches."""
        head_str = self.current_branch or ("Detached HEAD" if self.is_detached_head else "None")
        names = [b.name for b in self.branches]
        return f"Current Branch: {head_str}\nLocal Branches ({len(names)}): {', '.join(names)}"


class BranchOperationResult(BaseModel):
    """Outcome of a branch creation or checkout operation."""

    success: bool
    operation: str  # "create", "switch"
    branch_name: str
    previous_branch: Optional[str] = None
    message: str = ""


class BranchManager:
    """Manages Git local branch operations with strict validation and dirty-tree guardrails."""

    def __init__(
        self,
        workspace_root: Optional[Union[str, Path]] = None,
        detector: Optional[RepoDetector] = None,
        status_manager: Optional[StatusManager] = None,
        approval_callback: Optional[Callable[[str, dict], bool]] = None,
    ) -> None:
        """Initialize BranchManager."""
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        self.detector = detector or RepoDetector(self.workspace_root)
        self.status_manager = status_manager or StatusManager(self.workspace_root, self.detector)
        self.approval_callback = approval_callback

    @staticmethod
    def validate_branch_name(name: str) -> None:
        """Validate branch name according to git-check-ref-format specification.

        Rules:
        - Cannot be empty
        - Cannot contain whitespace, ASCII control chars, DEL
        - Cannot contain '..', '~', '^', ':', '?', '*', '['
        - Cannot begin or end with '/'
        - Cannot contain consecutive slashes '//'
        - Cannot end with '.lock'
        - Cannot start with '-'
        - Cannot be '@'
        """
        if not name or not name.strip():
            raise BranchValidationError("Branch name cannot be empty.")

        clean = name.strip()
        if clean.startswith("-"):
            raise BranchValidationError(f"Invalid branch name '{name}': Cannot start with a hyphen.")

        if any(c.isspace() for c in clean):
            raise BranchValidationError(f"Invalid branch name '{name}': Cannot contain whitespace.")

        # Disallowed characters or substrings
        disallowed = ["..", "~", "^", ":", "?", "*", "[", "\\", "@{"]
        for d in disallowed:
            if d in clean:
                raise BranchValidationError(f"Invalid branch name '{name}': Contains disallowed character or sequence '{d}'.")

        if clean.startswith("/") or clean.endswith("/"):
            raise BranchValidationError(f"Invalid branch name '{name}': Cannot start or end with a slash.")

        if "//" in clean:
            raise BranchValidationError(f"Invalid branch name '{name}': Cannot contain consecutive slashes '//'.")

        if clean.endswith(".lock"):
            raise BranchValidationError(f"Invalid branch name '{name}': Cannot end with '.lock'.")

        if clean == "@" or clean == "HEAD":
            raise BranchValidationError(f"Invalid branch name '{name}': Reserved ref name.")

    def list_branches(self, cwd: Optional[Path] = None) -> GitBranchListResult:
        """List all local branches in the repository."""
        target_dir = Path(cwd or self.workspace_root).resolve()
        repo_info = self.detector.detect_repository(target_dir)
        if not repo_info.is_git_repo:
            raise NotAGitRepositoryError(f"Directory '{target_dir}' is not inside a Git repository.")

        # If repo has no commits, git branch --list returns empty
        if not repo_info.has_commits:
            curr = repo_info.current_branch or "main"
            return GitBranchListResult(
                current_branch=curr,
                is_detached_head=False,
                branches=[GitBranchInfo(name=curr, is_current=True)],
            )

        res = self.detector.run_git_command(["branch", "--list", "-v", "--no-abbrev"], cwd=target_dir)
        if res.returncode != 0:
            raise GitExecutionError(f"Failed to list branches: {res.stderr.strip()}")

        branches: List[GitBranchInfo] = []
        current_branch: Optional[str] = repo_info.current_branch

        for line in res.stdout.splitlines():
            line_str = line.strip()
            if not line_str:
                continue

            is_curr = line.startswith("*")
            content = line[2:].strip()
            parts = content.split(maxsplit=2)
            bname = parts[0]
            chash = parts[1] if len(parts) > 1 else None
            subj = parts[2] if len(parts) > 2 else None

            if is_curr:
                if "(HEAD detached" in line:
                    repo_info.is_detached_head = True
                    current_branch = None
                else:
                    current_branch = bname

            branches.append(
                GitBranchInfo(
                    name=bname,
                    is_current=is_curr,
                    commit_hash=chash,
                    commit_subject=subj,
                )
            )

        return GitBranchListResult(
            current_branch=current_branch,
            is_detached_head=repo_info.is_detached_head,
            branches=branches,
        )

    def create_branch(
        self,
        branch_name: str,
        switch: bool = False,
        cwd: Optional[Path] = None,
    ) -> BranchOperationResult:
        """Create a new branch with validation and approval."""
        self.validate_branch_name(branch_name)
        target_dir = Path(cwd or self.workspace_root).resolve()
        repo_info = self.detector.detect_repository(target_dir)
        if not repo_info.is_git_repo:
            raise NotAGitRepositoryError(f"Directory '{target_dir}' is not inside a Git repository.")

        # Check collisions
        branch_list = self.list_branches(cwd=target_dir)
        existing_names = [b.name for b in branch_list.branches]
        if branch_name in existing_names:
            raise BranchCollisionError(f"Branch '{branch_name}' already exists in this repository.")

        # Check approval
        if self.approval_callback:
            approved = self.approval_callback(
                "git_create_branch",
                {"branch_name": branch_name, "switch": switch, "repo": repo_info.repo_root},
            )
            if not approved:
                raise BranchNotApprovedError(f"User rejected creation of branch '{branch_name}'.")

        cmd = ["switch", "-c", branch_name] if switch else ["branch", branch_name]
        res = self.detector.run_git_command(cmd, cwd=target_dir)
        if res.returncode != 0:
            raise GitExecutionError(f"Failed to create branch '{branch_name}': {res.stderr.strip()}")

        msg = f"Created and switched to branch '{branch_name}'." if switch else f"Created branch '{branch_name}'."
        return BranchOperationResult(
            success=True,
            operation="create_and_switch" if switch else "create",
            branch_name=branch_name,
            previous_branch=repo_info.current_branch,
            message=msg,
        )

    def switch_branch(
        self,
        branch_name: str,
        cwd: Optional[Path] = None,
    ) -> BranchOperationResult:
        """Switch to an existing branch with dirty-tree safety checks."""
        self.validate_branch_name(branch_name)
        target_dir = Path(cwd or self.workspace_root).resolve()
        repo_info = self.detector.detect_repository(target_dir)
        if not repo_info.is_git_repo:
            raise NotAGitRepositoryError(f"Directory '{target_dir}' is not inside a Git repository.")

        if repo_info.current_branch == branch_name:
            return BranchOperationResult(
                success=True,
                operation="switch",
                branch_name=branch_name,
                previous_branch=branch_name,
                message=f"Already on branch '{branch_name}'.",
            )

        # Check dirty tree: prevent losing or overwriting uncommitted changes
        status_report = self.status_manager.get_status(cwd=target_dir)
        if not status_report.is_clean:
            changed_names = [f.path for f in status_report.all_files[:5]]
            raise DirtyWorkingTreeError(
                f"Cannot switch to branch '{branch_name}': Working tree has uncommitted changes in "
                f"{len(status_report.all_files)} file(s) ({', '.join(changed_names)}). "
                "Please commit or stash your changes before switching branches."
            )

        # Check approval
        if self.approval_callback:
            approved = self.approval_callback(
                "git_switch_branch",
                {"target_branch": branch_name, "current_branch": repo_info.current_branch},
            )
            if not approved:
                raise BranchNotApprovedError(f"User rejected switching to branch '{branch_name}'.")

        res = self.detector.run_git_command(["switch", branch_name], cwd=target_dir)
        if res.returncode != 0:
            raise GitExecutionError(f"Failed to switch to branch '{branch_name}': {res.stderr.strip()}")

        return BranchOperationResult(
            success=True,
            operation="switch",
            branch_name=branch_name,
            previous_branch=repo_info.current_branch,
            message=f"Switched to branch '{branch_name}'.",
        )
