"""CodeAgent Git subsystem providing safe repository inspection, diffs, branches, and commits."""

from codeagent.git.branch_manager import (
    BranchCollisionError,
    BranchManager,
    BranchNotApprovedError,
    BranchOperationResult,
    BranchValidationError,
    DirtyWorkingTreeError,
    GitBranchInfo,
    GitBranchListResult,
)
from codeagent.git.commit_manager import (
    CommitManager,
    CommitNotApprovedError,
    CommitResult,
    CommitValidationError,
    SecretDetectedInCommitError,
)
from codeagent.git.diff_manager import DiffManager, GitDiffResult, GitFileDiff
from codeagent.git.git_manager import GitManager
from codeagent.git.repo_detector import (
    GitExecutionError,
    GitNotInstalledError,
    GitRepoInfo,
    GitSecurityError,
    NotAGitRepositoryError,
    RepoDetector,
)
from codeagent.git.status_manager import GitFileStatus, GitStatusReport, StatusManager

__all__ = [
    "BranchCollisionError",
    "BranchManager",
    "BranchNotApprovedError",
    "BranchOperationResult",
    "BranchValidationError",
    "CommitManager",
    "CommitNotApprovedError",
    "CommitResult",
    "CommitValidationError",
    "DiffManager",
    "DirtyWorkingTreeError",
    "GitBranchInfo",
    "GitBranchListResult",
    "GitDiffResult",
    "GitExecutionError",
    "GitFileDiff",
    "GitFileStatus",
    "GitManager",
    "GitNotInstalledError",
    "GitRepoInfo",
    "GitSecurityError",
    "GitStatusReport",
    "NotAGitRepositoryError",
    "RepoDetector",
    "SecretDetectedInCommitError",
    "StatusManager",
]
