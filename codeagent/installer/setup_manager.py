"""Interactive first-time setup manager and wizard orchestrating CodeAgent installation."""

import platform
import sys
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from codeagent.__version__ import __app_name__, __version__
from codeagent.installer.download_manager import DownloadManager
from codeagent.installer.installation_validator import InstallationValidator, ValidationReport
from codeagent.installer.model_manager import ModelManager
from codeagent.installer.ollama_detector import OllamaDetector, OllamaStatus
from codeagent.installer.ollama_installer import OllamaInstaller
from codeagent.installer.setup_state import SetupStateManager
from codeagent.installer.system_checker import SystemChecker


class SetupManager:
    """Orchestrates the 6-stage setup pipeline with Rich terminal feedback."""

    def __init__(
        self,
        console: Optional[Console] = None,
        state_manager: Optional[SetupStateManager] = None,
        system_checker: Optional[SystemChecker] = None,
        ollama_detector: Optional[OllamaDetector] = None,
        ollama_installer: Optional[OllamaInstaller] = None,
        model_manager: Optional[ModelManager] = None,
        validator: Optional[InstallationValidator] = None,
    ) -> None:
        self.console = console or Console()
        self.state_mgr = state_manager or SetupStateManager()
        self.system_checker = system_checker or SystemChecker()
        self.detector = ollama_detector or OllamaDetector()
        self.downloader = DownloadManager()
        self.installer = ollama_installer or OllamaInstaller(
            download_manager=self.downloader, detector=self.detector
        )
        self.model_mgr = model_manager or ModelManager()
        self.validator = validator or InstallationValidator(
            detector=self.detector, model_manager=self.model_mgr
        )

    def print_banner(self) -> None:
        """Render setup header."""
        self.console.print()
        self.console.print(
            Panel(
                f"[bold cyan]{__app_name__} First-Time Setup Wizard[/bold cyan]\n"
                f"[dim]Version {__version__} • Python {sys.version.split()[0]} on {platform.system()}[/dim]\n"
                "Configuring local inference runtime and AI model...",
                title="[bold green]SETUP[/bold green]",
                border_style="cyan",
            )
        )
        self.console.print()

    def run_setup(
        self,
        check_only: bool = False,
        skip_model: bool = False,
        model_name: str = "qwen3:latest",
        repair: bool = False,
        non_interactive: bool = False,
        auto_confirm: bool = False,
    ) -> bool:
        """Execute the 6-stage setup pipeline.

        Args:
            check_only: Read-only diagnostic check without making changes.
            skip_model: Skip model download phase.
            model_name: Target model identifier.
            repair: Force reset of setup state and re-verify everything.
            non_interactive: Assume yes or fail if user interaction required.
            auto_confirm: Auto-accept confirmation prompts.

        Returns:
            bool: True if system is verified and ready.
        """
        if repair:
            self.state_mgr.reset()

        if not check_only:
            self.print_banner()

        # -------------------------------------------------------------
        # [1/6] Checking Python Runtime
        # -------------------------------------------------------------
        self.console.print("[bold cyan][1/6][/bold cyan] Checking Python runtime...")
        py_ver, py_compat = self.system_checker.check_python_version()
        if not py_compat:
            self.console.print(
                f"[bold red][FAIL][/bold red] Python {py_ver} is unsupported. CodeAgent requires Python 3.12 or newer."
            )
            return False
        self.console.print(f"[bold green][OK][/bold green] Python {py_ver} verified.")

        # -------------------------------------------------------------
        # [2/6] Detecting Ollama
        # -------------------------------------------------------------
        self.console.print("[bold cyan][2/6][/bold cyan] Detecting Ollama installation...")
        ollama_res = self.detector.detect()
        if ollama_res.status == OllamaStatus.RUNNING:
            self.console.print(
                f"[bold green][OK][/bold green] Ollama is installed and running (version: {ollama_res.version or 'unknown'})."
            )
        elif ollama_res.status == OllamaStatus.INSTALLED_STOPPED:
            self.console.print(
                f"[bold yellow][NOTE][/bold yellow] Ollama is installed at '{ollama_res.executable_path}', but the background daemon is stopped."
            )
        else:
            self.console.print("[bold yellow][NOTE][/bold yellow] Ollama executable was not found on your system.")

        # -------------------------------------------------------------
        # [3/6] Checking System Requirements (RAM, Disk, GPU)
        # -------------------------------------------------------------
        self.console.print("[bold cyan][3/6][/bold cyan] Checking hardware and storage capacity...")
        sys_report = self.system_checker.run_full_check()

        table = Table(box=None, padding=(0, 2))
        table.add_column("Component", style="bold white", width=18)
        table.add_column("Detected Specification", style="cyan")

        table.add_row("Operating System", f"{sys_report.os_name} {sys_report.os_release} ({sys_report.architecture})")
        table.add_row("Total System RAM", f"{sys_report.total_ram_gb:.1f} GB ({sys_report.available_ram_gb:.1f} GB available)")
        table.add_row("Free Disk Space", f"{sys_report.free_disk_gb:.1f} GB free on {sys_report.disk_path}")
        if sys_report.gpu_name:
            vram = f" ({sys_report.gpu_vram_gb} GB VRAM)" if sys_report.gpu_vram_gb else ""
            table.add_row("GPU Acceleration", f"{sys_report.gpu_name}{vram}")
        else:
            table.add_row("Inference Mode", "CPU Optimized (System RAM)")

        self.console.print(table)

        for warn in sys_report.warnings:
            self.console.print(f"[bold yellow]Warning:[/bold yellow] {warn}")
        for adv in sys_report.advisories:
            self.console.print(f"[dim]• {adv}[/dim]")

        # In check-only mode, display results and return
        if check_only:
            val_report = self.validator.run_all_validations(model_name=model_name, check_model=not skip_model)
            self._display_validation_report(val_report)
            return val_report.all_passed

        # -------------------------------------------------------------
        # [4/6] Installing / Starting Ollama
        # -------------------------------------------------------------
        self.console.print("[bold cyan][4/6][/bold cyan] Ensuring Ollama runtime is active...")
        if ollama_res.status == OllamaStatus.NOT_INSTALLED:
            if platform.system() == "Windows":
                self.console.print(
                    "\n[bold white]Ollama is required for local AI inference.[/bold white]\n"
                    "CodeAgent can download and launch the official installer (OllamaSetup.exe).\n"
                    "Source: https://ollama.com/download/OllamaSetup.exe (Per-user, standard privileges)\n"
                )
                if not auto_confirm and not non_interactive:
                    confirmed = Confirm.ask("Install Ollama now?", default=True)
                    if not confirmed:
                        self.console.print("[yellow]Ollama installation skipped by user.[/yellow]")
                        self.state_mgr.mark_skipped(model_name=model_name)
                        return False
                elif not auto_confirm and non_interactive:
                    self.console.print("[red]Non-interactive mode: Ollama missing and auto-confirm disabled.[/red]")
                    return False

                ok, msg = self.installer.install_windows(silent=True)
                if not ok:
                    self.console.print(f"[bold red]Installation Failed:[/bold red] {msg}")
                    return False
                self.console.print(f"[bold green][OK][/bold green] {msg}")

            elif platform.system() == "Darwin":
                self.console.print(Panel(self.installer.get_macos_instructions(), title="macOS Installation Required"))
                return False
            else:
                self.console.print(Panel(self.installer.get_linux_instructions(), title="Linux Installation Required"))
                return False

        elif ollama_res.status == OllamaStatus.INSTALLED_STOPPED:
            self.console.print("[cyan]Attempting to start Ollama background service ('ollama serve')...[/cyan]")
            started, msg = self.installer.start_service(executable_path=ollama_res.executable_path)
            if started:
                self.console.print(f"[bold green][OK][/bold green] {msg}")
            else:
                self.console.print(f"[bold yellow][NOTE][/bold yellow] {msg}")
                self.console.print("Please start Ollama manually by opening the Ollama application or running 'ollama serve'.")
                return False

        # -------------------------------------------------------------
        # [5/6] Downloading Model if Required
        # -------------------------------------------------------------
        self.console.print(f"[bold cyan][5/6][/bold cyan] Verifying model '{model_name}'...")
        if skip_model:
            self.console.print("[yellow]Model download skipped via --skip-model flag.[/yellow]")
        else:
            if self.model_mgr.is_model_installed(model_name):
                self.console.print(f"[bold green][OK][/bold green] Model '{model_name}' is already installed.")
            else:
                self.console.print(
                    f"\n[bold white]Model '{model_name}' (~5.2 GB) is missing from local storage.[/bold white]\n"
                    "CodeAgent will download it directly through Ollama's official pull API.\n"
                    "Downloads are cached in your local Ollama storage and support resume.\n"
                )
                if not auto_confirm and not non_interactive:
                    confirmed = Confirm.ask(f"Download model '{model_name}' now?", default=True)
                    if not confirmed:
                        self.console.print("[yellow]Model download skipped by user.[/yellow]")
                        self.state_mgr.mark_skipped(model_name=model_name)
                        return False
                elif not auto_confirm and non_interactive:
                    self.console.print("[red]Non-interactive mode: Model missing and auto-confirm disabled.[/red]")
                    return False

                ok, msg = self.model_mgr.pull_model(model_name=model_name, show_progress=True)
                if not ok:
                    self.console.print(f"[bold red]Model Download Failed:[/bold red] {msg}")
                    return False
                self.console.print(f"[bold green][OK][/bold green] {msg}")

        # -------------------------------------------------------------
        # [6/6] Final End-to-End Verification
        # -------------------------------------------------------------
        self.console.print("[bold cyan][6/6][/bold cyan] Running final system verification...")
        val_report = self.validator.run_all_validations(model_name=model_name, check_model=not skip_model)
        self._display_validation_report(val_report)

        if val_report.all_passed:
            ollama_ver = self.detector.detect().version
            self.state_mgr.mark_completed(
                ollama_version=ollama_ver,
                model_name=model_name,
                model_installed=not skip_model,
            )
            self.console.print(
                Panel(
                    f"[bold green]Setup Completed Successfully![/bold green]\n"
                    f"CodeAgent is configured and ready to build with '{model_name}'.",
                    title="[bold green]READY[/bold green]",
                    border_style="green",
                )
            )
            return True

        self.console.print(
            Panel(
                "[bold yellow]Setup Incomplete[/bold yellow]\n"
                "Some verification checks did not pass. Run 'codeagent setup --repair' to retry.",
                title="[bold yellow]NOTICE[/bold yellow]",
                border_style="yellow",
            )
        )
        return False

    def _display_validation_report(self, report: ValidationReport) -> None:
        """Display table of validation steps."""
        table = Table(title="System Readiness Verification", show_header=True, header_style="bold cyan")
        table.add_column("Check Target", style="bold white", width=22)
        table.add_column("Status", justify="center", width=10)
        table.add_column("Details", style="white")

        for step in report.steps:
            status_style = "[bold green]PASS[/bold green]" if step.passed else "[bold red]FAIL[/bold red]"
            table.add_row(step.name, status_style, step.message)

        self.console.print()
        self.console.print(table)
        self.console.print()

