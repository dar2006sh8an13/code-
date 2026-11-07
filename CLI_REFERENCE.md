# CLI Reference Guide – Code AG

Comprehensive command-line manual and interactive command reference for **Code AG**.

---

## 1. Top-Level Command Synopsis

```text
codeag [OPTIONS] [PROMPT]
codeag COMMAND [ARGS]...
```

### Options

| Flag | Short | Description |
| :--- | :--- | :--- |
| `--model <NAME>` | `-m` | Override LLM model name (default: `qwen3:latest`) |
| `--agent-model <NAME>` | | Shared model for multi-agent execution |
| `--planner-model <NAME>` | | Specific model for Planner Agent |
| `--code-model <NAME>` | | Specific model for Code Agent (alias: `--coder-model`) |
| `--debugger-model <NAME>`| | Specific model for Debugger Agent |
| `--reviewer-model <NAME>`| | Specific model for Reviewer Agent |
| `--ollama-host <URL>` | | Local Ollama endpoint URL |
| `--temperature <FLOAT>`| `-t` | Model sampling temperature (0.0 to 2.0) |
| `--max-tokens <INT>` | | Maximum response token limit |
| `--workspace <PATH>` | `-w` | Target workspace directory |
| `--log-level <LEVEL>` | | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `--no-banner` | | Suppress startup ASCII logo banner |
| `--help` | `-h` | Display Typer help menu |

---

## 2. CLI Subcommands

### `codeag version`
Display version metadata, active Python runtime, and host OS.
```powershell
codeag version
```
*Executes instantly without initializing LLM or network.*

---

### `codeag health`
Execute comprehensive health assessment across all subsystems:
```powershell
codeag health [--timeout <seconds>]
```
- **Application:** Verifies Python runtime, version, and workspace boundaries.
- **Database:** Inspects SQLite persistent files and schema integrity.
- **Tool Registry:** Validates all 45 safe registered tools.
- **Multi-Agent System:** Verifies all 5 specialized agents.
- **System Resources:** Checks disk space and resident process memory.
- **LLM Inference:** Probes local Ollama server connectivity and model readiness.

---

### `codeag monitor`
Display lightweight subsystem monitoring status dashboard:
```powershell
codeag monitor
```
*Executes non-destructive, non-LLM status checks in under 50ms.*

---

### `codeag performance`
Execute local performance engine benchmarks:
```powershell
codeag performance
```
Measures:
- Safe AST calculator latency (avg ms per operation)
- Path safety validation latency (avg ms per check)
- Process resident memory (RSS MB)

---

### `codeag diagnostics`
Export detailed system diagnostics report in JSON format:
```powershell
codeag diagnostics [--export <output_path>]
```
Default output path: `data/logs/diagnostics.json`

---

### `codeag config`
Inspect and manage configuration settings:

- `codeag config show`: Print resolved settings table with masked secrets.
- `codeag config validate`: Validate active settings against operational bounds.
- `codeag config path`: Display path to user global config file.
- `codeag config init [--force]`: Create template user global config file.

---

### `codeag setup`
Interactive first-time installation and readiness verification wizard:
- `codeag setup`: Launch the 6-stage setup wizard (checks Python, Ollama, hardware, downloads installer and model with confirmation).
- `codeag setup --check`: Non-interactive, read-only diagnostic check of Python, Ollama, and model state.
- `codeag setup --skip-model`: Configure Ollama runtime without downloading the multi-GB model.
- `codeag setup --model <name>`: Configure and download an alternative model (e.g. `qwen2.5-coder:7b`).
- `codeag setup --repair`: Reset prior setup state, re-verify environment, and repair missing components.

---

### `codeag models`
Local model catalog management via Ollama:
- `codeag models list`: Display all models currently installed in local Ollama storage.
- `codeag models current`: Display active configured model and its local presence.
- `codeag models install <name>`: Download and verify a model with streaming progress bar.

---

### `codeag run <command>`
Execute a terminal command through Code AG's safety policy manager:
```powershell
codeag run "python -m pytest"
```
- Dangerous commands (destructive file deletion, arbitrary shell injection) are intercepted and rejected.
- Requires explicit user approval when configured.

---

### `codeag rollback <file>`
Restore a file to its previous state using automated backup snapshots:
```powershell
codeag rollback src/main.py [--backup-id <id>]
```

---

### `codeag git`
Git integration commands:
- `codeag git status`: Display repository branch and uncommitted modifications.
- `codeag git diff`: Display colorized syntax diff of changes.
- `codeag git branch <name>`: Create and checkout a new branch safely.
- `codeag git commit <message>`: Commit staged files with secret scanning.

---

## 3. Interactive REPL Slash Commands

When inside an interactive session (`codeag`), prefix commands with `/`:

| Command | Arguments | Description |
| :--- | :--- | :--- |
| `/help` | | Show interactive help menu |
| `/plan` | `<prompt>` | Create multi-step execution plan |
| `/tasks` | | View status of active workflow tasks |
| `/run` | `<cmd>` | Run terminal command with safety validation |
| `/test` | `[path]` | Run automated test runner |
| `/install`| `<pkg>` | Safely install Python package via pip |
| `/diff` | | Show unified Git diff of working tree |
| `/commit` | `[msg]` | Staged commit with secret scanner check |
| `/branch` | `<name>` | Create and switch to new branch |
| `/checkout`| `<name>`| Switch to existing branch |
| `/rollback`| `<file>`| Revert file from latest backup snapshot |
| `/index` | | Re-index project files and symbols |
| `/search`| `<query>`| Search indexed codebase symbols |
| `/health`| | Run subsystem health check |
| `/monitor`| | Show live subsystem monitoring status |
| `/performance`| | Run engine benchmark |
| `/config`| | Inspect active configuration |
| `/diagnostics`| `[file]`| Export JSON diagnostic report |
| `/clear` | | Clear terminal screen |
| `/exit` | | Exit interactive session |

---

## 4. Exit Codes

| Exit Code | Meaning |
| :--- | :--- |
| `0` | Success / Clean exit |
| `1` | Subsystem check failure or unhandled application error |
| `2` | Configuration validation failure |
| `130` | Interrupted by user (Ctrl+C / SIGINT) |

