"""Git diff generation engine supporting staged, unstaged, file-specific, and stat diffs with secret redaction."""

from pathlib import Path
import re
from typing import List, Optional, Union
from pydantic import BaseModel, Field

from codeagent.execution.audit_logger import redact_secrets_text
from codeagent.git.repo_detector import GitExecutionError, NotAGitRepositoryError, RepoDetector


class GitFileDiff(BaseModel):
    """Diff details for an individual changed file."""

    file_path: str
    is_binary: bool = False
    insertions: int = 0
    deletions: int = 0
    diff_text: str = ""


class GitDiffResult(BaseModel):
    """Comprehensive diff result with secret scrubbing and byte limits."""

    is_staged: bool = False
    stat_summary: str = ""
    total_files_changed: int = 0
    total_insertions: int = 0
    total_deletions: int = 0
    file_diffs: List[GitFileDiff] = Field(default_factory=list)
    raw_diff: str = ""
    is_truncated: bool = False

    def to_summary(self) -> str:
        """Formatted high-level diff summary."""
        scope = "Staged (Cached)" if self.is_staged else "Working Tree (Unstaged)"
        return (
            f"Diff Scope: {scope}\n"
            f"Files Changed: {self.total_files_changed} (+{self.total_insertions}, -{self.total_deletions})\n"
            f"Stat:\n{self.stat_summary}"
        )


class DiffManager:
    """Coordinates git diff operations with safety checks, secret redaction, and size capping."""

    DEFAULT_MAX_DIFF_BYTES = 500_000  # 500 KB limit for diff rendering

    def __init__(
        self,
        workspace_root: Optional[Union[str, Path]] = None,
        detector: Optional[RepoDetector] = None,
        max_bytes: int = DEFAULT_MAX_DIFF_BYTES,
    ) -> None:
        """Initialize DiffManager."""
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        self.detector = detector or RepoDetector(self.workspace_root)
        self.max_bytes = max_bytes

    def get_diff(
        self,
        staged: bool = False,
        file_path: Optional[str] = None,
        cwd: Optional[Path] = None,
        redact_secrets: bool = True,
    ) -> GitDiffResult:
        """Retrieve unified diff for working tree or staged changes with secret redaction.

        Args:
            staged: If True, inspect staged changes (`--cached`).
            file_path: Optional single file path filter.
            cwd: Working directory inside workspace.
            redact_secrets: Whether to scrub sensitive credentials from diff text.

        Returns:
            Structured GitDiffResult.
        """
        target_dir = Path(cwd or self.workspace_root).resolve()
        repo_info = self.detector.detect_repository(target_dir)
        if not repo_info.is_git_repo:
            raise NotAGitRepositoryError(f"Directory '{target_dir}' is not inside a Git repository.")

        # 1. Fetch stat summary
        stat_args = ["diff", "--stat"]
        if staged:
            stat_args.append("--cached")
        if file_path:
            stat_args.extend(["--", file_path])

        res_stat = self.detector.run_git_command(stat_args, cwd=target_dir)
        stat_raw = res_stat.stdout.strip() if res_stat.returncode == 0 else ""

        # Parse insertions / deletions from stat line e.g.:
        # " 2 files changed, 10 insertions(+), 3 deletions(-)"
        tot_files = 0
        tot_ins = 0
        tot_del = 0
        stat_match = re.search(r"(\d+)\s+file[s]?\s+changed(?:,\s+(\d+)\s+insertion[s]?\(\+\))?(?:,\s+(\d+)\s+deletion[s]?\(-\))?", stat_raw)
        if stat_match:
            tot_files = int(stat_match.group(1))
            if stat_match.group(2):
                tot_ins = int(stat_match.group(2))
            if stat_match.group(3):
                tot_del = int(stat_match.group(3))

        # 2. Fetch full unified diff
        diff_args = ["diff", "-p"]
        if staged:
            diff_args.append("--cached")
        if file_path:
            diff_args.extend(["--", file_path])

        res_diff = self.detector.run_git_command(diff_args, cwd=target_dir)
        if res_diff.returncode != 0:
            raise GitExecutionError(f"git diff failed: {res_diff.stderr.strip()}")

        raw_content = res_diff.stdout
        is_truncated = False
        if len(raw_content.encode("utf-8")) > self.max_bytes:
            raw_content = raw_content[: self.max_bytes] + "\n\n... [Diff truncated: exceeded size limit] ..."
            is_truncated = True

        # Redact secrets before parsing and returning unless explicitly disabled
        scrubbed_diff = redact_secrets_text(raw_content) if redact_secrets else raw_content

        # 3. Parse per-file diff sections
        file_diffs = self._parse_file_diffs(scrubbed_diff)

        return GitDiffResult(
            is_staged=staged,
            stat_summary=stat_raw,
            total_files_changed=tot_files or len(file_diffs),
            total_insertions=tot_ins,
            total_deletions=tot_del,
            file_diffs=file_diffs,
            raw_diff=scrubbed_diff,
            is_truncated=is_truncated,
        )

    def _parse_file_diffs(self, diff_text: str) -> List[GitFileDiff]:
        """Split unified diff text into per-file chunks."""
        file_diffs: List[GitFileDiff] = []
        if not diff_text.strip():
            return file_diffs

        # Split on standard git diff file headers
        chunks = re.split(r"(?=^diff --git )", diff_text, flags=re.MULTILINE)
        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk or not chunk.startswith("diff --git"):
                continue

            header_line = chunk.splitlines()[0]
            # e.g. diff --git a/file.py b/file.py
            m = re.match(r"^diff --git\s+(?:a/)?(\S+)\s+(?:b/)?(\S+)", header_line)
            fname = m.group(2) if m else "unknown"

            is_binary = (("Binary files" in chunk and "differ" in chunk) or "GIT binary patch" in chunk)
            insertions = sum(1 for l in chunk.splitlines() if l.startswith("+") and not l.startswith("+++"))
            deletions = sum(1 for l in chunk.splitlines() if l.startswith("-") and not l.startswith("---"))

            file_diffs.append(
                GitFileDiff(
                    file_path=fname,
                    is_binary=is_binary,
                    insertions=insertions,
                    deletions=deletions,
                    diff_text=chunk if not is_binary else f"[Binary file {fname} differs]",
                )
            )

        return file_diffs
