"""Setup state persistence and tracking for CodeAgent first-time configuration."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
from typing import Any, Dict, Optional

from codeagent.__version__ import __version__


def get_default_setup_state_path() -> Path:
    """Determine the platform-appropriate path for setup state storage.

    Windows: %USERPROFILE%/.codeagent/setup_state.json
    Linux/macOS: ~/.codeagent/setup_state.json
    """
    home = Path.home()
    return home / ".codeagent" / "setup_state.json"


@dataclass
class SetupState:
    """Structured record tracking CodeAgent environment setup and verified readiness."""

    codeagent_version: str = __version__
    ollama_version: Optional[str] = None
    configured_model: str = "qwen3:latest"
    model_installed: bool = False
    setup_completed: bool = False
    setup_skipped: bool = False
    last_verified_at: Optional[str] = None
    platform: str = platform.system()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize state to standard dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SetupState":
        """Instantiate state from dictionary with safe defaults."""
        return cls(
            codeagent_version=data.get("codeagent_version", __version__),
            ollama_version=data.get("ollama_version"),
            configured_model=data.get("configured_model", "qwen3:latest"),
            model_installed=data.get("model_installed", False),
            setup_completed=data.get("setup_completed", False),
            setup_skipped=data.get("setup_skipped", False),
            last_verified_at=data.get("last_verified_at"),
            platform=data.get("platform", platform.system()),
        )


class SetupStateManager:
    """Persists, updates, and inspects CodeAgent setup status."""

    def __init__(self, state_file: Optional[Path] = None) -> None:
        self.state_file = Path(state_file or get_default_setup_state_path())
        self._cached_state: Optional[SetupState] = None

    def load(self) -> SetupState:
        """Load setup state from disk, or return a fresh state if uninitialized."""
        if not self.state_file.exists():
            return SetupState()
        try:
            raw = self.state_file.read_text(encoding="utf-8")
            data = json.loads(raw)
            self._cached_state = SetupState.from_dict(data)
            return self._cached_state
        except Exception:
            # Fall back to uninitialized state on corrupted file
            return SetupState()

    def save(self, state: SetupState) -> bool:
        """Persist setup state to JSON file."""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(state.to_dict(), indent=2) + "\n"
            self.state_file.write_text(payload, encoding="utf-8")
            self._cached_state = state
            return True
        except Exception:
            return False

    def mark_completed(
        self,
        ollama_version: Optional[str] = None,
        model_name: str = "qwen3:latest",
        model_installed: bool = True,
    ) -> SetupState:
        """Record successful end-to-end verification and setup completion."""
        state = self.load()
        state.codeagent_version = __version__
        state.ollama_version = ollama_version or state.ollama_version
        state.configured_model = model_name
        state.model_installed = model_installed
        state.setup_completed = True
        state.setup_skipped = False
        state.last_verified_at = datetime.now(timezone.utc).isoformat()
        self.save(state)
        return state

    def mark_skipped(self, model_name: str = "qwen3:latest") -> SetupState:
        """Record that the user explicitly chose to skip the setup wizard."""
        state = self.load()
        state.codeagent_version = __version__
        state.configured_model = model_name
        state.setup_completed = False
        state.setup_skipped = True
        state.last_verified_at = datetime.now(timezone.utc).isoformat()
        self.save(state)
        return state

    def reset(self) -> bool:
        """Clear setup state to trigger fresh verification."""
        try:
            if self.state_file.exists():
                self.state_file.unlink()
            self._cached_state = None
            return True
        except Exception:
            return False

    def is_setup_needed(self) -> bool:
        """Check whether setup is needed or uncompleted."""
        state = self.load()
        if state.setup_completed or state.setup_skipped:
            return False
        return True

