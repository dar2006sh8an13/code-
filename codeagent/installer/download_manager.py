"""HTTP streaming download manager with real-time Rich progress tracking and integrity validation."""

import hashlib
import os
from pathlib import Path
import tempfile
import time
from typing import Callable, Optional

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


class DownloadError(Exception):
    """Raised when an HTTP file download fails or is interrupted."""
    pass


class ChecksumMismatchError(DownloadError):
    """Raised when the downloaded file does not match the expected cryptographic hash."""
    pass


class DownloadManager:
    """Manages file downloads with streaming progress visualization and checksum validation."""

    def __init__(self, timeout: float = 600.0) -> None:
        self.timeout = timeout

    @staticmethod
    def calculate_sha256(file_path: Path) -> str:
        """Compute the SHA-256 digest of a local file."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest().lower()

    def download_file(
        self,
        url: str,
        destination_path: Path,
        description: str = "Downloading",
        expected_sha256: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        show_progress: bool = True,
    ) -> Path:
        """Stream download a remote file to destination with progress feedback.

        Args:
            url: Remote HTTP/HTTPS URL.
            destination_path: Local target file path.
            description: Progress bar label.
            expected_sha256: Optional hex hash to verify against.
            progress_callback: Optional callable receiving (completed_bytes, total_bytes).
            show_progress: Whether to render Rich progress bar.

        Returns:
            Path: Absolute resolved path of the verified download.

        Raises:
            DownloadError: On network, HTTP, or filesystem failure.
            ChecksumMismatchError: If hash check fails.
        """
        dest = Path(destination_path).resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)

        temp_dest = dest.with_suffix(dest.suffix + ".tmp")

        try:
            with httpx.stream("GET", url, timeout=self.timeout, follow_redirects=True) as response:
                if response.status_code != 200:
                    raise DownloadError(f"Download failed with HTTP status {response.status_code}: {url}")

                total_bytes = int(response.headers.get("Content-Length", 0))

                if show_progress:
                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[bold cyan]{task.description}[/bold cyan]"),
                        BarColumn(bar_width=36),
                        "[progress.percentage]{task.percentage:>3.0f}%",
                        DownloadColumn(),
                        TransferSpeedColumn(),
                        TimeRemainingColumn(),
                    ) as progress_ui:
                        task_id = progress_ui.add_task(description, total=total_bytes or None)

                        with open(temp_dest, "wb") as f_out:
                            for chunk in response.iter_bytes(chunk_size=65536):
                                f_out.write(chunk)
                                progress_ui.update(task_id, advance=len(chunk))
                                if progress_callback and total_bytes:
                                    progress_callback(f_out.tell(), total_bytes)
                else:
                    with open(temp_dest, "wb") as f_out:
                        for chunk in response.iter_bytes(chunk_size=65536):
                            f_out.write(chunk)
                            if progress_callback and total_bytes:
                                progress_callback(f_out.tell(), total_bytes)

            # Validate checksum if specified
            if expected_sha256:
                actual_sha = self.calculate_sha256(temp_dest)
                if actual_sha.lower() != expected_sha256.lower():
                    if temp_dest.exists():
                        temp_dest.unlink()
                    raise ChecksumMismatchError(
                        f"Integrity check failed for {dest.name}. Expected {expected_sha256}, got {actual_sha}"
                    )

            # Atomic rename after complete download
            if dest.exists():
                dest.unlink()
            temp_dest.rename(dest)
            return dest

        except (httpx.RequestError, httpx.HTTPStatusError, OSError) as exc:
            if temp_dest.exists():
                try:
                    temp_dest.unlink()
                except OSError:
                    pass
            raise DownloadError(f"Download failed: {exc}") from exc

