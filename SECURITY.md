# Security & Safety Policy – Code AG

Code AG adheres to strict application security principles designed to prevent unintended modifications, data exfiltration, and credential leaks.

---

## 1. Core Security Guarantees

1. **Local-First Inference & Zero Telemetry:**
   - All AI inference occurs through your local Ollama server (`http://localhost:11434`).
   - Code AG transmits **zero source code, telemetry, prompts, or metrics** to external cloud servers.
2. **Deterministic Code Enforcement:**
   - All safety constraints, file write protections, and execution permissions are enforced by **Python code**, never entrusted to LLM prompt compliance.
3. **Explicit User Approval:**
   - Destructive actions (file writes, dependency installation, arbitrary Python execution) require explicit user approval when configured.
4. **Automated Safety Backups:**
   - Before modifying any file on disk, Code AG saves an immutable backup snapshot to `.codeagent/backups`.

---

## 2. Protected Paths & Sensitive Directories

The `ProtectedPathsManager` strictly enforces read/write boundaries:

- **Forbidden Write Targets:**
  - Git repository internals: `.git/`
  - Environment credentials: `.env`, `.env.*`
  - Operating system roots: `C:\Windows`, `C:\Program Files`, `/etc`, `/usr`
  - User root directories and system registries
- **Sandboxed Workspace Scope:**
  - Agents are restricted to operations inside the designated workspace root. Path traversal attempts (`../../`) are intercepted and rejected.

---

## 3. Automated Secret Redaction

Code AG scrubs sensitive information before writing to logs, displaying diagnostics, or executing Git commits.

### Redaction Rules
- **OpenAI / Anthropic API Keys:** `sk-[a-zA-Z0-9_-]{20,}` -> `[REDACTED_API_KEY]`
- **GitHub Tokens:** `(?:ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9]{36,}` -> `[REDACTED_GITHUB_TOKEN]`
- **Generic Secrets:** Key-value pairs matching `api_key`, `secret`, `password`, `auth_token`, `private_key` -> `[REDACTED_SECRET]`
- **Database Connection Strings:** `postgres://user:password@host` -> `postgres://user:[REDACTED_PASSWORD]@host`
- **Private Keys:** PEM blocks `-----BEGIN RSA PRIVATE KEY-----` -> `[REDACTED_PRIVATE_KEY]`
- **Bearer Tokens:** `Bearer <token>` -> `Bearer [REDACTED_TOKEN]`

---

## 4. Secure Subprocess Execution

- All terminal commands and subprocess executions are invoked using **explicit argument arrays with `shell=False`**.
- Shell string interpolations and command chaining attacks are prevented.
- Dangerous commands (e.g., `rm -rf /`, `format C:`, raw registry edits) are blocked by the command execution policy filter.

---

## 5. Pre-Commit Security Scans

When staging and committing changes through Code AG (`codeag git commit` or `/commit`):
1. Code AG scans the Git diff for detected credentials, private keys, and passwords.
2. If potential secrets are discovered, the commit is **aborted**, and a warning is displayed.

---

## 6. Reporting a Vulnerability

If you discover a potential security issue in Code AG, please report it via private disclosure or open an issue marked with `[SECURITY]` in the repository tracker.

