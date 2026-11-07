# Code AG — Advanced Local Autonomous AI Coding Assistant

Code AG is a 100% local, autonomous AI coding assistant running locally on Windows 11 powered by **Ollama** and **Qwen3 (`qwen3:latest`)**.

- **Phase 1: CLI Foundation** — Interactive REPL, one-shot mode, Pydantic Settings, diagnostics, and Rich terminal UI.
- **Phase 2: Advanced LLM Integration** — Real-time token streaming, multi-turn conversation memory, context budgeting, safe calculator tool-calling, and structured JSON validation.
- **Phase 3: Filesystem Intelligence** — Safe workspace file reading, creating, diff-editing with interactive approvals, confirmation-gated deletion, directory scanning, framework project analysis, and automated atomic backups.
- **Phase 5: Terminal and Code Execution** — Controlled Python runner, secure terminal command execution, dependency management via pip with mandatory human approval, test runner with structured reporting, process concurrency management with Windows process tree termination, multi-layer security validation, secret redaction, and audit logging.
- **Phase 6: Autonomous Debugging** — Automated error detection across 15+ Python exceptions and test failures, structured traceback parsing across Windows and chained traces, AST source code inspection, Qwen3 root cause diagnosis with confidence levels, minimal unified diff patch generation with AST syntax validation, atomic patch application with pre-patch backups and mandatory human approval, automatic test re-execution, regression verification, and Rich terminal session reporting.
- **Phase 7: Project Intelligence & Persistent Memory** — Deep project comprehension across 13+ languages and frameworks (FastAPI, Flask, Django, React, Vite, Node, Java, C/C++), non-executing dependency manifest analysis, architectural layer mapping, multi-project workspace isolation, persistent SQLite memory in WAL mode (9 relational tables, zero cross-project leakage), AST code symbol indexing, boundary-preserving chunking, import graph analysis with circular dependency detection, multimodal search (filename, exact text, regex, symbol, lexical/TF-IDF similarity), and token-budgeted context synthesis for Qwen3.
- **Phase 8: Git Integration & Safety Management** — Subprocess-based local Git engine (`shell=False`), machine-readable status (`--porcelain=v1`), staged and unstaged unified diffs with byte limits and secret scrubbing, Git refspec branch validation, collision detection and dirty-tree safety checks, controlled commit workflow with explicit file staging and commit hash verification, pre-commit secret scanning, verifiable SHA-256 pre-modification file backups with conflict protection, centralized 3-tier command permission policy (`ALLOW`, `DENY`, `REQUIRE_APPROVAL`), protected path manager with symlink escape detection, single-use time-bound (TTL) approvals, persistent SQLite + JSONL security audit logger with secret redaction, and 40 registered safe tools.
- **Phase 9: Advanced Multi-Agent Architecture & Workflow Orchestration** — Coordinated multi-agent system comprising 5 specialized agents (Planner, Code, Debugger, Reviewer, Coordinator), in-process validated message bus with impersonation protection, agent registry, canonical file-level concurrency locks, DAG task scheduling with cycle detection and cascading failure blocking, configurable workflow templates (`BUILD_PROJECT`, `FIX_BUG`, `CODE_REVIEW`, `ADD_FEATURE`, `REFACTOR_PROJECT`), persistent SQLite WAL state management (`data/workflows/workflows.db`), 5-category independent code review with rework loop, and 45 registered safe tools.
- **Phase 10: Production-Ready CLI, Optimization, Monitoring & Packaging** — Sub-50ms fast startup with lazy LLM initialization, centralized structured JSON logging with rotating file handler and automated credential redaction, performance profiler measuring AST calculator and path security latency, full subsystem monitoring dashboard (`codeag monitor`), multi-tiered configuration precedence engine with secret masking (`codeag config`), comprehensive system diagnostics export (`codeag diagnostics`), Windows 11 launcher integration (`code ag` and `codeag`), CI/CD automation, and full production documentation suite.

---

## Documentation Suite

Comprehensive production guides are available across dedicated documents:

- **[Installation Guide](INSTALLATION.md)** — Step-by-step setup for Windows 11, Linux, macOS, Ollama, and virtual environments.
- **[Quickstart Guide](QUICKSTART.md)** — 5-minute tutorial covering interactive sessions, prompt execution, and slash commands.
- **[Configuration Guide](CONFIGURATION.md)** — Multi-tier configuration precedence, settings reference, and secret masking.
- **[CLI Reference Manual](CLI_REFERENCE.md)** — Complete command-line manual, subcommands, flags, and REPL slash commands.
- **[Architecture Deep Dive](ARCHITECTURE.md)** — System architecture, subsystem layers, component interactions, and data flows.
- **[Security & Safety Policy](SECURITY.md)** — Sandbox boundaries, path protections, automated backups, and secret redaction rules.
- **[Troubleshooting Guide](TROUBLESHOOTING.md)** — Common operational diagnoses, Ollama connectivity solutions, and FAQ.
- **[Contributing Guide](CONTRIBUTING.md)** — Developer workflow, architectural invariants, code standards, and PR process.
- **[Changelog](CHANGELOG.md)** — Detailed version history across all 10 project development phases.

---

## Architecture & Project Structure

Code AG is built with modular, testable, decoupled components:

```text
CodeAgent/
│
├── codeagent/
│   ├── __init__.py               # Package metadata and version
│   ├── main.py                   # Application entrypoint
│   ├── cli.py                    # Typer & Rich CLI with slash commands & approval dialogs
│   ├── banner.py                 # Professional ASCII startup banner with responsive terminal layout
│   │
│   ├── config/
│   │   ├── __init__.py           # Config module exports
│   │   └── settings.py           # Pydantic Settings (Phases 1-6 configuration)
│   │
│   ├── context/
│   │   ├── __init__.py           # Context exports
│   │   ├── manager.py            # Budget calculation and history trimming
│   │   └── token_counter.py      # Conservative heuristic token estimation
│   │
│   ├── conversation/
│   │   ├── __init__.py           # Conversation exports
│   │   ├── manager.py            # Multi-turn state and session orchestration
│   │   └── storage.py            # Local JSON persistence & secret scrubbing
│   │
│   ├── debugging/                # Phase 6: Autonomous Debugging Subsystem
│   │   ├── __init__.py           # Debugging subsystem exports
│   │   ├── code_inspector.py     # Source-code AST context, imports, and related tests
│   │   ├── debugger.py           # 16-step autonomous debugging loop controller
│   │   ├── error_detector.py     # Detects Python exceptions, assertion failures, exit codes
│   │   ├── fix_generator.py      # Minimal patch generation with unified diffs & AST syntax checks
│   │   ├── patch_manager.py      # Atomic patch application, backups, approval gates, rollback
│   │   ├── regression_checker.py # Verification status & collateral regression detection
│   │   ├── report_generator.py   # Rich terminal & markdown debugging report generation
│   │   ├── retest_manager.py     # Test re-execution, before/after metrics comparison
│   │   ├── root_cause_analyzer.py# Qwen3 diagnosis with confidence classification
│   │   └── traceback_parser.py   # Pydantic parsing of Windows & chained tracebacks
│   │
│   ├── execution/                # Phase 5: Terminal and Code Execution Subsystem
│   │   ├── __init__.py           # Execution subsystem exports
│   │   ├── audit_logger.py       # JSONL audit log with secret redaction
│   │   ├── command_validator.py  # 5-layer command validation & injection prevention
│   │   ├── dependency_manager.py # Pip environment detection & approval-gated installation
│   │   ├── manager.py            # Central coordinator connecting execution tools & CLI
│   │   ├── output_capture.py     # Stream capture, size caps, secret scrubbing, ExecutionResult
│   │   ├── permission_manager.py # Human approval rules, execution plans & callbacks
│   │   ├── process_manager.py    # Process lifecycle, concurrency ceiling (3), taskkill tree kill
│   │   ├── python_runner.py      # Python script & code snippet execution in active venv
│   │   ├── terminal.py           # Controlled direct binary, CMD, & PowerShell execution
│   │   └── test_runner.py        # Pytest & Unittest runner with structured pass/fail reports
│   │
│   ├── filesystem/               # Phase 3: Filesystem Intelligence Subsystem
│   │   ├── __init__.py           # Subsystem exports
│   │   ├── path_validator.py     # Canonicalization, traversal prevention, sensitive file guard
│   │   ├── backup.py             # Atomic backups (.codeagent/backups/) with SHA256 & restore
│   │   ├── reader.py             # Safe file reading, line ranges, encoding & binary guards
│   │   ├── writer.py             # Atomic file creation and overwrite protection
│   │   ├── editor.py             # Unified diff generation, user approvals & atomic replacement
│   │   ├── deleter.py            # Single-file deletion with mandatory confirmation
│   │   ├── scanner.py            # Recursive tree traversal with ignore patterns & limits
│   │   ├── project_analyzer.py   # Framework detection (FastAPI, Django, Flask, React, Node)
│   │   └── manager.py            # Central coordinator connecting filesystem tools & CLI
│   │
│   ├── indexing/                 # Phase 7: Code Indexing Subsystem
│   │   ├── __init__.py           # Subsystem exports
│   │   ├── chunker.py            # AST & boundary-preserving code chunking
│   │   ├── file_watcher.py       # Timestamp & hash-based incremental change detector
│   │   ├── import_analyzer.py    # Import graph parser & circular dependency detector
│   │   ├── indexer.py            # Central project indexer & traversal coordinator
│   │   ├── search_engine.py      # Multimodal search (glob, exact, regex, symbol, chunk)
│   │   ├── symbol_extractor.py   # AST & regex symbol extraction (Py, JS/TS, Java, C/C++)
│   │   └── vector_search.py      # Local lexical/TF-IDF cosine similarity search
│   │
│   ├── intelligence/             # Phase 7: Project Intelligence Subsystem
│   │   ├── __init__.py           # Subsystem exports
│   │   ├── architecture_mapper.py# Layer categorization (CLI, API, Domain, Data, Test)
│   │   ├── context_builder.py    # Token-budgeted context assembler for Qwen3
│   │   ├── dependency_analyzer.py# Non-executing manifest analyzer (pip, npm, gradle, etc.)
│   │   ├── language_detector.py  # Language distribution & primary language detection
│   │   ├── project_analyzer.py   # Comprehensive framework, build, and deploy analysis
│   │   └── project_manager.py    # Multi-project workspace coordinator & isolation
│   │
│   ├── memory/                   # Phase 7: Persistent Memory Subsystem
│   │   ├── __init__.py           # Subsystem exports
│   │   ├── conversation_memory.py# Session persistence & extractive/LLM summarization
│   │   ├── memory_cleanup.py     # Deduplication, secret scrubbing, and SQLite VACUUM
│   │   ├── memory_manager.py     # Central memory coordinator facade
│   │   ├── memory_retriever.py   # Scored fact & conversation memory retrieval
│   │   ├── memory_store.py       # SQLite engine with WAL mode & 9 relational tables
│   │   └── project_memory.py     # Scoped project facts with secret scrubbing
│   │
│   ├── git/                      # Phase 8: Git Subsystem
│   │   ├── __init__.py           # Subsystem exports
│   │   ├── branch_manager.py     # Ref validation, listing, switching, dirty-tree safety
│   │   ├── commit_manager.py     # Controlled commit workflow, explicit staging, hash check
│   │   ├── diff_manager.py       # Staged, unstaged, file diffs, binary & secret guards
│   │   ├── git_manager.py        # Unified Git coordinator facade
│   │   ├── repo_detector.py      # Git CLI availability & repo boundary validation
│   │   └── status_manager.py     # Machine-readable status parser (--porcelain=v1)
│   │
│   ├── safety/                   # Phase 8: Safety & Security Subsystem
│   │   ├── __init__.py           # Subsystem exports
│   │   ├── approval_manager.py   # Single-use, time-bound (TTL) cryptographically tied approvals
│   │   ├── audit_logger.py       # Persistent SQLite + JSONL immutable audit logger
│   │   ├── backup_manager.py     # Pre-modification backups, SHA-256 integrity, conflict detection
│   │   ├── permission_manager.py # 3-tier command policy (ALLOW, DENY, REQUIRE_APPROVAL)
│   │   └── protected_paths.py    # Path traversal, symlink escapes, sensitive files guard
│   │
│   ├── agents/                   # Phase 9: Advanced Multi-Agent Architecture Subsystem
│   │   ├── __init__.py           # Multi-agent subsystem exports
│   │   ├── agent_factory.py      # Factory instantiating role-scoped agents with tools
│   │   ├── agent_messages.py     # Pydantic structured message bus & impersonation guard
│   │   ├── agent_registry.py     # Central discovery and registry for active agents
│   │   ├── base_agent.py         # Abstract BaseAgent, AgentRole, AgentStatus, AgentContext
│   │   ├── coder_agent.py        # Code generation, modification, file locks & AST verification
│   │   ├── coordinator_agent.py  # Orchestrator, ThreadPoolExecutor parallel DAG execution & retry loop
│   │   ├── debugger_agent.py     # Error diagnosis, traceback parsing & autonomous patch loop
│   │   ├── file_locks.py         # Granular canonical file locking preventing write races
│   │   ├── planner_agent.py      # Goal decomposition, task DAG generation & cycle validation
│   │   ├── reviewer_agent.py     # 5-factor code review (Quality, Security, Tests, Performance)
│   │   ├── task_scheduler.py     # DAG dependency resolver, topological sort & cascading block
│   │   ├── workflow_engine.py    # High-level engine runner, pause/cancel/resume coordinator
│   │   ├── workflow_state.py     # Persistent SQLite WAL state manager (data/workflows/workflows.db)
│   │   └── workflow_templates.py # Built-in workflow templates (BUILD, FIX, REVIEW, FEATURE, REFACTOR)
│   │
│   ├── llm/
│   │   ├── __init__.py           # LLM exports
│   │   ├── client.py             # Ollama SDK client, error handling, diagnostics
│   │   ├── streaming.py          # Real-time token streaming engine
│   │   └── structured.py         # Pydantic structured output & ErrorAnalysis
│   │
│   └── tools/
│       ├── __init__.py           # Tools exports
│       ├── calculator.py         # Safe AST-based arithmetic (no unrestricted eval)
│       ├── executor.py           # Argument validation & tool loop orchestration
│       └── registry.py           # Safe tool definitions (45 tools: Math, FS, Exec, Debug, Memory, Git, Safety, Workflows)
│
├── tests/
│   ├── agents/                   # Phase 9 Multi-Agent test suite (36 tests)
│   │   ├── test_agent_messages.py
│   │   ├── test_agent_registry.py
│   │   ├── test_base_agent.py
│   │   ├── test_coder_agent.py
│   │   ├── test_coordinator_agent.py
│   │   ├── test_debugger_agent.py
│   │   ├── test_file_locks.py
│   │   ├── test_multiagent_integration_e2e.py
│   │   ├── test_planner_agent.py
│   │   ├── test_reviewer_agent.py
│   │   ├── test_task_scheduler.py
│   │   └── test_workflow_state.py
│   │
│   ├── git/                      # Phase 8 Git test suite (33 tests)
│   │   ├── test_branch_manager.py
│   │   ├── test_commit_manager.py
│   │   ├── test_diff_manager.py
│   │   ├── test_git_integration_e2e.py
│   │   ├── test_repo_detector.py
│   │   └── test_status_manager.py
│   │
│   ├── safety/                   # Phase 8 Safety test suite (30 tests)
│   │   ├── test_approval_manager.py
│   │   ├── test_backup_manager.py
│   │   ├── test_protected_paths.py
│   │   ├── test_safety_permission_manager.py
│   │   └── test_security_audit_logger.py
│   ├── debugging/                # Phase 6 debugging test suite (42 unit tests)
│   │   ├── test_code_inspector.py
│   │   ├── test_debugger.py
│   │   ├── test_error_detector.py
│   │   ├── test_fix_generator.py
│   │   ├── test_patch_manager.py
│   │   ├── test_regression_checker.py
│   │   ├── test_report_generator.py
│   │   ├── test_retest_manager.py
│   │   ├── test_root_cause_analyzer.py
│   │   └── test_traceback_parser.py
│   │
│   ├── execution/                # Phase 5 execution test suite (37 unit tests)
│   │   ├── test_audit_logger.py
│   │   ├── test_command_validator.py
│   │   ├── test_dependency_manager.py
│   │   ├── test_execution_manager.py
│   │   ├── test_output_capture.py
│   │   ├── test_permission_manager.py
│   │   ├── test_process_manager.py
│   │   ├── test_python_runner.py
│   │   ├── test_terminal.py
│   │   └── test_test_runner.py
│   │
│   ├── indexing/                 # Phase 7 indexing test suite (16 unit tests)
│   │   ├── test_chunker.py
│   │   ├── test_file_watcher.py
│   │   ├── test_import_analyzer.py
│   │   ├── test_indexer.py
│   │   ├── test_search_engine.py
│   │   ├── test_symbol_extractor.py
│   │   └── test_vector_search.py
│   │
│   ├── intelligence/             # Phase 7 intelligence test suite (11 unit tests)
│   │   ├── test_architecture_mapper.py
│   │   ├── test_context_builder.py
│   │   ├── test_dependency_analyzer.py
│   │   ├── test_e2e_three_projects.py
│   │   ├── test_language_detector.py
│   │   ├── test_project_analyzer.py
│   │   └── test_project_manager.py
│   │
│   ├── memory/                   # Phase 7 persistent memory test suite (16 unit tests)
│   │   ├── test_conversation_memory.py
│   │   ├── test_memory_cleanup.py
│   │   ├── test_memory_manager.py
│   │   ├── test_memory_retriever.py
│   │   ├── test_memory_store.py
│   │   └── test_project_memory.py
│   │
│   ├── test_banner.py            # Startup banner rendering, dynamic metadata & offline state tests
│   ├── test_config.py            # Configuration unit tests
│   ├── test_context.py           # Token estimation and context window tests
│   ├── test_conversation.py      # Conversation manager and storage tests
│   ├── test_filesystem.py        # Complete Phase 3 filesystem intelligence test suite
│   ├── test_integration.py       # Live Ollama integration tests (optional)
│   ├── test_streaming.py         # Streaming engine unit tests
│   ├── test_structured.py        # Structured JSON validation tests
│   └── test_tools.py             # Calculator and tool-calling execution tests
│
├── data/
│   └── conversations/            # Local JSON conversation history files
│
├── .codeagent/
│   ├── audit/                    # Execution audit logs (execution.jsonl)
│   └── backups/                  # Automated timestamped file backups before edits/deletions/patches
│
├── .env                          # Local environment variable configuration
├── .gitignore                    # Git ignore rules
├── pyproject.toml                # Dependencies, console scripts, and test settings
└── README.md                     # Documentation
```

---

## Phase 6: Autonomous Debugging Capabilities

### 1. Robust Error Detection (`error_detector.py`)
- **Exception Coverage:** Detects and parses over 15+ standard Python exceptions (`SyntaxError`, `IndentationError`, `TabError`, `ImportError`, `ModuleNotFoundError`, `NameError`, `TypeError`, `AttributeError`, `IndexError`, `KeyError`, `ValueError`, `FileNotFoundError`, `ZeroDivisionError`, `AssertionError`, `RuntimeError`, etc.).
- **Execution Integration:** Directly inspects Phase 5 `ExecutionResult` and `TestReport` objects, extracting error type, message, target file, line number, exit code, and test failure metadata.
- **Untrusted Input Guard:** Treats raw terminal output and error strings strictly as untrusted data without execution.

### 2. Structured Traceback Parsing (`traceback_parser.py`)
- **Windows Path Handling:** Safely parses Windows absolute paths (`C:\...`), mixed slashes, and relative paths.
- **Chained Exceptions:** Automatically handles chained tracebacks (`The above exception was the direct cause...` / `During handling...`), parsing both cause and resulting exceptions.
- **Syntax Error Layouts:** Accurately parses Python SyntaxError and IndentationError caret blocks.
- **Workspace Priority:** Automatically identifies the primary failure frame residing within the active project workspace rather than deep standard library or virtual environment files.

### 3. Source-Code AST Inspection (`code_inspector.py`)
- **Context Extraction:** Reads target files and formats a contextual snippet around the failing line with line numbers and a current line pointer (`>`).
- **AST Symbol Extraction:** Identifies the enclosing function and class definition containing the error line.
- **Import Analysis:** Parses the file's abstract syntax tree to extract all imported modules.
- **Test Discovery:** Discovers corresponding test files (`test_<name>.py` or test files importing the affected module).
- **Workspace Security:** Confined strictly within the workspace; respects sensitive file guards (`.env`, `.git`) and file size limits.

### 4. Root Cause Analysis (`root_cause_analyzer.py`)
- **Qwen3 Integration:** Formulates structured root cause diagnoses using local Ollama function calling or Pydantic schemas.
- **Confidence Classification:** Distinguishes between:
  - `CONFIRMED`: Direct, indisputable evidence (e.g., zero divisor at specified line).
  - `LIKELY`: Highly probable cause based on type or syntax analysis.
  - `HYPOTHESIS`: Runtime condition requiring verification.
- **Deterministic Heuristics:** Includes a robust offline heuristic diagnosis engine ensuring reliable operation even if Ollama is temporarily offline.

### 5. Minimal Fix Generation (`fix_generator.py`)
- **Unified Diff Generation:** Synthesizes minimal diffs using standard `difflib.unified_diff`.
- **AST Syntax Validation:** Validates that the modified file produces valid Python syntax via `ast.parse` before proposing the patch.
- **Read-Only Generation:** Files on disk are **never** modified during fix generation. Fixes are purely held in memory as `ProposedFix` objects.
- **Dependency Awareness:** Identifies when an error requires package installation rather than code edits.

### 6. Atomic Patch Application & Rollback (`patch_manager.py`)
- **Mandatory Human Approval:** The LLM cannot self-approve modifications. Every patch displays a clear unified diff in the terminal and requires human user approval (`[y/N]`).
- **Concurrent Conflict Guard:** Verifies that target files on disk have not been altered since inspection before applying changes.
- **Pre-Patch Backups:** Automatically creates an atomic backup in `.codeagent/backups/` before any file write.
- **Atomic Disk Replacement:** Writes changes to a temporary file in the target directory and replaces atomically via `os.replace`.
- **Full Rollback Support:** Restores pre-patch backups via `/rollback [id]` or the Python API.

### 7. Automated Retesting & Regression Checking (`retest_manager.py`, `regression_checker.py`)
- **Verification Execution:** Automatically reruns the previously failing test suite or script using Phase 5 execution engines.
- **Never Disables Tests:** Tests are never modified, skipped, or disabled to artificially produce passing results.
- **Regression Detection:** Compares pre-fix and post-fix test results to catch any newly introduced test failures.
- **Status Classification:**
  - `FIXED_AND_VERIFIED`: Failing test resolved, zero regressions, 100% passing.
  - `PARTIALLY_FIXED`: Failure count reduced, but some tests remain failing.
  - `STILL_FAILING`: Error persists after patch application.
  - `VERIFICATION_BLOCKED`: Retest crashed or encountered environment issues.
  - `FIX_APPLIED_UNVERIFIED`: Patch applied without verification.

### 8. 16-Step Debugger Controller (`debugger.py`)
Orchestrates the complete autonomous debugging loop:
1. Receive failure evidence or execute target test.
2. Detect error and extract metadata.
3. Parse the traceback into structured stack frames.
4. Inspect affected source code and enclosing symbols.
5. Collect relevant test evidence.
6. Analyze root cause and determine confidence level.
7. Generate minimal proposed fix.
8. Render unified diff for review.
9. Request explicit user approval (`[y/N]`).
10. Create an automated pre-patch backup.
11. Apply approved patch atomically.
12. Rerun previously failing test.
13. Run regression tests across the project.
14. Inspect new results and check for regressions.
15. Continue diagnosis if needed within configured limits:
    - `MAX_DEBUG_ITERATIONS=5`
    - `MAX_FIX_ATTEMPTS=3`
    - `MAX_RETEST_ATTEMPTS=3`
    - `DEBUG_TIMEOUT_SECONDS=600`
16. Generate structured Markdown and Rich terminal reports.

---

## Registered Safe Tools (40 Tools Total)

| Tool Name | Parameters | Category | Description |
|:---|:---|:---:|:---|
| `calculate` | `operation`, `a`, `b` | Math | Basic arithmetic (`add`, `subtract`, `multiply`, `divide`). |
| `add` | `a`, `b` | Math | Add two numbers. |
| `subtract` | `a`, `b` | Math | Subtract `b` from `a`. |
| `multiply` | `a`, `b` | Math | Multiply two numbers. |
| `divide` | `a`, `b` | Math | Safely divide `a` by `b` (detects division by zero). |
| `evaluate_expression` | `expression` | Math | Safe AST arithmetic evaluation (no `eval`). |
| `read_file` | `path`, `start_line?`, `end_line?` | Filesystem | Read workspace text file with optional line slicing. |
| `create_file` | `path`, `content`, `overwrite?` | Filesystem | Create a new file safely in the workspace. |
| `edit_file` | `path`, `search_target?`, `replacement?`, `new_content?` | Filesystem | Edit a file with unified diff and mandatory approval. |
| `delete_file` | `path`, `confirmed?` | Filesystem | Delete an individual file with confirmation. |
| `list_directory` | `path?`, `max_depth?` | Filesystem | List files and directories directly under target path. |
| `scan_project` | `path?` | Filesystem | Recursively scan directory tree and file statistics. |
| `analyze_project` | `path?` | Filesystem | Inspect project type, frameworks, entry points, dependencies. |
| `run_python` | `script_path?`, `code?`, `args?` | Execution | Run a Python script or code snippet in the active environment. |
| `execute_command` | `command`, `args?`, `use_shell?`, `shell_type?` | Execution | Run an approved terminal command with security validation. |
| `install_dependency` | `package_name`, `version_spec?` | Execution | Install a Python package via pip (mandatory human approval). |
| `run_tests` | `test_path?`, `framework?` | Execution | Run tests using pytest or unittest and return structured reports. |
| `get_process_status` | `process_id?` | Execution | Check status of running or completed execution processes. |
| `cancel_execution` | `process_id` | Execution | Terminate a running process and its child tree safely. |
| `diagnose_error` | `error_text`, `target_file?`, `target_line?` | Debugging | Analyze and diagnose Python errors, tracebacks, and test failures. |
| `retest_code` | `test_path?`, `script_path?` | Debugging | Run automated retesting of a test suite or script to verify fixes. |
| `search_code` | `query`, `search_type?`, `file_extension?`, `limit?` | Intelligence | Search code symbols, exact text, regex, or TF-IDF vectors. |
| `get_project_architecture` | `project_path?` | Intelligence | Retrieve detected frameworks, entry points, and directory map. |
| `get_project_memory` | `project_id?`, `key?`, `category?`, `limit?` | Intelligence | Retrieve persistent project knowledge, facts, and conventions. |
| `store_project_memory` | `key`, `value`, `category?`, `confidence?` | Intelligence | Record architectural decision or convention into persistent memory. |
| `git_repository_info` | *(none)* | Git & Safety | Check if workspace is a Git repository, active branch, and HEAD commit hash. |
| `git_status` | *(none)* | Git & Safety | Inspect staged, unstaged, untracked files, and merge conflict status. |
| `git_diff` | `staged?`, `file_path?` | Git & Safety | Retrieve unified diff with secret scrubbing and output truncation. |
| `git_list_branches` | *(none)* | Git & Safety | List all local repository branches and active HEAD. |
| `git_create_branch` | `branch_name`, `switch?` | Git & Safety | Create a new local Git branch with ref name validation and collision prevention. |
| `git_switch_branch` | `branch_name` | Git & Safety | Switch to an existing branch safely with dirty working tree checks. |
| `git_commit_changes` | `message?`, `files?` | Git & Safety | Controlled Git commit with explicit staging, secret scanning, approval, and verification. |
| `check_command_permission` | `command` | Git & Safety | Evaluate command against 3-tier security policy (`ALLOW`, `DENY`, `REQUIRE_APPROVAL`). |
| `list_protected_paths` | *(none)* | Git & Safety | List all default and user-configured protected files, directories, and patterns. |
| `add_protected_path` | `path_or_pattern` | Git & Safety | Register an additional path or pattern to protect from agent write/delete. |
| `remove_protected_path` | `path_or_pattern` | Git & Safety | Remove a previously registered custom protected path. |
| `create_backup` | `file_path` | Git & Safety | Create a verifiable SHA-256 backup snapshot of an existing workspace file. |
| `list_backups` | `file_path?` | Git & Safety | View file backup archive history, timestamps, and SHA-256 hashes. |
| `restore_backup` | `backup_id`, `force?` | Git & Safety | Restore file from backup with SHA-256 integrity check and conflict warning. |
| `get_audit_log` | `operation_id?`, `operation_type?`, `limit?` | Git & Safety | Query immutable security audit logs to inspect past operations and outcomes. |

---

## Interactive Slash Commands

| Command | Category | Action |
|:---|:---:|:---|
| `/help` | General | Display interactive slash commands help table. |
| `/debug [path]` | Debugging | Autonomous 16-step diagnosis, patch generation, approval, and verification. |
| `/diagnose [err]` | Debugging | Analyze and explain an error traceback or failure message. |
| `/fix <file>` | Debugging | Generate a minimal unified diff repair for a diagnosed error. |
| `/retest [path]` | Debugging | Rerun previous failing test suite and check for regressions. |
| `/rollback [id]` | Debugging | Restore pre-debug backup or revert the last applied patch. |
| `/debug-report` | Debugging | Display the structured report from the most recent debugging session. |
| `/python <file> [a]` | Execution | Run a Python script in the active virtual environment. |
| `/run <command>` | Execution | Execute an approved terminal command with security validation. |
| `/install <pkg>` | Execution | Install a Python package with interactive approval dialog. |
| `/test [path]` | Execution | Discover and run test suites using pytest or unittest. |
| `/processes` | Execution | List active background processes and their resource status. |
| `/cancel <pid>` | Execution | Terminate a running process and its child tree safely. |
| `/workspace [path]` | Filesystem | Show current workspace root or switch to a new directory. |
| `/scan [path]` | Filesystem | Recursively scan workspace tree, format hierarchy and file stats. |
| `/tree [path]` | Filesystem | Alias for `/scan`. |
| `/project [path]` | Filesystem | Analyze project architecture, detected frameworks, and dependencies. |
| `/read <path> [s] [e]` | Filesystem | Read file contents directly with optional start/end line bounds. |
| `/newfile <path>` | Filesystem | Create a new file with interactive multiline input. |
| `/edit <path>` | Filesystem | Edit a file interactively with diff review and approval. |
| `/delete <path>` | Filesystem | Delete an individual file after interactive confirmation. |
| `/backups` | Filesystem | View all automatic file backups created before edits/deletions. |
| `/restore <id>` | Filesystem | Restore a file from an automatic backup ID. |
| `/git [status/diff/branch/commit]` | Git | Git operations: status, diff, branches, switch, and commit. |
| `/safety [paths/add/remove/check]` | Safety | Manage protected paths and evaluate terminal command permissions. |
| `/backup [list/create/restore]` | Safety | Manage and restore pre-modification SHA-256 file snapshots. |
| `/project [list/switch/new]` | Intelligence | List registered workspaces, switch active project, or register new project path. |
| `/index [--rebuild]` | Indexing | Perform incremental or full code indexing and symbol extraction. |
| `/search <query> [--type]` | Search | Multimodal codebase search (`symbol`, `filename`, `exact`, `regex`, `vector`). |
| `/memory [store/list/cleanup]` | Memory | Inspect, record, or purge persistent project facts and session memories. |
| `/context` | Intelligence | Display current token-budgeted project context bundle prepared for Qwen3. |
| `/new` | Session | Start a fresh conversation session with clean context. |
| `/history` | Session | View recent conversation turns in the active session. |
| `/save [name]` | Session | Save conversation history to `data/conversations/`. |
| `/load [name]` | Session | View saved conversations or load one by ID. |
| `/model [name]` | Session | View installed Ollama models or switch active model. |
| `/clear` | Session | Clear terminal screen and re-render header banner. |
| `/exit` or `/quit` | Session | Exit interactive mode. |

---

## Configuration Settings

Configured via `.env` or environment variables:

```ini
APP_NAME=Code AG
APP_VERSION=0.1.0
OLLAMA_HOST=http://localhost:11434
MODEL_NAME=qwen3:latest
REQUEST_TIMEOUT=300
TEMPERATURE=0.2
SHOW_STARTUP_BANNER=true

# Phase 2 Context Settings
CONTEXT_WINDOW=8192
MAX_OUTPUT_TOKENS=2048
MAX_HISTORY_MESSAGES=30
CONTEXT_RESERVE_TOKENS=1024
MAX_TOOL_ITERATIONS=5
CONVERSATION_STORAGE_PATH=data/conversations

# Phase 3 Filesystem Settings
WORKSPACE_ROOT=
MAX_FILE_SIZE_MB=5
MAX_SCAN_DEPTH=8
MAX_SCAN_ENTRIES=5000
BACKUP_ENABLED=true
REQUIRE_WRITE_APPROVAL=true
REQUIRE_DELETE_APPROVAL=true
BACKUP_DIRECTORY=.codeagent/backups

# Phase 5 Execution Settings
EXECUTION_ENABLED=true
EXECUTION_TIMEOUT_SECONDS=120
MAX_OUTPUT_SIZE_MB=5
MAX_CONCURRENT_PROCESSES=3
REQUIRE_PYTHON_APPROVAL=true
REQUIRE_DEPENDENCY_APPROVAL=true
REQUIRE_COMMAND_APPROVAL=true
EXECUTION_WORKSPACE_ONLY=true
EXECUTION_AUDIT_ENABLED=true
AUDIT_LOG_PATH=.codeagent/audit/execution.jsonl

# Phase 6 Autonomous Debugging Settings
MAX_DEBUG_ITERATIONS=5
MAX_FIX_ATTEMPTS=3
MAX_RETEST_ATTEMPTS=3
DEBUG_TIMEOUT_SECONDS=600
REQUIRE_PATCH_APPROVAL=true

# Phase 7 Project Intelligence & Persistent Memory Settings
PROJECT_DATA_PATH=data/projects
PROJECT_INDEX_ENABLED=true
MAX_INDEX_FILE_SIZE_MB=5
MAX_INDEX_FILES=20000
INDEX_CHUNK_SIZE=1200
INDEX_OVERLAP=150
INDEX_EXCLUDED_DIRS=.git,.venv,venv,node_modules,__pycache__,dist,build,.codeagent
MEMORY_ENABLED=true
MEMORY_MAX_RESULTS=10
SEMANTIC_SEARCH_ENABLED=false

# Phase 8 Git Integration & Safety Management Settings
GIT_ENABLED=true
GIT_REQUIRE_APPROVAL=true
GIT_REQUIRE_COMMIT_APPROVAL=true
GIT_REQUIRE_BRANCH_APPROVAL=true
GIT_BLOCK_FORCE_PUSH=true
GIT_BLOCK_DESTRUCTIVE_COMMANDS=true
BACKUP_BEFORE_WRITE=true
BACKUP_STORAGE_PATH=data/backups
COMMAND_POLICY_ENABLED=true
COMMAND_DEFAULT_POLICY=REQUIRE_APPROVAL
PROTECTED_PATHS_ENABLED=true
PROTECTED_PATHS=.git,.env,.venv,venv,node_modules,__pycache__
AUDIT_LOG_ENABLED=true
AUDIT_STORAGE_PATH=data/audit
SECRET_SCAN_BEFORE_COMMIT=true

# Phase 9 Multi-Agent Architecture & Workflow Settings
AGENT_MODEL=qwen3:latest
PLANNER_MODEL=qwen3:latest
CODER_MODEL=qwen3:latest
DEBUGGER_MODEL=qwen3:latest
REVIEWER_MODEL=qwen3:latest
MAX_WORKFLOW_TASKS=50
MAX_AGENT_ITERATIONS=20
MAX_AGENT_RETRIES=2
MAX_WORKFLOW_RETRIES=3
MAX_PARALLEL_AGENTS=2
MAX_WORKFLOW_TIMEOUT_SECONDS=1800
MAX_DEBUG_ATTEMPTS=3
MAX_REVIEW_REVISIONS=2
WORKFLOW_STORAGE_PATH=data/workflows
```

---

## Phase 8: Git Integration & Safety Management Architecture

Phase 8 equips Code AG with enterprise-grade Git version control capabilities and an unbreakable safety and permission subsystem. All security decisions are rigorously enforced in deterministic Python code, never delegated to the LLM.

### 1. Git Subsystem (`codeagent/git/`)
- **RepoDetector**: Inspects workspace root for `.git` boundary, verifies Git CLI binary availability, checks detached HEAD states, identifies empty (no-commit) repos, and prevents symlink escape.
- **StatusManager**: Executes `git status --porcelain=v1 --branch` using safe argument arrays (`shell=False`). Correctly handles paths with whitespace, octal escapes, and identifies unmerged conflict files (`UU`, `AA`, `UD`).
- **DiffManager**: Generates unified diffs for working tree, staged (`--cached`), or specific files. Enforces output size byte limits (default 50 KB), skips binary files safely, and scrubs sensitive secrets/tokens (`sk-...`, `ghp_...`, passwords).
- **BranchManager**: Validates branch names according to strict Git refspec rules (prohibiting `..`, `~`, `^`, `:`, `?`, `*`, `[`, `\`, leading/trailing slashes). Checks branch collisions, blocks dirty working-tree switching that would destroy uncommitted modifications, and enforces user approval.
- **CommitManager**: Strictly controlled commit workflow:
  1. Inspects repository status and validates uncommitted changes.
  2. Stages user-specified files explicitly (never wildcards or `git add .`).
  3. Previews staged diff and scans staged contents for exposed secrets (API keys, tokens, passwords).
  4. Generates Conventional Commit message suggestions (`feat:`, `fix:`, `refactor:`, `docs:`).
  5. Requires human confirmation before commit execution.
  6. Executes `git commit -m <msg>` and verifies commit existence via `git rev-parse HEAD`.
- **GitManager**: Unified facade coordinating detection, status, diff, branch, and commit managers.

### 2. Safety & Permission Subsystem (`codeagent/safety/`)
- **ProtectedPathsManager**: Canonicalizes workspace paths to prevent directory traversal (`../`) and symlink escapes. Enforces default protected directories (`.git`, `.env`, `.venv`, system directories) and sensitive file patterns (`*.pem`, `*.key`, `id_rsa`, `credentials.json`, `secrets.json`, backup and audit dirs). Provides CLI and agent tools to add/remove custom protection rules.
- **SafetyPermissionManager**: Centralized 3-tier command permission policy engine:
  - `ALLOW`: Safe, read-only inspection commands (`git status`, `git diff`, `git log`, `dir`, `ls`, `cat`).
  - `REQUIRE_APPROVAL`: Mutating commands requiring explicit approval (`git commit`, `git checkout -b`, `pip install`, file writes).
  - `DENY`: Dangerous and destructive commands blocked outright (`git push --force`, `git reset --hard`, `git clean -fd`, `rm -rf`, `del /s`, command chaining/injection like `;`, `&&`, `|`, `$(...)`).
- **ApprovalManager**: Cryptographically secure, single-use, time-bound (TTL) approval token system preventing token reuse or replay attacks.
- **SafetyBackupManager**: Creates pre-modification snapshots in `data/backups/` indexed with SHA-256 integrity hashes. Supports single-file restore with conflict detection to prevent overwriting newer external modifications without user confirmation.
- **SecurityAuditLogger**: Immutable append-only audit trail recorded simultaneously in SQLite WAL mode (`data/audit/audit.db`) and structured JSONL (`audit.jsonl`). Automatically redacts secrets, credentials, and sensitive tokens from audit logs.

### 3. CLI Subcommands & Interactive REPL

```powershell
# Git operations
codeagent git status
codeagent git diff [--staged] [--file <path>]
codeagent git branch [--list] [--create <name>] [--switch <name>]
codeagent git commit [-m "message"] [--files file1,file2]

# Safety operations
codeagent safety paths
codeagent safety add <path-or-pattern>
codeagent safety check "<command-string>"
codeagent safety audit [--type <operation_type>] [--limit 20]

# Backup operations
codeagent backup list [--file <path>]
codeagent backup create <file-path>
codeagent backup restore <backup-id> [--force]
```

Interactive REPL commands:
- `/git status`, `/git diff`, `/git branch`, `/git commit`
- `/safety paths`, `/safety add`, `/safety check`, `/safety audit`
- `/backup list`, `/backup create`, `/backup restore`

---

## Phase 9: Advanced Multi-Agent Architecture & Workflow Orchestration

Phase 9 transforms Code AG into a coordinated, multi-agent autonomous engineering organization. Five specialized agents collaborate via an in-process message bus, execute tasks scheduled through a topological DAG dependency graph, preserve concurrency safety with file-level locks, and persist all state in an ACID-compliant SQLite WAL database.

```text
               ┌──────────────────────────────────────────────┐
               │              Coordinator Agent               │
               │   (Task Scheduling, DAG Execution, Retries)  │
               └───────────────────────┬──────────────────────┘
                                       │
        ┌───────────────┬──────────────┼──────────────┬───────────────┐
        ▼               ▼              ▼              ▼               ▼
┌───────────────┐┌──────────────┐┌──────────────┐┌──────────────┐┌───────────────┐
│ Planner Agent ││  Code Agent  ││Debugger Agent││Reviewer Agent││  Message Bus  │
│(Decomposition)││ (Safe Writes)││(Root Causes) ││(5-Factor QA) ││ & File Locks  │
└───────────────┘└──────────────┘└──────────────┘└──────────────┘└───────────────┘
```

### 1. The Five Specialized Agents (`codeagent/agents/`)

| Agent | Role | Tools & Capabilities | Guardrails & Permissions |
|---|---|---|---|
| **Planner Agent** | Task decomposition & DAG creation | Read-only tools (`read_file`, `list_directory`, `scan_project`, `analyze_project`, `search_code`, `get_project_architecture`). | Read-only. Generates validated topological execution DAGs with strict cycle detection. |
| **Code Agent** | Implementation & modification | File write & test tools (`read_file`, `create_file`, `edit_file`, `run_python`, `run_tests`, `create_backup`). | Acquires canonical file locks, creates automatic pre-write backups, enforces protected-path boundaries, validates AST syntax. |
| **Debugger Agent** | Diagnosis & automated repair | Debugging & patch tools (`diagnose_error`, `retest_code`, `read_file`, `run_tests`, `create_backup`). | Classifies confidence levels (`CONFIRMED`, `LIKELY`, `UNVERIFIED_HYPOTHESIS`). Never weakens or deletes existing tests. |
| **Reviewer Agent** | Independent quality assurance | Inspection tools (`read_file`, `git_diff`, `run_tests`, `search_code`). | Strictly read-only. Cannot edit files directly. Evaluates code across 5 distinct axes: Correctness, Quality, Security, Tests, Performance. |
| **Coordinator Agent** | Workflow execution & state machine | Coordination & tool registry (`run_multiagent_workflow`, `get_workflow_status`, `list_workflows`, `inspect_workflow_task`, `cancel_workflow`). | Controls parallel execution (max 2 agents) via ThreadPoolExecutor. Dispatches tasks, orchestrates review loops, and manages rollbacks. |

### 2. Multi-Agent Coordination Infrastructure

- **Inter-Agent Message Bus (`agent_messages.py`)**: Structured Pydantic messaging (`TASK_ASSIGN`, `TASK_COMPLETE`, `TASK_FAILED`, `REVIEW_REQUEST`, `REVIEW_RESULT`, `STATUS_UPDATE`) with strict caller verification to prevent agent impersonation.
- **Granular File-Level Locks (`file_locks.py`)**: Canonical path-resolved locking system ensuring two agents never modify the same file concurrently, preventing write collisions and race conditions.
- **Task Dependency DAG Scheduler (`task_scheduler.py`)**: Topological sorting of task dependencies, priority scheduling, instant cycle detection (`DependencyCycleError`), and cascading failure blocking.
- **Workflow State Management (`workflow_state.py`)**: ACID-compliant SQLite storage operating in WAL mode (`data/workflows/workflows.db`) persisting workflows, step records, agent logs, and review outcomes.
- **Review & Rework Loop**: Code Agent modifications undergo independent Reviewer scrutiny. If findings trigger `NEEDS_REVISION`, the task routes back to the Code Agent with concrete findings for refinement (up to `MAX_REVIEW_REVISIONS=2`).

### 3. Built-in Workflow Templates (`workflow_templates.py`)

1. **`BUILD_PROJECT`**: Planner decomposes requirements -> Code Agent implements modules -> Reviewer inspects code -> Debugger fixes any failing tests.
2. **`FIX_BUG`**: Debugger isolates root cause & drafts fix -> Code Agent applies patch -> Reviewer verifies regression safety.
3. **`CODE_REVIEW`**: Reviewer analyzes recent commits/files across 5 factors -> Emits structured findings & recommendations.
4. **`ADD_FEATURE`**: Planner defines architecture -> Code Agent generates feature & tests -> Reviewer approves -> Debugger resolves edge cases.
5. **`REFACTOR_PROJECT`**: Planner scopes refactoring -> Code Agent transforms modules -> Reviewer checks quality & tests confirm zero regressions.

### 4. CLI Subcommands & Interactive REPL

```powershell
# Agent inspection
codeagent agents list
codeagent agents status
codeagent agents inspect <agent_role>

# Workflow operations
codeagent workflow list [--status <status>] [--limit 10]
codeagent workflow run <template_type> --goal "<description>" [--project-id <id>]
codeagent workflow status <workflow_id>
codeagent workflow cancel <workflow_id>

# Task inspection
codeagent task list <workflow_id>
codeagent task inspect <workflow_id> <task_id>
```

Interactive REPL commands:
- `/agents list`, `/agents status`, `/agents inspect <role>`
- `/workflow list`, `/workflow run <template> <goal>`, `/workflow status <id>`, `/workflow cancel <id>`
- `/task list <workflow_id>`, `/task inspect <workflow_id> <task_id>`

---

## Registered Safe Tools (45 Tools)

| Category | Count | Tools |
|---|---|---|
| **Math & Calculation** | 6 | `calculate`, `add`, `subtract`, `multiply`, `divide`, `evaluate_expression` |
| **Filesystem Intelligence** | 7 | `read_file`, `create_file`, `edit_file`, `delete_file`, `list_directory`, `scan_project`, `analyze_project` |
| **Terminal & Execution** | 6 | `run_python`, `execute_command`, `install_dependency`, `run_tests`, `get_process_status`, `cancel_execution` |
| **Autonomous Debugging** | 2 | `diagnose_error`, `retest_code` |
| **Project Memory & Search** | 4 | `search_code`, `get_project_architecture`, `get_project_memory`, `store_project_memory` |
| **Git Version Control** | 7 | `git_repository_info`, `git_status`, `git_diff`, `git_list_branches`, `git_create_branch`, `git_switch_branch`, `git_commit_changes` |
| **Safety & Security** | 8 | `check_command_permission`, `list_protected_paths`, `add_protected_path`, `remove_protected_path`, `create_backup`, `list_backups`, `restore_backup`, `get_audit_log` |
| **Multi-Agent Workflows** | 5 | `run_multiagent_workflow`, `get_workflow_status`, `list_workflows`, `inspect_workflow_task`, `cancel_workflow` |
| **Total Registered Safe Tools** | **45** | Fully integrated with Pydantic schemas, validation, and CLI diagnostics |

---

## Phase 10: Production-Ready CLI, Monitoring & Release

Code AG Phase 10 transforms the platform into an enterprise-ready, installable developer CLI:

### 1. Fast Startup & Lazy LLM Initialization
- Commands like `version`, `config`, `monitor`, `performance`, and `health` execute instantly (sub-50ms) without loading Ollama or importing large dependencies.
- LLM inference client is instantiated lazily only when autonomous reasoning or prompt generation is required.

### 2. Centralized Structured Logging & Secret Redaction
- **Log Path:** `data/logs/codeagent.jsonl` with rotating file handler (10 MB max, 5 backups).
- **Format:** Single-line JSON events with timestamp, severity level, subsystem component, and context metadata.
- **Automated Scrubbing:** Regex engine scrubs OpenAI/Anthropic API keys, GitHub tokens, database connection passwords, bearer tokens, and private keys.

### 3. Monitoring & System Health Diagnostics
- Comprehensive diagnostic checks executed via `codeag health`:
  - **Application Runtime:** Python version, OS platform, and workspace boundaries.
  - **Persistent Databases:** SQLite schema version, tables, and total storage size.
  - **Tool Catalog:** Verification of all 45 safe registered tools.
  - **Multi-Agent Subsystem:** Verification of all 5 specialized agents.
  - **System Resources:** Available disk storage and process resident memory (RSS).
  - **LLM Inference:** Local Ollama server connectivity and model availability.
- Fast status monitoring dashboard via `codeag monitor`.
- Sanitized diagnostic export via `codeag diagnostics --export <file>`.

### 4. Local Performance Profiling
- Real-time performance tracking via `@measure` decorator and `PerformanceProfiler`.
- Non-LLM benchmark engine measuring AST calculator latency and path security validation via `codeag performance`.

### 5. Multi-Tier Configuration Precedence
- Centralized configuration precedence: CLI Flags > Environment Variables > Global User Config (`~/.codeagent/config.json`) > Defaults.
- Configuration commands: `codeag config show`, `codeag config validate`, `codeag config path`, `codeag config init`.
- Automatic secret masking ensures API credentials and passwords are never exposed on console.

### 6. Windows 11 Native Launchers
- Launch via `codeag` or `code ag` directly from Command Prompt or PowerShell.
- `setup.bat` and `setup.ps1` configure PATH and shell aliases automatically while preserving standard `code <file>` behavior for Visual Studio Code.

### 7. Automatic First-Time Setup & Model Manager
- Interactive 6-stage setup wizard automatically detects whether Ollama is installed and running.
- Checks Python version, available RAM, free disk space (at least 6-10 GB), and GPU hardware acceleration.
- Official Ollama installer downloaded and executed with user consent (no admin elevation required on Windows).
- Streaming model download for `qwen3:latest` via official Ollama pull API with byte progress, retry support, and integrity verification.
- Setup CLI commands: `codeag setup [--check|--skip-model|--model <name>|--repair]`.
- Model management commands: `codeag models [list|current|install <name>]`.

---

## Verification & Testing

Run the complete test suite (Phases 1 through 10) completely offline:

```powershell
.\.venv\Scripts\python.exe -m pytest -v -m "not integration"
```

Output:
```text
===================== 334 passed, 4 deselected in 72.45s =====================
```

Run connection diagnostics and inspect all 45 registered tools:
```powershell
.\.venv\Scripts\codeag.exe health
```
