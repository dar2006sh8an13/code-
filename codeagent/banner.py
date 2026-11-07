"""Professional ASCII-art startup banner for Code AG CLI.

Renders an ASCII logo, tagline, dynamic configuration metadata,
connection status warnings, and readiness prompt with Windows CMD ASCII compatibility
and responsive narrow-terminal handling.
"""

from pathlib import Path
from typing import Any, Optional
from rich.box import ROUNDED, ASCII
from rich.console import Console, RenderableType
from rich.panel import Panel
from rich.text import Text

from codeagent.config.settings import Settings, get_settings


# ASCII art logo for Coder with Code (wide, width: 74)
CODER_WITH_CODE_ASCII_LOGO = r"""  ____          _                   _ _   _         ____          _      
 / ___|___   __| | ___ _ __  \  /\  /(_) |_| |__   / ___|___   __| | ___ 
| |   / _ \ / _` |/ _ \ '__|  \/  \/  | | __| '_ \ | |   / _ \ / _` |/ _ \
| |__| (_) | (_| |  __/ |     \ V /   | | |_| | | || |__| (_) | (_| |  __/
 \____\___/ \__,_|\___|_|      \_/    |_|\__|_| |_| \____\___/ \__,_|\___|"""

# ASCII art logo for Coder (compact, width: 29)
CODER_COMPACT_ASCII_LOGO = r"""  ____          _            
 / ___|___   __| | ___ _ __  
| |   / _ \ / _` |/ _ \ '__| 
| |__| (_) | (_| |  __/ |    
 \____\___/ \__,_|\___|_|    
        with Code"""

# Exact ASCII art logo for Code AG (width: 39 characters)
CODEAGENT_ASCII_LOGO = r"""  ____          _            _    ____ 
 / ___|___   __| | ___      / \  / ___|
| |   / _ \ / _` |/ _ \    / _ \| |  _ 
| |__| (_) | (_| |  __/   / ___ \ |_| |
 \____\___/ \__,_|\___|  /_/   \_\____|"""

# ASCII art logo for Code
CODE_ASCII_LOGO = r"""  ____          _      
 / ___|___   __| | ___ 
| |   / _ \ / _` |/ _ \
| |__| (_) | (_| |  __/
 \____\___/ \__,_|\___|"""

TAGLINE = "Built in India. Designed for developers everywhere."
PROMPT_MESSAGE = "Ready. What would you like to build?"
NARROW_TERMINAL_THRESHOLD = 45


def build_banner_renderable(
    settings: Optional[Settings] = None,
    active_model: Optional[str] = None,
    is_online: bool = True,
    workspace_root: Optional[str] = None,
    provider_name: str = "Ollama (Local)",
    terminal_width: int = 80,
) -> Panel:
    """Build a Rich Panel renderable containing the Code AG startup banner.

    Args:
        settings: Application settings instance (defaults to get_settings()).
        active_model: Name of the currently configured model.
        is_online: Whether the LLM provider backend is reachable.
        workspace_root: Active workspace root path.
        provider_name: Display name of the active provider backend.
        terminal_width: Width of the target terminal in characters.

    Returns:
        Rich Panel containing formatted ASCII art, tagline, metadata, and status.
    """
    cfg = settings or get_settings()
    model = active_model or cfg.model_name
    ws_path = workspace_root or str(cfg.workspace_root or Path.cwd().resolve())
    version = cfg.app_version

    # Format status text
    if is_online:
        status_line = "[bold green]Connected (Online)[/bold green]"
    else:
        status_line = "[bold red]Offline (Ollama unavailable)[/bold red]"

    # Handle narrow terminals gracefully without wrapping the ASCII logo
    app_lower = (cfg.app_name or "").strip().lower()
    if app_lower in ("coder with code", "coder"):
        logo_to_use = CODER_WITH_CODE_ASCII_LOGO if terminal_width >= 75 else CODER_COMPACT_ASCII_LOGO
    elif app_lower in ("code",):
        logo_to_use = CODE_ASCII_LOGO
    else:
        logo_to_use = CODEAGENT_ASCII_LOGO

    if terminal_width < NARROW_TERMINAL_THRESHOLD:
        header_text = (
            f"[bold cyan]{cfg.app_name}[/bold cyan] [dim]v{version}[/dim]\n"
            f"[italic white]{TAGLINE}[/italic white]\n"
        )
    else:
        header_text = (
            f"[bold cyan]{logo_to_use}[/bold cyan]\n\n"
            f"[bold white]{TAGLINE}[/bold white]\n"
        )

    # Dynamic application metadata
    metadata_lines = [
        header_text,
        f"[dim]{'-' * max(terminal_width - 8, 20)}[/dim]",
        f" [bold white]Application:[/bold white]  [cyan]{cfg.app_name}[/cyan] [dim]v{version}[/dim]",
        f" [bold white]Model:[/bold white]        [bold yellow]{model}[/bold yellow]",
        f" [bold white]Provider:[/bold white]     [green]{provider_name}[/green] [dim]({cfg.ollama_host})[/dim]",
        f" [bold white]Workspace:[/bold white]    [yellow]{ws_path}[/yellow]",
        f" [bold white]Status:[/bold white]       {status_line}",
    ]

    # Offline warning if provider is unreachable
    if not is_online:
        metadata_lines.append("")
        metadata_lines.append(
            f" [bold red][!] Warning:[/bold red] Ollama server is unreachable at [bold]{cfg.ollama_host}[/bold].\n"
            f"     {cfg.app_name} requires Ollama to generate responses.\n"
            "     Please start Ollama in another terminal using [bold green]ollama serve[/bold green]."
        )

    # Readiness prompt
    metadata_lines.append("")
    metadata_lines.append(f"[bold bright_green]{PROMPT_MESSAGE}[/bold bright_green]")

    content = "\n".join(metadata_lines)

    return Panel(
        content,
        title=f"[bold cyan]{cfg.app_name}[/bold cyan]",
        subtitle="[dim]Type /help for commands[/dim]",
        border_style="cyan" if is_online else "yellow",
        box=ROUNDED,
        padding=(1, 1) if terminal_width < 85 else (1, 2),
        expand=True,
    )


def display_startup_banner(
    console: Optional[Console] = None,
    settings: Optional[Settings] = None,
    active_model: Optional[str] = None,
    is_online: Optional[bool] = None,
    workspace_root: Optional[str] = None,
    client: Optional[Any] = None,
    force: bool = False,
) -> None:
    """Display the Code AG professional startup banner if enabled.

    Does not load or initialize the LLM. Only performs a lightweight
    connection probe if is_online is not explicitly provided and a client is supplied.

    Args:
        console: Rich Console to print to (defaults to Console()).
        settings: Application settings.
        active_model: Name of the configured model.
        is_online: Pre-determined connection state.
        workspace_root: Active workspace root directory string.
        client: Optional LLMClient to probe connection if is_online is None.
        force: If True, renders banner even when SHOW_STARTUP_BANNER is false.
    """
    cfg = settings or get_settings()
    con = console or Console()

    # Respect user configuration unless explicitly forced
    if not cfg.show_startup_banner and not force:
        return

    # Determine online status without heavy LLM initialization
    if is_online is None:
        if client is not None and hasattr(client, "check_connection"):
            try:
                online, _ = client.check_connection(timeout=1.5)
                is_online = bool(online)
            except Exception:
                is_online = False
        else:
            is_online = False

    term_width = con.width if con.width else 80

    panel = build_banner_renderable(
        settings=cfg,
        active_model=active_model,
        is_online=is_online,
        workspace_root=workspace_root,
        terminal_width=term_width,
    )

    con.print()
    con.print(panel)
    con.print()

