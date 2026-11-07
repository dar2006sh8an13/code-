"""Language detector analyzing file extensions and distribution across project source files."""

import os
from pathlib import Path
from typing import Dict, List, Optional, Set
from pydantic import BaseModel, Field


class LanguageStats(BaseModel):
    """File and line count metrics for a single programming language."""

    name: str
    file_count: int = 0
    total_lines: int = 0
    percentage: float = 0.0


class LanguageDistribution(BaseModel):
    """Overall language breakdown across the workspace."""

    primary_language: str = "Unknown"
    languages: List[LanguageStats] = Field(default_factory=list)
    total_files: int = 0
    total_lines: int = 0

    @property
    def total_source_files(self) -> int:
        return self.total_files

    @property
    def total_source_lines(self) -> int:
        return self.total_lines

    @property
    def percentages(self) -> Dict[str, float]:
        return {l.name: round(l.percentage, 1) for l in self.languages}

    def to_summary(self) -> str:
        """Format an informative summary of language composition."""
        parts = [f"{l.name}: {l.percentage:.1f}% ({l.file_count} files)" for l in self.languages[:5]]
        return f"Primary: {self.primary_language} | Breakdown: {', '.join(parts)}" if parts else "No languages detected"


class LanguageDetector:
    """Detects languages and computes code distributions across workspace projects."""

    EXTENSION_MAP = {
        ".py": "Python",
        ".js": "JavaScript",
        ".jsx": "JavaScript",
        ".ts": "TypeScript",
        ".tsx": "TypeScript",
        ".java": "Java",
        ".c": "C",
        ".cpp": "C++",
        ".cc": "C++",
        ".h": "C/C++ Header",
        ".hpp": "C++ Header",
        ".html": "HTML",
        ".htm": "HTML",
        ".css": "CSS",
        ".scss": "SCSS",
        ".sql": "SQL",
        ".sh": "Shell",
        ".bash": "Bash",
        ".bat": "Batch",
        ".ps1": "PowerShell",
        ".json": "JSON",
        ".toml": "TOML",
        ".yaml": "YAML",
        ".yml": "YAML",
        ".md": "Markdown",
        ".go": "Go",
        ".rs": "Rust",
        ".php": "PHP",
        ".rb": "Ruby",
        ".cs": "C#",
    }

    def __init__(self, excluded_dirs: Optional[Set[str]] = None) -> None:
        """Initialize LanguageDetector."""
        self.excluded_dirs = excluded_dirs or {
            ".git",
            ".venv",
            "venv",
            "node_modules",
            "__pycache__",
            "dist",
            "build",
            ".codeagent",
        }

    def detect_languages(self, workspace_root: Path) -> LanguageDistribution:
        """Walk workspace and calculate line counts and percentages per language."""
        if not workspace_root.exists() or not workspace_root.is_dir():
            return LanguageDistribution()

        file_counts: Dict[str, int] = {}
        line_counts: Dict[str, int] = {}

        for root, dirs, files in os.walk(workspace_root):
            dirs[:] = [d for d in dirs if d not in self.excluded_dirs and not d.startswith(".")]

            for fname in files:
                ext = Path(fname).suffix.lower()
                lang = self.EXTENSION_MAP.get(ext)
                if not lang:
                    continue

                full_p = Path(root) / fname
                try:
                    # Quick line counting
                    with open(full_p, "rb") as f:
                        lines = sum(1 for _ in f)
                    file_counts[lang] = file_counts.get(lang, 0) + 1
                    line_counts[lang] = line_counts.get(lang, 0) + max(lines, 1)
                except (OSError, PermissionError):
                    continue

        total_lines = sum(line_counts.values())
        total_files = sum(file_counts.values())

        if total_lines == 0 or total_files == 0:
            return LanguageDistribution()

        stats_list: List[LanguageStats] = []
        for lang, count in file_counts.items():
            l_count = line_counts.get(lang, 0)
            pct = (l_count / total_lines) * 100.0 if total_lines > 0 else 0.0
            stats_list.append(
                LanguageStats(
                    name=lang,
                    file_count=count,
                    total_lines=l_count,
                    percentage=round(pct, 1),
                )
            )

        # Sort by total lines descending
        stats_list.sort(key=lambda s: s.total_lines, reverse=True)

        # Select primary language, prioritizing code/programming over data/config formats
        data_formats = {"JSON", "TOML", "YAML", "Markdown", "XML", "Lockfile"}
        code_candidates = [s for s in stats_list if s.name not in data_formats]
        if code_candidates:
            primary = code_candidates[0].name
        else:
            primary = stats_list[0].name if stats_list else "Unknown"

        return LanguageDistribution(
            primary_language=primary,
            languages=stats_list,
            total_files=total_files,
            total_lines=total_lines,
        )

    detect_distribution = detect_languages
