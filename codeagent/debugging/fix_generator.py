"""Fix generator synthesizing minimal unified diffs and validating Python syntax in memory."""

import ast
import difflib
from pathlib import Path
import re
from typing import List, Optional, Union
import uuid
from pydantic import BaseModel, Field

from codeagent.debugging.code_inspector import InspectedCodeContext
from codeagent.debugging.error_detector import DetectedError
from codeagent.debugging.root_cause_analyzer import RootCauseDiagnosis
from codeagent.filesystem.path_validator import PathValidator
from codeagent.filesystem.reader import FileReader
from codeagent.llm.client import LLMClient


class FilePatch(BaseModel):
    """A proposed modification to a single source file."""

    file_path: str
    original_content: str
    modified_content: str
    diff: str
    explanation: str

    @property
    def has_changes(self) -> bool:
        """Return True if patch modifies content."""
        return self.original_content != self.modified_content


class ProposedFix(BaseModel):
    """A cohesive proposed fix comprising one or more file patches."""

    fix_id: str
    description: str
    patches: List[FilePatch] = Field(default_factory=list)
    requires_dependencies: List[str] = Field(default_factory=list)
    is_valid: bool = True
    validation_error: Optional[str] = None

    @property
    def affected_files(self) -> List[str]:
        """List of target file paths affected by this fix."""
        return [p.file_path for p in self.patches]


class FixGenerator:
    """Generates minimal code repairs with syntax validation and unified diffs."""

    def __init__(
        self,
        workspace_root: Optional[Union[str, Path]] = None,
        llm_client: Optional[LLMClient] = None,
        path_validator: Optional[PathValidator] = None,
        reader: Optional[FileReader] = None,
    ) -> None:
        """Initialize FixGenerator."""
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        self.llm_client = llm_client
        self.validator = path_validator or PathValidator(workspace_root=self.workspace_root)
        self.reader = reader or FileReader(validator=self.validator)

    def generate_fix(
        self,
        diagnosis: RootCauseDiagnosis,
        context: Optional[InspectedCodeContext] = None,
        target_file_path: Optional[str] = None,
        custom_replacement: Optional[tuple[str, str]] = None,  # (search_str, replace_str)
    ) -> ProposedFix:
        """Generate a validated ProposedFix for the diagnosed issue."""
        fix_id = uuid.uuid4().hex[:8]
        file_to_patch = target_file_path or diagnosis.affected_file
        if not file_to_patch and context:
            file_to_patch = context.file_path

        if not file_to_patch:
            # Check if this is a missing dependency
            if diagnosis.exception_type in ("ModuleNotFoundError", "ImportError"):
                dep_name = self._extract_missing_module_name(diagnosis.error_summary)
                return ProposedFix(
                    fix_id=fix_id,
                    description=f"Install missing dependency '{dep_name}'",
                    patches=[],
                    requires_dependencies=[dep_name] if dep_name else [],
                    is_valid=True,
                )
            return ProposedFix(
                fix_id=fix_id,
                description="Unable to determine target file for fix",
                patches=[],
                is_valid=False,
                validation_error="No affected file specified in diagnosis.",
            )

        # Resolve target file and read original content
        try:
            resolved = self.validator.validate_and_resolve(file_to_patch, allow_nonexistent=False)
            orig_content = self.reader.read(resolved).content
        except Exception as exc:
            return ProposedFix(
                fix_id=fix_id,
                description=f"Target file access error: {file_to_patch}",
                patches=[],
                is_valid=False,
                validation_error=str(exc),
            )

        # If custom replacement provided directly
        if custom_replacement:
            search_str, replace_str = custom_replacement
            if search_str not in orig_content:
                return ProposedFix(
                    fix_id=fix_id,
                    description=f"Replacement target not found in {file_to_patch}",
                    patches=[],
                    is_valid=False,
                    validation_error=f"Search target '{search_str}' not found in file.",
                )
            mod_content = orig_content.replace(search_str, replace_str, 1)
            explanation = f"Replace '{search_str.strip()}' with '{replace_str.strip()}'"
        else:
            # Generate replacement via heuristic rule or LLM
            mod_content, explanation = self._synthesize_patch_content(
                diagnosis=diagnosis,
                orig_content=orig_content,
                context=context,
            )

        # Validate resulting Python syntax if target is a Python file
        if resolved.suffix.lower() == ".py":
            try:
                ast.parse(mod_content, filename=str(resolved))
            except SyntaxError as syn_err:
                return ProposedFix(
                    fix_id=fix_id,
                    description=f"Syntax validation failed on proposed fix: {syn_err.msg}",
                    patches=[],
                    is_valid=False,
                    validation_error=f"Proposed patch generates invalid Python syntax: {syn_err.msg} at line {syn_err.lineno}",
                )

        # Check for no-op changes
        if orig_content == mod_content:
            return ProposedFix(
                fix_id=fix_id,
                description="Proposed fix produced no changes",
                patches=[],
                is_valid=False,
                validation_error="Modified content matches original content (empty diff).",
            )

        diff = self._generate_unified_diff(
            file_path=str(resolved.relative_to(self.workspace_root)),
            orig=orig_content,
            mod=mod_content,
        )

        patch = FilePatch(
            file_path=str(resolved.relative_to(self.workspace_root)),
            original_content=orig_content,
            modified_content=mod_content,
            diff=diff,
            explanation=explanation,
        )

        return ProposedFix(
            fix_id=fix_id,
            description=f"Fix {diagnosis.exception_type} in {patch.file_path}: {explanation}",
            patches=[patch],
            is_valid=True,
        )

    def _synthesize_patch_content(
        self,
        diagnosis: RootCauseDiagnosis,
        orig_content: str,
        context: Optional[InspectedCodeContext],
    ) -> tuple[str, str]:
        """Synthesize repaired content using heuristics or prompt guidance."""
        err_type = diagnosis.exception_type
        target_line = diagnosis.affected_line
        lines = orig_content.splitlines(keepends=True)

        # 1. Try LLM synthesis if available
        if self.llm_client:
            try:
                mod_llm, expl_llm = self._synthesize_with_llm(diagnosis, orig_content, context)
                if mod_llm and mod_llm != orig_content:
                    try:
                        ast.parse(mod_llm)
                        return mod_llm, expl_llm
                    except SyntaxError:
                        pass
            except Exception:
                pass

        # 2. Deterministic heuristic repairs
        if target_line and 1 <= target_line <= len(lines):
            line_idx = target_line - 1
            problem_line = lines[line_idx]

            # Heuristic ZeroDivisionError repair
            if err_type == "ZeroDivisionError" and "/" in problem_line:
                div_ret_match = re.match(r"^(\s*return\s+)(.+?)\s*/\s*([a-zA-Z_][a-zA-Z0-9_\.]*)(\s*)$", problem_line)
                if div_ret_match:
                    prefix, num, denom, suffix = div_ret_match.groups()
                    mod_line = f"{prefix}{num} / {denom} if {denom} != 0 else 0.0{suffix}"
                    lines[line_idx] = mod_line
                    return "".join(lines), f"Add non-zero divisor guard for '{denom}'"
                elif "divisor" in problem_line:
                    mod_line = problem_line.replace("/", " / (") + " if divisor != 0 else 0)"
                    lines[line_idx] = mod_line
                    return "".join(lines), "Add non-zero divisor guard"

            # Heuristic KeyError repair
            if err_type == "KeyError" and "[" in problem_line and "]" in problem_line:
                mod_line = re.sub(r"\[['\"]([^'\"]+)['\"]\]", r".get('\1')", problem_line)
                if mod_line != problem_line:
                    lines[line_idx] = mod_line
                    return "".join(lines), "Use dict.get() to safely access optional key"

        return orig_content, "No automated heuristic replacement available"

    def _synthesize_with_llm(
        self,
        diagnosis: RootCauseDiagnosis,
        orig_content: str,
        context: Optional[InspectedCodeContext],
    ) -> tuple[Optional[str], str]:
        """Synthesize repaired file content using local LLM."""
        if not self.llm_client:
            return None, ""

        file_name = context.file_path if context else (diagnosis.affected_file or "code.py")
        prompt = (
            f"You are an expert Python bug fixing assistant. Fix the diagnosed error in this file.\n\n"
            f"File: {file_name}\n"
            f"Error Type: {diagnosis.exception_type}\n"
            f"Root Cause: {diagnosis.root_cause}\n"
            f"Suggested Solution: {diagnosis.suggested_solution}\n"
            f"Affected Line: {diagnosis.affected_line}\n\n"
            f"Original Source Code:\n```python\n{orig_content}\n```\n\n"
            f"Provide ONLY the complete, valid, corrected Python code for the file.\n"
            f"Enclose the entire code inside a single ```python\n...\n``` code block.\n"
            f"Do not include conversational text or explanations outside the code block."
        )

        response_text = self.llm_client.generate(
            prompt=prompt,
            system_prompt="You are a precise Python code repair engineer. Output only the corrected Python code block.",
        )

        # Extract code block
        code_match = re.search(r"```(?:python)?\s*\n(.*?)\n```", response_text, re.DOTALL)
        if code_match:
            code = code_match.group(1)
            if orig_content.endswith("\n") and not code.endswith("\n"):
                code += "\n"
            return code, f"Apply fix suggested by LLM"

        return None, ""

    def _extract_missing_module_name(self, error_msg: str) -> Optional[str]:
        """Extract missing module name from error string."""
        match = re.search(r"No module named ['\"]([^'\"]+)['\"]", error_msg)
        if match:
            return match.group(1).split(".")[0]
        return None

    def _generate_unified_diff(self, file_path: str, orig: str, mod: str) -> str:
        """Produce unified diff string."""
        diff_lines = list(
            difflib.unified_diff(
                orig.splitlines(keepends=True),
                mod.splitlines(keepends=True),
                fromfile=f"a/{file_path}",
                tofile=f"b/{file_path}",
            )
        )
        return "".join(diff_lines)
