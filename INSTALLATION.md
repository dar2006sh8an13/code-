# Installation Guide – Code AG

**Code AG** is a local-first, production-ready autonomous AI coding CLI built in India and designed for developers everywhere. This guide walks you through setting up and running Code AG on Windows 11, Linux, and macOS.

---

## 1. System Requirements

| Component | Minimum Specification | Recommended Specification |
| :--- | :--- | :--- |
| **Operating System** | Windows 10/11 (x64), Linux (Ubuntu 22.04+), macOS 13+ | Windows 11 (x64) / Linux x86_64 |
| **Python** | Python 3.12.0 or higher | Python 3.12.9+ |
| **Local LLM Backend** | Ollama local server | Ollama v0.3.0+ |
| **Recommended Model** | `qwen3:latest` (or `qwen2.5-coder:7b`) | `qwen3:latest` |
| **RAM** | 8 GB System Memory | 16 GB+ System Memory |
| **Disk Space** | 10 GB Free Storage (for models & caches) | 20 GB SSD Storage |

---

## 2. Prerequisites

### Step 2.1: Install Python 3.12
Ensure Python 3.12 is installed and accessible in your system `PATH`:
```bash
python --version
# Output: Python 3.12.x
```

### Step 2.2: Install and Start Ollama
1. Download and install Ollama from [ollama.com](https://ollama.com).
2. Start the Ollama server:
   ```bash
   ollama serve
   ```
3. Pull the default `qwen3:latest` model:
   ```bash
   ollama pull qwen3:latest
   ```
4. Verify local connectivity:
   ```bash
   curl http://localhost:11434/api/tags
   ```

---

## 3. Installing Code AG

### Method A: Install in Virtual Environment (Recommended)

1. Clone or navigate to the repository directory:
   ```bash
   cd "C:\path\to\code AG"
   ```

2. Create and activate a Python 3.12 virtual environment:
   - **Windows (PowerShell):**
     ```powershell
     python -m venv .venv
     .\.venv\Scripts\Activate.ps1
     ```
   - **Windows (CMD):**
     ```cmd
     python -m venv .venv
     .\.venv\Scripts\activate.bat
     ```
   - **Linux / macOS:**
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```

3. Install Code AG in editable development mode with development dependencies:
   ```bash
   pip install --upgrade pip
   pip install -e ".[dev]"
   ```

---

## 4. Windows 11 Launcher Setup (`code ag` and `codeag`)

Code AG includes automated setup scripts to configure your PATH and terminal shortcuts so you can launch the CLI using `codeag` or `code ag`:

### Option A: Run Automated Setup Script (PowerShell)
Open PowerShell in the project directory and run:
```powershell
.\setup.ps1
```
This script:
1. Adds the `.venv\Scripts` directory and project root to your User environment `PATH`.
2. Configures a PowerShell profile function allowing `code ag` to launch Code AG while preserving standard `code <file>` behavior for Visual Studio Code.

### Option B: Run Automated Batch Setup (CMD)
Open Command Prompt (cmd.exe) and run:
```cmd
setup.bat
```

### Option C: Manual Batch Files
The repository includes pre-built launcher scripts:
- `codeag.cmd`: Launches `codeag.exe` in `.venv\Scripts`.
- `code.cmd`: Routes `code ag` to Code AG while routing other invocations (e.g. `code main.py`) to the VS Code executable.

---

## 5. Verifying Installation

Verify that Code AG is correctly installed and ready:

1. **Check Version (Fast Startup - Instant execution):**
   ```bash
   codeag version
   ```
   *Expected Output:*
   ```text
   Code AG version 0.1.0 (Python 3.12.x on Windows)
   Built in India. Designed for developers everywhere.
   ```

2. **Run System Health Diagnostics:**
   ```bash
   codeag health
   ```
   This will inspect:
   - Application runtime and workspace root
   - SQLite persistent database integrity
   - 45 safe registered tools
   - 5 specialized multi-agent roles
   - Host system disk space and memory
   - Local Ollama connection status

3. **Check Subsystem Monitoring:**
   ```bash
   codeag monitor
   ```

4. **Run Performance Engine Benchmark:**
   ```bash
   codeag performance
   ```

---

## 6. Launching Interactive Session

Start an interactive session:
```bash
codeag
```
or (with the launcher installed):
```powershell
code ag
```

You will be greeted with the balanced Code AG ASCII startup banner:
```text
  ____          _            _    ____ 
 / ___|___   __| | ___      / \  / ___|
| |   / _ \ / _` |/ _ \    / _ \| |  _ 
| |__| (_) | (_| |  __/   / ___ \ |_| |
 \____\___/ \__,_|\___|  /_/   \_\____|

Built in India. Designed for developers everywhere.
```

