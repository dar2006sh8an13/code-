"""Centralized structured logging system with rotation, JSON serialization, and secret redaction."""

import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import sys
from typing import Any, Dict, Optional

from rich.console import Console
from rich.logging import RichHandler

from codeagent.config.settings import Settings, get_settings


# Regular expressions for scrubbing sensitive credentials and keys from logs
SECRET_PATTERNS = [
    # Connection string passwords e.g. postgres://user:password@host
    (re.compile(r'(://[^:]+:)([^@]+)(@)'), r'\1[REDACTED_PASSWORD]\3'),
    # OpenAI API Keys
    (re.compile(r"sk-[a-zA-Z0-9_-]{20,}", re.IGNORECASE), "[REDACTED_API_KEY]"),
    # GitHub Tokens
    (re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9]{36,}", re.IGNORECASE), "[REDACTED_GITHUB_TOKEN]"),
    # Generic API Keys / Secrets / Passwords in key-value format
    (
        re.compile(r'(?i)((?:api_key|apikey|secret|password|auth_token|access_token|private_key)\s*[:=]\s*)(["\']?)[a-zA-Z0-9_\-\.\/+=]{8,}\2'),
        r'\1\2[REDACTED_SECRET]\2',
    ),
    # PEM Private Keys
    (
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        "[REDACTED_PRIVATE_KEY]",
    ),
    # Bearer tokens
    (re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.]{15,}", re.IGNORECASE), "Bearer [REDACTED_TOKEN]"),
]


def redact_secrets(text: str) -> str:
    """Scrub sensitive credentials, tokens, and keys from text before logging."""
    if not isinstance(text, str):
        text = str(text)
    redacted = text
    for pattern, replacement in SECRET_PATTERNS:
        try:
            redacted = pattern.sub(replacement, redacted)
        except Exception:
            pass
    return redacted


class StructuredJsonFormatter(logging.Formatter):
    """Custom formatter producing single-line JSON log events with redaction and context."""

    def __init__(self, service_name: str = "codeagent") -> None:
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        # Redact message string
        raw_msg = record.getMessage()
        clean_msg = redact_secrets(raw_msg)

        log_event: Dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z") or record.created,
            "level": record.levelname,
            "component": record.name,
            "logger": record.name,
            "line": record.lineno,
            "message": clean_msg,
            "service": self.service_name,
        }

        # Include structured context attributes if present
        for attr in ("operation_id", "workflow_id", "agent_id", "task_id", "duration_ms", "status_code"):
            val = getattr(record, attr, None)
            if val is not None:
                log_event[attr] = val

        # Handle exception information safely
        if record.exc_info:
            log_event["exception"] = redact_secrets(self.formatException(record.exc_info))

        return json.dumps(log_event, ensure_ascii=False)


# Backward-compatible alias
JSONFormatter = StructuredJsonFormatter


class CodeAgentLogger:
    """Singleton manager for application-wide logging setup and rotation."""

    _initialized: bool = False
    _root_logger: Optional[logging.Logger] = None

    @classmethod
    def setup_logging(
        cls,
        settings: Optional[Settings] = None,
        debug_mode: bool = False,
        quiet_mode: bool = False,
        force_reinit: bool = False,
        force_reconfigure: bool = False,
        reconfigure: bool = False,
    ) -> logging.Logger:
        """Initialize console and rotating file loggers with secret redaction."""
        should_reinit = force_reinit or force_reconfigure or reconfigure
        if cls._initialized and not should_reinit and cls._root_logger is not None:
            return cls._root_logger

        cfg = settings or get_settings()
        root_logger = logging.getLogger("codeagent")

        # Determine log level
        if debug_mode:
            target_level = logging.DEBUG
        else:
            level_name = cfg.log_level.upper() if hasattr(cfg, "log_level") else "INFO"
            target_level = getattr(logging, level_name, logging.INFO)

        root_logger.setLevel(target_level)
        root_logger.handlers.clear()

        # 1. Console Handler (Rich-formatted)
        if not quiet_mode:
            rich_console = Console(stderr=True)
            console_handler = RichHandler(
                console=rich_console,
                show_time=True,
                show_path=debug_mode,
                level=target_level,
                rich_tracebacks=True,
                markup=False,
            )
            console_handler.setLevel(target_level)
            root_logger.addHandler(console_handler)

        # 2. Rotating File Handler (Structured JSON)
        log_file = Path(cfg.log_file_path) if hasattr(cfg, "log_file_path") else Path("data/logs/codeagent.jsonl")
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            max_bytes = getattr(cfg, "log_max_bytes", 10 * 1024 * 1024)
            backup_count = getattr(cfg, "log_backup_count", 5)

            file_handler = RotatingFileHandler(
                filename=str(log_file),
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            file_handler.setLevel(target_level)
            file_handler.setFormatter(StructuredJsonFormatter(service_name=cfg.app_name))
            root_logger.addHandler(file_handler)
        except (PermissionError, OSError) as exc:
            root_logger.warning(f"Could not initialize rotating log file at '{log_file}': {exc}")

        cls._initialized = True
        cls._root_logger = root_logger
        return root_logger

    @classmethod
    def get_logger(cls, component_name: str) -> logging.Logger:
        """Get or create a namespaced child logger under codeagent.<component>."""
        if not cls._initialized:
            cls.setup_logging()
        return logging.getLogger(f"codeagent.{component_name}")


def setup_logging(settings: Optional[Settings] = None, force_reconfigure: bool = False) -> logging.Logger:
    """Configure application logging according to active settings."""
    return CodeAgentLogger.setup_logging(settings=settings, force_reconfigure=force_reconfigure)


def get_logger(component_name: str = "app") -> logging.Logger:
    """Convenience helper to retrieve a component logger."""
    return CodeAgentLogger.get_logger(component_name)


def export_diagnostic_logs(
    output_path: Path,
    max_lines: int = 500,
    settings: Optional[Settings] = None,
    source_file: Optional[Path] = None,
) -> Optional[Path]:
    """Export the most recent sanitized log records to a diagnostic file for troubleshooting."""
    if source_file is None:
        cfg = settings or get_settings()
        source_file = Path(getattr(cfg, "log_file_path", "data/logs/codeagent.jsonl"))

    if not source_file.exists():
        return None

    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        lines = source_file.read_text(encoding="utf-8", errors="replace").splitlines()
        recent = lines[-max_lines:]
        sanitized = [redact_secrets(line) for line in recent]
        output_path.write_text("\n".join(sanitized) + "\n", encoding="utf-8")
        return output_path
    except Exception:
        return None
