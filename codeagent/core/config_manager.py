"""Multi-tiered configuration manager supporting precedence, validation, and platform paths."""

import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple
from pydantic import ValidationError

from codeagent.config.settings import Settings, get_settings
from codeagent.core.logger import redact_secrets


# Standard configuration keys that contain sensitive information
SENSITIVE_CONFIG_KEYS = {
    "api_key",
    "secret_key",
    "password",
    "auth_token",
    "access_token",
    "private_key",
    "client_secret",
}


def get_default_user_config_path() -> Path:
    """Determine the platform-appropriate user global configuration path.

    Windows: %USERPROFILE%/.codeagent/config.json
    Linux/macOS: ~/.codeagent/config.json
    """
    home = Path.home()
    return home / ".codeagent" / "config.json"


class ConfigManager:
    """Manages multi-tier configuration precedence, user config files, and safe inspection."""

    def __init__(
        self,
        user_config_file: Optional[Path] = None,
        workspace_root: Optional[Path] = None,
        user_config_path: Optional[Path] = None,
        custom_settings: Optional[Settings] = None,
        cli_overrides: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.user_config_file = Path(user_config_path or user_config_file or get_default_user_config_path())
        if custom_settings is not None:
            self.settings = custom_settings
        else:
            self.settings = self.build_effective_settings(cli_overrides)

    def get_user_config_path(self) -> Path:
        """Return the user-level configuration file path."""
        return self.user_config_file

    def load_user_config_dict(self) -> Dict[str, Any]:
        """Read and parse the user-level JSON configuration file if it exists."""
        if not self.user_config_file.exists():
            return {}
        try:
            raw = self.user_config_file.read_text(encoding="utf-8")
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @classmethod
    def init_user_config(
        cls,
        target_path_or_self: Optional[Any] = None,
        force: bool = False,
    ) -> Any:
        """Initialize a template user global configuration file."""
        is_direct_path = False
        if isinstance(target_path_or_self, (Path, str)):
            path = Path(target_path_or_self)
            is_direct_path = True
        elif hasattr(target_path_or_self, "user_config_file"):
            path = target_path_or_self.user_config_file
        else:
            path = get_default_user_config_path()

        if path.exists() and not force:
            msg = f"User configuration file already exists at '{path}'. Use --force to overwrite."
            return (False, msg) if not is_direct_path else False

        path.parent.mkdir(parents=True, exist_ok=True)
        template: Dict[str, Any] = {
            "OLLAMA_HOST": "http://localhost:11434",
            "DEFAULT_MODEL": "qwen3:latest",
            "TEMPERATURE": 0.2,
            "REQUEST_TIMEOUT": 300,
            "SHOW_STARTUP_BANNER": True,
            "LOG_LEVEL": "INFO",
            "BACKUP_ENABLED": True,
            "MAX_PARALLEL_AGENTS": 2,
        }

        try:
            path.write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")
            msg = f"Initialized user configuration at '{path}'"
            return (True, msg) if not is_direct_path else True
        except Exception as exc:
            msg = f"Failed to initialize user config: {exc}"
            return (False, msg) if not is_direct_path else False

    def build_effective_settings(
        self,
        cli_overrides: Optional[Dict[str, Any]] = None,
    ) -> Settings:
        """Build Settings honoring priority: CLI args > Environment Variables > User Config > Defaults."""
        cli_kwargs = {k: v for k, v in (cli_overrides or {}).items() if v is not None}
        user_kwargs = self.load_user_config_dict()

        # Merge user kwargs into parameters if not overridden by env or CLI
        combined_kwargs: Dict[str, Any] = {}
        # 1. User config values
        for k, v in user_kwargs.items():
            combined_kwargs[k.lower()] = v

        # 2. CLI options have highest precedence
        for k, v in cli_kwargs.items():
            combined_kwargs[k.lower()] = v

        try:
            return Settings(**combined_kwargs)
        except ValidationError:
            # Fall back to standard settings if custom merge fails
            return get_settings()

    def validate_settings(self, settings: Optional[Settings] = None) -> List[Tuple[str, bool, str]]:
        """Validate configuration settings and return list of (key, is_valid, message)."""
        cfg = settings or self.build_effective_settings()
        results: List[Tuple[str, bool, str]] = []

        # 1. Ollama host check
        if cfg.ollama_host.startswith(("http://", "https://")):
            results.append(("OLLAMA_HOST", True, f"Valid URL format: {cfg.ollama_host}"))
        else:
            results.append(("OLLAMA_HOST", False, "Host must begin with http:// or https://"))

        # 2. Model name check
        if cfg.model_name and len(cfg.model_name.strip()) > 0:
            results.append(("MODEL_NAME", True, f"Configured model: {cfg.model_name}"))
        else:
            results.append(("MODEL_NAME", False, "MODEL_NAME cannot be empty"))

        # 3. Timeout check
        if cfg.request_timeout > 0:
            results.append(("REQUEST_TIMEOUT", True, f"{cfg.request_timeout}s is positive"))
        else:
            results.append(("REQUEST_TIMEOUT", False, "REQUEST_TIMEOUT must be greater than 0"))

        # 4. Temperature check
        if 0.0 <= cfg.temperature <= 2.0:
            results.append(("TEMPERATURE", True, f"Sampling temperature {cfg.temperature} is within [0.0, 2.0]"))
        else:
            results.append(("TEMPERATURE", False, f"Temperature {cfg.temperature} is outside normal bounds [0.0, 2.0]"))

        # 5. Workspace root check
        ws_path = Path(cfg.workspace_root or self.workspace_root)
        if ws_path.exists():
            results.append(("WORKSPACE_ROOT", True, f"Workspace path exists: {ws_path}"))
        else:
            results.append(("WORKSPACE_ROOT", False, f"Workspace directory does not exist: {ws_path}"))

        # 6. Concurrency ceiling check
        if 1 <= cfg.max_parallel_agents <= 16:
            results.append(("MAX_PARALLEL_AGENTS", True, f"{cfg.max_parallel_agents} parallel agents within safe ceiling"))
        else:
            results.append(("MAX_PARALLEL_AGENTS", False, "MAX_PARALLEL_AGENTS should be between 1 and 16"))

        # 7. Log level check
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if getattr(cfg, "log_level", "INFO").upper() in valid_levels:
            results.append(("LOG_LEVEL", True, f"Valid logging level: {getattr(cfg, 'log_level', 'INFO').upper()}"))
        else:
            results.append(("LOG_LEVEL", False, f"Invalid log level: {getattr(cfg, 'log_level', 'INFO')}"))

        return results

    def get_masked_config_dump(self, settings: Optional[Settings] = None, show_all: bool = False) -> Dict[str, Any]:
        """Return serialized configuration dictionary with passwords, tokens, and secrets masked."""
        cfg = settings or self.build_effective_settings()
        raw_dict = cfg.model_dump()
        masked: Dict[str, Any] = {}

        for key, val in raw_dict.items():
            key_lower = key.lower()
            is_sensitive = (
                any(s in key_lower for s in SENSITIVE_CONFIG_KEYS)
                or key_lower in ("api_key", "password", "secret", "token")
            ) and not key_lower.endswith(("_tokens", "token_size"))

            if is_sensitive and val:
                masked[key] = "[PROTECTED_SECRET]"
            elif isinstance(val, (str, int, float, bool)) or val is None:
                masked[key] = val
            elif show_all:
                masked[key] = str(val)

        return masked

    def get_masked_dict(self, settings: Optional[Settings] = None, show_all: bool = False) -> Dict[str, Any]:
        """Return serialized configuration dictionary with uppercase key aliases and masked secrets."""
        dump = self.get_masked_config_dump(settings=settings, show_all=show_all)
        res = dict(dump)
        for k, v in dump.items():
            res[k.upper()] = v
        return res
