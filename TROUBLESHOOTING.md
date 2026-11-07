# Troubleshooting Guide – Code AG

Common questions, operational diagnoses, and resolutions for **Code AG**.

---

## 1. Subsystem Health Diagnostics

If you encounter any issues, your first step should be running the automated health check:

```powershell
codeag health
```

To export an exhaustive JSON diagnostic snapshot for bug reports:
```powershell
codeag diagnostics --export report.json
```

---

## 2. Common Issues and Resolutions

### Issue A: "Ollama offline at http://localhost:11434"

**Symptoms:**
- Health check reports `[FAIL]` on LLM Inference.
- The startup banner displays a warning: `Ollama is currently unreachable`.

**Root Cause:**
The local Ollama server process is not running or is blocked by local firewall/antivirus.

**Resolution:**
1. Open a new terminal and start Ollama:
   ```bash
   ollama serve
   ```
2. Confirm the server is responding:
   ```bash
   curl http://localhost:11434/api/tags
   ```
3. If Ollama is running on a different port or remote host, configure `OLLAMA_HOST`:
   ```bash
   codeag --ollama-host "http://127.0.0.1:11434"
   ```
   or add to `.env`:
   ```env
   OLLAMA_HOST=http://127.0.0.1:11434
   ```

---

### Issue B: "Model not found: qwen3:latest"

**Symptoms:**
- Ollama responds with model pull errors or returns empty responses.

**Resolution:**
Pull the requested model using the Ollama CLI:
```bash
ollama pull qwen3:latest
```
Alternatively, switch to an existing downloaded model:
```bash
codeag --model "qwen2.5-coder:7b"
```

---

### Issue C: "codeag is not recognized as an internal or external command"

**Symptoms:**
- Typing `codeag` or `code ag` in Windows CMD or PowerShell produces a command not found error.

**Resolution:**
1. Ensure your virtual environment is activated:
   ```powershell
   .\.venv\Scripts\activate.ps1
   ```
2. Run the automated PATH installer:
   - **In PowerShell:** Run `.\setup.ps1`
   - **In CMD:** Run `setup.bat`
3. Restart your terminal session so the updated environment PATH is loaded.

---

### Issue D: "Permission denied on file write or backup"

**Symptoms:**
- File write operations fail with permission errors.

**Root Cause:**
- Target file is protected by `ProtectedPathsManager` (e.g., inside `.git/` or `.env`).
- Target file is locked by an external editor (e.g., VS Code or running Python process).

**Resolution:**
- Verify that the target path is inside your workspace root.
- Close external processes that have exclusive read/write locks on the target file.

---

### Issue E: "Subprocess execution not approved"

**Symptoms:**
- Terminal command or pip installation reports `ExecutionNotApprovedError`.

**Resolution:**
- Code AG requires explicit confirmation for executing shell scripts and installing dependencies when safety policies are enabled.
- Reply `y` or `yes` when prompted in interactive REPL.
- To adjust approval requirements, update your `.env` or `~/.codeagent/config.json`:
  ```env
  REQUIRE_WRITE_APPROVAL=false
  REQUIRE_PYTHON_APPROVAL=false
  ```

---

### Issue F: Log File Growth & Disk Space

**Symptoms:**
- Log files consuming too much disk space.

**Resolution:**
Code AG uses an automatic rotating file handler:
- Default file: `data/logs/codeagent.jsonl`
- Default ceiling: 10 MB per file, 5 rotated backup archives.
- Adjust in `.env`:
  ```env
  LOG_MAX_BYTES=5242880
  LOG_BACKUP_COUNT=2
  ```

