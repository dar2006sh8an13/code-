# Configuration Guide – Code AG

Code AG provides a unified, production-grade configuration architecture that ensures predictable behavior, secret protection, and zero runtime surprises.

---

## 1. Multi-Tier Configuration Precedence

Code AG resolves settings through a strict 4-tier hierarchy:

```
┌────────────────────────────────────────────────────────┐
│ Tier 1: Explicit Command-Line Arguments & Flags       │ (Highest Precedence)
├────────────────────────────────────────────────────────┤
│ Tier 2: Environment Variables (.env / Shell Env)      │
├────────────────────────────────────────────────────────┤
│ Tier 3: Global User Config (~/.codeagent/config.json)  │
├────────────────────────────────────────────────────────┤
│ Tier 4: Built-in Application Defaults (settings.py)    │ (Base Defaults)
└────────────────────────────────────────────────────────┘
```

When a setting is specified at a higher tier, it overrides identical keys configured at lower tiers.

---

## 2. Configuration Settings Reference

### LLM & Ollama Backend

| Setting Name | Env Variable | Default | Description |
| :--- | :--- | :--- | :--- |
| `ollama_host` | `OLLAMA_HOST` | `http://localhost:11434` | URL endpoint of the local Ollama server |
| `model_name` | `MODEL_NAME` | `qwen3:latest` | Default local LLM model name |
| `temperature` | `TEMPERATURE` | `0.2` | Generation sampling temperature (0.0 - 2.0) |
| `request_timeout` | `REQUEST_TIMEOUT` | `300.0` | Timeout in seconds for LLM inference requests |
| `context_window` | `CONTEXT_WINDOW` | `8192` | Model context window size in tokens |
| `context_reserve_tokens` | `CONTEXT_RESERVE_TOKENS` | `1024` | Reserved token headroom for output generation |

### Specialized Multi-Agent Models

| Setting Name | Env Variable | Default | Description |
| :--- | :--- | :--- | :--- |
| `agent_model` | `AGENT_MODEL` | `qwen3:latest` | Shared model for autonomous agents |
| `planner_model` | `PLANNER_MODEL` | `None` *(uses agent_model)* | Model override for Planner Agent |
| `coder_model` / `code_model` | `CODER_MODEL` / `CODE_MODEL` | `None` *(uses agent_model)* | Model override for Code Agent |
| `debugger_model`| `DEBUGGER_MODEL` | `None` *(uses agent_model)* | Model override for Debugger Agent |
| `reviewer_model`| `REVIEWER_MODEL` | `None` *(uses agent_model)* | Model override for Reviewer Agent |
| `max_parallel_agents` | `MAX_PARALLEL_AGENTS` | `2` | Maximum concurrent agent executions (1-16) |

### Safety & Permission Controls

| Setting Name | Env Variable | Default | Description |
| :--- | :--- | :--- | :--- |
| `require_write_approval` | `REQUIRE_WRITE_APPROVAL` | `True` | Require user confirmation before file write |
| `require_python_approval`| `REQUIRE_PYTHON_APPROVAL`| `True` | Require user confirmation before executing Python |
| `require_dependency_approval`| `REQUIRE_DEPENDENCY_APPROVAL`| `True`| Confirm before installing pip packages |
| `require_patch_approval` | `REQUIRE_PATCH_APPROVAL` | `True` | Confirm before applying debugging diff patches |
| `secret_scan_before_commit` | `SECRET_SCAN_BEFORE_COMMIT` | `True` | Block commits if secrets or API keys detected |

### Backups & Rollback

| Setting Name | Env Variable | Default | Description |
| :--- | :--- | :--- | :--- |
| `backup_enabled` | `BACKUP_ENABLED` | `True` | Automatically backup files before modification |
| `backup_storage_path` | `BACKUP_STORAGE_PATH` | `data/backups` | Directory for file backup snapshots |
| `max_backups_per_file`| `MAX_BACKUPS_PER_FILE` | `10` | Maximum historical backup snapshots kept per file |

### Logging, Diagnostics & Profiling

| Setting Name | Env Variable | Default | Description |
| :--- | :--- | :--- | :--- |
| `log_level` | `LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`) |
| `log_file_path` | `LOG_FILE_PATH` | `data/logs/codeagent.jsonl` | Path to rotating JSONL log file |
| `log_max_bytes` | `LOG_MAX_BYTES` | `10485760` (10 MB) | Max size per rotating log file |
| `log_backup_count`| `LOG_BACKUP_COUNT` | `5` | Number of rotated log files retained |
| `log_format_json`| `LOG_FORMAT_JSON` | `True` | Enable structured JSON formatting for log lines |
| `profiling_enabled` | `PROFILING_ENABLED` | `False` | Enable continuous execution profiling |
| `monitoring_enabled`| `MONITORING_ENABLED` | `True` | Enable background subsystem monitoring |
| `health_check_timeout`| `HEALTH_CHECK_TIMEOUT` | `3.0` | Timeout in seconds for LLM health check |
| `show_startup_banner`| `SHOW_STARTUP_BANNER` | `True` | Display ASCII art banner on session start |

---

## 3. Configuration Management CLI Commands

Code AG includes built-in commands to inspect, validate, and manage settings:

### View Effective Configuration
```powershell
codeag config show
```
Displays all resolved configuration settings in a formatted table. Sensitive credentials (API keys, passwords, bearer tokens) are **automatically masked** with `[PROTECTED_SECRET]`.

### Validate Configuration
```powershell
codeag config validate
```
Validates current settings against runtime constraints (Ollama URL format, model availability, timeout bounds, directory existence).

### Display Configuration File Path
```powershell
codeag config path
```
Outputs the active path to your user global configuration file:
- **Windows:** `%USERPROFILE%\.codeagent\config.json`
- **Linux/macOS:** `~/.codeagent/config.json`

### Initialize User Global Configuration
```powershell
codeag config init [--force]
```
Generates a template `config.json` at your user configuration path. Use `--force` to overwrite existing configuration.

---

## 4. User Configuration File Example (`config.json`)

```json
{
  "OLLAMA_HOST": "http://localhost:11434",
  "MODEL_NAME": "qwen3:latest",
  "TEMPERATURE": 0.2,
  "REQUEST_TIMEOUT": 300,
  "SHOW_STARTUP_BANNER": true,
  "LOG_LEVEL": "INFO",
  "BACKUP_ENABLED": true,
  "MAX_PARALLEL_AGENTS": 2,
  "SECRET_SCAN_BEFORE_COMMIT": true
}
```

