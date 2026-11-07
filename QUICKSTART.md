# Quickstart Guide – Code AG

Welcome to **Code AG**! In 5 minutes, you will learn how to initialize an interactive development session, use multi-agent collaboration, inspect Git diffs, evaluate execution safely, and use built-in slash commands.

---

## 1. Start Code AG

Launch the interactive REPL in your project directory:

```powershell
codeag
```
*(or `code ag` if launcher is installed)*

You will see the startup banner displaying your active version, configured model (`qwen3:latest`), Ollama host, and current workspace directory.

---

## 2. Your First Autonomous Task

Code AG accepts natural language prompts and automatically coordinates five specialized autonomous agents:
- **Planner Agent:** Breaks down your prompt into structured dependency tasks.
- **Code Agent:** Writes and modifies code according to safety policies.
- **Debugger Agent:** Localizes syntax or runtime errors and synthesizes AST diff patches.
- **Reviewer Agent:** Inspects code quality, security issues, and policy compliance.
- **Coordinator Agent:** Orchestrates agent execution, workflow states, and retry strategies.

### Example: Build a Calculator Module
Type the following prompt into the interactive REPL:

```text
Build a Python calculator module in src/calc.py with add, subtract, multiply, and divide functions, with division-by-zero protection and unit tests in tests/test_calc.py.
```

1. **Planner Agent** generates a task graph.
2. **Code Agent** safely generates the files.
3. Before writing to disk, Code AG displays the proposed changes and requests your approval (if configured).
4. Code AG creates an automatic backup in `.codeagent/backups` before any file write.

---

## 3. Useful Interactive Slash Commands

Type `/` in the prompt to see available slash commands:

| Command | Description | Example |
| :--- | :--- | :--- |
| `/help` | Display interactive help menu and command list | `/help` |
| `/plan <task>` | Formulate a multi-step execution plan without executing | `/plan Add JWT auth` |
| `/tasks` | List pending, running, and completed workflow tasks | `/tasks` |
| `/run <command>` | Execute a safe terminal command with policy checks | `/run pytest` |
| `/test [path]` | Automatically execute project test suite | `/test tests/` |
| `/diff` | Inspect Git diff of workspace modifications | `/diff` |
| `/commit [msg]` | Commit staged changes (with secret scan and approval) | `/commit "feat: add calc"` |
| `/branch <name>` | Create and switch to a new Git branch | `/branch feat/calculator` |
| `/rollback <file>`| Restore a modified file from an automated backup | `/rollback src/calc.py` |
| `/index` | Re-index project source files and AST symbols | `/index` |
| `/search <query>`| Search project files and symbols semantically | `/search calculate` |
| `/health` | Run live health checks across all subsystems | `/health` |
| `/monitor` | Open fast status dashboard of local components | `/monitor` |
| `/performance` | Run non-LLM latency benchmarks | `/performance` |
| `/config` | View effective configuration settings | `/config` |
| `/clear` | Clear terminal screen | `/clear` |
| `/exit` | Exit the Code AG session | `/exit` |

---

## 4. One-Shot Command Line Execution

Code AG also runs directly from the terminal without entering the interactive REPL:

### Inspect System Health
```powershell
codeag health
```

### Export Diagnostic Snapshot
```powershell
codeag diagnostics --export diagnostics.json
```

### Run Local Engine Benchmark
```powershell
codeag performance
```

### Safe Shell Execution
```powershell
codeag run "python -m pytest tests/"
```

### Configuration Inspection
```powershell
codeag config show
codeag config validate
codeag config path
```

---

## 5. Next Steps

- Explore [CONFIGURATION.md](CONFIGURATION.md) for custom model selection and security policies.
- Consult [CLI_REFERENCE.md](CLI_REFERENCE.md) for exhaustive CLI arguments.
- Review [ARCHITECTURE.md](ARCHITECTURE.md) to understand the multi-agent state machine.
- Read [SECURITY.md](SECURITY.md) to review safety boundaries and secret protection.

