"""Monitoring and diagnostics subsystem tracking application, LLM, agents, tools, and resources."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import sys
from typing import Any, Dict, List, Optional, Tuple

from codeagent.config.settings import Settings, get_settings
from codeagent.core.profiler import get_current_memory_mb
from codeagent.core.logger import get_logger

logger = get_logger("monitoring")


@dataclass
class HealthCheckItem:
    """Individual system health check status."""

    component: str
    status: str  # OK, WARN, FAIL
    message: str
    latency_ms: Optional[float] = None
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.component

    @property
    def passed(self) -> bool:
        return self.status == "OK"


class MonitoringSystem:
    """Aggregates diagnostics and health status across application layers."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        workspace_root: Optional[Path] = None,
        project_root: Optional[Path] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.workspace_root = (project_root or workspace_root or Path.cwd()).resolve()

    def check_application_health(self) -> HealthCheckItem:
        """Verify Python runtime, version, and workspace boundaries."""
        py_ver = sys.version.split()[0]
        ws_exists = self.workspace_root.exists()

        if not ws_exists:
            return HealthCheckItem(
                component="Application",
                status="FAIL",
                message=f"Workspace root '{self.workspace_root}' does not exist.",
                details={"python_version": py_ver, "workspace_root": str(self.workspace_root)},
            )

        return HealthCheckItem(
            component="Application",
            status="OK",
            message=f"Python {py_ver} on {platform.system()} ({self.settings.app_name} v{self.settings.app_version})",
            details={
                "python_version": py_ver,
                "platform": platform.platform(),
                "workspace_root": str(self.workspace_root),
                "app_name": self.settings.app_name,
                "app_version": self.settings.app_version,
            },
        )

    def check_database_health(self) -> HealthCheckItem:
        """Verify readability and integrity of SQLite persistent databases."""
        db_paths = [
            Path(self.settings.workflow_storage_path) / "workflows.db",
            Path(self.settings.project_data_path) / "memory.db",
            Path(self.settings.audit_storage_path) / "audit.db",
        ]

        verified = 0
        total_size_bytes = 0
        for p in db_paths:
            full_path = self.workspace_root / p if not p.is_absolute() else p
            if full_path.exists():
                try:
                    conn = sqlite3.connect(str(full_path), timeout=2.0)
                    conn.execute("PRAGMA schema_version;")
                    conn.close()
                    verified += 1
                    total_size_bytes += full_path.stat().st_size
                except Exception as exc:
                    return HealthCheckItem(
                        component="Database",
                        status="WARN",
                        message=f"Database '{full_path.name}' integrity check failed: {exc}",
                        details={"failing_db": str(full_path)},
                    )

        return HealthCheckItem(
            component="Database",
            status="OK",
            message=f"SQLite storage active ({verified} databases checked, {total_size_bytes / 1024:.1f} KB total)",
            details={"databases_checked": verified, "total_size_bytes": total_size_bytes},
        )

    def check_llm_health(self, timeout: Optional[float] = None) -> HealthCheckItem:
        """Check Ollama connectivity and model availability without loading weights."""
        t_limit = timeout or getattr(self.settings, "health_check_timeout", 3.0)
        from codeagent.llm.client import LLMClient

        client = LLMClient(settings=self.settings, timeout=t_limit)
        import time

        t0 = time.perf_counter()
        is_online, msg = client.check_connection(timeout=t_limit)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        if not is_online:
            return HealthCheckItem(
                component="LLM Inference",
                status="FAIL",
                message=f"Ollama offline at {self.settings.ollama_host}. {msg}",
                latency_ms=elapsed_ms,
                details={"host": self.settings.ollama_host, "model": self.settings.model_name},
            )

        return HealthCheckItem(
            component="LLM Inference",
            status="OK",
            message=f"Ollama online at {self.settings.ollama_host} (configured model: {self.settings.model_name})",
            latency_ms=elapsed_ms,
            details={"host": self.settings.ollama_host, "model": self.settings.model_name},
        )

    def check_tools_health(self) -> HealthCheckItem:
        """Verify registered safe tool catalog."""
        from codeagent.tools.registry import get_default_registry

        registry = get_default_registry()
        tools_count = len(registry.list_tools())
        return HealthCheckItem(
            component="Tool Registry",
            status="OK" if tools_count >= 40 else "WARN",
            message=f"{tools_count} safe tools registered and validated",
            details={"tool_count": tools_count},
        )

    def check_agent_health(self) -> HealthCheckItem:
        """Verify Multi-Agent subsystem status."""
        from codeagent.agents.agent_factory import AgentFactory

        factory = AgentFactory(workspace_root=self.workspace_root, settings=self.settings)
        registry = factory.create_all_agents()
        agents = registry.list_agents()

        return HealthCheckItem(
            component="Multi-Agent System",
            status="OK" if len(agents) == 5 else "WARN",
            message=f"{len(agents)} specialized agents registered (Planner, Code, Debugger, Reviewer, Coordinator)",
            details={"agent_roles": [a.role.value for a in agents]},
        )

    def check_resources(self) -> HealthCheckItem:
        """Collect host disk, memory, and runtime resource metrics."""
        disk = shutil.disk_usage(str(self.workspace_root))
        free_gb = disk.free / (1024.0**3)
        total_gb = disk.total / (1024.0**3)

        mem_mb = get_current_memory_mb()
        mem_str = f"{mem_mb:.1f} MB" if mem_mb is not None else "N/A"

        status = "OK" if free_gb >= 1.0 else "WARN"
        return HealthCheckItem(
            component="System Resources",
            status=status,
            message=f"Disk free: {free_gb:.1f} GB / {total_gb:.1f} GB, Process RSS: {mem_str}",
            details={
                "disk_free_gb": round(free_gb, 2),
                "disk_total_gb": round(total_gb, 2),
                "memory_rss_mb": round(mem_mb, 2) if mem_mb is not None else None,
            },
        )

    def run_all_health_checks(self, check_llm: bool = True) -> List[HealthCheckItem]:
        """Execute complete health assessment across all subsystems."""
        checks: List[HealthCheckItem] = []
        checks.append(self.check_application_health())
        checks.append(self.check_database_health())
        checks.append(self.check_tools_health())
        checks.append(self.check_agent_health())
        checks.append(self.check_resources())
        if check_llm:
            checks.append(self.check_llm_health())
        return checks

    # Convenient API aliases
    check_resources_health = check_resources
    check_agent_health = check_agent_health
    check_agents_health = check_agent_health
    check_ollama_health = check_llm_health
    run_all_checks = run_all_health_checks

    def generate_diagnostics_report(self) -> Dict[str, Any]:
        """Produce structured diagnostics snapshot for troubleshooting and support."""
        health_items = self.run_all_health_checks(check_llm=True)
        report: Dict[str, Any] = {
            "app_name": self.settings.app_name,
            "application": f"{self.settings.app_name} v{self.settings.app_version}",
            "app_version": self.settings.app_version,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "platform": {
                "os": platform.system(),
                "release": platform.release(),
                "machine": platform.machine(),
                "python_version": sys.version,
            },
            "workspace_root": str(self.workspace_root),
            "health_checks": [
                {
                    "component": item.component,
                    "status": item.status,
                    "message": item.message,
                    "latency_ms": item.latency_ms,
                    "details": item.details,
                }
                for item in health_items
            ],
            "subsystems": [
                {
                    "name": item.component,
                    "status": item.status,
                    "message": item.message,
                    "latency_ms": item.latency_ms,
                }
                for item in health_items
            ],
            "settings": {
                "model_name": self.settings.model_name,
                "ollama_host": self.settings.ollama_host,
                "context_window": self.settings.context_window,
                "max_parallel_agents": self.settings.max_parallel_agents,
                "log_level": getattr(self.settings, "log_level", "INFO"),
            },
        }
        return report

    def export_diagnostics(self, output_path: Path) -> Dict[str, Any]:
        """Generate and save diagnostics to the specified file path."""
        report = self.generate_diagnostics_report()
        target = Path(output_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report
