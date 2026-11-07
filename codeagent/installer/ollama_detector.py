"""Ollama installation and runtime state detection across Windows, Linux, and macOS."""

from dataclasses import dataclass, field
from enum import Enum
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import List, Optional

import httpx


class OllamaStatus(str, Enum):
    """Execution and installation state of Ollama."""

    RUNNING = "running"
    INSTALLED_STOPPED = "installed_stopped"
    NOT_INSTALLED = "not_installed"


@dataclass
class OllamaDetectionResult:
    """Consolidated findings from filesystem and network probes."""

    status: OllamaStatus
    executable_path: Optional[str] = None
    version: Optional[str] = None
    api_url: str = "http://localhost:11434"
    installed_models: List[str] = field(default_factory=list)
    message: str = ""

    @property
    def is_running(self) -> bool:
        return self.status == OllamaStatus.RUNNING

    @property
    def is_installed(self) -> bool:
        return self.status in (OllamaStatus.RUNNING, OllamaStatus.INSTALLED_STOPPED)


class OllamaDetector:
    """Detects Ollama binaries, service processes, and active HTTP API endpoints."""

    def __init__(self, api_url: str = "http://localhost:11434", timeout: float = 2.5) -> None:
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout

    def probe_http_api(self) -> tuple[bool, Optional[str], List[str]]:
        """Probe the Ollama REST API to determine if the server process is alive.

        Returns:
            tuple: (is_online, server_version, list_of_installed_model_names)
        """
        try:
            # 1. Probe version
            version_str: Optional[str] = None
            try:
                res_ver = httpx.get(f"{self.api_url}/api/version", timeout=self.timeout)
                if res_ver.status_code == 200:
                    data = res_ver.json()
                    version_str = data.get("version")
            except Exception:
                pass

            # 2. Probe tags (installed models)
            res_tags = httpx.get(f"{self.api_url}/api/tags", timeout=self.timeout)
            if res_tags.status_code == 200:
                tags_data = res_tags.json()
                models = [m.get("name", "") for m in tags_data.get("models", []) if m.get("name")]
                return True, version_str, models

            return False, version_str, []
        except Exception:
            return False, None, []

    def find_executable(self) -> Optional[str]:
        """Locate the Ollama binary across PATH and standard OS installation locations."""
        # 1. Search PATH
        binary_name = "ollama.exe" if sys.platform == "win32" else "ollama"
        path_binary = shutil.which(binary_name) or shutil.which("ollama")
        if path_binary and os.path.isfile(path_binary):
            return str(Path(path_binary).resolve())

        # 2. Platform-specific fallback locations
        candidates: List[Path] = []
        if sys.platform == "win32":
            local_appdata = os.environ.get("LOCALAPPDATA")
            prog_files = os.environ.get("ProgramFiles")
            prog_files_x86 = os.environ.get("ProgramFiles(x86)")

            if local_appdata:
                candidates.append(Path(local_appdata) / "Programs" / "Ollama" / "ollama.exe")
            if prog_files:
                candidates.append(Path(prog_files) / "Ollama" / "ollama.exe")
            if prog_files_x86:
                candidates.append(Path(prog_files_x86) / "Ollama" / "ollama.exe")

            # Common user home pattern
            user_profile = os.environ.get("USERPROFILE")
            if user_profile:
                candidates.append(Path(user_profile) / "AppData" / "Local" / "Programs" / "Ollama" / "ollama.exe")

        elif sys.platform == "darwin":
            candidates.extend([
                Path("/usr/local/bin/ollama"),
                Path("/opt/homebrew/bin/ollama"),
                Path("/usr/bin/ollama"),
                Path(os.path.expanduser("~/.local/bin/ollama")),
            ])
        else:  # Linux
            candidates.extend([
                Path("/usr/local/bin/ollama"),
                Path("/usr/bin/ollama"),
                Path("/bin/ollama"),
                Path(os.path.expanduser("~/.local/bin/ollama")),
            ])

        for c in candidates:
            if c.exists() and os.path.isfile(c):
                return str(c.resolve())

        return None

    def query_binary_version(self, executable_path: str) -> Optional[str]:
        """Invoke `ollama --version` to extract the CLI version string."""
        try:
            res = subprocess.run(
                [executable_path, "--version"],
                capture_output=True,
                text=True,
                timeout=3.0,
                shell=False,
            )
            output = (res.stdout or res.stderr or "").strip()
            # Match e.g. "ollama version is 0.3.14" or "0.3.14"
            match = re.search(r"(\d+\.\d+\.\d+(?:-[a-zA-Z0-9.]+)?(?:-rc\d+)?)", output)
            if match:
                return match.group(1)
            return output if output else None
        except Exception:
            return None

    def detect(self) -> OllamaDetectionResult:
        """Perform comprehensive probe of binary path and HTTP API state."""
        # 1. First probe API
        api_online, api_version, models = self.probe_http_api()

        # 2. Find binary
        binary_path = self.find_executable()

        # 3. Determine version
        detected_version = api_version
        if not detected_version and binary_path:
            detected_version = self.query_binary_version(binary_path)

        if api_online:
            return OllamaDetectionResult(
                status=OllamaStatus.RUNNING,
                executable_path=binary_path,
                version=detected_version,
                api_url=self.api_url,
                installed_models=models,
                message=f"Ollama is running (version: {detected_version or 'unknown'}, {len(models)} models installed)",
            )

        if binary_path:
            return OllamaDetectionResult(
                status=OllamaStatus.INSTALLED_STOPPED,
                executable_path=binary_path,
                version=detected_version,
                api_url=self.api_url,
                installed_models=[],
                message=f"Ollama is installed at '{binary_path}' but the background service is not running",
            )

        return OllamaDetectionResult(
            status=OllamaStatus.NOT_INSTALLED,
            executable_path=None,
            version=None,
            api_url=self.api_url,
            installed_models=[],
            message="Ollama executable not found on system PATH or standard locations",
        )

