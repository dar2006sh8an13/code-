"""Official Ollama installation coordinator for Windows, Linux, and macOS."""

import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Callable, Optional, Tuple

from codeagent.installer.download_manager import DownloadError, DownloadManager
from codeagent.installer.ollama_detector import OllamaDetectionResult, OllamaDetector, OllamaStatus


OFFICIAL_WINDOWS_INSTALLER_URL = "https://ollama.com/download/OllamaSetup.exe"
OFFICIAL_LINUX_INSTALL_CMD = "curl -fsSL https://ollama.com/install.sh | sh"
OFFICIAL_MACOS_URL = "https://ollama.com/download/Ollama-darwin.zip"


class OllamaInstaller:
    """Coordinates downloading, executing, and starting the official Ollama runtime."""

    def __init__(self, download_manager: Optional[DownloadManager] = None, detector: Optional[OllamaDetector] = None) -> None:
        self.downloader = download_manager or DownloadManager()
        self.detector = detector or OllamaDetector()

    def start_service(self, executable_path: Optional[str] = None, wait_seconds: float = 8.0) -> Tuple[bool, str]:
        """Attempt to start the Ollama background daemon if already installed."""
        exe = executable_path or self.detector.find_executable()
        if not exe or not os.path.isfile(exe):
            return False, "Cannot start service: Ollama executable not found on disk."

        try:
            # Launch 'ollama serve' in background without blocking
            if sys.platform == "win32":
                # DETACHED_PROCESS flag to let service run independently
                creationflags = 0x00000008  # DETACHED_PROCESS
                subprocess.Popen(
                    [exe, "serve"],
                    creationflags=creationflags,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    shell=False,
                )
            else:
                subprocess.Popen(
                    [exe, "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                    shell=False,
                )

            # Poll for HTTP API readiness
            t0 = time.time()
            while time.time() - t0 < wait_seconds:
                time.sleep(0.5)
                is_online, _, _ = self.detector.probe_http_api()
                if is_online:
                    return True, "Ollama service started successfully and is responding."

            return False, f"Ollama service was started, but HTTP API did not respond within {wait_seconds:.0f}s."
        except Exception as exc:
            return False, f"Failed to start Ollama background process: {exc}"

    def install_windows(
        self,
        confirm_callback: Optional[Callable[[str], bool]] = None,
        silent: bool = True,
        show_progress: bool = True,
    ) -> Tuple[bool, str]:
        """Download and execute the official Ollama Windows installer with user privileges.

        Args:
            confirm_callback: Function prompting user for consent before download/install.
            silent: Whether to pass /SILENT flag to the installer.
            show_progress: Whether to show progress bar during download.

        Returns:
            Tuple[bool, str]: (success, status_message)
        """
        if sys.platform != "win32":
            return False, f"Windows installer cannot run on {platform.system()}."

        prompt_text = (
            "Source: Official Ollama distribution (https://ollama.com/download/OllamaSetup.exe)\n"
            "Target: Per-user directory (%LOCALAPPDATA%\\Programs\\Ollama)\n"
            "Privileges: Standard User (No Administrator elevation required)\n"
            "Estimated disk footprint: ~120 MB"
        )

        if confirm_callback and not confirm_callback(prompt_text):
            return False, "Installation cancelled by user."

        temp_dir = Path(tempfile.gettempdir())
        installer_path = temp_dir / "OllamaSetup.exe"

        # 1. Download official installer
        try:
            self.downloader.download_file(
                url=OFFICIAL_WINDOWS_INSTALLER_URL,
                destination_path=installer_path,
                description="Downloading official Ollama Windows installer",
                show_progress=show_progress,
            )
        except DownloadError as exc:
            return False, f"Failed to download Ollama installer: {exc}"

        # 2. Run installer with standard user permissions
        try:
            cmd = [str(installer_path)]
            if silent:
                # /SILENT performs a silent per-user setup without admin prompts
                cmd.append("/SILENT")

            proc = subprocess.run(cmd, shell=False, timeout=180.0)
            if proc.returncode != 0:
                return False, f"Installer exited with non-zero return code: {proc.returncode}"

            # 3. Clean up installer binary
            try:
                installer_path.unlink()
            except OSError:
                pass

            # 4. Wait for Ollama service to start (installer typically launches it)
            time.sleep(2.0)
            is_online, ver, _ = self.detector.probe_http_api()
            if is_online:
                return True, f"Ollama v{ver or 'unknown'} installed and running successfully."

            # If not yet online, attempt to start service explicitly
            started, msg = self.start_service()
            if started:
                return True, "Ollama installed and background service started."

            return True, "Ollama was installed. Please restart your terminal or launch 'Ollama' from the Start menu."

        except subprocess.TimeoutExpired:
            return False, "Ollama installer timed out after 3 minutes."
        except Exception as exc:
            return False, f"Error launching Ollama installer: {exc}"

    def get_linux_instructions(self) -> str:
        """Provide official verified Linux installation instructions."""
        return (
            "To install Ollama on Linux, run the official installation script:\n\n"
            f"    {OFFICIAL_LINUX_INSTALL_CMD}\n\n"
            "After installation, start the service with:\n"
            "    systemctl start ollama   (or: ollama serve)"
        )

    def get_macos_instructions(self) -> str:
        """Provide official verified macOS installation instructions."""
        return (
            "To install Ollama on macOS:\n\n"
            f"1. Download the official application from: {OFFICIAL_MACOS_URL}\n"
            "2. Unzip and drag Ollama to your Applications folder.\n"
            "   (Or install via Homebrew: brew install ollama)\n"
            "3. Launch Ollama from Applications to initialize the background service."
        )

    def verify_readiness(self, timeout: float = 10.0) -> OllamaDetectionResult:
        """Poll detector until Ollama is online or timeout expires."""
        t0 = time.time()
        while time.time() - t0 < timeout:
            res = self.detector.detect()
            if res.is_running:
                return res
            time.sleep(1.0)
        return self.detector.detect()

