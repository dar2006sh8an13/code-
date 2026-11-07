# Changelog – Code AG

All notable changes to the **Code AG** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.0] - 2026-11-05

### Added (Phase 10: Production-Ready CLI, Optimization, Monitoring & Release)
- **Fast Startup Optimization:** Lazy loading for LLM client; non-LLM commands (`version`, `config`, `monitor`, `performance`, `health`) execute with sub-50ms latency.
- **Centralized Structured Logging:** Implemented `CodeAgentLogger` with rotating file handler (`data/logs/codeagent.jsonl`), JSON formatting (`StructuredJsonFormatter`), Rich console handler, and secret scrubber.
- **Automated Secret Redaction:** Regex engine (`redact_secrets`) scrubs OpenAI/Anthropic API keys, GitHub tokens, database connection passwords, bearer tokens, and private keys.
- **Performance Profiler Subsystem:** Implemented `PerformanceProfiler`, `@measure` decorator, and `run_local_benchmark` evaluating AST safe calculator and path safety checking latency.
- **Subsystem Monitoring Dashboard:** Added `codeag monitor` and `codeag health` testing Application runtime, SQLite databases, 45 safe tools, 5 specialized agents, host disk/RAM resources, and Ollama connectivity.
- **Diagnostic Export Tool:** Added `codeag diagnostics [--export <file>]` outputting sanitized JSON snapshots.
- **Multi-Tier Configuration Precedence:** CLI flags > Environment variables (`.env`) > Global user config (`~/.codeagent/config.json`) > Application defaults.
- **Configuration Management Commands:** `codeag config [show|validate|path|init]` with automatic secret masking.
- **Balanced ASCII Art Banner:** Rendered balanced "Code AG" logo with dynamic status metadata and Windows CMD ASCII fallback.
- **Windows 11 Setup Scripts:** Added `setup.bat`, `setup.ps1`, `code.cmd`, and `codeag.cmd` providing native `code ag` and `codeag` command invocation.
- **CI/CD Pipeline:** Added `.github/workflows/ci.yml` supporting Ubuntu and Windows matrix testing.
- **Complete Documentation Suite:** Created 10 production documentation files.
- **Phase 10 Test Suite:** Added 16 comprehensive unit tests in `tests/test_phase10.py` (total project passing tests: 334).

### Added (Phase 9: Advanced Multi-Agent Architecture)
- Five core specialized agents: Planner Agent, Coder Agent, Debugger Agent, Reviewer Agent, and Coordinator Agent.
- Structured inter-agent communication messages (`AgentMessage`, `TaskAssignment`, `AgentEvaluation`).
- Multi-agent coordinator state machine and dependency-driven task execution.
- Shared workflow blackboard with SQLite persistence.

### Added (Phase 8: Git Integration and Safety Management)
- Git status, diff, branch creation, branch switching, and safe staging.
- Pre-modification file backup snapshot engine (`.codeagent/backups`).
- Protected paths manager preventing modification of `.git`, `.env`, and operating system directories.
- Secret scanner blocking commits containing sensitive API credentials.
- Rollback engine restoring files from automated backup snapshots.

### Added (Phase 7: Project Intelligence and Persistent Memory)
- Project analyzer and architecture mapper.
- Multi-language AST indexer supporting Python, TypeScript, JavaScript, Go, Rust, and Java.
- Persistent conversation and project memory in SQLite.

### Added (Phase 6: Autonomous Debugging)
- Automated test discovery and execution.
- Traceback parser and fault localization engine.
- Hypothesis generator and AST diff patch synthesizer.

### Added (Phase 5: Terminal and Code Execution)
- Safe execution manager with process isolation (`shell=False`).
- Execution approval policies for shell commands and Python execution.
- Automated package dependency installer with pip.

### Added (Phase 4: Agent Loop and Tool Calling)
- Autonomous ReAct loop with tool invocation.
- Tool registry with 45 safe registered tools.

### Added (Phase 3: Filesystem Intelligence)
- Safe file reading, writing, directory listing, and line-range inspection.

### Added (Phase 2: Advanced LLM Integration)
- Ollama local inference integration supporting `qwen3:latest`.
- Streaming responses and token counting.

### Added (Phase 1: CLI Foundation)
- Typer CLI and Rich terminal interface.
- Pydantic Settings integration.

