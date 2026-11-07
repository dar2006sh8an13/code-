"""Tool registry for registering and discovering callable tools with JSON schemas."""

from dataclasses import dataclass
from typing import Any, Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from codeagent.filesystem.manager import FilesystemManager
    from codeagent.execution.manager import ExecutionManager
    from codeagent.intelligence.project_manager import ProjectManager

from codeagent.tools.calculator import (
    add,
    calculate,
    divide,
    multiply,
    safe_eval_arithmetic,
    subtract,
)


@dataclass
class ToolDefinition:
    """Definition and metadata for an agent tool."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]

    def to_ollama_format(self) -> dict[str, Any]:
        """Convert tool to the official Ollama / OpenAI function format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Registry maintaining available agent tools and their schemas."""

    def __init__(self) -> None:
        """Initialize empty tool registry."""
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool definition."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[ToolDefinition]:
        """Retrieve a registered tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[ToolDefinition]:
        """Return list of all registered tools."""
        return list(self._tools.values())

    def get_ollama_tools(self, tool_names: Optional[list[str]] = None) -> list[dict[str, Any]]:
        """Return list of tools formatted for the Ollama chat API, optionally filtered by name."""
        if tool_names:
            names_set = set(tool_names)
            return [t.to_ollama_format() for t in self._tools.values() if t.name in names_set]
        return [t.to_ollama_format() for t in self._tools.values()]


def get_default_registry(
    filesystem_manager: Optional["FilesystemManager"] = None,
    execution_manager: Optional["ExecutionManager"] = None,
    project_manager: Optional["ProjectManager"] = None,
) -> ToolRegistry:
    """Create and return default tool registry populated with calculator, filesystem, and execution tools."""
    registry = ToolRegistry()

    # Unified calculate tool
    registry.register(
        ToolDefinition(
            name="calculate",
            description="Perform basic arithmetic calculations (add, subtract, multiply, divide).",
            parameters={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["add", "subtract", "multiply", "divide"],
                        "description": "The arithmetic operation to perform",
                    },
                    "a": {
                        "type": "number",
                        "description": "First number",
                    },
                    "b": {
                        "type": "number",
                        "description": "Second number",
                    },
                },
                "required": ["operation", "a", "b"],
            },
            handler=calculate,
        )
    )

    # Addition tool
    registry.register(
        ToolDefinition(
            name="add",
            description="Add two numbers together (a + b).",
            parameters={
                "type": "object",
                "properties": {
                    "a": {"type": "number", "description": "First number"},
                    "b": {"type": "number", "description": "Second number"},
                },
                "required": ["a", "b"],
            },
            handler=add,
        )
    )

    # Subtraction tool
    registry.register(
        ToolDefinition(
            name="subtract",
            description="Subtract b from a (a - b).",
            parameters={
                "type": "object",
                "properties": {
                    "a": {"type": "number", "description": "First number (minuend)"},
                    "b": {"type": "number", "description": "Second number (subtrahend)"},
                },
                "required": ["a", "b"],
            },
            handler=subtract,
        )
    )

    # Multiplication tool
    registry.register(
        ToolDefinition(
            name="multiply",
            description="Multiply two numbers together (a * b).",
            parameters={
                "type": "object",
                "properties": {
                    "a": {"type": "number", "description": "First number"},
                    "b": {"type": "number", "description": "Second number"},
                },
                "required": ["a", "b"],
            },
            handler=multiply,
        )
    )

    # Division tool
    registry.register(
        ToolDefinition(
            name="divide",
            description="Divide a by b (a / b). Safely detects division by zero.",
            parameters={
                "type": "object",
                "properties": {
                    "a": {"type": "number", "description": "Numerator"},
                    "b": {"type": "number", "description": "Denominator (cannot be zero)"},
                },
                "required": ["a", "b"],
            },
            handler=divide,
        )
    )

    # Arithmetic Expression evaluator tool
    registry.register(
        ToolDefinition(
            name="evaluate_expression",
            description="Safely evaluate a multi-step mathematical expression (e.g. '(42 + 58) * 2').",
            parameters={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Arithmetic expression to evaluate safely",
                    },
                },
                "required": ["expression"],
            },
            handler=safe_eval_arithmetic,
        )
    )

    # Register filesystem intelligence tools
    register_filesystem_tools(registry, filesystem_manager=filesystem_manager)

    # Register execution intelligence tools (Phase 5)
    register_execution_tools(registry, execution_manager=execution_manager)

    # Register autonomous debugging tools (Phase 6)
    register_debugging_tools(registry)

    # Register project intelligence and persistent memory tools (Phase 7)
    register_intelligence_tools(registry, project_manager=project_manager)

    # Register Git integration and safety management tools (Phase 8)
    register_git_and_safety_tools(registry)

    # Register multi-agent architecture and workflow tools (Phase 9)
    register_multiagent_tools(registry)

    return registry


def register_filesystem_tools(
    registry: ToolRegistry,
    filesystem_manager: Optional["FilesystemManager"] = None,
) -> None:
    """Register all Phase 3 filesystem intelligence tools into the registry.

    Args:
        registry: ToolRegistry instance to populate.
        filesystem_manager: Optional FilesystemManager instance.
    """
    from codeagent.filesystem.manager import FilesystemManager

    fs = filesystem_manager or FilesystemManager()

    def _read_file_handler(path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> dict[str, Any]:
        res = fs.read_file(path, start_line=start_line, end_line=end_line)
        return {
            "path": res.path,
            "content": res.content,
            "total_lines": res.total_lines,
            "start_line": res.start_line,
            "end_line": res.end_line,
            "size_bytes": res.size_bytes,
            "encoding": res.encoding,
        }

    registry.register(
        ToolDefinition(
            name="read_file",
            description="Read a text file within the workspace, optionally sliced between start_line and end_line.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path of the file to read within the workspace"},
                    "start_line": {"type": "integer", "description": "Optional starting line number (1-indexed)"},
                    "end_line": {"type": "integer", "description": "Optional ending line number (1-indexed)"},
                },
                "required": ["path"],
            },
            handler=_read_file_handler,
        )
    )

    def _create_file_handler(path: str, content: str, overwrite: bool = False) -> dict[str, Any]:
        res = fs.create_file(path, content=content, overwrite=overwrite)
        full_path = (fs.workspace_root / path).resolve()
        verified = full_path.exists() and full_path.stat().st_size > 0
        file_size = full_path.stat().st_size if full_path.exists() else 0
        return {
            "path": res.path,
            "absolute_path": str(full_path),
            "created": res.created_new,
            "overwritten": res.overwritten,
            "bytes_written": res.bytes_written,
            "verified": verified,
            "file_size": file_size,
            "message": f"Successfully created file '{res.path}' ({res.bytes_written} bytes) at {full_path}. Verified on disk.",
        }

    registry.register(
        ToolDefinition(
            name="create_file",
            description="Create a new text file within the workspace with the specified UTF-8 content.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path where the file should be created"},
                    "content": {"type": "string", "description": "Full text content to write into the file"},
                    "overwrite": {"type": "boolean", "description": "Whether to overwrite an existing file (default: false)"},
                },
                "required": ["path", "content"],
            },
            handler=_create_file_handler,
        )
    )

    def _create_directory_handler(path: str, parents: bool = True) -> dict[str, Any]:
        return fs.create_directory(path=path, parents=parents)

    registry.register(
        ToolDefinition(
            name="create_directory",
            description="Create a directory safely within the workspace boundary.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative directory path to create within workspace"},
                    "parents": {"type": "boolean", "description": "Whether to create parent directories if missing (default: true)"},
                },
                "required": ["path"],
            },
            handler=_create_directory_handler,
        )
    )

    def _edit_file_handler(
        path: str,
        search_target: Optional[str] = None,
        replacement: Optional[str] = None,
        new_content: Optional[str] = None,
    ) -> dict[str, Any]:
        res = fs.edit_file(
            path=path,
            search_target=search_target,
            replacement=replacement,
            new_content=new_content,
        )
        return {
            "path": res.path,
            "diff": res.diff,
            "backup_id": res.backup_id,
            "bytes_modified": res.bytes_modified,
            "verified": res.verified,
            "message": res.to_summary(),
        }

    registry.register(
        ToolDefinition(
            name="edit_file",
            description="Edit an existing file within the workspace by specifying new content or targeted search and replacement.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path of the file to edit"},
                    "search_target": {"type": "string", "description": "Target substring to locate and replace"},
                    "replacement": {"type": "string", "description": "Replacement string to substitute"},
                    "new_content": {"type": "string", "description": "Complete new content if replacing entire file"},
                },
                "required": ["path"],
            },
            handler=_edit_file_handler,
        )
    )

    def _delete_file_handler(path: str, confirmed: bool = False) -> dict[str, Any]:
        res = fs.delete_file(path=path, confirmed=confirmed)
        return {
            "path": res.path,
            "deleted": res.deleted,
            "backup_id": res.backup_id,
            "message": res.to_summary(),
        }

    registry.register(
        ToolDefinition(
            name="delete_file",
            description="Delete an individual file within the workspace with mandatory confirmation.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path of the individual file to delete"},
                    "confirmed": {"type": "boolean", "description": "Explicit confirmation of deletion (must be true)"},
                },
                "required": ["path"],
            },
            handler=_delete_file_handler,
        )
    )

    def _list_directory_handler(path: Optional[str] = None, max_depth: int = 1) -> dict[str, Any]:
        entries = fs.list_directory(path=path, max_depth=max_depth)
        return {
            "path": path or ".",
            "entries": [
                {
                    "name": e.name,
                    "relative_path": e.relative_path,
                    "is_dir": e.is_dir,
                    "size_bytes": e.size_bytes,
                    "extension": e.extension,
                }
                for e in entries
            ],
        }

    registry.register(
        ToolDefinition(
            name="list_directory",
            description="List files and subdirectories directly inside a directory within the workspace.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path to list (defaults to workspace root)"},
                    "max_depth": {"type": "integer", "description": "Depth of directory listing (default: 1)"},
                },
                "required": [],
            },
            handler=_list_directory_handler,
        )
    )

    def _scan_project_handler(path: Optional[str] = None) -> dict[str, Any]:
        res = fs.scan_project(path=path)
        return {
            "root_path": res.root_path,
            "total_files": res.total_files,
            "total_dirs": res.total_dirs,
            "extension_counts": res.extension_counts,
            "tree_view": res.tree_view,
            "truncated": res.truncated,
        }

    registry.register(
        ToolDefinition(
            name="scan_project",
            description="Recursively scan the workspace directory tree, returning file counts, extensions, and structure.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Root directory to scan (defaults to workspace root)"},
                },
                "required": [],
            },
            handler=_scan_project_handler,
        )
    )

    def _analyze_project_handler(path: Optional[str] = None) -> dict[str, Any]:
        res = fs.analyze_project(path=path)
        return {
            "project_type": res.project_type,
            "languages": res.languages,
            "frameworks": res.frameworks,
            "entry_points": res.entry_points,
            "dependency_files": res.dependency_files,
            "configuration_files": res.configuration_files,
            "important_directories": res.important_directories,
            "summary": res.summary,
        }

    registry.register(
        ToolDefinition(
            name="analyze_project",
            description="Analyze the project structure, detect languages, frameworks, entry-point files, and dependencies.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Root directory to analyze (defaults to workspace root)"},
                },
                "required": [],
            },
            handler=_analyze_project_handler,
        )
    )


def register_execution_tools(
    registry: ToolRegistry,
    execution_manager: Optional["ExecutionManager"] = None,
) -> None:
    """Register Phase 5 terminal and code execution tools into the registry.

    Args:
        registry: ToolRegistry instance to populate.
        execution_manager: Optional ExecutionManager instance.
    """
    from codeagent.execution.manager import ExecutionManager

    em = execution_manager or ExecutionManager()

    def _run_python_handler(
        script_path: str,
        args: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        res = em.run_python(script_path=script_path, args=args)
        return {
            "command": res.command,
            "exit_code": res.exit_code,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "duration_seconds": res.duration_seconds,
            "timed_out": res.timed_out,
            "success": res.success,
        }

    registry.register(
        ToolDefinition(
            name="run_python",
            description="Execute a Python script within the workspace using the configured virtual environment.",
            parameters={
                "type": "object",
                "properties": {
                    "script_path": {"type": "string", "description": "Relative path to Python script file"},
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional command-line arguments to pass to the script",
                    },
                },
                "required": ["script_path"],
            },
            handler=_run_python_handler,
        )
    )

    def _execute_command_handler(
        command: str,
        shell_type: str = "direct",
    ) -> dict[str, Any]:
        res = em.execute_command(command_or_args=command, shell_type=shell_type)
        return {
            "command": res.command,
            "exit_code": res.exit_code,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "duration_seconds": res.duration_seconds,
            "timed_out": res.timed_out,
            "success": res.success,
        }

    registry.register(
        ToolDefinition(
            name="execute_command",
            description="Execute an approved Windows terminal command or utility in the workspace.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command string to execute"},
                    "shell_type": {
                        "type": "string",
                        "enum": ["direct", "cmd", "powershell"],
                        "description": "Terminal environment (default: direct)",
                    },
                },
                "required": ["command"],
            },
            handler=_execute_command_handler,
        )
    )

    def _install_dependency_handler(
        package_name: Optional[str] = None,
        requirements_file: Optional[str] = None,
        upgrade: bool = False,
    ) -> dict[str, Any]:
        if requirements_file:
            res = em.install_requirements(requirements_file=requirements_file)
        elif package_name:
            res = em.install_dependency(package_name=package_name, upgrade=upgrade)
        else:
            raise ValueError("Must provide either 'package_name' or 'requirements_file'.")
        return {
            "command": res.command,
            "exit_code": res.exit_code,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "success": res.success,
        }

    registry.register(
        ToolDefinition(
            name="install_dependency",
            description="Install Python dependencies via pip into the active virtual environment.",
            parameters={
                "type": "object",
                "properties": {
                    "package_name": {"type": "string", "description": "Package name and optional version (e.g. 'flask==3.0.0')"},
                    "requirements_file": {"type": "string", "description": "Path to requirements.txt if installing from file"},
                    "upgrade": {"type": "boolean", "description": "Whether to upgrade existing package"},
                },
                "required": [],
            },
            handler=_install_dependency_handler,
        )
    )

    def _run_tests_handler(
        framework: Optional[str] = None,
        test_path: Optional[str] = None,
    ) -> dict[str, Any]:
        report = em.run_tests(framework=framework, test_path=test_path)
        return {
            "framework": report.framework,
            "status": report.status,
            "passed": report.passed,
            "failed": report.failed,
            "skipped": report.skipped,
            "total": report.total,
            "duration_seconds": report.duration_seconds,
            "stdout": report.stdout,
            "stderr": report.stderr,
        }

    registry.register(
        ToolDefinition(
            name="run_tests",
            description="Execute automated tests in the workspace using pytest or unittest.",
            parameters={
                "type": "object",
                "properties": {
                    "framework": {
                        "type": "string",
                        "enum": ["pytest", "unittest"],
                        "description": "Test runner framework (auto-detected if omitted)",
                    },
                    "test_path": {"type": "string", "description": "Optional test file or directory path"},
                },
                "required": [],
            },
            handler=_run_tests_handler,
        )
    )

    def _get_process_status_handler(process_id: Optional[int] = None) -> dict[str, Any]:
        procs = em.list_processes()
        if process_id is not None:
            match = next((p for p in procs if p.process_id == process_id), None)
            return {"process": match.__dict__ if match else None}
        return {"processes": [p.__dict__ for p in procs]}

    registry.register(
        ToolDefinition(
            name="get_process_status",
            description="Check status of actively running or recent processes.",
            parameters={
                "type": "object",
                "properties": {
                    "process_id": {"type": "integer", "description": "Optional process PID to inspect"},
                },
                "required": [],
            },
            handler=_get_process_status_handler,
        )
    )

    def _cancel_execution_handler(process_id: int) -> dict[str, Any]:
        cancelled = em.cancel_execution(process_id)
        return {"process_id": process_id, "cancelled": cancelled}

    registry.register(
        ToolDefinition(
            name="cancel_execution",
            description="Cancel and terminate a running process by its process ID.",
            parameters={
                "type": "object",
                "properties": {
                    "process_id": {"type": "integer", "description": "Process ID to cancel"},
                },
                "required": ["process_id"],
            },
            handler=_cancel_execution_handler,
        )
    )


def register_debugging_tools(
    registry: ToolRegistry,
    debugger: Optional[Any] = None,
) -> None:
    """Register Phase 6 autonomous debugging tools into registry."""
    from codeagent.debugging.debugger import AutonomousDebugger

    dbg = debugger or AutonomousDebugger()

    def _diagnose_error_handler(
        error_text: str,
        target_file: Optional[str] = None,
        target_line: Optional[int] = None,
    ) -> dict[str, Any]:
        err = dbg.error_detector.detect_from_text(error_text)
        if not err:
            return {"status": "no_error_detected", "message": "Unable to detect error in provided text."}
        if target_file:
            err.file_path = target_file
        if target_line:
            err.line_number = target_line

        ctx = None
        if err.file_path:
            try:
                ctx = dbg.code_inspector.inspect_file(err.file_path, target_line=err.line_number)
            except Exception:
                pass

        diag = dbg.root_cause_analyzer.analyze(err, code_context=ctx)
        return {
            "error_type": err.error_type,
            "error_message": err.error_message,
            "file_path": err.file_path,
            "line_number": err.line_number,
            "root_cause": diag.root_cause,
            "confidence": diag.confidence,
            "suggested_solution": diag.suggested_solution,
            "evidence": diag.evidence,
        }

    registry.register(
        ToolDefinition(
            name="diagnose_error",
            description="Analyze and diagnose Python errors, tracebacks, and test failures.",
            parameters={
                "type": "object",
                "properties": {
                    "error_text": {"type": "string", "description": "Raw traceback or error message to diagnose"},
                    "target_file": {"type": "string", "description": "Optional affected file path"},
                    "target_line": {"type": "integer", "description": "Optional affected line number"},
                },
                "required": ["error_text"],
            },
            handler=_diagnose_error_handler,
        )
    )

    def _retest_code_handler(
        test_path: Optional[str] = None,
        script_path: Optional[str] = None,
    ) -> dict[str, Any]:
        res = dbg.retest_manager.retest(test_path=test_path, script_path=script_path)
        return {
            "target": res.test_target,
            "status": res.status,
            "is_resolved": res.is_resolved,
            "passed": res.passed,
            "failed": res.new_failed,
            "total": res.total,
            "duration_seconds": res.duration_seconds,
        }

    registry.register(
        ToolDefinition(
            name="retest_code",
            description="Execute automated retesting of a test suite or script to verify fixes.",
            parameters={
                "type": "object",
                "properties": {
                    "test_path": {"type": "string", "description": "Path to test file to rerun (e.g. 'tests/test_app.py')"},
                    "script_path": {"type": "string", "description": "Path to Python script to rerun"},
                },
                "required": [],
            },
            handler=_retest_code_handler,
        )
    )


def register_intelligence_tools(
    registry: ToolRegistry,
    project_manager: Optional[Any] = None,
) -> None:
    """Register Phase 7 project intelligence and persistent memory tools into registry."""
    from codeagent.intelligence.project_manager import ProjectManager

    proj_mgr = project_manager or ProjectManager()

    def _search_code_handler(query: str, search_type: str = "text", limit: int = 10) -> list[dict[str, Any]]:
        results = proj_mgr.search_active_project(query=query, search_type=search_type, limit=limit)
        return [
            {
                "file_path": r.file_path,
                "line_number": r.line_number,
                "matched_content": r.matched_content,
                "match_type": r.match_type,
                "relevance_score": r.relevance_score,
            }
            for r in results
        ]

    registry.register(
        ToolDefinition(
            name="search_code",
            description="Search indexed source code across project files, symbols, functions, or text.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search string, symbol name, or regex pattern"},
                    "search_type": {
                        "type": "string",
                        "enum": ["text", "symbol", "file", "semantic"],
                        "description": "Search strategy: 'text' (substring), 'symbol' (function/class name), 'file' (filename pattern), 'semantic' (concept similarity)",
                    },
                    "limit": {"type": "integer", "description": "Maximum results to return (default 10)"},
                },
                "required": ["query"],
            },
            handler=_search_code_handler,
        )
    )

    def _get_project_architecture_handler() -> dict[str, Any]:
        analysis = proj_mgr.analyze_active_project()
        return {
            "project_type": analysis.project_type,
            "primary_language": analysis.primary_language,
            "languages": analysis.languages,
            "frameworks": analysis.frameworks,
            "entry_points": analysis.entry_points,
            "build_systems": analysis.build_systems,
            "dependency_files": analysis.dependency_files,
            "test_directories": analysis.test_directories,
            "summary": analysis.to_summary(),
        }

    registry.register(
        ToolDefinition(
            name="get_project_architecture",
            description="Retrieve project architectural summary, detected frameworks, entry points, and directory layout.",
            parameters={
                "type": "object",
                "properties": {},
            },
            handler=_get_project_architecture_handler,
        )
    )

    def _get_project_memory_handler(query: Optional[str] = None, category: Optional[str] = None) -> list[dict[str, Any]]:
        if query:
            facts = proj_mgr.memory_manager.search_facts(project_id=proj_mgr.active_project_id, query=query)
        else:
            facts = proj_mgr.memory_manager.list_facts(project_id=proj_mgr.active_project_id, category=category)
        return [
            {
                "id": f.id,
                "category": f.category,
                "key": f.key,
                "value": f.value,
                "confidence": f.confidence,
            }
            for f in facts
        ]

    registry.register(
        ToolDefinition(
            name="get_project_memory",
            description="Retrieve persisted project facts, coding conventions, architectural decisions, and constraints.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Optional search query to filter memories"},
                    "category": {
                        "type": "string",
                        "enum": ["architecture", "convention", "decision", "limitation", "dependency", "stack", "general"],
                        "description": "Optional category filter",
                    },
                },
            },
            handler=_get_project_memory_handler,
        )
    )

    def _store_project_memory_handler(key: str, value: str, category: str = "general") -> dict[str, Any]:
        fact = proj_mgr.memory_manager.store_fact(
            project_id=proj_mgr.active_project_id,
            key=key,
            value=value,
            category=category,
            source="assistant",
        )
        return {
            "id": fact.id,
            "status": "stored",
            "summary": fact.to_summary(),
        }

    registry.register(
        ToolDefinition(
            name="store_project_memory",
            description="Persist an important project fact, decision, coding convention, or limitation to SQLite memory.",
            parameters={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Short identifier or topic (e.g. 'auth_method', 'database_orm')"},
                    "value": {"type": "string", "description": "Details of the fact, convention, or decision"},
                    "category": {
                        "type": "string",
                        "enum": ["architecture", "convention", "decision", "limitation", "dependency", "stack", "general"],
                        "description": "Category for the memory item",
                    },
                },
                "required": ["key", "value"],
            },
            handler=_store_project_memory_handler,
        )
    )

    return registry


def register_git_and_safety_tools(
    registry: ToolRegistry,
    git_manager: Optional[Any] = None,
    permission_manager: Optional[Any] = None,
    protected_paths_manager: Optional[Any] = None,
    backup_manager: Optional[Any] = None,
    audit_logger: Optional[Any] = None,
) -> ToolRegistry:
    """Register all Phase 8 Git integration and safety management tools into the registry."""
    from codeagent.git.git_manager import GitManager
    from codeagent.safety.permission_manager import SafetyPermissionManager
    from codeagent.safety.protected_paths import ProtectedPathsManager
    from codeagent.safety.backup_manager import SafetyBackupManager
    from codeagent.safety.audit_logger import SecurityAuditLogger

    gm = git_manager or GitManager()
    pm = permission_manager or SafetyPermissionManager()
    ppm = protected_paths_manager or ProtectedPathsManager()
    bm = backup_manager or SafetyBackupManager()
    al = audit_logger or SecurityAuditLogger()

    # 1. git_repository_info
    def _git_repository_info_handler() -> dict[str, Any]:
        info = gm.get_repository_info()
        return {
            "is_git_repo": info.is_git_repo,
            "repo_root": info.repo_root,
            "current_branch": info.current_branch,
            "is_detached_head": info.is_detached_head,
            "has_commits": info.has_commits,
            "head_commit_hash": info.head_commit_hash,
            "is_clean": info.is_clean,
            "summary": info.to_summary(),
        }

    registry.register(
        ToolDefinition(
            name="git_repository_info",
            description="Check whether the workspace is a Git repository, and inspect branch, HEAD commit, and cleanliness.",
            parameters={"type": "object", "properties": {}},
            handler=_git_repository_info_handler,
        )
    )

    # 2. git_status
    def _git_status_handler() -> dict[str, Any]:
        status = gm.get_status()
        return {
            "branch": status.branch,
            "upstream": status.upstream,
            "ahead": status.ahead,
            "behind": status.behind,
            "is_clean": status.is_clean,
            "has_conflicts": status.has_conflicts,
            "staged_files": [f.model_dump() for f in status.staged_files],
            "unstaged_files": [f.model_dump() for f in status.unstaged_files],
            "untracked_files": [f.model_dump() for f in status.untracked_files],
            "conflict_files": [f.model_dump() for f in status.conflict_files],
            "summary": status.to_summary(),
        }

    registry.register(
        ToolDefinition(
            name="git_status",
            description="Inspect Git working tree status: staged, unstaged, untracked, and conflict files.",
            parameters={"type": "object", "properties": {}},
            handler=_git_status_handler,
        )
    )

    # 3. git_diff
    def _git_diff_handler(staged: bool = False, file_path: Optional[str] = None) -> dict[str, Any]:
        res = gm.get_diff(staged=staged, file_path=file_path)
        return {
            "is_staged": res.is_staged,
            "stat_summary": res.stat_summary,
            "total_files_changed": res.total_files_changed,
            "total_insertions": res.total_insertions,
            "total_deletions": res.total_deletions,
            "raw_diff": res.raw_diff,
            "is_truncated": res.is_truncated,
            "summary": res.to_summary(),
        }

    registry.register(
        ToolDefinition(
            name="git_diff",
            description="Retrieve unified Git diff of working tree or staged changes with secret redaction and byte limits.",
            parameters={
                "type": "object",
                "properties": {
                    "staged": {"type": "boolean", "description": "If true, inspect staged changes (--cached)"},
                    "file_path": {"type": "string", "description": "Optional single file filter"},
                },
            },
            handler=_git_diff_handler,
        )
    )

    # 4. git_list_branches
    def _git_list_branches_handler() -> dict[str, Any]:
        res = gm.list_branches()
        return {
            "current_branch": res.current_branch,
            "is_detached_head": res.is_detached_head,
            "branches": [b.model_dump() for b in res.branches],
            "summary": res.to_summary(),
        }

    registry.register(
        ToolDefinition(
            name="git_list_branches",
            description="List all local repository branches and active HEAD.",
            parameters={"type": "object", "properties": {}},
            handler=_git_list_branches_handler,
        )
    )

    # 5. git_create_branch
    def _git_create_branch_handler(branch_name: str, switch: bool = False) -> dict[str, Any]:
        res = gm.create_branch(branch_name=branch_name, switch=switch)
        return res.model_dump()

    registry.register(
        ToolDefinition(
            name="git_create_branch",
            description="Create a new local Git branch with ref name validation and collision prevention.",
            parameters={
                "type": "object",
                "properties": {
                    "branch_name": {"type": "string", "description": "Name of the new branch to create"},
                    "switch": {"type": "boolean", "description": "Whether to switch to the new branch immediately"},
                },
                "required": ["branch_name"],
            },
            handler=_git_create_branch_handler,
        )
    )

    # 6. git_switch_branch
    def _git_switch_branch_handler(branch_name: str) -> dict[str, Any]:
        res = gm.switch_branch(branch_name=branch_name)
        return res.model_dump()

    registry.register(
        ToolDefinition(
            name="git_switch_branch",
            description="Switch to an existing local branch safely with dirty working tree checks.",
            parameters={
                "type": "object",
                "properties": {
                    "branch_name": {"type": "string", "description": "Target branch to check out"},
                },
                "required": ["branch_name"],
            },
            handler=_git_switch_branch_handler,
        )
    )

    # 7. git_commit_changes
    def _git_commit_changes_handler(
        message: Optional[str] = None,
        files: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        res = gm.commit_changes(files_to_stage=files, commit_message=message)
        return {
            "success": res.success,
            "commit_hash": res.commit_hash,
            "branch": res.branch,
            "message": res.message,
            "files_committed": res.files_committed,
            "summary": res.to_summary(),
        }

    registry.register(
        ToolDefinition(
            name="git_commit_changes",
            description="Execute controlled Git commit with explicit file staging, secret scanning, approval, and hash verification.",
            parameters={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Commit message (conventional commits format recommended)"},
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Explicit list of files to stage (never wildcards or '.')",
                    },
                },
            },
            handler=_git_commit_changes_handler,
        )
    )

    # 8. check_command_permission
    def _check_command_permission_handler(command: str) -> dict[str, Any]:
        res = pm.evaluate_command(command)
        return {
            "verdict": res.verdict.value,
            "command": res.command,
            "executable": res.executable,
            "subcommand": res.subcommand,
            "reason": res.reason,
            "risk_level": res.risk_level,
            "requires_approval": res.requires_approval,
        }

    registry.register(
        ToolDefinition(
            name="check_command_permission",
            description="Evaluate any terminal or Git command against centralized 3-tier security policy (ALLOW, DENY, REQUIRE_APPROVAL).",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command string to evaluate"},
                },
                "required": ["command"],
            },
            handler=_check_command_permission_handler,
        )
    )

    # 9. list_protected_paths
    def _list_protected_paths_handler() -> list[dict[str, Any]]:
        rules = ppm.list_protected_rules()
        return [r.model_dump() for r in rules]

    registry.register(
        ToolDefinition(
            name="list_protected_paths",
            description="List all active default and user-configured protected files, directories, and sensitive patterns.",
            parameters={"type": "object", "properties": {}},
            handler=_list_protected_paths_handler,
        )
    )

    # 10. add_protected_path
    def _add_protected_path_handler(path_or_pattern: str) -> dict[str, Any]:
        ppm.add_custom_protected_path(path_or_pattern)
        return {"status": "added", "pattern": path_or_pattern}

    registry.register(
        ToolDefinition(
            name="add_protected_path",
            description="Register an additional file, directory, or pattern to protect from agent write/delete operations.",
            parameters={
                "type": "object",
                "properties": {
                    "path_or_pattern": {"type": "string", "description": "Relative path or glob pattern to protect"},
                },
                "required": ["path_or_pattern"],
            },
            handler=_add_protected_path_handler,
        )
    )

    # 11. remove_protected_path
    def _remove_protected_path_handler(path_or_pattern: str) -> dict[str, Any]:
        removed = ppm.remove_custom_protected_path(path_or_pattern)
        return {"status": "removed" if removed else "not_found", "pattern": path_or_pattern}

    registry.register(
        ToolDefinition(
            name="remove_protected_path",
            description="Remove a previously registered custom protected path.",
            parameters={
                "type": "object",
                "properties": {
                    "path_or_pattern": {"type": "string", "description": "Custom protected path to remove"},
                },
                "required": ["path_or_pattern"],
            },
            handler=_remove_protected_path_handler,
        )
    )

    # 12. create_backup
    def _create_backup_handler(file_path: str) -> dict[str, Any]:
        rec = bm.create_backup(file_path)
        if not rec:
            return {"status": "skipped", "message": f"File '{file_path}' does not exist yet."}
        return {"status": "created", "backup": rec.model_dump()}

    registry.register(
        ToolDefinition(
            name="create_backup",
            description="Create a verifiable SHA-256 backup snapshot of an existing workspace file.",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to file to back up"},
                },
                "required": ["file_path"],
            },
            handler=_create_backup_handler,
        )
    )

    # 13. list_backups
    def _list_backups_handler(file_path: Optional[str] = None) -> list[dict[str, Any]]:
        records = bm.list_backups(file_path_filter=file_path)
        return [r.model_dump() for r in records[:20]]

    registry.register(
        ToolDefinition(
            name="list_backups",
            description="View file backup archive history, timestamps, and SHA-256 integrity hashes.",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Optional file path filter"},
                },
            },
            handler=_list_backups_handler,
        )
    )

    # 14. restore_backup
    def _restore_backup_handler(backup_id: str, force: bool = False) -> dict[str, Any]:
        res = bm.restore_backup(backup_id=backup_id, force=force)
        return res.model_dump()

    registry.register(
        ToolDefinition(
            name="restore_backup",
            description="Restore a file from safety backup verifying SHA-256 integrity and preventing overwrite of newer modifications.",
            parameters={
                "type": "object",
                "properties": {
                    "backup_id": {"type": "string", "description": "ID of backup to restore"},
                    "force": {"type": "boolean", "description": "Override conflict warnings if file was modified after backup"},
                },
                "required": ["backup_id"],
            },
            handler=_restore_backup_handler,
        )
    )

    # 15. get_audit_log
    def _get_audit_log_handler(
        operation_id: Optional[str] = None,
        operation_type: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if operation_id:
            ev = al.get_event(operation_id)
            return [ev.model_dump()] if ev else []
        records = al.list_events(operation_type=operation_type, limit=limit)
        return [r.model_dump() for r in records]

    registry.register(
        ToolDefinition(
            name="get_audit_log",
            description="Query immutable security audit logs to inspect past operations, decisions, and outcomes.",
            parameters={
                "type": "object",
                "properties": {
                    "operation_id": {"type": "string", "description": "Optional specific operation ID to lookup"},
                    "operation_type": {"type": "string", "description": "Optional operation type filter (e.g. 'git_commit')"},
                    "limit": {"type": "integer", "description": "Maximum records to return (default: 20)"},
                },
            },
            handler=_get_audit_log_handler,
        )
    )

    return registry


def register_multiagent_tools(
    registry: ToolRegistry,
    workflow_engine: Optional[Any] = None,
) -> ToolRegistry:
    """Register all Phase 9 Multi-Agent Architecture and Workflow Orchestration tools."""
    from codeagent.agents.workflow_engine import WorkflowEngine
    from codeagent.agents.workflow_templates import WorkflowType

    we = workflow_engine or WorkflowEngine()

    # 1. run_multiagent_workflow
    def _run_multiagent_workflow_handler(
        goal: str,
        workflow_type: str = "BUILD_PROJECT",
    ) -> dict[str, Any]:
        try:
            wt = WorkflowType(workflow_type)
        except ValueError:
            wt = WorkflowType.BUILD_PROJECT
        res = we.run_workflow(goal=goal, workflow_type=wt)
        return {
            "workflow_id": res.workflow_id,
            "status": res.status.value,
            "tasks_total": res.tasks_total,
            "tasks_completed": res.tasks_completed,
            "tasks_failed": res.tasks_failed,
            "review_verdict": res.review_verdict,
            "summary": res.summary,
            "duration_seconds": res.execution_duration_seconds,
        }

    registry.register(
        ToolDefinition(
            name="run_multiagent_workflow",
            description="Launch a coordinated multi-agent workflow (Planner, Code, Debugger, Reviewer, Coordinator).",
            parameters={
                "type": "object",
                "properties": {
                    "goal": {"type": "string", "description": "High-level user coding goal or bugfix objective"},
                    "workflow_type": {
                        "type": "string",
                        "enum": ["BUILD_PROJECT", "FIX_BUG", "CODE_REVIEW", "ADD_FEATURE", "REFACTOR_PROJECT"],
                        "description": "Standard workflow template (default: BUILD_PROJECT)",
                    },
                },
                "required": ["goal"],
            },
            handler=_run_multiagent_workflow_handler,
        )
    )

    # 2. get_workflow_status
    def _get_workflow_status_handler(workflow_id: str) -> dict[str, Any]:
        wf = we.get_workflow_status(workflow_id)
        if not wf:
            return {"error": f"Workflow '{workflow_id}' not found."}
        tasks = we.list_tasks_for_workflow(workflow_id)
        return {
            "workflow_id": wf.workflow_id,
            "status": wf.status.value,
            "user_task": wf.user_task,
            "workflow_type": wf.workflow_type,
            "start_time": wf.start_time,
            "end_time": wf.end_time,
            "error": wf.error,
            "tasks": [t.to_summary() for t in tasks],
        }

    registry.register(
        ToolDefinition(
            name="get_workflow_status",
            description="Inspect the current state, progress, and task list of an active or completed workflow.",
            parameters={
                "type": "object",
                "properties": {
                    "workflow_id": {"type": "string", "description": "Unique workflow ID to inspect"},
                },
                "required": ["workflow_id"],
            },
            handler=_get_workflow_status_handler,
        )
    )

    # 3. list_workflows
    def _list_workflows_handler(limit: int = 20) -> list[dict[str, Any]]:
        records = we.list_workflows(limit=limit)
        return [
            {
                "workflow_id": r.workflow_id,
                "status": r.status.value,
                "user_task": r.user_task[:60],
                "workflow_type": r.workflow_type,
                "start_time": r.start_time,
            }
            for r in records
        ]

    registry.register(
        ToolDefinition(
            name="list_workflows",
            description="List recent multi-agent workflow executions and their statuses.",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Maximum records to return (default: 20)"},
                },
            },
            handler=_list_workflows_handler,
        )
    )

    # 4. inspect_workflow_task
    def _inspect_workflow_task_handler(task_id: str) -> dict[str, Any]:
        task = we.get_task(task_id)
        if not task:
            return {"error": f"Task '{task_id}' not found."}
        return task.model_dump()

    registry.register(
        ToolDefinition(
            name="inspect_workflow_task",
            description="Retrieve granular details, inputs, outputs, and dependencies for a workflow task.",
            parameters={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Unique task ID to inspect"},
                },
                "required": ["task_id"],
            },
            handler=_inspect_workflow_task_handler,
        )
    )

    # 5. cancel_workflow
    def _cancel_workflow_handler(workflow_id: str) -> dict[str, Any]:
        success = we.cancel_workflow(workflow_id)
        return {
            "workflow_id": workflow_id,
            "cancelled": success,
            "message": "Workflow cancelled." if success else "Workflow not found.",
        }

    registry.register(
        ToolDefinition(
            name="cancel_workflow",
            description="Immediately cancel an active multi-agent workflow and all its pending tasks.",
            parameters={
                "type": "object",
                "properties": {
                    "workflow_id": {"type": "string", "description": "Workflow ID to cancel"},
                },
                "required": ["workflow_id"],
            },
            handler=_cancel_workflow_handler,
        )
    )

    return registry



