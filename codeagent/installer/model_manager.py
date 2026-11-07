"""Model lifecycle management, streaming downloads, and verification using official Ollama APIs."""

import json
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)


class ModelPullError(Exception):
    """Raised when pulling a model via Ollama fails or is interrupted."""
    pass


class ModelManager:
    """Interfaces with Ollama's model catalog and pull endpoints with streaming progress."""

    def __init__(self, api_url: str = "http://localhost:11434", timeout: float = 1800.0) -> None:
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout

    def list_installed_models(self) -> List[str]:
        """Fetch list of all model tags currently available in local Ollama storage."""
        try:
            res = httpx.get(f"{self.api_url}/api/tags", timeout=5.0)
            if res.status_code == 200:
                data = res.json()
                return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
            return []
        except Exception:
            return []

    def is_model_installed(self, model_name: str) -> bool:
        """Check whether the requested model (or its bare tag) is present locally."""
        installed = self.list_installed_models()
        target = model_name.strip().lower()
        target_bare = target.split(":")[0]

        for m in installed:
            m_lower = m.lower()
            if m_lower == target:
                return True
            # Match e.g. "qwen3:latest" if requested "qwen3" or vice-versa
            m_bare = m_lower.split(":")[0]
            if m_bare == target_bare and (m_lower.endswith(":latest") or target.endswith(":latest") or ":" not in target):
                return True
        return False

    def pull_model(
        self,
        model_name: str = "qwen3:latest",
        show_progress: bool = True,
        max_retries: int = 3,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> Tuple[bool, str]:
        """Download and register a model via Ollama's official streaming pull endpoint.

        Args:
            model_name: Model identifier (e.g. 'qwen3:latest').
            show_progress: Render interactive Rich progress UI.
            max_retries: Number of automatic resume attempts on connection drops.
            progress_callback: Optional hook receiving (status, completed_bytes, total_bytes).

        Returns:
            Tuple[bool, str]: (success, message)
        """
        # 1. Skip if already downloaded
        if self.is_model_installed(model_name):
            return True, f"Model '{model_name}' is already installed locally."

        endpoint = f"{self.api_url}/api/pull"
        payload = {"name": model_name, "stream": True}

        for attempt in range(1, max_retries + 1):
            try:
                if show_progress:
                    success, msg = self._pull_with_rich_progress(endpoint, payload, model_name, progress_callback)
                else:
                    success, msg = self._pull_silent(endpoint, payload, progress_callback)

                if success:
                    # Verify model appears in /api/tags
                    time.sleep(1.0)
                    if self.is_model_installed(model_name):
                        return True, f"Model '{model_name}' verified and ready for inference."
                    return True, f"Model '{model_name}' downloaded successfully."

                if attempt < max_retries:
                    time.sleep(2.0)
                    continue
                return False, msg

            except (httpx.RequestError, httpx.HTTPStatusError, ModelPullError) as exc:
                if attempt < max_retries:
                    time.sleep(3.0)
                    continue
                return False, f"Failed to pull model '{model_name}' after {max_retries} attempts: {exc}"

        return False, f"Could not complete model download for '{model_name}'."

    def _pull_with_rich_progress(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        model_name: str,
        progress_callback: Optional[Callable[[str, int, int], None]],
    ) -> Tuple[bool, str]:
        """Stream Ollama pull events and render Rich progress bar."""
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}[/bold cyan]"),
            BarColumn(bar_width=36),
            "[progress.percentage]{task.percentage:>3.0f}%",
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
        ) as progress:
            task_id = progress.add_task(f"Pulling {model_name}", total=None)

            with httpx.stream("POST", endpoint, json=payload, timeout=self.timeout) as response:
                if response.status_code != 200:
                    raise ModelPullError(f"Ollama pull returned status {response.status_code}")

                for line in response.iter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    status_str = chunk.get("status", "")
                    total = chunk.get("total", 0)
                    completed = chunk.get("completed", 0)

                    # Update description with status message
                    if status_str and not total:
                        progress.update(task_id, description=f"{model_name}: {status_str}")

                    if total and total > 0:
                        progress.update(
                            task_id,
                            description=f"Downloading {model_name}",
                            total=total,
                            completed=completed,
                        )

                    if progress_callback:
                        progress_callback(status_str, completed, total)

                    if "error" in chunk:
                        return False, f"Ollama error: {chunk['error']}"

            return True, "Download finished"

    def _pull_silent(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        progress_callback: Optional[Callable[[str, int, int], None]],
    ) -> Tuple[bool, str]:
        """Stream pull events without rendering to console."""
        with httpx.stream("POST", endpoint, json=payload, timeout=self.timeout) as response:
            if response.status_code != 200:
                raise ModelPullError(f"Ollama pull returned status {response.status_code}")

            for line in response.iter_lines():
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if "error" in chunk:
                    return False, f"Ollama error: {chunk['error']}"

                status_str = chunk.get("status", "")
                completed = chunk.get("completed", 0)
                total = chunk.get("total", 0)

                if progress_callback:
                    progress_callback(status_str, completed, total)

        return True, "Download finished"
