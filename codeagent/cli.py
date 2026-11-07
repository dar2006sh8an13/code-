"""Command Line Interface (CLI) implementation for CodeAgent using Typer and Rich."""

import os
from pathlib import Path
import socket
import sys
from typing import Optional

import httpx
from ollama import Client as OllamaSDKClient

# Ensure standard output streams support UTF-8 on Windows without charmap encoding errors
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
import typer

from codeagent.config.settings import Settings, get_settings
from codeagent.context.manager import ContextManager
from codeagent.conversation.manager import ConversationManager
from codeagent.conversation.storage import ConversationNotFoundError, CorruptedConversationError
from codeagent.llm.client import (
    LLMClient,
    ModelNotFoundError,
    OllamaClientError,
    OllamaConnectionError,
    OllamaTimeoutError,
)
from codeagent.llm.streaming import StreamingEngine
from codeagent.llm.structured import (
    ErrorAnalysis,
    StructuredResponseEngine,
    StructuredValidationError,
)
from codeagent.tools.executor import MaxIterationsExceededError, ToolExecutor
from codeagent.tools.registry import get_default_registry
from codeagent.filesystem.editor import EditNotApprovedError, EditProposal
from codeagent.filesystem.manager import FilesystemManager
from codeagent.filesystem.path_validator import (
    InvalidPathError,
    PathTraversalError,
    SensitiveFileError,
    WorkspaceSecurityError,
)
from codeagent.filesystem.reader import BinaryFileError, FileTooLargeError
from codeagent.filesystem.writer import FileAlreadyExistsError
from codeagent.filesystem.deleter import DeletionNotConfirmedError, DirectoryDeletionBlockedError
from codeagent.execution.command_validator import (
    CommandInjectionError,
    CommandSecurityError,
    DangerousCommandError,
    DisallowedExecutableError,
)
from codeagent.execution.manager import ExecutionManager
from codeagent.execution.permission_manager import (
    ExecutionDisabledError,
    ExecutionNotApprovedError,
    ExecutionPlan,
)
from codeagent.execution.process_manager import ProcessLimitExceededError
from codeagent.debugging.debugger import AutonomousDebugger
from codeagent.debugging.fix_generator import FilePatch
from codeagent.debugging.patch_manager import PatchConflictError, PatchRejectedError, PatchVerificationError
from codeagent.debugging.report_generator import DebugReport
from codeagent.intelligence.project_manager import ProjectManager
from codeagent.indexing.indexer import ProjectIndexer
from codeagent.memory.memory_manager import MemoryManager
from codeagent.context.token_counter import estimate_tokens
from codeagent.git.git_manager import GitManager
from codeagent.safety.permission_manager import SafetyPermissionManager, PolicyVerdict
from codeagent.safety.protected_paths import ProtectedPathsManager
from codeagent.safety.backup_manager import SafetyBackupManager
from codeagent.safety.audit_logger import SecurityAuditLogger
from codeagent.agents.agent_factory import AgentFactory
from codeagent.agents.base_agent import AgentRole
from codeagent.agents.workflow_engine import WorkflowEngine
from codeagent.agents.workflow_templates import WorkflowType
from codeagent.banner import display_startup_banner, build_banner_renderable

# Initialize Rich Console and Typer app
console = Console()
app = typer.Typer(
    name="codeag",
    help="Coder with Code: Local Autonomous AI Coding Assistant powered by Ollama and Qwen3.",
    no_args_is_help=False,
    add_completion=False,
)

SYSTEM_CODING_INSTRUCTIONS = (
    "You are Coder with Code, an autonomous AI coding assistant running locally. Built in India. Designed for developers everywhere.\n"
    "You have access to safe filesystem tools: `create_file`, `read_file`, `edit_file`, `create_directory`.\n\n"
    "CRITICAL CODING INSTRUCTIONS:\n"
    "1. When the user asks you to create, write, generate, or build any code or file, you MUST invoke the `create_file` tool.\n"
    "2. Provide the exact path and the COMPLETE, fully working content with all HTML, CSS, and JavaScript.\n"
    "3. Do NOT just output code blocks in markdown text. You must call `create_file` to write the file to disk.\n"
    "4. For web applications, include modern responsive design, all requested features, and LocalStorage persistence.\n"
    "5. After creating a file, verify it by calling `read_file` to confirm that the file exists and is populated.\n"
    "6. Never report completion until the file has been created and verified on disk.\n"
)


def render_execution_status(phase: str, details: str, target_console: Optional[Console] = None) -> None:
    """Render structured execution lifecycle status distinguishing agent phases."""
    out = target_console or console
    phase_styles = {
        "Planning": "bold cyan",
        "Generating": "bold blue",
        "Tool selected": "bold yellow",
        "Awaiting approval": "bold magenta",
        "Executing": "bold blue",
        "Execution successful": "bold green",
        "Execution failed": "bold red",
        "File verified": "bold green",
    }
    style = phase_styles.get(phase, "bold white")
    out.print(f"[{style}]● {phase}:[/{style}] {details}")


def display_banner(settings: Settings, active_model: str, is_online: bool, workspace_root: Optional[str] = None) -> None:
    """Display a professional startup banner for Coder with Code (backward compatibility wrapper)."""
    display_startup_banner(
        console=console,
        settings=settings,
        active_model=active_model,
        is_online=is_online,
        workspace_root=workspace_root,
        force=True,
    )


def show_help_menu() -> None:
    """Display interactive slash commands help table."""
    table = Table(
        title="Interactive Mode Commands",
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
    )
    table.add_column("Command", style="bold yellow", width=22)
    table.add_column("Description", style="white")

    table.add_row("/help", "Display this help menu with all available commands.")
    # Production & Diagnostics commands (Phase 10)
    table.add_row("/health", "Run quick health checks across application, databases, and Ollama.")
    table.add_row("/diagnostics [-e f]", "Display or export complete JSON system diagnostic snapshot.")
    table.add_row("/monitor", "View real-time subsystem status, database sizes, and host memory.")
    table.add_row("/performance", "Run local non-LLM latency benchmarks and memory consumption check.")
    table.add_row("/config [subcmd]", "Inspect, validate, or initialize multi-tier configuration.")

    # Multi-Agent Architecture & Workflow commands (Phase 9)
    table.add_row("/agents [subcmd]", "Multi-agent subsystem (list, status, inspect <role>).")
    table.add_row("/workflow [subcmd]", "Autonomous workflows (run <goal>, status [id], list, inspect <id>, cancel <id>, resume <id>).")
    table.add_row("/task [subcmd]", "Workflow task inspection (list [workflow_id], inspect <task_id>).")

    # Git & Safety commands (Phase 8)
    table.add_row("/git [subcmd]", "Git engine (status, diff [--staged], branches, branch-create <n>, switch <n>, commit).")
    table.add_row("/safety [subcmd]", "Safety policy & audit (permissions [cmd], protected [add/remove], audit [-o ID]).")
    table.add_row("/backup [subcmd]", "Verifiable file backups (create <file>, list, restore <id> [--force]).")

    # Project Intelligence & Memory commands (Phase 7)
    table.add_row("/project [subcmd]", "Multi-project manager (list, add <path>, switch <id>, info, analyze).")
    table.add_row("/index [refresh]", "Trigger incremental indexing or full rebuild of project code.")
    table.add_row("/search <query>", "Codebase search (text, symbol <name>, file <pattern>, semantic <query>).")
    table.add_row("/memory [subcmd]", "Persistent project memory (show, search <query>, store <c> <k> <v>, delete <id>).")
    table.add_row("/context [show]", "Inspect active token budget, context window headroom, and project context.")

    # Debugging commands (Phase 6)
    table.add_row("/debug [path]", "Autonomous 16-step diagnosis, patch generation, approval, and verification.")
    table.add_row("/diagnose [err]", "Analyze and explain an error traceback or failure message.")
    table.add_row("/fix <file>", "Generate a minimal unified diff repair for a diagnosed error.")
    table.add_row("/retest [path]", "Rerun previous failing test suite and check for regressions.")
    table.add_row("/rollback [id]", "Restore pre-debug backup or revert the last applied patch.")
    table.add_row("/debug-report", "Display the structured report from the most recent debugging session.")

    # Execution commands (Phase 5)
    table.add_row("/python <file> [a]", "Execute a Python script using the active virtual environment.")
    table.add_row("/run <command>", "Execute an approved terminal command inside the workspace.")
    table.add_row("/install <pkg>", "Install Python package via pip with mandatory approval.")
    table.add_row("/test [path]", "Run automated project tests using pytest or unittest.")
    table.add_row("/processes", "List running and active background processes.")
    table.add_row("/cancel <pid>", "Cancel a running process by its process ID.")

    # Filesystem commands (Phase 3)
    table.add_row("/workspace [path]", "Show current workspace boundary or set a new root directory.")
    table.add_row("/scan [path]", "Scan workspace directory tree and display formatted hierarchy & stats.")
    table.add_row("/tree [path]", "Alias for /scan.")
    table.add_row("/project [path]", "Analyze project structure, frameworks, entry points, and dependencies.")
    table.add_row("/read <path> [s] [e]", "Read file contents (optional start and end line ranges).")
    table.add_row("/newfile <path>", "Create a new file with interactive multiline content.")
    table.add_row("/edit <path>", "Propose an edit, show unified diff, and apply upon approval.")
    table.add_row("/delete <path>", "Safely delete a single file after explicit user confirmation.")
    table.add_row("/backups", "List automatic file backups created before edits or deletions.")
    table.add_row("/restore <id>", "Restore a file from a specified backup ID.")

    # Session commands (Phase 1 & 2)
    table.add_row("/new", "Start a fresh conversation session with clean context.")
    table.add_row("/history", "View recent conversation messages in the current session.")
    table.add_row("/save [name]", "Save current conversation history to disk.")
    table.add_row("/load <name>", "Load a previously saved conversation by name or ID.")
    table.add_row(
        "/model [name]",
        "List installed models, or switch active model (e.g., /model qwen3:latest).",
    )
    table.add_row("/clear", "Clear the terminal screen.")
    table.add_row("/exit", "Exit interactive mode and return to terminal.")
    table.add_row("/quit", "Alias for /exit.")

    console.print(table)


def run_connection_check(client: LLMClient, selected_model: str, settings: Settings) -> None:
    """Run diagnostics and display connection status and installed models."""
    console.print()
    console.print(
        Panel(
            f"[bold cyan]{settings.app_name}[/bold cyan] Diagnostic & Connection Check",
            border_style="cyan",
            expand=False,
        )
    )

    # Info table
    info_table = Table(show_header=False, box=None)
    info_table.add_column("Key", style="bold white", width=26)
    info_table.add_column("Value", style="cyan")

    ws_root = settings.workspace_root or str(os.getcwd())
    info_table.add_row("Application Name:", settings.app_name)
    info_table.add_row("Application Version:", settings.app_version)
    info_table.add_row("Ollama Host:", settings.ollama_host)
    info_table.add_row("Selected Model:", f"[bold green]{selected_model}[/bold green]")
    info_table.add_row("Workspace Root:", f"[bold yellow]{ws_root}[/bold yellow]")
    info_table.add_row("Request Timeout:", f"{settings.request_timeout:.0f} seconds")
    info_table.add_row("Temperature:", str(settings.temperature))
    info_table.add_row("Context Window:", f"{settings.context_window} tokens")
    info_table.add_row("Max Output Tokens:", f"{settings.max_output_tokens} tokens")
    info_table.add_row("Max History Messages:", str(settings.max_history_messages))
    info_table.add_row("Max Tool Iterations:", str(settings.max_tool_iterations))
    info_table.add_row("Conversation Storage:", settings.conversation_storage_path)
    info_table.add_row("Max File Read Size:", f"{settings.max_file_size_mb} MB")
    info_table.add_row("Max Scan Depth / Entries:", f"{settings.max_scan_depth} levels / {settings.max_scan_entries} entries")
    info_table.add_row("Automatic Backups:", "Enabled" if settings.backup_enabled else "Disabled")
    info_table.add_row("Backup Directory:", settings.backup_directory)
    info_table.add_row("Code Execution:", "Enabled" if settings.execution_enabled else "Disabled")
    info_table.add_row("Execution Timeout:", f"{settings.execution_timeout_seconds:.0f}s")
    info_table.add_row("Max Concurrent Procs:", str(settings.max_concurrent_processes))
    info_table.add_row("Audit Logging:", "Enabled" if settings.execution_audit_enabled else "Disabled")
    info_table.add_row("Autonomous Debugging:", f"Enabled (max {settings.max_debug_iterations} iters, {settings.max_fix_attempts} fixes)")
    info_table.add_row("Debug Timeout:", f"{settings.debug_timeout_seconds:.0f}s")
    info_table.add_row("Project Indexing:", f"{'Enabled' if settings.project_index_enabled else 'Disabled'} (max {settings.max_index_files} files, chunk {settings.index_chunk_size})")
    info_table.add_row("Persistent Memory:", f"{'Enabled' if settings.memory_enabled else 'Disabled'} ({settings.project_data_path}/memory.db)")
    info_table.add_row("Semantic Search:", "Enabled" if settings.semantic_search_enabled else "Fallback (Lexical/TF-IDF Cosine)")
    info_table.add_row("Git Integration:", f"{'Enabled' if settings.git_enabled else 'Disabled'} (Commit Approval: {'Required' if settings.git_require_commit_approval else 'No'}, Force Push Block: {'Enabled' if settings.git_block_force_push else 'No'})")
    info_table.add_row("Command Policy:", f"{'Enabled' if settings.command_policy_enabled else 'Disabled'} (Default: {settings.command_default_policy})")
    info_table.add_row("Protected Paths:", f"{'Enabled' if settings.protected_paths_enabled else 'Disabled'} ({len(settings.protected_paths.split(','))} rules)")
    info_table.add_row("Safety Audit Log:", f"{'Enabled' if settings.audit_log_enabled else 'Disabled'} ({settings.audit_storage_path}/audit.db)")
    info_table.add_row("Safety Backups:", f"{'Enabled' if settings.backup_before_write else 'Disabled'} ({settings.backup_storage_path})")
    info_table.add_row("Multi-Agent System:", f"Enabled (5 Core Agents, max parallel: {settings.max_parallel_agents}, timeout: {settings.max_workflow_timeout_seconds:.0f}s)")
    info_table.add_row("Workflow Database:", f"Enabled ({settings.workflow_storage_path}/workflows.db)")

    registry = get_default_registry()
    tool_names = ", ".join(t.name for t in registry.list_tools())
    info_table.add_row(f"Registered Tools ({len(registry.list_tools())}):", f"[yellow]{tool_names}[/yellow]")

    console.print(info_table)
    console.print()

    # Check connection
    with console.status("[bold cyan]Connecting to Ollama server...[/bold cyan]", spinner="dots"):
        is_online, status_msg = client.check_connection()

    if not is_online:
        console.print(f"[bold red][FAIL] Ollama Connection:[/bold red] Offline")
        console.print(
            Panel(
                f"[bold red]Connection Error:[/bold red] {status_msg}\n\n"
                "[yellow]Troubleshooting steps:[/yellow]\n"
                " 1. Ensure Ollama is installed (download from https://ollama.com).\n"
                " 2. Start the Ollama server: open terminal and run [bold green]ollama serve[/bold green] (or launch Ollama app).\n"
                f" 3. Verify that Ollama is listening on [bold cyan]{settings.ollama_host}[/bold cyan].",
                title="[bold red]Ollama Unavailable[/bold red]",
                border_style="red",
            )
        )
        raise typer.Exit(code=1)

    console.print(f"[bold green][OK] Ollama Connection:[/bold green] [green]Online[/green] ({settings.ollama_host})")
    console.print()

    # List installed models
    with console.status("[bold cyan]Retrieving installed models...[/bold cyan]", spinner="dots"):
        try:
            installed_models = client.get_installed_models()
        except OllamaClientError as exc:
            console.print(f"[bold red]Failed to retrieve model list:[/bold red] {exc}")
            raise typer.Exit(code=1)

    if not installed_models:
        console.print("[yellow]No models found installed in Ollama.[/yellow]")
        console.print(f"To download the default model, run: [bold green]ollama pull {selected_model}[/bold green]\n")
        return

    models_table = Table(
        title="Installed Ollama Models",
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
    )
    models_table.add_column("Model Name", style="bold white")
    models_table.add_column("Size", justify="right", style="green")
    models_table.add_column("Parameters", justify="center", style="yellow")
    models_table.add_column("Quantization", justify="center", style="blue")
    models_table.add_column("Family", justify="center", style="magenta")
    models_table.add_column("Status", justify="center")

    found_selected = False
    for m in installed_models:
        is_active = m.name == selected_model or m.name.startswith(f"{selected_model}:")
        if is_active:
            found_selected = True
            status = "[bold green][Selected][/bold green]"
        else:
            status = "[dim]Installed[/dim]"

        models_table.add_row(
            m.name,
            m.size_formatted,
            m.parameter_size,
            m.quantization,
            m.family,
            status,
        )

    console.print(models_table)
    console.print()

    if found_selected:
        console.print(f"[bold green][Ready][/bold green] Target model '[bold cyan]{selected_model}[/bold cyan]' is installed and ready.\n")
    else:
        console.print(
            f"[bold yellow][Notice][/bold yellow] Target model '[bold cyan]{selected_model}[/bold cyan]' is not in the installed list.\n"
            f"Run [bold green]ollama pull {selected_model}[/bold green] to download it before generation.\n"
        )


def display_error_analysis(analysis: ErrorAnalysis) -> None:
    """Render a structured error analysis in a professional Rich panel."""
    sev_color = {
        "low": "blue",
        "medium": "yellow",
        "high": "red",
        "critical": "bold red",
    }.get(analysis.severity.lower(), "yellow")

    table = Table(show_header=False, box=None)
    table.add_column("Key", style="bold white", width=16)
    table.add_column("Value")

    table.add_row("Error Type:", f"[bold cyan]{analysis.error_type}[/bold cyan]")
    table.add_row("Severity:", f"[{sev_color}]{analysis.severity.upper()}[/{sev_color}]")
    table.add_row("Root Cause:", analysis.cause)
    table.add_row("Solution Fix:", analysis.solution)

    console.print()
    console.print(
        Panel(
            table,
            title="[bold cyan]Structured Error Analysis[/bold cyan]",
            border_style="cyan",
            padding=(1, 2),
        )
    )
    console.print()


def handle_history_command(conv_mgr: ConversationManager) -> None:
    """Display the active conversation message history."""
    messages = conv_mgr.active_conversation.messages
    if not messages:
        console.print("[dim]No messages in active conversation yet.[/dim]")
        return

    table = Table(
        title=f"Conversation: {conv_mgr.active_conversation.title} ({conv_mgr.active_conversation.id})",
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
    )
    table.add_column("Role", style="bold yellow", width=12)
    table.add_column("Content preview", style="white")

    for m in messages:
        preview = m.content.strip().replace("\n", " ")
        if len(preview) > 90:
            preview = preview[:90] + "..."
        if m.role == "tool":
            preview = f"[Tool:{m.name}] {preview}"
        table.add_row(m.role.capitalize(), preview)

    console.print(table)


def handle_save_command(conv_mgr: ConversationManager, arg: Optional[str]) -> None:
    """Handle the /save slash command."""
    target_name = arg.strip() if arg else None
    try:
        saved_path = conv_mgr.save(target_name)
        console.print(f"[bold green][Saved][/bold green] Conversation saved to [cyan]{saved_path.name}[/cyan]")
    except Exception as exc:
        console.print(f"[bold red]Failed to save conversation:[/bold red] {exc}")


def handle_load_command(conv_mgr: ConversationManager, arg: Optional[str]) -> None:
    """Handle the /load slash command."""
    if not arg or not arg.strip():
        # List saved conversations
        saved = conv_mgr.list_saved()
        if not saved:
            console.print("[yellow]No saved conversations found.[/yellow]")
            return
        table = Table(title="Saved Conversations", show_header=True, header_style="bold cyan")
        table.add_column("ID / File", style="bold yellow")
        table.add_column("Title", style="white")
        table.add_column("Turns", justify="right")
        for s in saved:
            table.add_row(s["id"], s["title"], str(s["message_count"]))
        console.print(table)
        console.print("[dim]Use [bold]/load <id>[/bold] to load a conversation.[/dim]\n")
        return

    target_id = arg.strip()
    try:
        conv = conv_mgr.load(target_id)
        console.print(f"[bold green][Loaded][/bold green] Active conversation set to '[bold cyan]{conv.title}[/bold cyan]' ({len(conv.messages)} turns).")
    except ConversationNotFoundError:
        console.print(f"[bold red]Not Found:[/bold red] Saved conversation '{target_id}' does not exist.")
    except CorruptedConversationError as exc:
        console.print(f"[bold red]Corrupted File:[/bold red] {exc}")
    except Exception as exc:
        console.print(f"[bold red]Load Error:[/bold red] {exc}")


def handle_model_command(client: LLMClient, active_model: str, arg: Optional[str]) -> str:
    """Handle the /model slash command in interactive mode."""
    if arg:
        new_model = arg.strip()
        console.print(f"[green]Active model switched to:[/green] [bold cyan]{new_model}[/bold cyan]")
        return new_model

    # No argument: display current and available models
    console.print(f"\n[bold]Current Active Model:[/bold] [bold green]{active_model}[/bold green]")
    try:
        models = client.list_models()
        if models:
            console.print("[bold]Available Models in Ollama:[/bold]")
            for m in models:
                indicator = " [bold green]* (active)[/bold green]" if m == active_model else "  -"
                console.print(f"{indicator} {m}")
        else:
            console.print("[yellow]No models found in Ollama.[/yellow]")
    except OllamaClientError as exc:
        console.print(f"[yellow]Could not list models: {exc}[/yellow]")
    console.print("[dim]Use [bold]/model <name>[/bold] to switch active model.[/dim]\n")
    return active_model


def cli_write_approval(proposal: EditProposal) -> bool:
    """Interactive CLI callback displaying unified diff and prompting for approval."""
    console.print()
    diff_text = proposal.diff if proposal.diff.strip() else "[dim]No text modification detected.[/dim]"
    console.print(
        Panel(
            diff_text,
            title=f"[bold yellow]Proposed Modification: {proposal.display_path}[/bold yellow]",
            border_style="yellow",
        )
    )
    ans = console.input("[bold yellow]Approve applying these modifications to disk? [y/N]: [/bold yellow]").strip().lower()
    return ans in ("y", "yes")


def cli_delete_confirmation(target_path: Path) -> bool:
    """Interactive CLI callback prompting explicit confirmation for file deletion."""
    console.print()
    ans = console.input(
        f"[bold red]WARNING: Permanently delete file '{target_path.name}'? [y/N]: [/bold red]"
    ).strip().lower()
    return ans in ("y", "yes")


def cli_execution_approval(plan: ExecutionPlan) -> bool:
    """Interactive CLI callback displaying execution details and prompting for human authorization."""
    console.print()
    table = Table(show_header=False, box=None)
    table.add_column("Key", style="bold white", width=20)
    table.add_column("Value")

    table.add_row("Operation Type:", f"[bold cyan]{plan.operation.upper()}[/bold cyan]")
    table.add_row("Command to Run:", f"[bold yellow]{plan.command}[/bold yellow]")
    table.add_row("Working Directory:", plan.working_directory)
    if plan.reason:
        table.add_row("Purpose:", plan.reason)
    for k, v in plan.details.items():
        table.add_row(f"{k}:", str(v))

    console.print(
        Panel(
            table,
            title="[bold yellow]Execution Authorization Required[/bold yellow]",
            border_style="yellow",
            padding=(1, 2),
        )
    )
    ans = console.input("[bold yellow]Authorize running this command? [y/N]: [/bold yellow]").strip().lower()
    return ans in ("y", "yes")


def handle_python_command(exec_mgr: ExecutionManager, arg: Optional[str]) -> None:
    """Handle /python command to execute a Python script."""
    if not arg or not arg.strip():
        console.print("[yellow]Usage: /python <script_path> [args...][/yellow]")
        return

    import shlex
    tokens = shlex.split(arg.strip(), posix=False)
    script = tokens[0]
    script_args = tokens[1:] if len(tokens) > 1 else None

    try:
        with console.status(f"[bold cyan]Running Python: {script}...[/bold cyan]", spinner="dots"):
            res = exec_mgr.run_python(script_path=script, args=script_args)

        status_style = "bold green" if res.success else "bold red"
        console.print()
        console.print(f"[{status_style}]Exit code: {res.exit_code}[/{status_style}] ({res.duration_seconds:.2f}s)")
        if res.stdout.strip():
            console.print(Panel(res.stdout.strip(), title="[green]Standard Output[/green]", border_style="dim"))
        if res.stderr.strip():
            console.print(Panel(res.stderr.strip(), title="[red]Standard Error[/red]", border_style="red"))
    except ExecutionNotApprovedError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
    except Exception as exc:
        console.print(f"[bold red]Python execution failed:[/bold red] {exc}")


def handle_run_command(exec_mgr: ExecutionManager, arg: Optional[str]) -> None:
    """Handle /run command to execute a terminal command."""
    if not arg or not arg.strip():
        console.print("[yellow]Usage: /run <command>[/yellow]")
        return

    try:
        with console.status(f"[bold cyan]Running command: {arg}...[/bold cyan]", spinner="dots"):
            res = exec_mgr.execute_command(command_or_args=arg.strip())

        status_style = "bold green" if res.success else "bold red"
        console.print()
        console.print(f"[{status_style}]Exit code: {res.exit_code}[/{status_style}] ({res.duration_seconds:.2f}s)")
        if res.stdout.strip():
            console.print(Panel(res.stdout.strip(), title="[green]Output[/green]", border_style="dim"))
        if res.stderr.strip():
            console.print(Panel(res.stderr.strip(), title="[red]Error Output[/red]", border_style="red"))
    except ExecutionNotApprovedError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
    except Exception as exc:
        console.print(f"[bold red]Command failed:[/bold red] {exc}")


def handle_install_command(exec_mgr: ExecutionManager, arg: Optional[str]) -> None:
    """Handle /install command to install dependencies via pip."""
    if not arg or not arg.strip():
        console.print("[yellow]Usage: /install <package_name or requirements.txt>[/yellow]")
        return

    target = arg.strip()
    try:
        with console.status(f"[bold cyan]Installing {target}...[/bold cyan]", spinner="dots"):
            if target.endswith(".txt"):
                res = exec_mgr.install_requirements(target)
            else:
                res = exec_mgr.install_dependency(target)

        console.print(f"[bold green][Installed][/bold green] {res.to_summary()}")
        if res.stdout.strip():
            console.print(f"[dim]{res.stdout.strip()[-300:]}[/dim]")
    except ExecutionNotApprovedError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
    except Exception as exc:
        console.print(f"[bold red]Installation failed:[/bold red] {exc}")


def handle_test_command(exec_mgr: ExecutionManager, arg: Optional[str]) -> None:
    """Handle /test command to execute project tests."""
    target = arg.strip() if arg and arg.strip() else None
    try:
        with console.status("[bold cyan]Running automated tests...[/bold cyan]", spinner="dots"):
            report = exec_mgr.run_tests(test_path=target)

        status_color = "bold green" if report.status == "PASSED" else "bold red"
        table = Table(title="Test Execution Report", show_header=False, box=None)
        table.add_column("Key", style="bold white", width=18)
        table.add_column("Value")

        table.add_row("Framework:", f"[bold cyan]{report.framework}[/bold cyan]")
        table.add_row("Status:", f"[{status_color}]{report.status}[/{status_color}]")
        table.add_row("Passed:", f"[green]{report.passed}[/green]")
        table.add_row("Failed:", f"[red]{report.failed}[/red]")
        table.add_row("Skipped:", f"[yellow]{report.skipped}[/yellow]")
        table.add_row("Total:", str(report.total))
        table.add_row("Duration:", f"{report.duration_seconds:.2f}s")

        console.print()
        console.print(Panel(table, title="[bold cyan]Test Results[/bold cyan]", border_style="cyan"))

        if report.failed > 0 or report.status != "PASSED":
            err_preview = report.stdout or report.stderr
            if err_preview.strip():
                console.print(Panel(err_preview.strip()[-1000:], title="[red]Failure Details[/red]", border_style="red"))
    except Exception as exc:
        console.print(f"[bold red]Test execution failed:[/bold red] {exc}")


def handle_processes_command(exec_mgr: ExecutionManager) -> None:
    """Handle /processes command to list active background processes."""
    procs = exec_mgr.list_processes()
    if not procs:
        console.print("[dim]No active background processes running.[/dim]")
        return

    table = Table(title="Active Processes", show_header=True, header_style="bold cyan")
    table.add_column("PID", style="bold yellow", width=10)
    table.add_column("Command", style="white")
    table.add_column("Status", style="green")

    for p in procs:
        table.add_row(str(p.process_id), p.command, p.status)

    console.print(table)


def handle_cancel_command(exec_mgr: ExecutionManager, arg: Optional[str]) -> None:
    """Handle /cancel command to terminate a running process."""
    if not arg or not arg.strip() or not arg.strip().isdigit():
        console.print("[yellow]Usage: /cancel <process_id_number>[/yellow]")
        return

    pid = int(arg.strip())
    cancelled = exec_mgr.cancel_execution(pid)
    if cancelled:
        console.print(f"[bold green][Cancelled][/bold green] Process PID {pid} was terminated.")
    else:
        console.print(f"[yellow]Process PID {pid} not found among active processes.[/yellow]")


def cli_patch_approval(patch: FilePatch) -> bool:
    """CLI dialog displaying proposed code patch unified diff and requesting approval."""
    from rich.syntax import Syntax

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Key", style="bold yellow", width=18)
    table.add_column("Value")

    table.add_row("Target File:", f"[bold cyan]{patch.file_path}[/bold cyan]")
    table.add_row("Explanation:", patch.explanation)

    console.print()
    console.print(
        Panel(
            table,
            title="[bold yellow]Code Patch Approval Required[/bold yellow]",
            border_style="yellow",
            padding=(1, 2),
        )
    )

    if patch.diff:
        syntax = Syntax(patch.diff, "diff", theme="monokai", line_numbers=False)
        console.print(Panel(syntax, title=f"Unified Diff: {patch.file_path}", border_style="cyan"))

    ans = console.input(f"[bold yellow]Apply this patch to '{patch.file_path}'? [y/N]: [/bold yellow]").strip().lower()
    return ans in ("y", "yes")


_last_debug_report: Optional[DebugReport] = None


def handle_debug_command(debugger: AutonomousDebugger, arg: Optional[str]) -> None:
    """Handle /debug command for autonomous diagnosis, patching, and verification."""
    global _last_debug_report
    target = arg.strip() if arg else None

    # Validate target existence if explicitly specified
    if target:
        target_path = debugger.workspace_root / target
        if not target_path.exists():
            console.print(
                f"[yellow]Target not found:[/yellow] [bold red]{target}[/bold red]\n"
                f"Please specify an existing file, or run [bold green]/debug[/bold green] without arguments to test all workspace tests."
            )
            return

    test_target = target if target and ("test" in target.lower() or target.endswith(".py")) else None
    script_target = target if target and not test_target else None

    console.print()
    console.print(
        Panel(
            f"[bold cyan]Debugging Target:[/bold cyan] {target or 'All discovered tests in workspace'}",
            title="[bold cyan]Autonomous Debugging Session[/bold cyan]",
            border_style="cyan",
        )
    )

    try:
        with console.status("[bold cyan]Analyzing error, generating patch, and running verification...[/bold cyan]", spinner="dots"):
            report = debugger.debug_target(
                test_path=test_target,
                script_path=script_target,
                approval_callback=cli_patch_approval,
            )

        _last_debug_report = report
        console.print()
        report.render_rich(console)
    except Exception as exc:
        console.print(f"[bold red]Debugging workflow failed:[/bold red] {exc}")


def handle_diagnose_command(debugger: AutonomousDebugger, arg: Optional[str]) -> None:
    """Handle /diagnose command to analyze an error or traceback."""
    if not arg or not arg.strip():
        console.print("[yellow]Usage: /diagnose <error_traceback_or_message>[/yellow]")
        return

    err = debugger.error_detector.detect_from_text(arg.strip())
    if not err:
        console.print("[yellow]No Python exception or error pattern detected in input.[/yellow]")
        return

    code_ctx = None
    if err.file_path:
        try:
            code_ctx = debugger.code_inspector.inspect_file(err.file_path, target_line=err.line_number)
        except Exception:
            pass

    with console.status("[bold cyan]Diagnosing root cause...[/bold cyan]", spinner="dots"):
        diag = debugger.root_cause_analyzer.analyze(err, code_context=code_ctx)

    console.print()
    console.print(Panel(diag.to_summary(), title="[bold cyan]Root Cause Diagnosis[/bold cyan]", border_style="cyan"))


def handle_fix_command(debugger: AutonomousDebugger, arg: Optional[str]) -> None:
    """Handle /fix command to propose a repair for a target file."""
    if not arg or not arg.strip():
        console.print("[yellow]Usage: /fix <file_path>[/yellow]")
        return

    target_file = arg.strip()
    try:
        code_ctx = debugger.code_inspector.inspect_file(target_file)
        # Formulate a generic diagnosis to prompt fix generator
        from codeagent.debugging.root_cause_analyzer import RootCauseDiagnosis
        diag = RootCauseDiagnosis(
            error_summary=f"Fix issues in {target_file}",
            exception_type="GeneralFix",
            root_cause="User requested code repair",
            affected_file=target_file,
            suggested_solution="Inspect and review diff",
        )
        prop_fix = debugger.fix_generator.generate_fix(diag, context=code_ctx, target_file_path=target_file)
        if not prop_fix.is_valid or not prop_fix.patches:
            console.print(f"[yellow]Unable to synthesize automated patch:[/yellow] {prop_fix.validation_error or 'No changes'}")
            return

        records = debugger.patch_manager.apply_fix(prop_fix, approval_callback=cli_patch_approval)
        console.print(f"[bold green]Successfully patched {len(records)} file(s).[/bold green]")
    except PatchRejectedError:
        console.print("[yellow]Patch rejected by user. No files were modified.[/yellow]")
    except Exception as exc:
        console.print(f"[bold red]Fix failed:[/bold red] {exc}")


def handle_retest_command(debugger: AutonomousDebugger, arg: Optional[str]) -> None:
    """Handle /retest command to run verification and check regressions."""
    target = arg.strip() if arg else None
    test_target = target if target and ("test" in target.lower() or target.endswith(".py")) else None
    script_target = target if target and not test_target else None

    with console.status("[bold cyan]Executing retest and checking regressions...[/bold cyan]", spinner="dots"):
        res = debugger.retest_manager.retest(test_path=test_target, script_path=script_target)
        reg = debugger.regression_checker.evaluate(res)

    console.print()
    console.print(Panel(res.to_summary(), title="[bold cyan]Retest Execution[/bold cyan]", border_style="cyan"))
    console.print(Panel(reg.to_summary(), title="[bold cyan]Regression Analysis[/bold cyan]", border_style="green" if reg.status.value == "fixed_and_verified" else "yellow"))


def handle_debug_rollback_command(debugger: AutonomousDebugger, arg: Optional[str]) -> None:
    """Handle /rollback command to revert debug patches."""
    global _last_debug_report
    if arg and arg.strip():
        backup_id = arg.strip()
        try:
            debugger.backup_manager.restore_backup(backup_id)
            console.print(f"[bold green][Restored][/bold green] Successfully rolled back backup ID: {backup_id}")
        except Exception as exc:
            console.print(f"[bold red]Rollback failed:[/bold red] {exc}")
    elif _last_debug_report and _last_debug_report.backups_created:
        count = debugger.rollback_session(_last_debug_report)
        console.print(f"[bold green][Restored][/bold green] Rolled back {count} backup(s) from last debugging session.")
    else:
        console.print("[yellow]No recent debugging session backups found. Provide specific backup ID: /rollback <id>[/yellow]")


def handle_debug_report_command() -> None:
    """Handle /debug-report command to show last report."""
    global _last_debug_report
    if not _last_debug_report:
        console.print("[yellow]No debugging report available from active session.[/yellow]")
        return
    _last_debug_report.render_rich(console)


def handle_workspace_command(fs_mgr: FilesystemManager, arg: Optional[str]) -> None:
    """Handle /workspace command to view or switch workspace root."""
    if arg and arg.strip():
        new_dir = arg.strip()
        try:
            resolved = fs_mgr.set_workspace_root(new_dir)
            console.print(f"[bold green]Workspace root updated to:[/bold green] [bold cyan]{resolved}[/bold cyan]")
        except Exception as exc:
            console.print(f"[bold red]Failed to change workspace root:[/bold red] {exc}")
    else:
        console.print(f"[bold]Active Workspace Root:[/bold] [bold cyan]{fs_mgr.workspace_root}[/bold cyan]")
        console.print("[dim]Use [bold]/workspace <path>[/bold] to change workspace boundary.[/dim]")


def handle_scan_command(fs_mgr: FilesystemManager, arg: Optional[str]) -> None:
    """Handle /scan or /tree command to scan and display directory structure."""
    target = arg.strip() if arg and arg.strip() else None
    try:
        with console.status("[bold cyan]Scanning workspace hierarchy...[/bold cyan]", spinner="dots"):
            res = fs_mgr.scan_project(path=target)

        console.print()
        console.print(
            Panel(
                res.tree_view,
                title=f"[bold cyan]Workspace Tree: {res.root_path}[/bold cyan]",
                border_style="cyan",
            )
        )
        console.print(f"[dim]{res.to_summary()}[/dim]")
    except Exception as exc:
        console.print(f"[bold red]Scan failed:[/bold red] {exc}")


def handle_project_command(
    project_mgr: ProjectManager,
    fs_mgr: FilesystemManager,
    exec_mgr: ExecutionManager,
    arg: Optional[str] = None,
) -> None:
    """Handle /project command for multi-project management and deep project analysis."""
    parts = arg.strip().split(maxsplit=1) if arg and arg.strip() else []
    subcmd = parts[0].lower() if parts else "list"
    subarg = parts[1].strip() if len(parts) > 1 else ""

    if subcmd in ("list", "ls") or not arg or not arg.strip():
        projects = project_mgr.list_projects()
        if not projects:
            console.print("[yellow]No projects registered yet.[/yellow]")
            return

        table = Table(title="Registered Projects", show_header=True, header_style="bold cyan")
        table.add_column("Status", justify="center", width=10)
        table.add_column("Project ID", style="bold yellow", width=18)
        table.add_column("Name", style="white")
        table.add_column("Path", style="dim")
        table.add_column("Last Updated", style="dim")

        for p in projects:
            status = "[bold green]✓ ACTIVE[/bold green]" if p.is_active else "[dim]inactive[/dim]"
            updated = (p.updated_at or "")[:19].replace("T", " ")
            table.add_row(status, p.id, p.name, p.path, updated)

        console.print(table)
        console.print("[dim]Use [bold]/project switch <name_or_id>[/bold] or [bold]/project add <path>[/bold][/dim]")

    elif subcmd == "add":
        if not subarg:
            console.print("[yellow]Usage: /project add <path>[/yellow]")
            return
        try:
            rec = project_mgr.register_project(subarg, set_active=True)
            fs_mgr.set_workspace_root(rec.path)
            exec_mgr.workspace_root = Path(rec.path)
            console.print(f"[bold green]Registered and activated project:[/bold green] [bold cyan]{rec.name}[/bold cyan] ({rec.id})")
            console.print(f"Workspace path: [dim]{rec.path}[/dim]")
        except Exception as exc:
            console.print(f"[bold red]Failed to register project:[/bold red] {exc}")

    elif subcmd == "switch":
        if not subarg:
            console.print("[yellow]Usage: /project switch <name_or_id>[/yellow]")
            return
        try:
            rec = project_mgr.switch_project(subarg)
            fs_mgr.set_workspace_root(rec.path)
            exec_mgr.workspace_root = Path(rec.path)
            console.print(f"[bold green]Switched active project to:[/bold green] [bold cyan]{rec.name}[/bold cyan] ({rec.id})")
            console.print(f"Workspace path: [dim]{rec.path}[/dim]")
        except Exception as exc:
            console.print(f"[bold red]Switch failed:[/bold red] {exc}")

    elif subcmd == "info":
        try:
            info = project_mgr.get_project_info()
            rec = info["project"]
            idx = info["index_status"]
            facts_count = info["facts_count"]

            table = Table(title=f"Active Project: {rec.name}", show_header=False, box=None)
            table.add_column("Key", style="bold white", width=24)
            table.add_column("Value")

            table.add_row("Project ID:", f"[bold yellow]{rec.id}[/bold yellow]")
            table.add_row("Project Name:", rec.name)
            table.add_row("Workspace Root:", rec.path)
            table.add_row("Indexed Files:", str(idx.files_indexed))
            table.add_row("Total Code Chunks:", str(idx.total_chunks))
            table.add_row("Total Code Symbols:", str(idx.total_symbols))
            table.add_row("Stored Memory Facts:", f"{facts_count} facts recorded")
            table.add_row("Last Indexed:", idx.last_indexed_at or "Never")

            console.print()
            console.print(Panel(table, title="[bold cyan]Project Overview[/bold cyan]", border_style="cyan"))
        except Exception as exc:
            console.print(f"[bold red]Failed to retrieve project info:[/bold red] {exc}")

    elif subcmd in ("analyze", "analysis"):
        try:
            target_path = Path(subarg) if subarg else project_mgr.active_workspace_path
            with console.status("[bold cyan]Analyzing comprehensive project intelligence...[/bold cyan]", spinner="dots"):
                analysis = project_mgr.project_analyzer.analyze(target_path)

            table = Table(title="Project Intelligence Analysis", show_header=False, box=None)
            table.add_column("Key", style="bold white", width=26)
            table.add_column("Value")

            table.add_row("Project Name:", f"[bold cyan]{analysis.project_name}[/bold cyan]")
            table.add_row("Detected Project Type:", f"[bold green]{analysis.project_type}[/bold green]")
            table.add_row("Primary Language:", f"[bold]{analysis.primary_language}[/bold]")
            lang_dist = ", ".join(f"{lang} ({pct}%)" for lang, pct in list(analysis.language_distribution.items())[:5])
            table.add_row("Language Breakdown:", lang_dist or "N/A")
            table.add_row("Frameworks / Stacks:", ", ".join(analysis.frameworks) or "[dim]None detected[/dim]")
            table.add_row("Entry Points:", ", ".join(analysis.entry_points) or "[dim]None detected[/dim]")
            table.add_row("Build Systems:", ", ".join(analysis.build_systems) or "[dim]None detected[/dim]")
            table.add_row("Deployment Configs:", ", ".join(analysis.deployment_configs) or "[dim]None detected[/dim]")
            table.add_row("Dependency Manifests:", ", ".join(analysis.dependency_files) or "[dim]None[/dim]")
            table.add_row("Important Directories:", ", ".join(analysis.important_directories) or "[dim]None[/dim]")
            table.add_row("Test Directories:", ", ".join(analysis.test_directories) or "[dim]None[/dim]")

            console.print()
            console.print(
                Panel(
                    table,
                    title="[bold cyan]Comprehensive Project Intelligence[/bold cyan]",
                    border_style="cyan",
                    padding=(1, 2),
                )
            )
        except Exception as exc:
            console.print(f"[bold red]Project analysis failed:[/bold red] {exc}")
    else:
        # Check if arg is a path to analyze
        if Path(arg).exists():
            handle_project_command(project_mgr, fs_mgr, exec_mgr, f"analyze {arg}")
        else:
            console.print(f"[yellow]Unknown project command: '{arg}'.[/yellow]")
            console.print("[dim]Available: /project [list | add <path> | switch <id> | info | analyze][/dim]")


def handle_index_command(project_mgr: ProjectManager, arg: Optional[str]) -> None:
    """Handle /index command for workspace code indexing."""
    action = arg.strip().lower() if arg and arg.strip() else ""

    if action in ("status", "info"):
        try:
            indexer = ProjectIndexer(store=project_mgr.store, workspace_root=project_mgr.active_workspace_path)
            status = indexer.get_status(project_mgr.active_project_id)
            table = Table(title="Code Index Status", show_header=False, box=None)
            table.add_column("Metric", style="bold white", width=22)
            table.add_column("Value", style="cyan")

            table.add_row("Project ID:", project_mgr.active_project_id)
            table.add_row("Workspace Root:", str(project_mgr.active_workspace_path))
            table.add_row("Indexed Files:", str(status.files_indexed))
            table.add_row("Total Code Chunks:", str(status.total_chunks))
            table.add_row("Total Code Symbols:", str(status.total_symbols))
            table.add_row("Last Indexed At:", status.last_indexed_at or "Never")

            console.print(Panel(table, title="[bold cyan]Code Indexing Status[/bold cyan]", border_style="cyan"))
        except Exception as exc:
            console.print(f"[bold red]Failed to get index status:[/bold red] {exc}")
        return

    rebuild = action in ("refresh", "rebuild", "--rebuild")
    mode_text = "Rebuilding entire" if rebuild else "Incrementally indexing"

    try:
        with console.status(f"[bold cyan]{mode_text} project index...[/bold cyan]", spinner="dots"):
            status = project_mgr.index_active_project(rebuild=rebuild)

        console.print(
            Panel(
                f"[bold green]Indexing Complete![/bold green]\n\n"
                f" * [bold]Files Indexed:[/bold]  {status.files_indexed}\n"
                f" * [bold]Code Chunks:[/bold]    {status.total_chunks}\n"
                f" * [bold]Code Symbols:[/bold]   {status.total_symbols}\n"
                f" * [bold]Duration:[/bold]       {status.duration_seconds:.2f}s",
                title="[bold cyan]Project Code Index[/bold cyan]",
                border_style="green",
            )
        )
    except Exception as exc:
        console.print(f"[bold red]Indexing failed:[/bold red] {exc}")


def handle_search_command(project_mgr: ProjectManager, arg: Optional[str]) -> None:
    """Handle /search command for multi-strategy codebase search."""
    if not arg or not arg.strip():
        console.print("[yellow]Usage:[/yellow]")
        console.print("  [bold]/search <query>[/bold]            - Search code chunks & exact text")
        console.print("  [bold]/search symbol <name>[/bold]     - Search functions, classes, and methods")
        console.print("  [bold]/search file <pattern>[/bold]     - Search filenames matching glob/pattern")
        console.print("  [bold]/search semantic <query>[/bold]   - Local lexical/semantic relevance search")
        return

    raw = arg.strip()
    if raw.startswith("symbol "):
        search_type = "symbol"
        query = raw[7:].strip()
    elif raw.startswith("file "):
        search_type = "file"
        query = raw[5:].strip()
    elif raw.startswith("semantic "):
        search_type = "semantic"
        query = raw[9:].strip()
    else:
        search_type = "text"
        query = raw

    try:
        with console.status(f"[bold cyan]Searching {search_type} for '{query}'...[/bold cyan]", spinner="dots"):
            results = project_mgr.search_active_project(query=query, search_type=search_type, limit=10)

        if not results:
            console.print(f"[yellow]No matches found for '{query}'.[/yellow]")
            return

        table = Table(title=f"Search Results: {search_type.capitalize()} ('{query}')", show_header=True, header_style="bold cyan")

        if search_type == "symbol":
            table.add_column("Symbol", style="bold yellow")
            table.add_column("Type", style="cyan")
            table.add_column("File", style="white")
            table.add_column("Lines", justify="center")
            table.add_column("Signature", style="dim")
            for r in results:
                table.add_row(
                    getattr(r, "symbol_name", getattr(r, "matched_content", "")),
                    getattr(r, "symbol_type", getattr(r, "match_type", "")),
                    getattr(r, "file_path", ""),
                    f"L{getattr(r, 'line_start', getattr(r, 'line_number', 0))}-{getattr(r, 'line_end', getattr(r, 'line_number', 0))}",
                    (getattr(r, "signature", "") or "")[:35],
                )
        elif search_type == "file":
            table.add_column("File Path", style="bold yellow")
            table.add_column("Language", style="cyan")
            table.add_column("Lines", justify="right")
            table.add_column("Size", justify="right")
            for r in results:
                meta = getattr(r, "metadata", {}) or {}
                table.add_row(
                    r.file_path,
                    str(meta.get("language", "unknown")),
                    str(meta.get("line_count", "-")),
                    f"{meta.get('file_size_bytes', 0)} B",
                )
        else:
            table.add_column("File", style="bold yellow", width=25)
            table.add_column("Line", justify="center", width=8)
            table.add_column("Matched Snippet", style="white")
            for r in results:
                snippet = (getattr(r, "matched_content", "") or getattr(r, "snippet", "") or "").strip().replace("\n", " ")[:70]
                line_no = getattr(r, "line_number", getattr(r, "line_start", "-"))
                table.add_row(r.file_path, str(line_no), snippet)

        console.print(table)
    except Exception as exc:
        console.print(f"[bold red]Search failed:[/bold red] {exc}")


def handle_memory_command(project_mgr: ProjectManager, arg: Optional[str]) -> None:
    """Handle /memory command for persistent project knowledge."""
    p_id = project_mgr.active_project_id
    raw = arg.strip() if arg and arg.strip() else "show"
    parts = raw.split(maxsplit=1)
    subcmd = parts[0].lower()
    subarg = parts[1].strip() if len(parts) > 1 else ""

    if subcmd in ("show", "list"):
        facts = project_mgr.memory_manager.list_facts(project_id=p_id, limit=25)
        if not facts:
            console.print("[yellow]No persistent facts stored for this project.[/yellow]")
            return

        table = Table(title="Persistent Project Memory", show_header=True, header_style="bold cyan")
        table.add_column("ID", justify="right", style="dim", width=4)
        table.add_column("Category", style="bold yellow", width=14)
        table.add_column("Key", style="bold white", width=20)
        table.add_column("Value / Knowledge", style="white")
        table.add_column("Confidence", justify="center", width=10)

        for f in facts:
            val_preview = (f.value or "").strip().replace("\n", " ")[:60]
            table.add_row(str(f.id), f.category, f.key, val_preview, f"{f.confidence:.2f}")

        console.print(table)
        console.print("[dim]Use [bold]/memory search <query>[/bold] or [bold]/memory delete <id>[/bold][/dim]")

    elif subcmd == "search":
        if not subarg:
            console.print("[yellow]Usage: /memory search <query>[/yellow]")
            return
        results = project_mgr.memory_manager.retrieve_memories(project_id=p_id, query=subarg, limit=10)
        if not results:
            console.print(f"[yellow]No memories matching '{subarg}'.[/yellow]")
            return

        table = Table(title=f"Memory Matches: '{subarg}'", show_header=True, header_style="bold cyan")
        table.add_column("Category", style="bold yellow")
        table.add_column("Key", style="bold white")
        table.add_column("Value Snippet", style="white")
        table.add_column("Score", justify="right", style="cyan")

        for r in results:
            val_preview = (r.value or "").strip().replace("\n", " ")[:60]
            table.add_row(r.category, r.key, val_preview, f"{r.relevance_score:.2f}")

        console.print(table)

    elif subcmd == "delete":
        if not subarg or not subarg.isdigit():
            console.print("[yellow]Usage: /memory delete <id>[/yellow]")
            return
        fid = int(subarg)
        success = project_mgr.memory_manager.delete_fact(fact_id=fid)
        if success:
            console.print(f"[bold green]Deleted memory ID {fid}.[/bold green]")
        else:
            console.print(f"[yellow]Memory ID {fid} not found.[/yellow]")

    elif subcmd in ("store", "add"):
        store_parts = subarg.split(maxsplit=2)
        if len(store_parts) < 3:
            console.print("[yellow]Usage: /memory store <category> <key> <value>[/yellow]")
            console.print("[dim]Categories: architecture, convention, decision, limitation, dependency, stack, general[/dim]")
            return
        cat, key, val = store_parts[0], store_parts[1], store_parts[2]
        try:
            fact = project_mgr.memory_manager.store_fact(
                project_id=p_id,
                category=cat,
                key=key,
                value=val,
                source="user",
            )
            console.print(f"[bold green]Stored memory [yellow]{fact.key}[/yellow] (ID {fact.id}).[/bold green]")
        except Exception as exc:
            console.print(f"[bold red]Failed to store memory:[/bold red] {exc}")
    else:
        console.print("[yellow]Available: /memory [show | search <query> | delete <id> | store <cat> <key> <val>][/yellow]")


def handle_context_command(
    context_mgr: ContextManager,
    conv_mgr: ConversationManager,
    project_mgr: ProjectManager,
    arg: Optional[str] = None,
) -> None:
    """Handle /context command to display token budget utilization and active project context."""
    history = conv_mgr.get_messages_for_llm()
    status = context_mgr.get_budget_status(history)

    # Estimate project context bundle size
    bundle = project_mgr.build_active_context()
    bundle_prompt = bundle.to_prompt_context(max_tokens=2500)
    project_tokens = estimate_tokens(bundle_prompt)

    table = Table(title="Token Budget & Context Window Utilization", show_header=False, box=None)
    table.add_column("Metric", style="bold white", width=26)
    table.add_column("Value", style="cyan")

    table.add_row("Total Context Window:", f"{status['context_window']} tokens")
    table.add_row("Max Output Reserve:", f"{status['max_output_tokens']} tokens")
    table.add_row("Safety Reserve Margin:", f"{context_mgr.context_reserve_tokens} tokens")
    table.add_row("Available Input Budget:", f"{status['input_budget']} tokens")
    table.add_row("Conversation Messages:", f"{status['message_count']} messages ({status['used_tokens']} tokens)")
    table.add_row("Project Context Tokens:", f"~{project_tokens} tokens ({project_mgr.active_project_id})")

    total_used = status['used_tokens'] + project_tokens
    remaining = max(0, status['input_budget'] - total_used)
    pct = round((total_used / status['input_budget']) * 100, 1)

    table.add_row("Net Input Utilization:", f"[bold {'red' if pct > 85 else 'green'}]{pct}%[/bold] ({total_used} / {status['input_budget']} tokens)")
    table.add_row("Remaining Free Tokens:", f"[bold green]{remaining}[/bold green] tokens")

    console.print()
    console.print(Panel(table, title="[bold cyan]Context Window Status[/bold cyan]", border_style="cyan"))

    if arg and arg.strip().lower() in ("show", "preview", "dump"):
        if bundle_prompt.strip():
            console.print(Panel(bundle_prompt, title="[bold cyan]Active Project Context Bundle[/bold cyan]", border_style="dim"))
        else:
            console.print("[dim]Active project context is empty.[/dim]")


def handle_git_cli(args: list[str], git_mgr: GitManager) -> None:
    """Handle CLI command 'codeagent git <subcommand>'."""
    if not args:
        console.print("[yellow]Usage: codeagent git [status | diff | branches | branch-create <name> | switch <name> | commit][/yellow]")
        return
    subcmd = args[0].lower()
    subarg = " ".join(args[1:]) if len(args) > 1 else ""
    handle_git_command(git_mgr, f"{subcmd} {subarg}".strip())


def handle_git_command(git_mgr: GitManager, arg: Optional[str]) -> None:
    """Handle /git and CLI git operations."""
    parts = arg.strip().split(maxsplit=1) if arg and arg.strip() else []
    subcmd = parts[0].lower() if parts else "status"
    subarg = parts[1].strip() if len(parts) > 1 else ""

    try:
        if subcmd == "status":
            status = git_mgr.get_status()
            console.print(status.to_rich_table())
        elif subcmd == "diff":
            staged = "--staged" in subarg or "-s" in subarg
            clean_arg = subarg.replace("--staged", "").replace("-s", "").strip() or None
            res = git_mgr.get_diff(staged=staged, file_path=clean_arg)
            console.print(Panel(res.to_summary(), title="Git Diff Summary", border_style="cyan"))
            if res.raw_diff:
                console.print(Panel(res.raw_diff, title="Unified Diff Output", border_style="dim"))
            else:
                console.print("[dim]No diff output for selected scope.[/dim]")
        elif subcmd in ("branches", "branch"):
            res = git_mgr.list_branches()
            table = Table(title="Local Git Branches", show_header=True, header_style="bold magenta")
            table.add_column("Current", width=8, justify="center")
            table.add_column("Branch Name", style="bold cyan")
            table.add_column("HEAD Commit", style="yellow", width=12)
            table.add_column("Subject", style="white")
            for b in res.branches:
                curr_mark = "[bold green]*[/bold green]" if b.is_current else " "
                table.add_row(curr_mark, b.name, (b.commit_hash or "")[:8], b.commit_subject or "-")
            console.print(table)
        elif subcmd in ("branch-create", "create"):
            if not subarg:
                console.print("[yellow]Usage: /git branch-create <branch-name>[/yellow]")
                return
            b_name = subarg.split()[0]
            confirm = typer.confirm(f"Create new Git branch '{b_name}'?", default=True)
            if not confirm:
                console.print("[yellow]Branch creation cancelled by user.[/yellow]")
                return
            res = git_mgr.create_branch(b_name)
            console.print(f"[bold green]{res.message}[/bold green]")
        elif subcmd in ("switch", "checkout"):
            if not subarg:
                console.print("[yellow]Usage: /git switch <branch-name>[/yellow]")
                return
            b_name = subarg.split()[0]
            confirm = typer.confirm(f"Switch to Git branch '{b_name}'?", default=True)
            if not confirm:
                console.print("[yellow]Branch switch cancelled by user.[/yellow]")
                return
            res = git_mgr.switch_branch(b_name)
            console.print(f"[bold green]{res.message}[/bold green]")
        elif subcmd == "commit":
            status = git_mgr.get_status()
            if status.is_clean:
                console.print("[green]Working tree is clean. Nothing to commit.[/green]")
                return

            console.print(status.to_rich_table())
            console.print("[bold yellow]Enter comma-separated file paths to stage (or leave blank if files already staged):[/bold yellow]")
            files_input = input().strip()
            files_to_stage = [f.strip() for f in files_input.split(",") if f.strip()] if files_input else None

            if files_to_stage:
                git_mgr.stage_files(files_to_stage)
                console.print(f"[green]Staged {len(files_to_stage)} file(s).[/green]")

            staged_diff = git_mgr.get_diff(staged=True)
            if not staged_diff.file_diffs and staged_diff.total_files_changed == 0:
                console.print("[yellow]No staged changes to commit. Aborting.[/yellow]")
                return

            console.print(Panel(staged_diff.to_summary(), title="Staged Changes Preview", border_style="green"))

            suggested = git_mgr.commit_mgr.generate_commit_message_suggestion(staged_diff)
            console.print(f"[dim]Suggested commit message: [italic]{suggested}[/italic][/dim]")
            console.print("[bold yellow]Enter commit message (press Enter to accept suggested):[/bold yellow]")
            user_msg = input().strip()
            final_msg = user_msg or suggested

            confirm = typer.confirm(f"Proceed with commit '{final_msg}'?", default=True)
            if not confirm:
                console.print("[yellow]Commit cancelled by user.[/yellow]")
                return

            commit_res = git_mgr.commit_changes(commit_message=final_msg)
            console.print(Panel(commit_res.to_summary(), title="[bold green]Commit Verified[/bold green]", border_style="green"))
        else:
            console.print(f"[yellow]Unknown git command: '{subcmd}'.[/yellow]")
            console.print("[dim]Available: status, diff [--staged], branches, branch-create <name>, switch <name>, commit[/dim]")
    except Exception as exc:
        console.print(f"[bold red]Git Error:[/bold red] {exc}")


def handle_safety_cli(args: list[str], perm_mgr: SafetyPermissionManager, paths_mgr: ProtectedPathsManager, audit_logger: SecurityAuditLogger) -> None:
    """Handle CLI command 'codeagent safety <subcommand>'."""
    if not args:
        console.print("[yellow]Usage: codeagent safety [permissions | protected | audit [--operation-id ID]][/yellow]")
        return
    subcmd = args[0].lower()
    subarg = " ".join(args[1:]) if len(args) > 1 else ""
    handle_safety_command(perm_mgr, paths_mgr, audit_logger, f"{subcmd} {subarg}".strip())


def handle_safety_command(perm_mgr: SafetyPermissionManager, paths_mgr: ProtectedPathsManager, audit_logger: SecurityAuditLogger, arg: Optional[str]) -> None:
    """Handle /safety and CLI safety operations."""
    parts = arg.strip().split(maxsplit=1) if arg and arg.strip() else []
    subcmd = parts[0].lower() if parts else "permissions"
    subarg = parts[1].strip() if len(parts) > 1 else ""

    # Normalize aliases
    if subcmd in ("check", "eval", "evaluate"):
        subcmd = "permissions"
    elif subcmd in ("paths", "rules", "list-paths"):
        subcmd = "protected"
    elif subcmd == "add":
        subcmd = "protected"
        subarg = f"add {subarg}"
    elif subcmd == "remove":
        subcmd = "protected"
        subarg = f"remove {subarg}"

    try:
        if subcmd == "permissions":
            if subarg:
                eval_res = perm_mgr.evaluate_command(subarg)
                table = Table(title=f"Command Permission Evaluation: '{subarg}'", show_header=False, box=None)
                table.add_column("Field", style="bold cyan", width=18)
                table.add_column("Value", style="white")
                v_style = "green" if eval_res.verdict == PolicyVerdict.ALLOW else ("yellow" if eval_res.verdict == PolicyVerdict.REQUIRE_APPROVAL else "bold red")
                table.add_row("Verdict:", f"[{v_style}]{eval_res.verdict.value}[/{v_style}]")
                table.add_row("Executable:", eval_res.executable)
                table.add_row("Subcommand:", eval_res.subcommand or "-")
                table.add_row("Reason:", eval_res.reason)
                table.add_row("Risk Level:", eval_res.risk_level.upper())
                table.add_row("Requires Approval:", str(eval_res.requires_approval))
                console.print(table)
            else:
                table = Table(title="Command Permission Policy Categories", show_header=True, header_style="bold cyan")
                table.add_column("Category", style="bold white", width=20)
                table.add_column("Policy Verdict", justify="center", width=18)
                table.add_column("Example Commands", style="dim")
                table.add_row("Read-only Queries", "[bold green]ALLOW[/bold green]", "git status, git diff, git log, pytest")
                table.add_row("Mutating Commands", "[bold yellow]REQUIRE_APPROVAL[/bold yellow]", "git add, git commit, git switch, pip install, file write")
                table.add_row("Destructive Actions", "[bold red]DENY[/bold red]", "git push --force, git reset --hard, git clean -fd, rm -rf")
                console.print(table)
                console.print("[dim]Test any command: [bold]/safety permissions <command>[/bold][/dim]")

        elif subcmd == "protected":
            if subarg.startswith("add "):
                pat = subarg[4:].strip()
                paths_mgr.add_custom_protected_path(pat)
                console.print(f"[bold green]Added custom protected rule:[/bold green] '{pat}'")
            elif subarg.startswith("remove "):
                pat = subarg[7:].strip()
                if paths_mgr.remove_custom_protected_path(pat):
                    console.print(f"[bold green]Removed custom protected rule:[/bold green] '{pat}'")
                else:
                    console.print(f"[yellow]Rule '{pat}' not found in custom list.[/yellow]")
            else:
                rules = paths_mgr.list_protected_rules()
                table = Table(title="Protected Files, Directories, and Sensitive Patterns", show_header=True, header_style="bold cyan")
                table.add_column("Protected Pattern", style="bold yellow", width=24)
                table.add_column("Type", style="cyan", width=16)
                table.add_column("Rule Description", style="white")
                for r in rules:
                    t_str = "Custom" if r.is_custom else ("Directory" if r.is_directory_only else "Sensitive Pattern")
                    table.add_row(r.pattern, t_str, r.description)
                console.print(table)
                console.print("[dim]Manage rules: [bold]/safety protected add <pattern>[/bold] or [bold]remove <pattern>[/bold][/dim]")

        elif subcmd == "audit":
            op_id = None
            if "--operation-id" in subarg:
                parts_id = subarg.split("--operation-id")
                op_id = parts_id[1].strip().split()[0] if len(parts_id) > 1 and parts_id[1].strip() else None

            if op_id:
                rec = audit_logger.get_event(op_id)
                if not rec:
                    console.print(f"[yellow]No audit record found for operation ID: {op_id}[/yellow]")
                    return
                table = Table(title=f"Security Audit Record: {op_id}", show_header=False, box=None)
                table.add_column("Field", style="bold cyan", width=20)
                table.add_column("Value", style="white")
                table.add_row("Timestamp:", rec.timestamp)
                table.add_row("Operation Type:", rec.operation_type)
                table.add_row("User Action:", rec.user_action)
                table.add_row("Target Paths:", ", ".join(rec.target_paths) if rec.target_paths else "-")
                table.add_row("Permission Verdict:", rec.permission_decision)
                table.add_row("Approval Decision:", rec.approval_decision)
                table.add_row("Execution Result:", rec.execution_result)
                if rec.git_commit_hash:
                    table.add_row("Git Commit Hash:", rec.git_commit_hash)
                if rec.error_message:
                    table.add_row("Error Details:", rec.error_message)
                console.print(table)
            else:
                events = audit_logger.list_events(limit=15)
                if not events:
                    console.print("[dim]No security audit records logged yet.[/dim]")
                    return
                table = Table(title="Recent Security Audit Log Events", show_header=True, header_style="bold cyan")
                table.add_column("Time (UTC)", style="dim", width=20)
                table.add_column("Operation ID", style="bold yellow", width=12)
                table.add_column("Type", style="cyan", width=14)
                table.add_column("Action Summary", style="white")
                table.add_column("Verdict", justify="center", width=12)
                table.add_column("Result", justify="center", width=10)
                for e in events:
                    table.add_row(
                        e.timestamp[:19].replace("T", " "),
                        e.operation_id[:8],
                        e.operation_type,
                        e.user_action[:40],
                        e.permission_decision,
                        f"[green]{e.execution_result}[/green]" if e.execution_result == "SUCCESS" else f"[red]{e.execution_result}[/red]",
                    )
                console.print(table)
                console.print("[dim]Lookup operation: [bold]/safety audit --operation-id <ID>[/bold][/dim]")
        else:
            console.print(f"[yellow]Unknown safety command: '{subcmd}'.[/yellow]")
            console.print("[dim]Available: permissions, protected, audit[/dim]")
    except Exception as exc:
        console.print(f"[bold red]Safety Error:[/bold red] {exc}")


def handle_backup_cli(args: list[str], backup_mgr: SafetyBackupManager) -> None:
    """Handle CLI command 'codeagent backup <subcommand>'."""
    if not args:
        console.print("[yellow]Usage: codeagent backup [create <file> | list | restore <backup_id>][/yellow]")
        return
    subcmd = args[0].lower()
    subarg = " ".join(args[1:]) if len(args) > 1 else ""
    handle_backup_command(backup_mgr, f"{subcmd} {subarg}".strip())


def handle_backup_command(backup_mgr: SafetyBackupManager, arg: Optional[str]) -> None:
    """Handle /backup and CLI backup operations."""
    parts = arg.strip().split(maxsplit=1) if arg and arg.strip() else []
    subcmd = parts[0].lower() if parts else "list"
    subarg = parts[1].strip() if len(parts) > 1 else ""

    try:
        if subcmd == "create":
            if not subarg:
                console.print("[yellow]Usage: /backup create <relative_file_path>[/yellow]")
                return
            rec = backup_mgr.create_backup(subarg)
            if rec:
                console.print(f"[bold green]Safety backup created:[/bold green] ID [bold cyan]{rec.backup_id}[/bold cyan] ({rec.size_bytes}B, SHA256: {rec.sha256_hash[:12]}...)")
            else:
                console.print(f"[yellow]File '{subarg}' does not exist yet. Nothing backed up.[/yellow]")
        elif subcmd in ("list", "show"):
            records = backup_mgr.list_backups(file_path_filter=subarg or None)
            if not records:
                console.print("[dim]No safety file backups stored.[/dim]")
                return
            table = Table(title="Verifiable Safety File Backups", show_header=True, header_style="bold cyan")
            table.add_column("Backup ID", style="bold yellow", width=24)
            table.add_column("Original File", style="white")
            table.add_column("Created (UTC)", style="dim", width=20)
            table.add_column("Size", justify="right", style="green", width=10)
            table.add_column("SHA-256 Digest", style="cyan", width=14)
            for r in records[:25]:
                table.add_row(r.backup_id, r.original_rel_path, r.created_at[:19].replace("T", " "), f"{r.size_bytes} B", f"{r.sha256_hash[:10]}...")
            console.print(table)
            console.print("[dim]Restore backup: [bold]/backup restore <backup_id>[/bold][/dim]")
        elif subcmd == "restore":
            if not subarg:
                console.print("[yellow]Usage: /backup restore <backup_id> [--force][/yellow]")
                return
            force = "--force" in subarg or "-f" in subarg
            clean_id = subarg.replace("--force", "").replace("-f", "").strip().split()[0]
            confirm = typer.confirm(f"Restore file from backup '{clean_id}'?", default=True)
            if not confirm:
                console.print("[yellow]Restoration cancelled by user.[/yellow]")
                return
            res = backup_mgr.restore_backup(backup_id=clean_id, force=force)
            console.print(f"[bold green]{res.message}[/bold green]")
        else:
            console.print(f"[yellow]Unknown backup command: '{subcmd}'.[/yellow]")
            console.print("[dim]Available: create <file>, list, restore <id> [--force][/dim]")
    except Exception as exc:
        console.print(f"[bold red]Backup Error:[/bold red] {exc}")


def handle_agents_cli(args: list[str], factory: AgentFactory) -> None:
    """Handle CLI command 'codeagent agents <subcommand>'."""
    if not args:
        console.print("[yellow]Usage: codeagent agents [list | status | inspect <role>][/yellow]")
        return
    subcmd = args[0].lower()
    subarg = " ".join(args[1:]) if len(args) > 1 else ""
    handle_agents_command(factory, f"{subcmd} {subarg}".strip())


def handle_agents_command(factory: AgentFactory, arg: Optional[str]) -> None:
    """Handle /agents and CLI agents operations."""
    parts = arg.strip().split(maxsplit=1) if arg and arg.strip() else []
    subcmd = parts[0].lower() if parts else "list"
    subarg = parts[1].strip() if len(parts) > 1 else ""

    # Direct agent shortcuts: e.g. /agents code or codeag agents code directly inspects that agent
    if subcmd in ("code", "coder", "codeagent", "coderagent"):
        subarg = "code"
        subcmd = "inspect"
    elif subcmd in ("planner", "debugger", "reviewer", "coordinator"):
        subarg = subcmd
        subcmd = "inspect"

    try:
        coordinator = factory.create_coordinator()
        registry = factory.registry

        if subcmd == "list":
            table = Table(title="Autonomous Agent Directory", show_header=True, header_style="bold cyan")
            table.add_column("Agent ID", style="bold yellow", width=22)
            table.add_column("Name", style="white", width=18)
            table.add_column("Role", style="bold green", width=14)
            table.add_column("Status", justify="center", width=12)
            table.add_column("Capabilities", style="dim")

            for agent in registry.list_agents():
                status_color = "green" if agent.status.value == "idle" else "yellow"
                display_role = "Code" if agent.role.value in ("coder", "code") else agent.role.value.capitalize()
                table.add_row(
                    agent.agent_id,
                    agent.name,
                    display_role,
                    f"[{status_color}]{agent.status.value}[/{status_color}]",
                    ", ".join(agent.capabilities[:3]),
                )
            console.print(table)
            console.print("[dim]Inspect an agent: [bold]/agents inspect <role>[/bold][/dim]")

        elif subcmd == "status":
            table = Table(title="Autonomous Agents Live Status Overview", show_header=True, header_style="bold cyan")
            table.add_column("Role", style="bold cyan", width=16)
            table.add_column("Agent Name", style="white", width=20)
            table.add_column("Current State", justify="center", width=16)
            table.add_column("Assigned Tools", style="dim")

            for agent in registry.list_agents():
                display_role = "CODE" if agent.role.value in ("coder", "code") else agent.role.value.upper()
                table.add_row(
                    display_role,
                    agent.name,
                    f"[bold green]{agent.status.value}[/bold green]",
                    f"{len(agent.tools)} tools authorized",
                )
            console.print(table)

        elif subcmd == "inspect":
            if not subarg:
                console.print("[yellow]Usage: /agents inspect <planner | code | debugger | reviewer | coordinator>[/yellow]")
                return
            target_role = subarg.lower()
            match = next((
                a for a in registry.list_agents()
                if a.role.value == target_role
                or a.name.lower() == target_role
                or (target_role in ("code", "coder") and a.role.value in ("coder", "code"))
            ), None)
            if not match:
                console.print(f"[yellow]No agent registered matching role or name: '{subarg}'[/yellow]")
                return

            info = match.to_info_dict()
            display_role = "code" if info['role'] in ("coder", "code") else info['role']
            content = (
                f"[bold cyan]Name:[/bold cyan] {info['name']}\n"
                f"[bold cyan]Role:[/bold cyan] {display_role}\n"
                f"[bold cyan]Agent ID:[/bold cyan] {info['agent_id']}\n"
                f"[bold cyan]Status:[/bold cyan] {info['status']}\n"
                f"[bold cyan]Description:[/bold cyan] {info['description']}\n"
                f"[bold cyan]Input Schema:[/bold cyan] {info['input_schema']}\n"
                f"[bold cyan]Output Schema:[/bold cyan] {info['output_schema']}\n"
                f"[bold cyan]Timeout:[/bold cyan] {info['timeout_seconds']}s\n"
                f"[bold cyan]Capabilities:[/bold cyan] {', '.join(info['capabilities'])}\n"
                f"[bold cyan]Authorized Tools:[/bold cyan] {', '.join(info['tools'])}\n\n"
                f"[bold cyan]System Instructions:[/bold cyan]\n[italic dim]{match.system_instructions}[/italic dim]"
            )
            console.print(Panel(content, title=f"[bold green]Agent Profile: {info['name']}[/bold green]", border_style="cyan"))
        else:
            console.print(f"[yellow]Unknown agents command: '{subcmd}'. Available: list, status, inspect <role>[/yellow]")
    except Exception as exc:
        console.print(f"[bold red]Agents Error:[/bold red] {exc}")


def handle_workflow_cli(args: list[str], engine: WorkflowEngine) -> None:
    """Handle CLI command 'codeagent workflow <subcommand>'."""
    if not args:
        console.print("[yellow]Usage: codeagent workflow [run <goal> | status [id] | list | inspect <id> | cancel <id> | resume <id>][/yellow]")
        return
    subcmd = args[0].lower()
    subarg = " ".join(args[1:]) if len(args) > 1 else ""
    handle_workflow_command(engine, f"{subcmd} {subarg}".strip())


def handle_workflow_command(engine: WorkflowEngine, arg: Optional[str]) -> None:
    """Handle /workflow and CLI workflow operations."""
    parts = arg.strip().split(maxsplit=1) if arg and arg.strip() else []
    subcmd = parts[0].lower() if parts else "list"
    subarg = parts[1].strip() if len(parts) > 1 else ""

    try:
        if subcmd == "run":
            if not subarg:
                console.print("[yellow]Usage: /workflow run <goal> [--type <BUILD_PROJECT|FIX_BUG|CODE_REVIEW|ADD_FEATURE|REFACTOR_PROJECT>][/yellow]")
                return

            wf_type_str = "BUILD_PROJECT"
            goal = subarg
            if "--type" in subarg:
                p_type = subarg.split("--type")
                goal = p_type[0].strip()
                wf_type_str = p_type[1].strip().split()[0].upper()

            try:
                wf_type = WorkflowType(wf_type_str)
            except ValueError:
                wf_type = WorkflowType.BUILD_PROJECT

            console.print(f"[bold cyan]Starting Multi-Agent Workflow:[/bold cyan] [bold yellow]{wf_type.value}[/bold yellow]")
            console.print(f"[dim]Goal: {goal}[/dim]")
            with console.status("[bold cyan]Orchestrating agents (Planner, Code, Reviewer)...[/bold cyan]", spinner="dots"):
                res = engine.run_workflow(goal=goal, workflow_type=wf_type)

            title_style = "bold green" if res.status.value == "COMPLETED" else "bold red"
            console.print(
                Panel(
                    f"[bold]Workflow ID:[/bold] {res.workflow_id}\n"
                    f"[bold]Status:[/bold] [{title_style}]{res.status.value}[/{title_style}]\n"
                    f"[bold]Duration:[/bold] {res.execution_duration_seconds}s\n"
                    f"[bold]Tasks Completed:[/bold] {res.tasks_completed} / {res.tasks_total}\n"
                    f"[bold]Review Decision:[/bold] [bold cyan]{res.review_verdict or 'N/A'}[/bold cyan]\n"
                    f"[bold]Summary:[/bold] {res.summary}",
                    title=f"[{title_style}]Workflow Outcome: {res.status.value}[/{title_style}]",
                    border_style="green" if res.status.value == "COMPLETED" else "red",
                )
            )

            if res.task_summaries:
                table = Table(title="Workflow Task Execution History", show_header=True, header_style="bold cyan")
                table.add_column("Task ID", style="bold yellow", width=14)
                table.add_column("Task Name", style="white")
                table.add_column("Assigned Agent", style="cyan", width=14)
                table.add_column("Status", justify="center", width=14)
                table.add_column("Retries", justify="center", width=10)

                for ts in res.task_summaries:
                    s_color = "green" if ts["status"] == "COMPLETED" else ("red" if ts["status"] in ("FAILED", "BLOCKED") else "yellow")
                    table.add_row(
                        ts["task_id"],
                        ts["name"],
                        ts["agent"].capitalize(),
                        f"[{s_color}]{ts['status']}[/{s_color}]",
                        str(ts["retries"]),
                    )
                console.print(table)

        elif subcmd in ("list", "show"):
            wfs = engine.list_workflows(limit=25)
            if not wfs:
                console.print("[dim]No multi-agent workflows recorded yet.[/dim]")
                return

            table = Table(title="Multi-Agent Workflows", show_header=True, header_style="bold cyan")
            table.add_column("Workflow ID", style="bold yellow", width=16)
            table.add_column("Type", style="cyan", width=18)
            table.add_column("Status", justify="center", width=14)
            table.add_column("User Goal", style="white")
            table.add_column("Start Time (UTC)", style="dim", width=20)

            for w in wfs:
                s_color = "green" if w.status.value == "COMPLETED" else ("red" if w.status.value in ("FAILED", "CANCELLED") else "yellow")
                table.add_row(
                    w.workflow_id,
                    w.workflow_type,
                    f"[{s_color}]{w.status.value}[/{s_color}]",
                    w.user_task[:40] + ("..." if len(w.user_task) > 40 else ""),
                    w.start_time[:19].replace("T", " "),
                )
            console.print(table)
            console.print("[dim]Inspect workflow: [bold]/workflow inspect <workflow_id>[/bold][/dim]")

        elif subcmd == "status":
            wf_id = subarg.split()[0] if subarg else None
            if not wf_id:
                wfs = engine.list_workflows(limit=1)
                if not wfs:
                    console.print("[yellow]No workflows recorded yet.[/yellow]")
                    return
                wf_id = wfs[0].workflow_id

            wf = engine.get_workflow_status(wf_id)
            if not wf:
                console.print(f"[yellow]Workflow '{wf_id}' not found.[/yellow]")
                return

            tasks = engine.list_tasks_for_workflow(wf_id)
            completed_n = sum(1 for t in tasks if t.status.value == "COMPLETED")

            table = Table(title=f"Workflow Status: {wf_id}", show_header=False, box=None)
            table.add_column("Field", style="bold cyan", width=18)
            table.add_column("Value", style="white")
            table.add_row("Status:", wf.status.value)
            table.add_row("Type:", wf.workflow_type)
            table.add_row("Goal:", wf.user_task)
            table.add_row("Tasks:", f"{completed_n} / {len(tasks)} completed")
            table.add_row("Start Time:", wf.start_time)
            table.add_row("End Time:", wf.end_time or "-")
            if wf.error:
                table.add_row("Error:", f"[bold red]{wf.error}[/bold red]")
            console.print(table)

        elif subcmd == "inspect":
            if not subarg:
                console.print("[yellow]Usage: /workflow inspect <workflow_id>[/yellow]")
                return
            wf_id = subarg.split()[0]
            wf = engine.get_workflow_status(wf_id)
            if not wf:
                console.print(f"[yellow]Workflow '{wf_id}' not found.[/yellow]")
                return

            tasks = engine.list_tasks_for_workflow(wf_id)
            console.print(f"\n[bold cyan]Workflow:[/bold cyan] {wf.workflow_id} ({wf.workflow_type}) - [bold]{wf.status.value}[/bold]")
            console.print(f"[dim]Goal: {wf.user_task}[/dim]\n")

            table = Table(title=f"Tasks for Workflow {wf_id}", show_header=True, header_style="bold cyan")
            table.add_column("Task ID", style="bold yellow", width=14)
            table.add_column("Name", style="white")
            table.add_column("Agent", style="cyan", width=12)
            table.add_column("Status", justify="center", width=12)
            table.add_column("Dependencies", style="dim", width=20)

            for t in tasks:
                table.add_row(
                    t.task_id,
                    t.name,
                    t.assigned_agent.value.capitalize(),
                    t.status.value,
                    ", ".join(t.dependencies) if t.dependencies else "-",
                )
            console.print(table)

        elif subcmd == "cancel":
            if not subarg:
                console.print("[yellow]Usage: /workflow cancel <workflow_id>[/yellow]")
                return
            wf_id = subarg.split()[0]
            ok = engine.cancel_workflow(wf_id)
            if ok:
                console.print(f"[bold green]Workflow '{wf_id}' cancelled successfully.[/bold green]")
            else:
                console.print(f"[yellow]Could not cancel workflow '{wf_id}'.[/yellow]")

        elif subcmd == "resume":
            if not subarg:
                console.print("[yellow]Usage: /workflow resume <workflow_id>[/yellow]")
                return
            wf_id = subarg.split()[0]
            with console.status(f"[bold cyan]Resuming workflow '{wf_id}'...[/bold cyan]", spinner="dots"):
                res = engine.resume_workflow(wf_id)
            if res:
                console.print(f"[bold green]Workflow '{wf_id}' resumed: {res.status.value}[/bold green]")
            else:
                console.print(f"[yellow]Workflow '{wf_id}' cannot be resumed (ineligible or expired approvals).[/yellow]")
        else:
            console.print(f"[yellow]Unknown workflow command: '{subcmd}'. Available: run, status, list, inspect, cancel, resume[/yellow]")
    except Exception as exc:
        console.print(f"[bold red]Workflow Error:[/bold red] {exc}")


def handle_task_cli(args: list[str], engine: WorkflowEngine) -> None:
    """Handle CLI command 'codeagent task <subcommand>'."""
    if not args:
        console.print("[yellow]Usage: codeagent task [list [workflow_id] | inspect <task_id>][/yellow]")
        return
    subcmd = args[0].lower()
    subarg = " ".join(args[1:]) if len(args) > 1 else ""
    handle_task_command(engine, f"{subcmd} {subarg}".strip())


def handle_task_command(engine: WorkflowEngine, arg: Optional[str]) -> None:
    """Handle /task and CLI task operations."""
    parts = arg.strip().split(maxsplit=1) if arg and arg.strip() else []
    subcmd = parts[0].lower() if parts else "list"
    subarg = parts[1].strip() if len(parts) > 1 else ""

    try:
        if subcmd == "list":
            wf_id = subarg.split()[0] if subarg else None
            if not wf_id:
                wfs = engine.list_workflows(limit=1)
                if not wfs:
                    console.print("[dim]No workflows or tasks recorded.[/dim]")
                    return
                wf_id = wfs[0].workflow_id

            tasks = engine.list_tasks_for_workflow(wf_id)
            table = Table(title=f"Tasks for Workflow: {wf_id}", show_header=True, header_style="bold cyan")
            table.add_column("Task ID", style="bold yellow", width=14)
            table.add_column("Task Name", style="white")
            table.add_column("Assigned Agent", style="cyan", width=14)
            table.add_column("Priority", justify="center", width=10)
            table.add_column("Status", justify="center", width=12)

            for t in tasks:
                s_color = "green" if t.status.value == "COMPLETED" else ("red" if t.status.value in ("FAILED", "BLOCKED") else "yellow")
                table.add_row(
                    t.task_id,
                    t.name,
                    t.assigned_agent.value.capitalize(),
                    f"P{t.priority}",
                    f"[{s_color}]{t.status.value}[/{s_color}]",
                )
            console.print(table)
            console.print("[dim]Inspect task: [bold]/task inspect <task_id>[/bold][/dim]")

        elif subcmd == "inspect":
            if not subarg:
                console.print("[yellow]Usage: /task inspect <task_id>[/yellow]")
                return
            t_id = subarg.split()[0]
            task = engine.get_task(t_id)
            if not task:
                console.print(f"[yellow]Task '{t_id}' not found.[/yellow]")
                return

            table = Table(title=f"Task Inspection: {task.task_id}", show_header=False, box=None)
            table.add_column("Field", style="bold cyan", width=18)
            table.add_column("Value", style="white")
            table.add_row("Task Name:", task.name)
            table.add_row("Workflow ID:", task.workflow_id)
            table.add_row("Assigned Agent:", task.assigned_agent.value.capitalize())
            table.add_row("Status:", task.status.value)
            table.add_row("Priority:", f"P{task.priority}")
            table.add_row("Risk Level:", task.risk_level)
            table.add_row("Complexity:", task.estimated_complexity)
            table.add_row("Dependencies:", ", ".join(task.dependencies) if task.dependencies else "-")
            table.add_row("Description:", task.description)
            if task.acceptance_criteria:
                table.add_row("Acceptance Criteria:", "\n".join(f"- {c}" for c in task.acceptance_criteria))
            if task.error:
                table.add_row("Error Message:", f"[bold red]{task.error}[/bold red]")
            console.print(Panel(table, border_style="cyan"))
        else:
            console.print(f"[yellow]Unknown task command: '{subcmd}'. Available: list [wf_id], inspect <task_id>[/yellow]")
    except Exception as exc:
        console.print(f"[bold red]Task Error:[/bold red] {exc}")


def handle_health_cli(settings: Settings) -> None:
    """Execute health checks across subsystems and display formatted table."""
    from codeagent.core.monitoring import MonitoringSystem
    mon = MonitoringSystem(settings=settings)
    with console.status("[bold cyan]Running system health checks...[/bold cyan]", spinner="dots"):
        items = mon.run_all_health_checks(check_llm=True)

    table = Table(title="System Health & Diagnostics", show_header=True, header_style="bold cyan")
    table.add_column("Subsystem", style="bold white", width=22)
    table.add_column("Status", justify="center", width=12)
    table.add_column("Message", style="white")
    table.add_column("Latency", justify="right", style="cyan", width=12)

    has_fail = False
    for item in items:
        if item.status == "OK":
            s_badge = "[bold green][OK][/bold green]"
        elif item.status == "WARN":
            s_badge = "[bold yellow][WARN][/bold yellow]"
        else:
            s_badge = "[bold red][FAIL][/bold red]"
            has_fail = True
        lat_str = f"{item.latency_ms:.1f}ms" if item.latency_ms is not None else "-"
        table.add_row(item.component, s_badge, item.message, lat_str)

    console.print()
    console.print(table)
    console.print()
    if has_fail:
        raise typer.Exit(code=1)


def handle_diagnostics_cli(args: list[str], settings: Settings) -> None:
    """Generate and display or export complete diagnostics report."""
    from codeagent.core.monitoring import MonitoringSystem
    import json
    mon = MonitoringSystem(settings=settings)
    with console.status("[bold cyan]Collecting system diagnostics...[/bold cyan]", spinner="dots"):
        report = mon.generate_diagnostics_report()

    # Check for --export or -e flag
    export_path = None
    if args:
        for i, a in enumerate(args):
            if a in ("--export", "-e") and i + 1 < len(args):
                export_path = Path(args[i + 1])
                break

    if export_path:
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        console.print(f"[bold green]Diagnostics report exported to:[/bold green] [cyan]{export_path}[/cyan]")
        return

    # Display summary
    console.print()
    console.print(
        Panel(
            f"[bold cyan]Application:[/bold cyan] {report['app_name']} v{report['app_version']}\n"
            f"[bold cyan]Platform:[/bold cyan]    {report['platform']['os']} {report['platform']['release']} ({report['platform']['machine']})\n"
            f"[bold cyan]Python:[/bold cyan]      {report['platform']['python_version'].split()[0]}\n"
            f"[bold cyan]Workspace:[/bold cyan]   {report['workspace_root']}\n"
            f"[bold cyan]Model:[/bold cyan]       {report['settings']['model_name']} @ {report['settings']['ollama_host']}",
            title="[bold cyan]System Diagnostics Summary[/bold cyan]",
            border_style="cyan",
        )
    )
    console.print("[dim]Export full JSON report with: [bold]codeagent diagnostics --export report.json[/bold][/dim]\n")


def handle_monitor_cli(settings: Settings) -> None:
    """Display real-time subsystem state and resource metrics."""
    from codeagent.core.monitoring import MonitoringSystem
    mon = MonitoringSystem(settings=settings)
    res_item = mon.check_resources()
    app_item = mon.check_application_health()
    db_item = mon.check_database_health()
    agent_item = mon.check_agent_health()
    tools_item = mon.check_tools_health()

    table = Table(title="Coder with Code Subsystem Monitor", show_header=True, header_style="bold cyan")
    table.add_column("Component", style="bold white", width=22)
    table.add_column("Status", justify="center", width=10)
    table.add_column("Details", style="white")

    for it in [app_item, db_item, agent_item, tools_item, res_item]:
        badge = f"[green]{it.status}[/green]" if it.status == "OK" else f"[yellow]{it.status}[/yellow]"
        table.add_row(it.component, badge, it.message)

    console.print()
    console.print(table)
    console.print()


def handle_performance_cli(settings: Settings) -> None:
    """Execute local benchmarks measuring engine and path safety latency."""
    from codeagent.core.profiler import run_local_benchmark
    with console.status("[bold cyan]Running local performance benchmarks...[/bold cyan]", spinner="dots"):
        results = run_local_benchmark()

    table = Table(title="Local Engine Benchmarks", show_header=True, header_style="bold cyan")
    table.add_column("Benchmark Target", style="bold white", width=32)
    table.add_column("Measured Metric", style="cyan")

    table.add_row("Calculator Tool Latency (avg)", f"{results['benchmarks']['calculator_tool_avg_ms']:.4f} ms")
    table.add_row("Path Safety Validation (avg)", f"{results['benchmarks']['path_safety_check_avg_ms']:.4f} ms")
    table.add_row("Current Process RSS Memory", f"{results['benchmarks']['current_process_rss_mb']} MB")
    table.add_row("Python Runtime", results["python_version"])
    table.add_row("Host OS", results["platform"])

    console.print()
    console.print(table)
    console.print()


def handle_config_cli(args: list[str], settings: Settings) -> None:
    """Handle 'codeagent config <subcmd>' commands."""
    from codeagent.core.config_manager import ConfigManager
    cm = ConfigManager(workspace_root=Path(settings.workspace_root or Path.cwd()))
    subcmd = args[0].lower() if args else "show"
    subarg = args[1:] if len(args) > 1 else []

    if subcmd == "show":
        show_all = "--all" in subarg or "-a" in subarg
        data = cm.get_masked_config_dump(settings=settings, show_all=show_all)
        table = Table(title="Effective Configuration Settings", show_header=True, header_style="bold cyan")
        table.add_column("Configuration Key", style="bold yellow", width=28)
        table.add_column("Effective Value", style="white")
        for k, v in sorted(data.items()):
            table.add_row(k, str(v))
        console.print()
        console.print(table)
        console.print(f"[dim]Secrets are masked automatically. User config file: [bold]{cm.get_user_config_path()}[/bold][/dim]\n")

    elif subcmd == "validate":
        results = cm.validate_settings(settings=settings)
        table = Table(title="Configuration Validation Check", show_header=True, header_style="bold cyan")
        table.add_column("Setting", style="bold white", width=24)
        table.add_column("Verdict", justify="center", width=12)
        table.add_column("Details", style="white")

        all_valid = True
        for key, is_ok, msg in results:
            verdict = "[bold green]VALID[/bold green]" if is_ok else "[bold red]INVALID[/bold red]"
            table.add_row(key, verdict, msg)
            if not is_ok:
                all_valid = False

        console.print()
        console.print(table)
        console.print()
        if not all_valid:
            raise typer.Exit(code=1)

    elif subcmd == "path":
        console.print(f"User global config path: [bold cyan]{cm.get_user_config_path()}[/bold cyan]")

    elif subcmd == "init":
        force = "--force" in subarg or "-f" in subarg
        ok, msg = cm.init_user_config(force=force)
        if ok:
            console.print(f"[bold green][OK][/bold green] {msg}")
        else:
            console.print(f"[bold yellow][NOTE][/bold yellow] {msg}")
    else:
        console.print(f"[yellow]Unknown config command: '{subcmd}'. Available: show, validate, path, init[/yellow]")


def handle_setup_cli(args: list[str], settings: Settings) -> None:
    """Execute CodeAgent first-time setup or repair."""
    from codeagent.installer.setup_manager import SetupManager

    check_only = "--check" in args
    skip_model = "--skip-model" in args
    repair = "--repair" in args
    auto_confirm = "--yes" in args or "-y" in args

    model_name = settings.model_name
    if "--model" in args:
        idx = args.index("--model")
        if idx + 1 < len(args):
            model_name = args[idx + 1]

    mgr = SetupManager(console=console)
    success = mgr.run_setup(
        check_only=check_only,
        skip_model=skip_model,
        model_name=model_name,
        repair=repair,
        auto_confirm=auto_confirm,
    )
    if not success and check_only:
        raise typer.Exit(code=1)


def handle_models_cli(args: list[str], settings: Settings) -> None:
    """Manage local models via Ollama."""
    from codeagent.installer.model_manager import ModelManager
    from codeagent.installer.ollama_detector import OllamaDetector

    mgr = ModelManager(api_url=settings.ollama_host)
    detector = OllamaDetector(api_url=settings.ollama_host)
    subcmd = args[0].lower() if args else "list"

    if subcmd == "list":
        models = mgr.list_installed_models()
        if not models:
            res = detector.detect()
            if not res.is_running:
                console.print(f"[bold yellow]Ollama is not running at {settings.ollama_host}.[/bold yellow] Start it with 'ollama serve'.")
            else:
                console.print(f"[yellow]No models found in local Ollama storage. Install one with 'codeagent models install {settings.model_name}'[/yellow]")
            return

        table = Table(title="Installed Ollama Models", show_header=True, header_style="bold cyan")
        table.add_column("Model Name", style="bold white", width=32)
        table.add_column("Status", style="cyan")

        for m in models:
            is_active = (m.lower() == settings.model_name.lower()) or (m.lower().split(":")[0] == settings.model_name.lower().split(":")[0])
            status = "[bold green]ACTIVE MODEL[/bold green]" if is_active else "Installed"
            table.add_row(m, status)

        console.print()
        console.print(table)
        console.print()

    elif subcmd == "current":
        is_inst = mgr.is_model_installed(settings.model_name)
        status_text = "[bold green]Installed locally[/bold green]" if is_inst else "[bold red]Missing (run 'codeagent models install')[/bold red]"
        console.print()
        console.print(f"Configured model: [bold cyan]{settings.model_name}[/bold cyan]")
        console.print(f"Local storage status: {status_text}")
        console.print(f"Ollama server URL: [dim]{settings.ollama_host}[/dim]\n")

    elif subcmd in ("install", "pull"):
        target_model = args[1] if len(args) > 1 else settings.model_name
        console.print(f"[bold cyan]Pulling model '{target_model}' via Ollama...[/bold cyan]")
        ok, msg = mgr.pull_model(model_name=target_model, show_progress=True)
        if ok:
            console.print(f"[bold green][OK][/bold green] {msg}")
        else:
            console.print(f"[bold red][FAIL][/bold red] {msg}")
            raise typer.Exit(code=1)
    else:
        console.print(f"[yellow]Unknown models subcommand: '{subcmd}'. Available: list, current, install[/yellow]")


def handle_read_command(fs_mgr: FilesystemManager, arg: Optional[str]) -> None:
    """Handle /read command to inspect files."""
    if not arg or not arg.strip():
        console.print("[yellow]Usage: /read <relative_path> [start_line] [end_line][/yellow]")
        return

    parts = arg.strip().split()
    fpath = parts[0]
    s_line = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
    e_line = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None

    try:
        res = fs_mgr.read_file(fpath, start_line=s_line, end_line=e_line)
        console.print()
        console.print(f"[dim]{res.to_summary()}[/dim]")
        console.print(
            Panel(
                res.content,
                title=f"[bold green]{res.path}[/bold green]",
                border_style="dim",
            )
        )
    except Exception as exc:
        console.print(f"[bold red]Read Error:[/bold red] {exc}")


def handle_newfile_command(fs_mgr: FilesystemManager, arg: Optional[str]) -> None:
    """Handle /newfile command to interactively create a file."""
    if not arg or not arg.strip():
        console.print("[yellow]Usage: /newfile <relative_path>[/yellow]")
        return

    fpath = arg.strip()
    console.print(f"Creating file at [bold cyan]{fpath}[/bold cyan].")
    console.print("Enter file content (press Ctrl+Z and Enter on Windows to finish, or enter blank line):")
    lines = []
    try:
        while True:
            line = input()
            if line == "":
                break
            lines.append(line)
    except (EOFError, KeyboardInterrupt):
        pass

    content = "\n".join(lines)
    try:
        res = fs_mgr.create_file(fpath, content=content, overwrite=False)
        console.print(f"[bold green][Created][/bold green] {res.to_summary()}")
    except Exception as exc:
        console.print(f"[bold red]Create Error:[/bold red] {exc}")


def handle_delete_command(fs_mgr: FilesystemManager, arg: Optional[str]) -> None:
    """Handle /delete command to safely delete a file."""
    if not arg or not arg.strip():
        console.print("[yellow]Usage: /delete <relative_path>[/yellow]")
        return

    try:
        res = fs_mgr.delete_file(arg.strip(), confirmed=False)
        console.print(f"[bold green][Deleted][/bold green] {res.to_summary()}")
    except DeletionNotConfirmedError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
    except Exception as exc:
        console.print(f"[bold red]Delete Error:[/bold red] {exc}")


def handle_backups_command(fs_mgr: FilesystemManager) -> None:
    """Handle /backups command to list available file backups."""
    backups = fs_mgr.list_backups()
    if not backups:
        console.print("[yellow]No backups recorded in workspace.[/yellow]")
        return

    table = Table(title="Workspace Backups", show_header=True, header_style="bold cyan")
    table.add_column("Backup ID", style="bold yellow")
    table.add_column("Original File", style="white")
    table.add_column("Action", style="cyan")
    table.add_column("Size (Bytes)", justify="right")
    table.add_column("Timestamp", style="dim")

    for b in backups[:15]:
        table.add_row(b.backup_id, b.original_path, b.operation, str(b.size_bytes), b.timestamp)

    console.print(table)


def handle_restore_command(fs_mgr: FilesystemManager, arg: Optional[str]) -> None:
    """Handle /restore command to restore a file from backup."""
    if not arg or not arg.strip():
        console.print("[yellow]Usage: /restore <backup_id>[/yellow]")
        return

    try:
        restored = fs_mgr.restore_backup(arg.strip())
        console.print(f"[bold green][Restored][/bold green] File restored to [cyan]{restored}[/cyan]")
    except Exception as exc:
        console.print(f"[bold red]Restore Error:[/bold red] {exc}")


def _extract_and_save_code_blocks(
    prompt: str,
    response_text: str,
    fs_mgr: FilesystemManager,
    console: Console,
) -> list[str]:
    """Detect if the user prompt requested creating a file and automatically save code blocks to the workspace.

    Args:
        prompt: User's original prompt.
        response_text: Markdown text produced by model (via tool or streaming).
        fs_mgr: FilesystemManager instance for safe atomic writes.
        console: Rich console instance.

    Returns:
        list[str]: Names of saved files.
    """
    import re

    saved_files: list[str] = []
    if not prompt or not response_text:
        return saved_files

    prompt_lower = prompt.lower()
    create_indicators = [
        "create", "write", "generate", "save", "make", "build", "add", "new file", "an index", "a file",
    ]
    if not any(ci in prompt_lower for ci in create_indicators):
        return saved_files

    # Match filenames in prompt like index.html, styles.css, app.js, main.py
    filename_matches = re.findall(
        r"\b([a-zA-Z0-9_\-\.\/\\]+\.(?:html|htm|css|js|jsx|ts|tsx|py|json|md|txt|sh|bat|ps1|yml|yaml|sql|vue|svelte))\b",
        prompt,
        re.IGNORECASE,
    )

    # Extract markdown code blocks: (language, code)
    code_block_pattern = re.compile(r"```([a-zA-Z0-9_\-\.\+]*)\r?\n(.*?)```", re.DOTALL)
    blocks = code_block_pattern.findall(response_text)
    if not blocks:
        return saved_files

    # Check for labeled code blocks (e.g., `### index.html\n```html...`)
    labeled_pattern = re.compile(
        r"(?:###?\s*|\*\*|File:\s*|Filename:\s*)?([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9]{1,10})\*?\*?[:\s]*\r?\n```[a-zA-Z0-9_\-\.\+]*\r?\n(.*?)```",
        re.DOTALL | re.IGNORECASE,
    )
    labeled_blocks = labeled_pattern.findall(response_text)

    targets_to_save: list[tuple[str, str]] = []
    if labeled_blocks:
        for fname, code in labeled_blocks:
            fname_clean = fname.strip().strip("`*:")
            if fname_clean and code.strip():
                targets_to_save.append((fname_clean, code))
    elif filename_matches:
        for target_fname in dict.fromkeys(filename_matches):
            target_ext = Path(target_fname).suffix.lstrip(".").lower()
            matched_code = None
            for lang, code in blocks:
                lang_clean = lang.lower().strip()
                if target_ext in (lang_clean, "htm" if lang_clean == "html" else ""):
                    matched_code = code
                    break
            if not matched_code:
                # Default to the largest code block
                matched_code = max(blocks, key=lambda b: len(b[1]))[1]

            if matched_code and matched_code.strip():
                targets_to_save.append((target_fname, matched_code))
                break

    if not targets_to_save and blocks:
        # Infer default filenames based on code language and user intent
        for lang, code in blocks:
            code_str = code.strip()
            if not code_str:
                continue
            lang_clean = lang.lower().strip()
            if lang_clean in ("html", "htm") or "<!doctype html" in code_str.lower() or "<html" in code_str.lower():
                targets_to_save.append(("index.html", code_str))
            elif lang_clean == "css":
                targets_to_save.append(("styles.css", code_str))
            elif lang_clean in ("js", "javascript"):
                targets_to_save.append(("script.js", code_str))
            elif lang_clean in ("py", "python"):
                suggested = "calculator.py" if "calculator" in prompt_lower else "app.py"
                targets_to_save.append((suggested, code_str))
            elif lang_clean == "json":
                targets_to_save.append(("data.json", code_str))
            elif len(blocks) == 1:
                targets_to_save.append(("index.html" if "website" in prompt_lower or "web" in prompt_lower else "output.txt", code_str))

    for fname, code in targets_to_save:
        try:
            norm_name = Path(fname).name
            res = fs_mgr.create_file(norm_name, content=code, overwrite=True)
            console.print(
                f"[bold green]✔ Auto-saved generated code to [cyan]{norm_name}[/cyan] ({res.bytes_written} bytes)[/bold green]"
            )
            saved_files.append(norm_name)
        except Exception as exc:
            console.print(f"[dim yellow]Could not auto-save {fname}: {exc}[/dim yellow]")

    return saved_files


def interactive_mode(client: LLMClient, model_name: str, settings: Settings) -> None:
    """Run Coder with Code in continuous interactive REPL mode with Phase 2, 3 & 5 capabilities."""
    active_model = model_name

    # Initialize Phase 2, 3 & 5 engines
    fs_mgr = FilesystemManager(
        settings=settings,
        write_approval_callback=cli_write_approval,
        delete_confirmation_callback=cli_delete_confirmation,
    )
    exec_mgr = ExecutionManager(
        settings=settings,
        workspace_root=fs_mgr.workspace_root,
        approval_callback=cli_execution_approval,
    )
    project_mgr = ProjectManager(settings=settings)
    debugger = AutonomousDebugger(
        workspace_root=fs_mgr.workspace_root,
        settings=settings,
        llm_client=client,
        execution_manager=exec_mgr,
        backup_manager=fs_mgr.backup_manager,
    )
    streaming_engine = StreamingEngine(console=console)
    conv_mgr = ConversationManager(storage_path=settings.conversation_storage_path)
    context_mgr = ContextManager(settings=settings)
    tool_registry = get_default_registry(
        filesystem_manager=fs_mgr,
        execution_manager=exec_mgr,
        project_manager=project_mgr,
    )
    tool_executor = ToolExecutor(registry=tool_registry)

    # Initialize Git and Safety Subsystems (Phase 8)
    git_mgr = GitManager(workspace_root=fs_mgr.workspace_root, settings=settings)
    safety_perm_mgr = SafetyPermissionManager(workspace_root=fs_mgr.workspace_root)
    protected_paths_mgr = ProtectedPathsManager(workspace_root=fs_mgr.workspace_root)
    safety_backup_mgr = SafetyBackupManager(
        workspace_root=fs_mgr.workspace_root,
        backup_storage_path=settings.backup_storage_path,
        protected_paths_mgr=protected_paths_mgr,
    )
    safety_audit_logger = SecurityAuditLogger(
        workspace_root=fs_mgr.workspace_root,
        audit_storage_path=settings.audit_storage_path,
        enabled=settings.audit_log_enabled,
    )

    # Initialize Multi-Agent System (Phase 9)
    agent_factory = AgentFactory(
        workspace_root=fs_mgr.workspace_root,
        settings=settings,
        llm_client=client,
    )
    workflow_engine = WorkflowEngine(
        workspace_root=fs_mgr.workspace_root,
        settings=settings,
        agent_factory=agent_factory,
    )

    # Check connection at startup and display banner if enabled
    is_online, _ = client.check_connection(timeout=1.5)
    if settings.show_startup_banner:
        display_startup_banner(
            console=console,
            settings=settings,
            active_model=active_model,
            is_online=is_online,
            workspace_root=str(fs_mgr.workspace_root),
        )
    elif not is_online:
        console.print(
            Panel(
                f"[bold red]Warning:[/bold red] Ollama server is unreachable at [bold]{settings.ollama_host}[/bold].\n"
                f"{settings.app_name} requires Ollama to be running to generate responses.\n"
                "Please start Ollama in another terminal using [bold green]ollama serve[/bold green].",
                title="[bold yellow]Ollama Offline[/bold yellow]",
                border_style="yellow",
            )
        )

    # First-time setup auto-detection
    if not is_online:
        try:
            from codeagent.installer.setup_state import SetupStateManager
            from codeagent.installer.setup_manager import SetupManager
            from rich.prompt import Confirm

            setup_state_mgr = SetupStateManager()
            if setup_state_mgr.is_setup_needed():
                console.print()
                console.print(
                    Panel(
                        "[bold cyan]First-Time Setup Detected[/bold cyan]\n"
                        f"Ollama server or configured model '{active_model}' is not currently ready.\n"
                        "Would you like to run the automated setup wizard now to configure Ollama?",
                        title="[bold green]SETUP[/bold green]",
                        border_style="cyan",
                    )
                )
                if Confirm.ask("Launch setup wizard?", default=True):
                    wiz = SetupManager(console=console, state_manager=setup_state_mgr)
                    wiz.run_setup(model_name=active_model)
                else:
                    setup_state_mgr.mark_skipped(model_name=active_model)
                    console.print("[dim]Setup skipped. Run 'codeagent setup' whenever you are ready.[/dim]\n")
        except Exception:
            pass

    # Interactive REPL loop
    while True:
        try:
            console.print()
            user_input = console.input(
                f"[bold cyan]{settings.app_name}[/bold cyan] [dim]({active_model})[/dim] [bold green]>[/bold green] "
            ).strip()
        except KeyboardInterrupt:
            console.print("\n[yellow]KeyboardInterrupt received. Type /exit or /quit to exit.[/yellow]")
            continue
        except EOFError:
            console.print("\n[dim]Goodbye![/dim]")
            break

        if not user_input:
            continue

        # Handle slash commands
        if user_input.startswith("/"):
            parts = user_input.split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else None

            if cmd in ("/exit", "/quit"):
                console.print(f"[bold cyan]Exiting {settings.app_name}. Happy coding![/bold cyan]")
                break
            elif cmd == "/help":
                show_help_menu()
                continue
            elif cmd == "/clear":
                os.system("cls" if os.name == "nt" else "clear")
                display_banner(settings, active_model, is_online, workspace_root=str(fs_mgr.workspace_root))
                continue
            # Multi-Agent Architecture and Workflow commands (Phase 9)
            elif cmd in ("/agents", "/agent"):
                handle_agents_command(agent_factory, arg)
                continue
            elif cmd in ("/code", "/coder"):
                handle_agents_command(agent_factory, "code")
                continue
            elif cmd in ("/workflow", "/wf"):
                handle_workflow_command(workflow_engine, arg)
                continue
            elif cmd in ("/task", "/tasks"):
                handle_task_command(workflow_engine, arg)
                continue
            # Git and Safety commands (Phase 8)
            elif cmd == "/git":
                handle_git_command(git_mgr, arg)
                continue
            elif cmd == "/safety":
                handle_safety_command(safety_perm_mgr, protected_paths_mgr, safety_audit_logger, arg)
                continue
            elif cmd == "/backup":
                handle_backup_command(safety_backup_mgr, arg)
                continue
            # Debugging commands (Phase 6)
            elif cmd == "/debug":
                handle_debug_command(debugger, arg)
                continue
            elif cmd == "/diagnose":
                handle_diagnose_command(debugger, arg)
                continue
            elif cmd == "/fix":
                handle_fix_command(debugger, arg)
                continue
            elif cmd == "/retest":
                handle_retest_command(debugger, arg)
                continue
            elif cmd == "/rollback":
                handle_debug_rollback_command(debugger, arg)
                continue
            elif cmd == "/debug-report":
                handle_debug_report_command()
                continue
            # Execution commands (Phase 5)
            elif cmd == "/python":
                handle_python_command(exec_mgr, arg)
                continue
            elif cmd == "/run":
                handle_run_command(exec_mgr, arg)
                continue
            elif cmd == "/install":
                handle_install_command(exec_mgr, arg)
                continue
            elif cmd == "/test":
                handle_test_command(exec_mgr, arg)
                continue
            elif cmd == "/processes":
                handle_processes_command(exec_mgr)
                continue
            elif cmd == "/cancel":
                handle_cancel_command(exec_mgr, arg)
                continue
            # Filesystem & Project Intelligence commands (Phase 3 & 7)
            elif cmd == "/workspace":
                handle_workspace_command(fs_mgr, arg)
                continue
            elif cmd in ("/scan", "/tree"):
                handle_scan_command(fs_mgr, arg)
                continue
            elif cmd in ("/project", "/analyze-project"):
                handle_project_command(project_mgr, fs_mgr, exec_mgr, arg)
                continue
            elif cmd == "/index":
                handle_index_command(project_mgr, arg)
                continue
            elif cmd == "/search":
                handle_search_command(project_mgr, arg)
                continue
            elif cmd == "/memory":
                handle_memory_command(project_mgr, arg)
                continue
            elif cmd == "/context":
                handle_context_command(context_mgr, conv_mgr, project_mgr, arg)
                continue
            elif cmd == "/read":
                handle_read_command(fs_mgr, arg)
                continue
            elif cmd == "/newfile":
                handle_newfile_command(fs_mgr, arg)
                continue
            elif cmd == "/delete":
                handle_delete_command(fs_mgr, arg)
                continue
            elif cmd == "/backups":
                handle_backups_command(fs_mgr)
                continue
            elif cmd == "/restore":
                handle_restore_command(fs_mgr, arg)
                continue
            # Production & Diagnostics commands (Phase 10)
            elif cmd == "/health":
                handle_health_cli(settings=settings)
                continue
            elif cmd in ("/diagnostics", "/diagnostic"):
                handle_diagnostics_cli(args=arg.split() if arg else [], settings=settings)
                continue
            elif cmd == "/monitor":
                handle_monitor_cli(settings=settings)
                continue
            elif cmd in ("/performance", "/profile"):
                handle_performance_cli(settings=settings)
                continue
            elif cmd == "/config":
                handle_config_cli(args=arg.split() if arg else [], settings=settings)
                continue
            elif cmd == "/setup":
                handle_setup_cli(args=arg.split() if arg else [], settings=settings)
                continue
            elif cmd in ("/models", "/model"):
                handle_models_cli(args=arg.split() if arg else [], settings=settings)
                continue
            # Session commands (Phase 1 & 2)
            elif cmd == "/new":
                conv_mgr.new_conversation()
                console.print("[bold green]Started a new conversation session.[/bold green]")
                continue
            elif cmd == "/history":
                handle_history_command(conv_mgr)
                continue
            elif cmd == "/save":
                handle_save_command(conv_mgr, arg)
                continue
            elif cmd == "/load":
                handle_load_command(conv_mgr, arg)
                continue
            elif cmd == "/model":
                active_model = handle_model_command(client, active_model, arg)
                continue
            elif cmd == "/analyze":
                if not arg:
                    console.print("[yellow]Usage: /analyze <error message or stack trace>[/yellow]")
                    continue
                try:
                    with console.status("[bold cyan]Analyzing error trace...[/bold cyan]", spinner="dots"):
                        engine = StructuredResponseEngine()
                        result = engine.generate_structured(
                            client=client._client,
                            prompt=arg,
                            schema_class=ErrorAnalysis,
                            model=active_model,
                        )
                    display_error_analysis(result)
                except Exception as exc:
                    console.print(f"[bold red]Analysis failed:[/bold red] {exc}")
                continue
            else:
                console.print(f"[yellow]Unknown command: {cmd}. Type /help for available commands.[/yellow]")
                continue

        # Append user message to conversation history
        conv_mgr.add_user_message(user_input)

        # Build project-aware context bundle
        project_context_bundle = project_mgr.build_active_context(user_query=user_input)

        # Check if user prompt is a file creation or coding task
        is_coding_request = any(
            kw in user_input.lower()
            for kw in ("create", "write", "build", "make", "generate", "code", "index.html", "website", "app", "file")
        )

        if is_coding_request:
            # Compact context to maximize prompt processing speed on local inference
            project_context_text = project_context_bundle.to_prompt_context(max_tokens=300)
            system_prompt = f"{SYSTEM_CODING_INSTRUCTIONS}\n\nWorkspace Context:\n{project_context_text}" if project_context_text else SYSTEM_CODING_INSTRUCTIONS
        else:
            project_context_text = project_context_bundle.to_prompt_context(max_tokens=2500)
            system_prompt = f"You are Coder with Code, an advanced autonomous AI coding assistant.\n\n{project_context_text}" if project_context_text else None

        # Enforce context window and token budget
        fitted_messages = context_mgr.fit_messages(conv_mgr.get_messages_for_llm(), system_prompt=system_prompt)

        # Check if math, filesystem, execution, debugging, or code intelligence tool-calling applies
        math_indicators = ["add", "plus", "+", "subtract", "minus", "-", "multiply", "*", "divide", "/", "calculate", "calc"]
        prompt_has_math = any(indicator in user_input.lower() for indicator in math_indicators) and any(char.isdigit() for char in user_input)
        fs_indicators = [
            "read", "create", "write", "edit", "modify", "delete", "remove",
            "list", "dir", "scan", "tree", "analyze", "file", "folder",
            "directory", "project", "codebase", "backup", "restore", "patch",
        ]
        prompt_has_fs = any(ind in user_input.lower() for ind in fs_indicators)
        exec_indicators = [
            "run", "exec", "execute", "python", "terminal", "pip", "install",
            "test", "tests", "pytest", "unittest", "process", "cancel", "kill", "cmd", "powershell",
        ]
        prompt_has_exec = any(ind in user_input.lower() for ind in exec_indicators)
        debug_indicators = [
            "debug", "debugger", "error", "traceback", "exception", "fix", "repair", "diagnose", "retest", "regression",
        ]
        prompt_has_debug = any(ind in user_input.lower() for ind in debug_indicators)
        intel_indicators = [
            "search", "symbol", "project", "architecture", "memory", "index", "function", "class", "dependency", "framework",
        ]
        prompt_has_intel = any(ind in user_input.lower() for ind in intel_indicators)
        should_use_tools = prompt_has_math or prompt_has_fs or prompt_has_exec or prompt_has_debug or prompt_has_intel

        # Select focused relevant tools based on matched indicators (prevents context overload)
        relevant_tools: list[str] = []
        if is_coding_request:
            relevant_tools.extend(["create_file", "read_file", "edit_file", "create_directory", "list_directory"])
        else:
            if prompt_has_math:
                relevant_tools.extend(["calculate", "evaluate_expression", "add", "subtract", "multiply", "divide"])
            if prompt_has_fs:
                relevant_tools.extend(["create_file", "read_file", "edit_file", "create_directory", "list_directory", "scan_project"])
            if prompt_has_exec:
                relevant_tools.extend(["execute_command", "run_python", "run_tests", "install_dependency"])
            if prompt_has_debug:
                relevant_tools.extend(["diagnose_error", "retest_code"])
            if prompt_has_intel:
                relevant_tools.extend(["search_code", "get_project_architecture", "get_project_memory"])

        focused_tools = list(dict.fromkeys(relevant_tools)) if relevant_tools else None

        try:
            if is_coding_request:
                # Fast responsive streaming for code generation with automatic file saving
                render_execution_status("Generating", f"Streaming code synthesis with {active_model}...", console)
                console.print()
                assistant_response = streaming_engine.stream_chat(
                    client=client._client,
                    messages=fitted_messages,
                    model=active_model,
                    temperature=settings.temperature,
                    max_output_tokens=settings.max_output_tokens,
                    display=True,
                )
                conv_mgr.add_assistant_message(assistant_response)
                console.print()
                saved_files = _extract_and_save_code_blocks(user_input, assistant_response, fs_mgr, console)
                if saved_files:
                    for sf in saved_files:
                        render_execution_status("File verified", f"Created and confirmed '{sf}' on disk", console)
            elif should_use_tools:
                # Run through tool executor loop with execution lifecycle status
                tool_timed_out = False
                final_text = None

                tool_client = OllamaSDKClient(
                    host=settings.ollama_host,
                    timeout=max(settings.tool_call_timeout, 300.0),
                )

                def _on_call(fname: str, fargs: dict):
                    pass

                def _status_callback(phase: str, details: str):
                    render_execution_status(phase, details, console)

                try:
                    final_text, updated_messages = tool_executor.run_tool_loop(
                        client=tool_client,
                        model=active_model,
                        messages=fitted_messages,
                        max_iterations=settings.max_tool_iterations,
                        temperature=settings.temperature,
                        on_tool_call=_on_call,
                        tool_names=focused_tools,
                        on_status=_status_callback,
                    )
                except (OllamaTimeoutError, httpx.TimeoutException, TimeoutError, socket.timeout):
                    tool_timed_out = True
                except KeyboardInterrupt:
                    render_execution_status("Execution failed", "Request cancelled by user.", console)
                    raise

                if tool_timed_out:
                    console.print(
                        f"\n[yellow]Notice: Tool call timed out waiting for {active_model}. Falling back to direct streaming generation...[/yellow]\n"
                    )
                    assistant_response = streaming_engine.stream_chat(
                        client=client._client,
                        messages=fitted_messages,
                        model=active_model,
                        temperature=settings.temperature,
                        max_output_tokens=settings.max_output_tokens,
                        display=True,
                    )
                    conv_mgr.add_assistant_message(assistant_response)
                    console.print()
                    saved = _extract_and_save_code_blocks(user_input, assistant_response, fs_mgr, console)
                    if saved:
                        for sf in saved:
                            render_execution_status("File verified", f"Generated and confirmed '{sf}' on disk", console)
                elif final_text is not None:
                    console.print()
                    console.print(Markdown(final_text))
                    conv_mgr.add_assistant_message(final_text)

                    # Post-execution filesystem validation: confirm requested file exists on disk
                    import re
                    requested_files = re.findall(r"\b([a-zA-Z0-9_\-\.\/\\]+\.(?:html|css|js|py|json|md|txt))\b", user_input, re.IGNORECASE)
                    for rf in dict.fromkeys(requested_files):
                        target_f = fs_mgr.workspace_root / rf
                        if target_f.exists() and target_f.stat().st_size > 0:
                            render_execution_status("File verified", f"Confirmed '{rf}' on disk ({target_f.stat().st_size} bytes at {target_f})", console)
                        else:
                            render_execution_status("Execution failed", f"Target file '{rf}' was not verified on disk.", console)
            else:
                # Normal conversation: use live streaming engine
                console.print()
                assistant_response = streaming_engine.stream_chat(
                    client=client._client,
                    messages=fitted_messages,
                    model=active_model,
                    temperature=settings.temperature,
                    max_output_tokens=settings.max_output_tokens,
                    display=True,
                )
                conv_mgr.add_assistant_message(assistant_response)
                console.print()
                _extract_and_save_code_blocks(user_input, assistant_response, fs_mgr, console)

        except KeyboardInterrupt:
            console.print("\n[yellow]Request cancelled by user.[/yellow]")
        except EditNotApprovedError as exc:
            console.print(f"[yellow]{exc}[/yellow]")
        except DeletionNotConfirmedError as exc:
            console.print(f"[yellow]{exc}[/yellow]")
        except ExecutionNotApprovedError as exc:
            console.print(f"[yellow]{exc}[/yellow]")
        except (CommandSecurityError, DisallowedExecutableError, DangerousCommandError, CommandInjectionError, ExecutionDisabledError) as exc:
            console.print(
                Panel(
                    f"[bold red]Execution Security Violation:[/bold red] {exc}",
                    title="[bold red]Blocked Operation[/bold red]",
                    border_style="red",
                )
            )
        except ProcessLimitExceededError as exc:
            console.print(f"[yellow]{exc}[/yellow]")
        except WorkspaceSecurityError as exc:
            console.print(
                Panel(
                    f"[bold red]Workspace Security Boundary Violated:[/bold red] {exc}",
                    title="[bold red]Access Blocked[/bold red]",
                    border_style="red",
                )
            )
        except SensitiveFileError as exc:
            console.print(
                Panel(
                    f"[bold red]Protected File Access Forbidden:[/bold red] {exc}",
                    title="[bold red]Security Guard[/bold red]",
                    border_style="red",
                )
            )
        except (FileTooLargeError, BinaryFileError, FileAlreadyExistsError, DirectoryDeletionBlockedError) as exc:
            console.print(f"[yellow]Filesystem Notice: {exc}[/yellow]")
        except (OllamaConnectionError, httpx.ConnectError, httpx.ConnectTimeout, ConnectionRefusedError) as exc:
            console.print(
                Panel(
                    f"[bold red]Connection Error:[/bold red] Cannot reach Ollama at {client.host}.\n"
                    f"[dim]{exc}\n"
                    f"Please verify that Ollama is running ('ollama serve') and accessible.[/dim]",
                    title="[bold red]Ollama Unavailable[/bold red]",
                    border_style="red",
                )
            )
        except ModelNotFoundError as exc:
            console.print(
                Panel(
                    f"[bold yellow]Model Not Found:[/bold yellow] {exc}",
                    title="[bold yellow]Model Missing[/bold yellow]",
                    border_style="yellow",
                )
            )
        except (OllamaTimeoutError, httpx.TimeoutException, TimeoutError, socket.timeout) as exc:
            console.print(
                Panel(
                    f"[bold red]Timeout Error:[/bold red] Request timed out while waiting for model '{active_model}'.\n\n"
                    f"[dim]Possible causes:\n"
                    f" • Ollama is still loading the {active_model} model into memory (cold start)\n"
                    f" • Your machine is under heavy CPU/GPU load\n"
                    f" • Large multi-file generation requires a higher timeout\n\n"
                    f"Tip: Increase REQUEST_TIMEOUT in your .env file (currently {settings.request_timeout:.0f}s) or run 'ollama run {active_model}' once to warm it up.[/dim]",
                    title="[bold red]Request Timed Out[/bold red]",
                    border_style="red",
                )
            )
        except MaxIterationsExceededError as exc:
            console.print(
                Panel(
                    f"[bold yellow]Tool Iteration Limit:[/bold yellow] {exc}",
                    title="[bold yellow]Loop Protected[/bold yellow]",
                    border_style="yellow",
                )
            )
        except OllamaClientError as exc:
            console.print(
                Panel(
                    f"[bold red]Error:[/bold red] {exc}",
                    title="[bold red]LLM Error[/bold red]",
                    border_style="red",
                )
            )
        except Exception as exc:
            console.print(
                Panel(
                    f"[bold red]Unexpected Error:[/bold red] {exc}",
                    title="[bold red]System Error[/bold red]",
                    border_style="red",
                )
            )


def one_shot_mode(
    client: LLMClient,
    prompt: str,
    model_name: str,
    stream: bool = True,
    settings: Optional[Settings] = None,
    show_banner: bool = False,
) -> None:
    """Execute a single prompt and display response."""
    clean_prompt = prompt.strip() if prompt else ""
    if not clean_prompt:
        console.print("[bold red]Error:[/bold red] Prompt cannot be empty.", style="red")
        raise typer.Exit(code=1)

    cfg = settings or get_settings()

    if show_banner:
        display_startup_banner(
            console=console,
            settings=cfg,
            active_model=model_name,
            workspace_root=str(cfg.workspace_root or Path.cwd().resolve()),
            client=client,
            force=True,
        )

    try:
        math_indicators = ["add", "plus", "+", "subtract", "minus", "-", "multiply", "*", "divide", "/", "calculate", "calc"]
        prompt_has_math = any(indicator in clean_prompt.lower() for indicator in math_indicators) and any(char.isdigit() for char in clean_prompt)
        fs_indicators = [
            "read", "create", "write", "edit", "modify", "delete", "remove",
            "list", "dir", "scan", "tree", "analyze", "file", "folder",
            "directory", "project", "codebase", "backup", "restore", "patch",
        ]
        prompt_has_fs = any(ind in clean_prompt.lower() for ind in fs_indicators)
        exec_indicators = [
            "run", "exec", "execute", "python", "terminal", "pip", "install",
            "test", "tests", "pytest", "unittest", "process", "cancel", "kill", "cmd", "powershell",
        ]
        prompt_has_exec = any(ind in clean_prompt.lower() for ind in exec_indicators)
        debug_indicators = [
            "debug", "debugger", "error", "traceback", "exception", "fix", "repair", "diagnose", "retest", "regression",
        ]
        prompt_has_debug = any(ind in clean_prompt.lower() for ind in debug_indicators)
        intel_indicators = [
            "search", "symbol", "project", "architecture", "memory", "index", "function", "class", "dependency", "framework",
        ]
        prompt_has_intel = any(ind in clean_prompt.lower() for ind in intel_indicators)
        should_use_tools = prompt_has_math or prompt_has_fs or prompt_has_exec or prompt_has_debug or prompt_has_intel

        # Check if one-shot prompt is a coding/file creation task
        is_coding_request = any(
            kw in clean_prompt.lower()
            for kw in ("create", "write", "build", "make", "generate", "code", "index.html", "website", "app", "file")
        )

        # Select focused relevant tools
        relevant_tools_one_shot: list[str] = []
        if is_coding_request:
            relevant_tools_one_shot.extend(["create_file", "read_file", "edit_file", "create_directory", "list_directory"])
        else:
            if prompt_has_math:
                relevant_tools_one_shot.extend(["calculate", "evaluate_expression", "add", "subtract", "multiply", "divide"])
            if prompt_has_fs:
                relevant_tools_one_shot.extend(["create_file", "read_file", "edit_file", "create_directory", "list_directory", "scan_project"])
            if prompt_has_exec:
                relevant_tools_one_shot.extend(["execute_command", "run_python", "run_tests", "install_dependency"])
            if prompt_has_debug:
                relevant_tools_one_shot.extend(["diagnose_error", "retest_code"])
            if prompt_has_intel:
                relevant_tools_one_shot.extend(["search_code", "get_project_architecture", "get_project_memory"])

        focused_tools_one_shot = list(dict.fromkeys(relevant_tools_one_shot)) if relevant_tools_one_shot else None

        if is_coding_request:
            render_execution_status("Generating", f"Streaming code synthesis with {model_name}...", console)
            console.print()
            fs_mgr = FilesystemManager(
                settings=cfg,
                write_approval_callback=cli_write_approval,
                delete_confirmation_callback=cli_delete_confirmation,
            )
            streaming_engine = StreamingEngine(console=console)
            sys_prompt = SYSTEM_CODING_INSTRUCTIONS
            messages = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": clean_prompt},
            ]
            assistant_response = streaming_engine.stream_chat(
                client=client._client,
                messages=messages,
                model=model_name,
                temperature=cfg.temperature,
                max_output_tokens=cfg.max_output_tokens,
                display=True,
            )
            console.print()
            saved_files = _extract_and_save_code_blocks(clean_prompt, assistant_response, fs_mgr, console)
            if saved_files:
                for sf in saved_files:
                    render_execution_status("File verified", f"Created and confirmed '{sf}' on disk", console)
        elif should_use_tools:
            fs_mgr = FilesystemManager(
                settings=cfg,
                write_approval_callback=cli_write_approval,
                delete_confirmation_callback=cli_delete_confirmation,
            )
            exec_mgr = ExecutionManager(
                settings=cfg,
                workspace_root=fs_mgr.workspace_root,
                approval_callback=cli_execution_approval,
            )
            project_mgr = ProjectManager(settings=cfg)
            tool_registry = get_default_registry(
                filesystem_manager=fs_mgr,
                execution_manager=exec_mgr,
                project_manager=project_mgr,
            )
            tool_executor = ToolExecutor(registry=tool_registry)

            sys_prompt = SYSTEM_CODING_INSTRUCTIONS if is_coding_request else "You are Coder with Code, an advanced autonomous AI coding assistant."
            messages = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": clean_prompt},
            ]
            tool_timed_out = False
            response = None
            tool_client = OllamaSDKClient(
                host=cfg.ollama_host,
                timeout=max(cfg.tool_call_timeout, 300.0),
            )

            def _status_callback(phase: str, details: str):
                render_execution_status(phase, details, console)

            try:
                response, _ = tool_executor.run_tool_loop(
                    client=tool_client,
                    model=model_name,
                    messages=messages,
                    max_iterations=cfg.max_tool_iterations,
                    temperature=cfg.temperature,
                    tool_names=focused_tools_one_shot,
                    on_status=_status_callback,
                )
            except (OllamaTimeoutError, httpx.TimeoutException, TimeoutError, socket.timeout):
                tool_timed_out = True
            except KeyboardInterrupt:
                render_execution_status("Execution failed", "Request cancelled by user.", console)
                raise

            if tool_timed_out:
                console.print(
                    f"\n[yellow]Notice: Tool call timed out waiting for {model_name}. Falling back to direct streaming generation...[/yellow]\n"
                )
                assistant_response = streaming_engine.stream_chat(
                    client=client._client,
                    messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": clean_prompt}],
                    model=model_name,
                    temperature=cfg.temperature,
                    max_output_tokens=cfg.max_output_tokens,
                    display=True,
                )
                console.print()
                saved = _extract_and_save_code_blocks(clean_prompt, assistant_response, fs_mgr, console)
                if saved:
                    for sf in saved:
                        render_execution_status("File verified", f"Generated and confirmed '{sf}' on disk", console)
            elif response is not None:
                console.print()
                console.print(Markdown(response))
                console.print()

                # Post-execution filesystem validation
                import re
                requested_files = re.findall(r"\b([a-zA-Z0-9_\-\.\/\\]+\.(?:html|css|js|py|json|md|txt))\b", clean_prompt, re.IGNORECASE)
                for rf in dict.fromkeys(requested_files):
                    target_f = fs_mgr.workspace_root / rf
                    if target_f.exists() and target_f.stat().st_size > 0:
                        render_execution_status("File verified", f"Confirmed '{rf}' on disk ({target_f.stat().st_size} bytes at {target_f})", console)
                    else:
                        render_execution_status("Execution failed", f"Target file '{rf}' was not verified on disk.", console)
        elif stream:
            console.print()
            streaming_engine = StreamingEngine(console=console)
            messages = [{"role": "user", "content": clean_prompt}]
            assistant_response = streaming_engine.stream_chat(
                client=client._client,
                messages=messages,
                model=model_name,
                temperature=cfg.temperature,
                max_output_tokens=cfg.max_output_tokens,
                display=True,
            )
            console.print()
            fs_mgr = FilesystemManager(settings=cfg)
            _extract_and_save_code_blocks(clean_prompt, assistant_response, fs_mgr, console)
            console.print()
        else:
            with console.status(
                f"[bold cyan]Thinking with {model_name}...[/bold cyan]",
                spinner="dots",
            ):
                response = client.generate(
                    prompt=clean_prompt,
                    model=model_name,
                )
            console.print()
            console.print(Markdown(response))
            console.print()

    except KeyboardInterrupt:
        console.print("\n[yellow]Request cancelled by user.[/yellow]")
        raise typer.Exit(code=130)
    except ExecutionNotApprovedError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(code=1)
    except (CommandSecurityError, DisallowedExecutableError, DangerousCommandError, CommandInjectionError, ExecutionDisabledError) as exc:
        console.print(
            Panel(
                f"[bold red]Execution Security Violation:[/bold red] {exc}",
                title="[bold red]Blocked Operation[/bold red]",
                border_style="red",
            )
        )
        raise typer.Exit(code=1)
    except ProcessLimitExceededError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(code=1)
    except EditNotApprovedError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
    except DeletionNotConfirmedError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
    except WorkspaceSecurityError as exc:
        console.print(
            Panel(
                f"[bold red]Workspace Security Boundary Violated:[/bold red] {exc}",
                title="[bold red]Access Blocked[/bold red]",
                border_style="red",
            )
        )
        raise typer.Exit(code=1)
    except SensitiveFileError as exc:
        console.print(
            Panel(
                f"[bold red]Protected File Access Forbidden:[/bold red] {exc}",
                title="[bold red]Security Guard[/bold red]",
                border_style="red",
            )
        )
        raise typer.Exit(code=1)
    except (OllamaConnectionError, httpx.ConnectError, httpx.ConnectTimeout, ConnectionRefusedError) as exc:
        console.print(
            Panel(
                f"[bold red]Connection Error:[/bold red] Cannot reach Ollama at {client.host}.\n"
                f"[dim]{exc}\n"
                f"Please verify that Ollama is running ('ollama serve') and accessible.[/dim]",
                title="[bold red]Ollama Unavailable[/bold red]",
                border_style="red",
            )
        )
        raise typer.Exit(code=1)
    except ModelNotFoundError as exc:
        console.print(
            Panel(
                f"[bold yellow]Model Not Found:[/bold yellow] {exc}",
                title="[bold yellow]Model Missing[/bold yellow]",
                border_style="yellow",
            )
        )
        raise typer.Exit(code=1)
    except (OllamaTimeoutError, httpx.TimeoutException, TimeoutError, socket.timeout) as exc:
        console.print(
            Panel(
                f"[bold red]Timeout Error:[/bold red] Request timed out while waiting for model '{model_name}'.\n\n"
                f"[dim]Possible causes:\n"
                f" • Ollama is still loading the {model_name} model into memory (cold start)\n"
                f" • Your machine is under heavy CPU/GPU load\n"
                f" • Large multi-file generation requires a higher timeout\n\n"
                f"Tip: Increase REQUEST_TIMEOUT in your .env file or run 'ollama run {model_name}' once to warm it up.[/dim]",
                title="[bold red]Request Timed Out[/bold red]",
                border_style="red",
            )
        )
        raise typer.Exit(code=1)
    except MaxIterationsExceededError as exc:
        console.print(
            Panel(
                f"[bold yellow]Tool Iteration Limit:[/bold yellow] {exc}",
                title="[bold yellow]Loop Protected[/bold yellow]",
                border_style="yellow",
            )
        )
        raise typer.Exit(code=1)
    except OllamaClientError as exc:
        console.print(
            Panel(
                f"[bold red]Error:[/bold red] {exc}",
                title="[bold red]LLM Error[/bold red]",
                border_style="red",
            )
        )
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(
            Panel(
                f"[bold red]Unexpected Error:[/bold red] {exc}",
                title="[bold red]System Error[/bold red]",
                border_style="red",
            )
        )
        raise typer.Exit(code=1)


def version_callback(value: bool) -> None:
    """Print version information and exit quickly without initializing LLM."""
    if value:
        from codeagent.__version__ import __app_name__, __tagline__, __version__
        import platform
        py_ver = sys.version.split()[0]
        console.print(
            f"[bold cyan]{__app_name__}[/bold cyan] version [bold green]{__version__}[/bold green] (Python {py_ver} on {platform.system()})\n"
            f"[dim]{__tagline__}[/dim]"
        )
        raise typer.Exit(code=0)


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def cli(
    ctx: typer.Context,
    prompt: Optional[str] = typer.Argument(
        None,
        help="Optional prompt for one-shot execution, or subcommand (git, safety, backup, agents, workflow, task, health, diagnostics, monitor, performance, config), or 'check' to run diagnostics. If omitted, starts interactive mode.",
    ),
    args: Optional[list[str]] = typer.Argument(
        None,
        help="Optional arguments for subcommands.",
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        "-m",
        help="Ollama model to use (overrides MODEL_NAME in settings / .env).",
    ),
    analyze_error: Optional[str] = typer.Option(
        None,
        "--analyze-error",
        "-a",
        help="Perform structured JSON error analysis on the provided error stack trace.",
    ),
    stream: bool = typer.Option(
        True,
        "--stream/--no-stream",
        help="Enable or disable real-time token streaming.",
    ),
    banner: bool = typer.Option(
        False,
        "--banner",
        help="Display startup banner in one-shot execution.",
    ),
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        help="Show application version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """Coder with Code: Local Autonomous AI Coding Assistant powered by Ollama and Qwen3."""
    from codeagent.core.logger import CodeAgentLogger
    settings = get_settings()
    CodeAgentLogger.setup_logging(settings=settings)
    target_model = model or settings.model_name

    # Lazy LLMClient loader: do not initialize Ollama or network until needed
    _client: Optional[LLMClient] = None

    def get_client() -> LLMClient:
        nonlocal _client
        if _client is None:
            _client = LLMClient(settings=settings, model_name=target_model)
        return _client

    # Route 1: Structured Error Analysis Mode
    if analyze_error:
        try:
            with console.status("[bold cyan]Analyzing error trace...[/bold cyan]", spinner="dots"):
                engine = StructuredResponseEngine()
                analysis = engine.generate_structured(
                    client=get_client()._client,
                    prompt=analyze_error,
                    schema_class=ErrorAnalysis,
                    model=target_model,
                )
            display_error_analysis(analysis)
            return
        except StructuredValidationError as exc:
            console.print(f"[bold red]Validation Error:[/bold red] {exc}")
            raise typer.Exit(code=1)
        except Exception as exc:
            console.print(f"[bold red]Error Analysis Failed:[/bold red] {exc}")
            raise typer.Exit(code=1)

    # Route 2: Subcommands (Phase 8, 9, 10)
    if prompt:
        p_lower = prompt.strip().lower()
        sub_args = (args or []) + (list(ctx.args) if ctx and hasattr(ctx, "args") else [])

        # Phase 10 Production Commands (fast, non-LLM)
        if p_lower in ("version", "--version", "-v"):
            version_callback(True)
            return
        elif p_lower == "health":
            handle_health_cli(settings=settings)
            return
        elif p_lower in ("diagnostics", "diagnostic"):
            handle_diagnostics_cli(args=sub_args, settings=settings)
            return
        elif p_lower == "monitor":
            handle_monitor_cli(settings=settings)
            return
        elif p_lower in ("performance", "profile"):
            handle_performance_cli(settings=settings)
            return
        elif p_lower in ("config", "configuration"):
            handle_config_cli(args=sub_args, settings=settings)
            return
        elif p_lower == "setup":
            handle_setup_cli(args=sub_args, settings=settings)
            return
        elif p_lower in ("models", "model"):
            handle_models_cli(args=sub_args, settings=settings)
            return

        # Phase 9 Multi-Agent Commands
        elif p_lower in ("agents", "agent"):
            af = AgentFactory(settings=settings, llm_client=get_client())
            handle_agents_cli(sub_args, af)
            return
        elif p_lower in ("workflow", "wf"):
            we = WorkflowEngine(settings=settings)
            handle_workflow_cli(sub_args, we)
            return
        elif p_lower in ("task", "tasks"):
            we = WorkflowEngine(settings=settings)
            handle_task_cli(sub_args, we)
            return

        # Phase 8 Git & Safety Commands
        elif p_lower == "git":
            gm = GitManager(settings=settings)
            handle_git_cli(sub_args, gm)
            return
        elif p_lower == "safety":
            spm = SafetyPermissionManager()
            ppm = ProtectedPathsManager()
            sal = SecurityAuditLogger(audit_storage_path=settings.audit_storage_path, enabled=settings.audit_log_enabled)
            handle_safety_cli(sub_args, spm, ppm, sal)
            return
        elif p_lower == "backup":
            sbm = SafetyBackupManager(backup_storage_path=settings.backup_storage_path)
            handle_backup_cli(sub_args, sbm)
            return
        elif p_lower == "check":
            run_connection_check(client=get_client(), selected_model=target_model, settings=settings)
            return
        else:
            full_prompt = prompt if not sub_args else f"{prompt} {' '.join(sub_args)}"
            one_shot_mode(client=get_client(), prompt=full_prompt, model_name=target_model, stream=stream, settings=settings, show_banner=banner)
            return

    # Route 3: Interactive REPL Mode
    interactive_mode(client=get_client(), model_name=target_model, settings=settings)


if __name__ == "__main__":
    app()
