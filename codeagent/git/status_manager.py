"""Machine-readable Git status parser and Rich status reporter."""

from pathlib import Path
import re
from typing import List, Optional, Union
from pydantic import BaseModel, Field
from rich.table import Table

from codeagent.git.repo_detector import GitExecutionError, NotAGitRepositoryError, RepoDetector


class GitFileStatus(BaseModel):
    """Status description for an individual file in the working tree."""

    path: str
    original_path: Optional[str] = None  # Populated for renames
    staged_status: str = " "             # 'M', 'A', 'D', 'R', 'C', '?'
    unstaged_status: str = " "           # 'M', 'D', '?', 'U'
    is_staged: bool = False
    is_unstaged: bool = False
    is_untracked: bool = False
    is_conflict: bool = False

    @property
    def display_status(self) -> str:
        """Formatted 2-character Git status code."""
        return f"{self.staged_status}{self.unstaged_status}"


class GitStatusReport(BaseModel):
    """Comprehensive structured status report of a Git working directory."""

    branch: str = "unknown"
    upstream: Optional[str] = None
    ahead: int = 0
    behind: int = 0
    is_clean: bool = True
    has_conflicts: bool = False
    staged_files: List[GitFileStatus] = Field(default_factory=list)
    unstaged_files: List[GitFileStatus] = Field(default_factory=list)
    untracked_files: List[GitFileStatus] = Field(default_factory=list)
    conflict_files: List[GitFileStatus] = Field(default_factory=list)
    all_files: List[GitFileStatus] = Field(default_factory=list)

    @property
    def total_changed_files(self) -> int:
        """Count of all files with any modification, staging, or untracked status."""
        return len(self.all_files)

    def to_summary(self) -> str:
        """Textual summary of current Git status."""
        if self.is_clean:
            return f"On branch {self.branch}. Working tree clean."

        parts = [f"On branch {self.branch}"]
        if self.ahead or self.behind:
            parts.append(f"[ahead {self.ahead}, behind {self.behind}]")
        if self.staged_files:
            parts.append(f"Staged: {len(self.staged_files)}")
        if self.unstaged_files:
            parts.append(f"Unstaged: {len(self.unstaged_files)}")
        if self.untracked_files:
            parts.append(f"Untracked: {len(self.untracked_files)}")
        if self.has_conflicts:
            parts.append(f"Conflicts: {len(self.conflict_files)}")
        return " | ".join(parts)

    def to_rich_table(self) -> Table:
        """Generate a colored Rich table displaying working directory changes."""
        table = Table(title=f"Git Status: branch '{self.branch}'", show_header=True, header_style="bold magenta")
        table.add_column("Staged", width=8, justify="center")
        table.add_column("Unstaged", width=8, justify="center")
        table.add_column("Path", style="cyan")
        table.add_column("Details", style="dim")

        if self.is_clean:
            table.add_row("[green]--[/green]", "[green]--[/green]", "[green]Working tree clean[/green]", "No changes")
            return table

        for f in self.all_files:
            staged_style = "green" if f.is_staged else "dim"
            unstaged_style = "red" if f.is_conflict else ("yellow" if f.is_unstaged else "dim")

            staged_display = f"[{staged_style}]{f.staged_status}[/{staged_style}]"
            unstaged_display = f"[{unstaged_style}]{f.unstaged_status}[/{unstaged_style}]"

            path_text = f.path
            details = ""
            if f.is_conflict:
                details = "[bold red]Merge Conflict[/bold red]"
            elif f.original_path:
                details = f"Renamed from {f.original_path}"
            elif f.is_untracked:
                details = "Untracked file"
            elif f.is_staged and f.is_unstaged:
                details = "Partially staged"

            table.add_row(staged_display, unstaged_display, path_text, details)

        return table


class StatusManager:
    """Retrieves and parses machine-readable Git status output."""

    def __init__(
        self,
        workspace_root: Optional[Union[str, Path]] = None,
        detector: Optional[RepoDetector] = None,
    ) -> None:
        """Initialize StatusManager."""
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        self.detector = detector or RepoDetector(self.workspace_root)

    def _unquote_git_path(self, raw_path: str) -> str:
        """Handle Git C-style path escaping and stripping quotes for paths with spaces."""
        clean = raw_path.strip()
        if clean.startswith('"') and clean.endswith('"'):
            clean = clean[1:-1]
            # Replace common escaped characters
            clean = (
                clean.replace(r'\"', '"')
                .replace(r"\t", "\t")
                .replace(r"\n", "\n")
                .replace(r"\\", "\\")
            )
        return clean

    def get_status(self, cwd: Optional[Path] = None) -> GitStatusReport:
        """Execute git status --porcelain=v1 --branch and build structured GitStatusReport."""
        target_dir = Path(cwd or self.workspace_root).resolve()
        repo_info = self.detector.detect_repository(target_dir)
        if not repo_info.is_git_repo:
            raise NotAGitRepositoryError(f"Directory '{target_dir}' is not inside a Git repository.")

        res = self.detector.run_git_command(
            ["status", "--porcelain=v1", "--branch", "-uall"],
            cwd=target_dir,
        )
        if res.returncode != 0:
            raise GitExecutionError(f"Failed to query git status: {res.stderr.strip()}")

        lines = res.stdout.splitlines()
        branch_name = repo_info.current_branch or "HEAD"
        upstream: Optional[str] = None
        ahead = 0
        behind = 0

        staged_list: List[GitFileStatus] = []
        unstaged_list: List[GitFileStatus] = []
        untracked_list: List[GitFileStatus] = []
        conflict_list: List[GitFileStatus] = []
        all_list: List[GitFileStatus] = []

        for line in lines:
            if not line:
                continue

            # Branch header: ## main...origin/main [ahead 1, behind 2]
            # or ## Initial commit on main
            # or ## No commits yet on main
            if line.startswith("## "):
                b_info = line[3:].strip()
                if "No commits yet on " in b_info:
                    branch_name = b_info.replace("No commits yet on ", "").strip()
                elif "Initial commit on " in b_info:
                    branch_name = b_info.replace("Initial commit on ", "").strip()
                else:
                    # Match branch and upstream
                    m = re.match(r"^([^\.\s]+)(?:\.\.\.([^\s]+))?(?:\s+\[(.*)\])?", b_info)
                    if m:
                        branch_name = m.group(1)
                        upstream = m.group(2)
                        bracket = m.group(3) or ""
                        ahead_m = re.search(r"ahead\s+(\d+)", bracket)
                        behind_m = re.search(r"behind\s+(\d+)", bracket)
                        if ahead_m:
                            ahead = int(ahead_m.group(1))
                        if behind_m:
                            behind = int(behind_m.group(1))
                continue

            if len(line) < 3:
                continue

            code_staged = line[0]
            code_unstaged = line[1]
            raw_path = line[3:].strip()

            original_path: Optional[str] = None
            path = raw_path

            # Rename format: R  old -> new or "old name" -> "new name"
            if " -> " in raw_path:
                parts = raw_path.split(" -> ", 1)
                original_path = self._unquote_git_path(parts[0])
                path = self._unquote_git_path(parts[1])
            else:
                path = self._unquote_git_path(raw_path)

            # Detect conflict states (e.g. UU, AA, UD, DU)
            is_conflict = (
                (code_staged == "U" or code_unstaged == "U")
                or (code_staged == "A" and code_unstaged == "A")
                or (code_staged == "D" and code_unstaged == "D")
            )

            is_untracked = (code_staged == "?" and code_unstaged == "?")
            is_staged = (code_staged not in (" ", "?") and not is_conflict)
            is_unstaged = (code_unstaged not in (" ", "?") and not is_conflict)

            file_stat = GitFileStatus(
                path=path,
                original_path=original_path,
                staged_status=code_staged,
                unstaged_status=code_unstaged,
                is_staged=is_staged,
                is_unstaged=is_unstaged,
                is_untracked=is_untracked,
                is_conflict=is_conflict,
            )

            all_list.append(file_stat)

            if is_conflict:
                conflict_list.append(file_stat)
            if is_staged:
                staged_list.append(file_stat)
            if is_unstaged:
                unstaged_list.append(file_stat)
            if is_untracked:
                untracked_list.append(file_stat)

        is_clean = len(all_list) == 0

        return GitStatusReport(
            branch=branch_name,
            upstream=upstream,
            ahead=ahead,
            behind=behind,
            is_clean=is_clean,
            has_conflicts=len(conflict_list) > 0,
            staged_files=staged_list,
            unstaged_files=unstaged_list,
            untracked_files=untracked_list,
            conflict_files=conflict_list,
            all_files=all_list,
        )
