# Contributing Guide – Code AG

Thank you for your interest in contributing to **Code AG**! We welcome bug reports, documentation enhancements, feature proposals, and pull requests.

---

## 1. Development Environment Setup

1. **Prerequisites:**
   - Python 3.12 or higher
   - Git
   - Local Ollama server with `qwen3:latest`

2. **Clone and Setup Virtual Environment:**
   ```bash
   git clone https://github.com/your-username/codeagent.git
   cd codeagent
   python -m venv .venv
   ```

3. **Activate Environment:**
   - **Windows PowerShell:**
     ```powershell
     .\.venv\Scripts\Activate.ps1
     ```
   - **Linux / macOS:**
     ```bash
     source .venv/bin/activate
     ```

4. **Install in Editable Mode with Dev Dependencies:**
   ```bash
   pip install --upgrade pip
   pip install -e ".[dev]"
   ```

---

## 2. Running Tests & Quality Assurance

Code AG has a test suite covering Phases 1 through 10.

### Running Non-Integration Unit Tests (Fast - No LLM required):
```bash
python -m pytest -v -m "not integration"
```

### Running Specific Test Modules:
```bash
# Phase 10 Tests (Logging, Profiling, Config, Monitoring)
python -m pytest tests/test_phase10.py -v

# Agent Architecture Tests
python -m pytest tests/agents/ -v

# Git & Safety Tests
python -m pytest tests/git/ tests/safety/ -v
```

### Running Full Live Integration Tests (Requires Ollama):
```bash
python -m pytest -v
```

---

## 3. Architecture Invariants & Standards

When submitting changes, please ensure compliance with these architectural invariants:

1. **Local-First Inference:** Never introduce telemetry, cloud API calls, or remote dependency requirements for core features.
2. **Deterministic Security:** All path validation, execution policy checks, and file protection must be implemented in Python code (`codeagent/safety/`). Do not rely on prompt engineering for security boundaries.
3. **Subprocess Isolation:** Always use argument arrays with `shell=False` in subprocess invocations.
4. **Lazy Imports:** Fast CLI commands (`version`, `config`, `monitor`, `performance`, `health`) must execute within milliseconds and never import or initialize the Ollama LLM client unless strictly necessary.
5. **No Regressions:** All unit tests across Phases 1–10 must pass with 100% success rate.

---

## 4. Submitting a Pull Request

1. Create a feature branch:
   ```bash
   git checkout -b feature/my-enhancement
   ```
2. Write clean code following PEP 8 conventions with full type annotations.
3. Add unit tests for new functionality in `tests/`.
4. Ensure all tests pass:
   ```bash
   python -m pytest -q -m "not integration"
   ```
5. Commit and push your changes, then open a Pull Request against `main`.

