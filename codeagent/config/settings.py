"""Application settings and configuration management using Pydantic Settings."""

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for CodeAgent loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
        case_sensitive=False,
    )

    app_name: str = Field(
        default="Coder with Code",
        description="Name of the application",
        alias="APP_NAME",
    )
    app_version: str = Field(
        default="0.1.0",
        description="Current application version",
        alias="APP_VERSION",
    )
    ollama_host: str = Field(
        default="http://localhost:11434",
        description="Ollama server host URL",
        alias="OLLAMA_HOST",
    )
    model_name: str = Field(
        default="qwen3:latest",
        description="Default LLM model name",
        alias="MODEL_NAME",
    )
    request_timeout: float = Field(
        default=600.0,
        description="Request timeout in seconds",
        alias="REQUEST_TIMEOUT",
    )
    tool_call_timeout: float = Field(
        default=300.0,
        description="Tool evaluation timeout in seconds",
        alias="TOOL_CALL_TIMEOUT",
    )
    temperature: float = Field(
        default=0.2,
        description="Model sampling temperature",
        alias="TEMPERATURE",
    )
    show_startup_banner: bool = Field(
        default=True,
        description="Whether to display the ASCII startup banner in interactive sessions",
        alias="SHOW_STARTUP_BANNER",
    )

    # Phase 2: Context and Tool Configuration
    context_window: int = Field(
        default=8192,
        description="Maximum context window size in tokens",
        alias="CONTEXT_WINDOW",
    )
    max_output_tokens: int = Field(
        default=2048,
        description="Maximum tokens reserved for generation",
        alias="MAX_OUTPUT_TOKENS",
    )
    max_history_messages: int = Field(
        default=30,
        description="Maximum conversation history messages to retain",
        alias="MAX_HISTORY_MESSAGES",
    )
    context_reserve_tokens: int = Field(
        default=1024,
        description="Safety token buffer for system prompt and tool definitions",
        alias="CONTEXT_RESERVE_TOKENS",
    )
    max_tool_iterations: int = Field(
        default=5,
        description="Maximum consecutive tool-calling loop iterations",
        alias="MAX_TOOL_ITERATIONS",
    )
    conversation_storage_path: str = Field(
        default="data/conversations",
        description="Local directory for saving conversation history",
        alias="CONVERSATION_STORAGE_PATH",
    )

    # Phase 3: Filesystem and Workspace Configuration
    workspace_root: Optional[str] = Field(
        default=None,
        description="Root directory of the safe workspace. Defaults to current working directory.",
        alias="WORKSPACE_ROOT",
    )
    max_file_size_mb: int = Field(
        default=5,
        description="Maximum file size in megabytes that reader will inspect",
        alias="MAX_FILE_SIZE_MB",
    )
    max_scan_depth: int = Field(
        default=8,
        description="Maximum directory recursion depth for scanning",
        alias="MAX_SCAN_DEPTH",
    )
    max_scan_entries: int = Field(
        default=5000,
        description="Maximum directory entries counted during scan to prevent hang",
        alias="MAX_SCAN_ENTRIES",
    )
    backup_enabled: bool = Field(
        default=True,
        description="Whether automatic file backups before edit and delete are enabled",
        alias="BACKUP_ENABLED",
    )
    require_write_approval: bool = Field(
        default=True,
        description="Whether user approval is required before writing or editing files",
        alias="REQUIRE_WRITE_APPROVAL",
    )
    require_delete_approval: bool = Field(
        default=True,
        description="Whether explicit confirmation is required before deleting files",
        alias="REQUIRE_DELETE_APPROVAL",
    )
    backup_directory: str = Field(
        default=".codeagent/backups",
        description="Directory relative to workspace root where backups are stored",
        alias="BACKUP_DIRECTORY",
    )

    # Phase 5: Terminal and Code Execution Configuration
    execution_enabled: bool = Field(
        default=True,
        description="Master switch allowing controlled code and command execution",
        alias="EXECUTION_ENABLED",
    )
    execution_timeout_seconds: float = Field(
        default=120.0,
        description="Default process execution timeout in seconds",
        alias="EXECUTION_TIMEOUT_SECONDS",
    )
    max_output_size_mb: int = Field(
        default=5,
        description="Maximum process standard output/error capture limit in MB",
        alias="MAX_OUTPUT_SIZE_MB",
    )
    max_concurrent_processes: int = Field(
        default=3,
        description="Maximum simultaneous background processes managed by agent",
        alias="MAX_CONCURRENT_PROCESSES",
    )
    require_python_approval: bool = Field(
        default=True,
        description="Whether user approval is required before running Python programs",
        alias="REQUIRE_PYTHON_APPROVAL",
    )
    require_dependency_approval: bool = Field(
        default=True,
        description="Whether user approval is strictly required before pip installing packages",
        alias="REQUIRE_DEPENDENCY_APPROVAL",
    )
    require_command_approval: bool = Field(
        default=True,
        description="Whether user approval is required before executing terminal commands",
        alias="REQUIRE_COMMAND_APPROVAL",
    )
    execution_workspace_only: bool = Field(
        default=True,
        description="Confine execution working directories strictly to the workspace",
        alias="EXECUTION_WORKSPACE_ONLY",
    )
    execution_audit_enabled: bool = Field(
        default=True,
        description="Whether all execution operations are recorded in structured audit logs",
        alias="EXECUTION_AUDIT_ENABLED",
    )
    audit_log_path: str = Field(
        default=".codeagent/audit/execution.jsonl",
        description="Path to JSONL audit log relative to workspace root",
        alias="AUDIT_LOG_PATH",
    )

    # Phase 6: Autonomous Debugging Configuration
    max_debug_iterations: int = Field(
        default=5,
        description="Maximum iterations per autonomous debugging session",
        alias="MAX_DEBUG_ITERATIONS",
    )
    max_fix_attempts: int = Field(
        default=3,
        description="Maximum fix generation and patch attempts per error",
        alias="MAX_FIX_ATTEMPTS",
    )
    max_retest_attempts: int = Field(
        default=3,
        description="Maximum retest execution attempts during verification",
        alias="MAX_RETEST_ATTEMPTS",
    )
    debug_timeout_seconds: float = Field(
        default=600.0,
        description="Overall timeout in seconds for an autonomous debugging session",
        alias="DEBUG_TIMEOUT_SECONDS",
    )
    require_patch_approval: bool = Field(
        default=True,
        description="Whether human user approval is strictly required before applying code patches",
        alias="REQUIRE_PATCH_APPROVAL",
    )

    # Phase 7: Project Intelligence and Persistent Memory Configuration
    project_data_path: str = Field(
        default="data/projects",
        description="Directory where persistent project databases and indices are stored",
        alias="PROJECT_DATA_PATH",
    )
    project_index_enabled: bool = Field(
        default=True,
        description="Whether local source code indexing is enabled",
        alias="PROJECT_INDEX_ENABLED",
    )
    max_index_file_size_mb: int = Field(
        default=5,
        description="Maximum file size in megabytes to index",
        alias="MAX_INDEX_FILE_SIZE_MB",
    )
    max_index_files: int = Field(
        default=20000,
        description="Maximum number of files to index per project",
        alias="MAX_INDEX_FILES",
    )
    index_chunk_size: int = Field(
        default=1200,
        description="Approximate character count per code chunk",
        alias="INDEX_CHUNK_SIZE",
    )
    index_overlap: int = Field(
        default=150,
        description="Character overlap between consecutive code chunks",
        alias="INDEX_OVERLAP",
    )
    index_excluded_dirs: str = Field(
        default=".git,.venv,node_modules,__pycache__,dist,build",
        description="Comma-separated directory names excluded from indexing",
        alias="INDEX_EXCLUDED_DIRS",
    )
    memory_enabled: bool = Field(
        default=True,
        description="Master switch for persistent SQLite memory and project context",
        alias="MEMORY_ENABLED",
    )
    memory_max_results: int = Field(
        default=10,
        description="Maximum relevant memory items to retrieve into context",
        alias="MEMORY_MAX_RESULTS",
    )
    semantic_search_enabled: bool = Field(
        default=False,
        description="Whether optional local semantic vector search is enabled",
        alias="SEMANTIC_SEARCH_ENABLED",
    )

    # Phase 8: Git Integration and Safety Management Configuration
    git_enabled: bool = Field(
        default=True,
        description="Whether Git integration features are enabled",
        alias="GIT_ENABLED",
    )
    git_require_approval: bool = Field(
        default=True,
        description="Whether Git operations require explicit user approval",
        alias="GIT_REQUIRE_APPROVAL",
    )
    git_require_commit_approval: bool = Field(
        default=True,
        description="Whether Git commits require explicit approval",
        alias="GIT_REQUIRE_COMMIT_APPROVAL",
    )
    git_require_branch_approval: bool = Field(
        default=True,
        description="Whether creating or switching branches requires approval",
        alias="GIT_REQUIRE_BRANCH_APPROVAL",
    )
    git_block_force_push: bool = Field(
        default=True,
        description="Strictly block force-push operations",
        alias="GIT_BLOCK_FORCE_PUSH",
    )
    git_block_destructive_commands: bool = Field(
        default=True,
        description="Block destructive Git commands like hard reset and clean -fd",
        alias="GIT_BLOCK_DESTRUCTIVE_COMMANDS",
    )
    backup_before_write: bool = Field(
        default=True,
        description="Automatically back up files before modification",
        alias="BACKUP_BEFORE_WRITE",
    )
    backup_storage_path: str = Field(
        default="data/backups",
        description="Dedicated path for backup archives",
        alias="BACKUP_STORAGE_PATH",
    )
    command_policy_enabled: bool = Field(
        default=True,
        description="Enable centralized command policy enforcement",
        alias="COMMAND_POLICY_ENABLED",
    )
    command_default_policy: str = Field(
        default="REQUIRE_APPROVAL",
        description="Default policy verdict for unclassified commands",
        alias="COMMAND_DEFAULT_POLICY",
    )
    protected_paths_enabled: bool = Field(
        default=True,
        description="Enforce protected path boundaries",
        alias="PROTECTED_PATHS_ENABLED",
    )
    protected_paths: str = Field(
        default=".git,.env,.venv,venv,node_modules,__pycache__",
        description="Comma-separated default protected paths and patterns",
        alias="PROTECTED_PATHS",
    )
    audit_log_enabled: bool = Field(
        default=True,
        description="Whether security audit logging is enabled",
        alias="AUDIT_LOG_ENABLED",
    )
    audit_storage_path: str = Field(
        default="data/audit",
        description="Storage location for security audit database and logs",
        alias="AUDIT_STORAGE_PATH",
    )
    secret_scan_before_commit: bool = Field(
        default=True,
        description="Scan staged diff for secrets before committing",
        alias="SECRET_SCAN_BEFORE_COMMIT",
    )

    # Phase 9: Advanced Multi-Agent Architecture and Workflow Orchestration
    agent_model: str = Field(
        default="qwen3:latest",
        description="Default shared model for autonomous agents",
        alias="AGENT_MODEL",
    )
    planner_model: Optional[str] = Field(
        default=None,
        description="Optional model override for Planner Agent",
        alias="PLANNER_MODEL",
    )
    coder_model: Optional[str] = Field(
        default=None,
        description="Optional model override for Code Agent",
        alias="CODER_MODEL",
    )
    debugger_model: Optional[str] = Field(
        default=None,
        description="Optional model override for Debugger Agent",
        alias="DEBUGGER_MODEL",
    )
    reviewer_model: Optional[str] = Field(
        default=None,
        description="Optional model override for Reviewer Agent",
        alias="REVIEWER_MODEL",
    )
    max_workflow_tasks: int = Field(
        default=50,
        description="Maximum tasks allowed in a single workflow plan",
        alias="MAX_WORKFLOW_TASKS",
    )
    max_agent_iterations: int = Field(
        default=20,
        description="Maximum execution iterations for an agent",
        alias="MAX_AGENT_ITERATIONS",
    )
    max_agent_retries: int = Field(
        default=2,
        description="Maximum retry attempts per individual agent task",
        alias="MAX_AGENT_RETRIES",
    )
    max_workflow_retries: int = Field(
        default=3,
        description="Maximum retry attempts per workflow execution",
        alias="MAX_WORKFLOW_RETRIES",
    )
    max_parallel_agents: int = Field(
        default=2,
        description="Maximum concurrent agents for independent parallel tasks",
        alias="MAX_PARALLEL_AGENTS",
    )
    max_workflow_timeout_seconds: float = Field(
        default=1800.0,
        description="Overall timeout in seconds for a multi-agent workflow",
        alias="MAX_WORKFLOW_TIMEOUT_SECONDS",
    )
    max_debug_attempts: int = Field(
        default=3,
        description="Maximum autonomous debugging attempts within a workflow",
        alias="MAX_DEBUG_ATTEMPTS",
    )
    max_review_revisions: int = Field(
        default=2,
        description="Maximum review-rework iterations between Reviewer and Code Agent",
        alias="MAX_REVIEW_REVISIONS",
    )
    workflow_storage_path: str = Field(
        default="data/workflows",
        description="Directory path for persistent multi-agent workflow state database",
        alias="WORKFLOW_STORAGE_PATH",
    )

    # Phase 10: Production Logging, Monitoring, and Configuration
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
        alias="LOG_LEVEL",
    )
    log_file_path: str = Field(
        default="data/logs/codeagent.jsonl",
        description="Path to rotating structured JSON log file",
        alias="LOG_FILE_PATH",
    )
    log_max_bytes: int = Field(
        default=10 * 1024 * 1024,
        description="Maximum log file size in bytes before rotation (default 10MB)",
        alias="LOG_MAX_BYTES",
    )
    log_backup_count: int = Field(
        default=5,
        description="Number of rotated log backups to retain",
        alias="LOG_BACKUP_COUNT",
    )
    log_format_json: bool = Field(
        default=True,
        description="Whether file logs should be formatted as structured JSON",
        alias="LOG_FORMAT_JSON",
    )
    user_config_path: Optional[str] = Field(
        default=None,
        description="Custom path to user global config file (defaults to ~/.codeagent/config.json)",
        alias="USER_CONFIG_PATH",
    )
    profiling_enabled: bool = Field(
        default=False,
        description="Whether performance profiling is enabled for operations",
        alias="PROFILING_ENABLED",
    )
    monitoring_enabled: bool = Field(
        default=True,
        description="Whether health and diagnostic monitoring subsystem is active",
        alias="MONITORING_ENABLED",
    )
    health_check_timeout: float = Field(
        default=3.0,
        description="Timeout in seconds for external health checks (e.g. Ollama ping)",
        alias="HEALTH_CHECK_TIMEOUT",
    )


@lru_cache()
def get_settings() -> Settings:
    """Return a cached singleton instance of Settings."""
    return Settings()
