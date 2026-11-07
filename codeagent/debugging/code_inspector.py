"""Source-code inspector retrieving code context, AST symbols, imports, and related tests."""

import ast
from pathlib import Path
from typing import List, Optional, Set, Union
from pydantic import BaseModel, Field

from codeagent.filesystem.path_validator import PathValidator, WorkspaceSecurityError
from codeagent.filesystem.reader import FileReader


class InspectedCodeContext(BaseModel):
    """Structured evidence collected from source code inspection."""

    file_path: str
    target_line: Optional[int] = None
    lines_context: str = ""
    start_line: int = 1
    end_line: int = 1
    imports: List[str] = Field(default_factory=list)
    enclosing_function: Optional[str] = None
    enclosing_class: Optional[str] = None
    related_tests: List[str] = Field(default_factory=list)
    related_files: List[str] = Field(default_factory=list)
    full_content: Optional[str] = None


class CodeInspector:
    """Safely inspects project source files, AST structures, and test suites."""

    def __init__(
        self,
        workspace_root: Optional[Union[str, Path]] = None,
        path_validator: Optional[PathValidator] = None,
        reader: Optional[FileReader] = None,
    ) -> None:
        """Initialize CodeInspector with workspace boundary guards."""
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        self.validator = path_validator or PathValidator(workspace_root=self.workspace_root)
        self.reader = reader or FileReader(validator=self.validator)

    def inspect_file(
        self,
        file_path: Union[str, Path],
        target_line: Optional[int] = None,
        window: int = 10,
    ) -> InspectedCodeContext:
        """Inspect a file at target line, extracting context snippet, AST symbols, and related tests."""
        # Validate path containment and sensitive file rules
        resolved = self.validator.validate_and_resolve(file_path, allow_nonexistent=False)
        read_res = self.reader.read(resolved)
        content = read_res.content
        lines = content.splitlines()
        total_lines = len(lines)

        # Context lines calculation
        if target_line is not None and total_lines > 0:
            target_idx = max(1, min(target_line, total_lines))
            start_l = max(1, target_idx - window)
            end_l = min(total_lines, target_idx + window)
            snippet_lines = []
            for idx in range(start_l, end_l + 1):
                prefix = "> " if idx == target_idx else "  "
                line_text = lines[idx - 1]
                snippet_lines.append(f"{prefix}{idx:4d} | {line_text}")
            lines_context = "\n".join(snippet_lines)
        else:
            start_l = 1
            end_l = total_lines
            lines_context = content[:1500]

        # AST analysis
        imports: List[str] = []
        enclosing_func: Optional[str] = None
        enclosing_cls: Optional[str] = None

        if resolved.suffix.lower() == ".py":
            try:
                tree = ast.parse(content, filename=str(resolved))
                imports = self._extract_imports(tree)
                if target_line:
                    enclosing_func, enclosing_cls = self._find_enclosing_symbols(tree, target_line)
            except SyntaxError:
                # Syntax errors in target file prevent full AST traversal
                pass

        # Discover related test suites and related workspace files
        rel_tests = self.find_related_tests(resolved)
        rel_files = self.find_related_files(resolved)

        return InspectedCodeContext(
            file_path=str(resolved.relative_to(self.workspace_root)),
            target_line=target_line,
            lines_context=lines_context,
            start_line=start_l,
            end_line=end_l,
            imports=imports,
            enclosing_function=enclosing_func,
            enclosing_class=enclosing_cls,
            related_tests=rel_tests,
            related_files=rel_files,
            full_content=content,
        )

    def _extract_imports(self, tree: ast.AST) -> List[str]:
        """Extract import module names from AST."""
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
        return sorted(list(set(imports)))

    def _find_enclosing_symbols(
        self,
        tree: ast.AST,
        target_line: int,
    ) -> tuple[Optional[str], Optional[str]]:
        """Identify enclosing function and class for a given line number."""
        enclosing_func = None
        enclosing_cls = None

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start = getattr(node, "lineno", 0)
                end = getattr(node, "end_lineno", start)
                if start <= target_line <= end:
                    enclosing_func = node.name
            elif isinstance(node, ast.ClassDef):
                start = getattr(node, "lineno", 0)
                end = getattr(node, "end_lineno", start)
                if start <= target_line <= end:
                    enclosing_cls = node.name

        return enclosing_func, enclosing_cls

    def find_related_tests(self, file_path: Path) -> List[str]:
        """Find tests that test or reference the specified file."""
        tests_found: List[str] = []
        stem = file_path.stem
        # Direct pattern match: test_<stem>.py or <stem>_test.py
        candidates = [
            f"test_{stem}.py",
            f"{stem}_test.py",
        ]

        for p in self.workspace_root.rglob("*.py"):
            # Skip hidden or build folders
            if any(part.startswith((".", "__pycache__", "node_modules", ".venv")) for part in p.parts):
                continue
            if p.name in candidates:
                tests_found.append(str(p.relative_to(self.workspace_root)))
            elif "test" in p.name.lower():
                try:
                    text = p.read_text(encoding="utf-8", errors="ignore")
                    if stem in text:
                        tests_found.append(str(p.relative_to(self.workspace_root)))
                except Exception:
                    pass

        return sorted(list(set(tests_found)))

    def find_related_files(self, file_path: Path) -> List[str]:
        """Find other files in the workspace that import or are imported by target file."""
        related: List[str] = []
        stem = file_path.stem

        for p in self.workspace_root.rglob("*.py"):
            if p == file_path:
                continue
            if any(part.startswith((".", "__pycache__", "node_modules", ".venv")) for part in p.parts):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
                if stem in text:
                    related.append(str(p.relative_to(self.workspace_root)))
            except Exception:
                pass

        return sorted(list(set(related)))[:10]
