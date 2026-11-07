"""Tests for Phase 10 - Production-Ready CLI, Logging, Profiling, Config, and Monitoring."""

import json
import logging
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from codeagent.__version__ import __app_name__, __version__
from codeagent.cli import app
from codeagent.config.settings import Settings
from codeagent.core.config_manager import ConfigManager
from codeagent.core.logger import (
    CodeAgentLogger,
    JSONFormatter,
    export_diagnostic_logs,
    get_logger,
    redact_secrets,
    setup_logging,
)
from codeagent.core.monitoring import HealthCheckItem, MonitoringSystem
from codeagent.core.profiler import PerformanceProfiler, measure, run_local_benchmark


# ---------------------------------------------------------------------------
# 1. Version and App Metadata
# ---------------------------------------------------------------------------


def test_app_version_metadata():
    assert __version__ == "0.1.0"
    assert __app_name__ in ("Coder with Code", "Code AG", "Code")


# ---------------------------------------------------------------------------
# 2. Structured Logging and Secret Redaction
# ---------------------------------------------------------------------------


def test_redact_secrets_patterns():
    # Bearer token
    assert redact_secrets("Authorization: Bearer my-auth-token-1234567890abcdef") == "Authorization: Bearer [REDACTED_TOKEN]"
    assert redact_secrets("Authorization: Bearer sk-1234567890abcdef1234567890abcdef") == "Authorization: Bearer [REDACTED_API_KEY]"
    # API key
    assert redact_secrets("api_key = 'abcdef1234567890abcdef1234567890'") == "api_key = '[REDACTED_SECRET]'"
    # Password
    assert redact_secrets("password: secret_pass_123") == "password: [REDACTED_SECRET]"
    # URL password
    assert redact_secrets("postgres://user:mypassword123@localhost:5432/db") == "postgres://user:[REDACTED_PASSWORD]@localhost:5432/db"
    # Normal text should remain untouched
    normal_text = "Processing file src/main.py with context reserve 1024"
    assert redact_secrets(normal_text) == normal_text


def test_json_formatter():
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=42,
        msg="Test message with password: secret_pass_123",
        args=(),
        exc_info=None,
    )
    formatted = formatter.format(record)
    parsed = json.loads(formatted)
    assert parsed["logger"] == "test_logger"
    assert parsed["level"] == "INFO"
    assert parsed["line"] == 42
    assert "[REDACTED_SECRET]" in parsed["message"]
    assert "timestamp" in parsed


def test_codeagent_logger_setup_and_rotation():
    with tempfile.TemporaryDirectory() as tmp_dir:
        log_file = Path(tmp_dir) / "test_log.jsonl"
        settings = Settings(
            LOG_LEVEL="DEBUG",
            LOG_FILE_PATH=str(log_file),
            LOG_MAX_BYTES=1024,
            LOG_BACKUP_COUNT=2,
            LOG_FORMAT_JSON=True,
        )
        try:
            CodeAgentLogger.setup_logging(settings=settings, force_reconfigure=True)
            test_logger = CodeAgentLogger.get_logger("phase10_test")
            test_logger.info("Test log line for phase 10")

            # Flush handlers
            for handler in logging.getLogger().handlers:
                handler.flush()
            for handler in logging.getLogger("codeagent").handlers:
                handler.flush()

            assert log_file.exists()
            content = log_file.read_text(encoding="utf-8")
            assert "Test log line for phase 10" in content
        finally:
            # Release file handlers on Windows before temp dir cleanup
            for h in list(logging.getLogger().handlers):
                h.close()
                logging.getLogger().removeHandler(h)
            for h in list(logging.getLogger("codeagent").handlers):
                h.close()
                logging.getLogger("codeagent").removeHandler(h)


def test_export_diagnostic_logs():
    with tempfile.TemporaryDirectory() as tmp_dir:
        src_log = Path(tmp_dir) / "source.log"
        src_log.write_text("Log entry 1\nLog entry 2\n", encoding="utf-8")
        dest_log = Path(tmp_dir) / "export" / "diagnostics.log"

        result = export_diagnostic_logs(dest_log, source_file=src_log)
        assert result is not None
        assert dest_log.exists()
        assert "Log entry 1" in dest_log.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 3. Configuration Management and Precedence
# ---------------------------------------------------------------------------


def test_config_precedence_cli_overrides():
    with tempfile.TemporaryDirectory() as tmp_dir:
        user_cfg_path = Path(tmp_dir) / "config.json"
        user_cfg_path.write_text(json.dumps({"MODEL_NAME": "user-model"}), encoding="utf-8")

        # Tier 4 Default, Tier 3 User, Tier 2 Env, Tier 1 CLI
        manager = ConfigManager(user_config_path=user_cfg_path, cli_overrides={"MODEL_NAME": "cli-model"})
        assert manager.settings.model_name == "cli-model"


def test_config_masking():
    settings = Settings(
        OLLAMA_HOST="http://localhost:11434",
        MODEL_NAME="qwen3:latest",
        CONTEXT_RESERVE_TOKENS=1024,
    )
    manager = ConfigManager(custom_settings=settings)
    masked = manager.get_masked_dict()

    # Numeric tokens preserved
    assert masked["CONTEXT_RESERVE_TOKENS"] == 1024
    assert masked["MODEL_NAME"] == "qwen3:latest"
    assert masked["OLLAMA_HOST"] == "http://localhost:11434"


def test_config_validation():
    manager = ConfigManager()
    results = manager.validate_settings()
    assert isinstance(results, list)
    failed = [r for r in results if not r[1]]
    assert len(failed) == 0


def test_config_init_user_config():
    with tempfile.TemporaryDirectory() as tmp_dir:
        target_path = Path(tmp_dir) / "subfolder" / "config.json"
        created = ConfigManager.init_user_config(target_path)
        assert created is True
        assert target_path.exists()
        data = json.loads(target_path.read_text(encoding="utf-8"))
        assert "DEFAULT_MODEL" in data
        assert "OLLAMA_HOST" in data


# ---------------------------------------------------------------------------
# 4. Performance Profiler
# ---------------------------------------------------------------------------


def test_profiler_measure_decorator():
    profiler = PerformanceProfiler(enabled=True)

    @profiler.profile_function("custom_operation")
    def dummy_task(x):
        return x * 2

    res = dummy_task(5)
    assert res == 10

    records = profiler.get_records()
    assert len(records) >= 1
    assert any(r.name == "custom_operation" for r in records)


def test_run_local_benchmark():
    metrics = run_local_benchmark()
    assert "benchmarks" in metrics
    benchmarks = metrics["benchmarks"]
    assert "calculator_tool_avg_ms" in benchmarks
    assert "path_safety_check_avg_ms" in benchmarks
    assert "current_process_rss_mb" in benchmarks
    assert benchmarks["calculator_tool_avg_ms"] > 0
    assert benchmarks["path_safety_check_avg_ms"] > 0


# ---------------------------------------------------------------------------
# 5. Monitoring & Diagnostics System
# ---------------------------------------------------------------------------


def test_monitoring_system_checks():
    system = MonitoringSystem(project_root=Path("."))

    # 1. Application check
    app_check = system.check_application_health()
    assert app_check.name == "Application"
    assert app_check.passed is True
    assert "Code" in app_check.message

    # 2. Database check
    db_check = system.check_database_health()
    assert db_check.name == "Database"
    assert db_check.passed is True

    # 3. Tools check
    tool_check = system.check_tools_health()
    assert tool_check.name == "Tool Registry"
    assert tool_check.passed is True
    assert "safe tools" in tool_check.message

    # 4. Agent check
    agent_check = system.check_agent_health()
    assert agent_check.name == "Multi-Agent System"
    assert agent_check.passed is True
    assert "5 specialized agents" in agent_check.message

    # 5. Resource check
    res_check = system.check_resources_health()
    assert res_check.name == "System Resources"
    assert res_check.passed is True


def test_monitoring_export_diagnostics():
    with tempfile.TemporaryDirectory() as tmp_dir:
        export_file = Path(tmp_dir) / "diag.json"
        system = MonitoringSystem(project_root=Path("."))
        report = system.export_diagnostics(export_file)

        assert export_file.exists()
        assert "timestamp" in report
        assert "application" in report
        assert "subsystems" in report
        assert len(report["subsystems"]) >= 5


# ---------------------------------------------------------------------------
# 6. CLI Command Integration (Fast Startup & Subsystem Commands)
# ---------------------------------------------------------------------------


def test_cli_version_fast_startup():
    runner = CliRunner()
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "Code" in result.stdout
    assert "0.1.0" in result.stdout


def test_cli_config_commands():
    runner = CliRunner()
    # config show
    res_show = runner.invoke(app, ["config", "show"])
    assert res_show.exit_code == 0
    assert "ollama_host" in res_show.stdout.lower()

    # config validate
    res_val = runner.invoke(app, ["config", "validate"])
    assert res_val.exit_code == 0
    assert "Configuration Validation Check" in res_val.stdout
    assert "VALID" in res_val.stdout

    # config path
    res_path = runner.invoke(app, ["config", "path"])
    assert res_path.exit_code == 0
    assert "User global config path" in res_path.stdout


def test_cli_performance_benchmark():
    runner = CliRunner()
    result = runner.invoke(app, ["performance"])
    assert result.exit_code == 0
    assert "Local Engine Benchmarks" in result.stdout
    assert "Calculator Tool Latency" in result.stdout


# ---------------------------------------------------------------------------
# 7. Safe Code Extraction and Auto-Save Helper
# ---------------------------------------------------------------------------


def test_extract_and_save_code_blocks_single_file():
    from rich.console import Console
    from codeagent.cli import _extract_and_save_code_blocks
    from codeagent.filesystem.manager import FilesystemManager

    with tempfile.TemporaryDirectory() as tmp_dir:
        settings = Settings(workspace_boundary=tmp_dir)
        fs_mgr = FilesystemManager(settings=settings, workspace_root=tmp_dir)
        console = Console(record=True)

        prompt = "create an index.html file for a modern todo list website with HTML, CSS, and JavaScript"
        response_text = """Here is your todo list website:
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Modern Todo List</title>
</head>
<body>
    <h1>Todo App</h1>
</body>
</html>
```
Enjoy your new website!"""

        saved = _extract_and_save_code_blocks(prompt, response_text, fs_mgr, console)
        assert "index.html" in saved
        target_file = Path(tmp_dir) / "index.html"
        assert target_file.exists()
        content = target_file.read_text(encoding="utf-8")
        assert "<title>Modern Todo List</title>" in content


def test_extract_and_save_code_blocks_labeled_multi_file():
    from rich.console import Console
    from codeagent.cli import _extract_and_save_code_blocks
    from codeagent.filesystem.manager import FilesystemManager

    with tempfile.TemporaryDirectory() as tmp_dir:
        settings = Settings(workspace_boundary=tmp_dir)
        fs_mgr = FilesystemManager(settings=settings, workspace_root=tmp_dir)
        console = Console(record=True)

        prompt = "create a website with index.html and style.css"
        response_text = """### index.html
```html
<!DOCTYPE html><html><body><h1>Hello</h1></body></html>
```

### style.css
```css
body { background: #000; color: #fff; }
```"""

        saved = _extract_and_save_code_blocks(prompt, response_text, fs_mgr, console)
        assert "index.html" in saved
        assert "style.css" in saved
        assert (Path(tmp_dir) / "index.html").exists()
        assert (Path(tmp_dir) / "style.css").exists()


def test_extract_and_save_ignores_general_questions():
    from rich.console import Console
    from codeagent.cli import _extract_and_save_code_blocks
    from codeagent.filesystem.manager import FilesystemManager

    with tempfile.TemporaryDirectory() as tmp_dir:
        settings = Settings(workspace_boundary=tmp_dir)
        fs_mgr = FilesystemManager(settings=settings, workspace_root=tmp_dir)
        console = Console(record=True)

        prompt = "Explain how python generators work with an example"
        response_text = """Generators produce items on demand:
```python
def my_gen():
    yield 42
```"""

        saved = _extract_and_save_code_blocks(prompt, response_text, fs_mgr, console)
        assert len(saved) == 0
        user_files = [p.name for p in Path(tmp_dir).iterdir() if not p.name.startswith(".")]
        assert len(user_files) == 0


def test_settings_tool_call_timeout_configuration():
    s = Settings(tool_call_timeout=15.0)
    assert s.tool_call_timeout == 15.0
    s_default = Settings(_env_file=None)
    assert s_default.tool_call_timeout == 45.0

