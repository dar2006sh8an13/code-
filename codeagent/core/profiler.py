"""Performance profiling, latency tracking, and execution benchmarking for CodeAgent."""

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
import platform
import time
from typing import Any, Callable, Dict, Generator, List, Optional
import sys

from codeagent.core.logger import get_logger

logger = get_logger("profiler")


@dataclass
class MetricRecord:
    """Single measured performance event."""

    name: str
    duration_seconds: float
    timestamp: str
    memory_mb: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "duration_ms": round(self.duration_seconds * 1000.0, 2),
            "timestamp": self.timestamp,
            "memory_mb": round(self.memory_mb, 2) if self.memory_mb is not None else None,
            "metadata": self.metadata,
        }


def get_current_memory_mb() -> Optional[float]:
    """Retrieve the current resident memory (RSS) in megabytes."""
    try:
        import psutil
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / (1024.0 * 1024.0)
    except Exception:
        # Fallback using Windows-specific or Unix sys facilities if psutil is unavailable
        return None


class PerformanceProfiler:
    """Tracks latency, memory consumption, and operational metrics across subsystems."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled: bool = enabled
        self.metrics: List[MetricRecord] = []
        self._start_time: float = time.perf_counter()

    @contextmanager
    def measure(self, operation_name: str, **metadata: Any) -> Generator[None, None, None]:
        """Context manager to measure the execution duration of a block."""
        t0 = time.perf_counter()
        mem_before = get_current_memory_mb()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - t0
            mem_after = get_current_memory_mb()
            rec = MetricRecord(
                name=operation_name,
                duration_seconds=elapsed,
                timestamp=datetime.now(timezone.utc).isoformat(),
                memory_mb=mem_after or mem_before,
                metadata=metadata,
            )
            self.metrics.append(rec)
            logger.debug(f"Operation '{operation_name}' completed in {elapsed*1000.0:.2f}ms")

    def record_metric(self, name: str, duration_seconds: float, **metadata: Any) -> None:
        """Explicitly record a measured duration."""
        rec = MetricRecord(
            name=name,
            duration_seconds=duration_seconds,
            timestamp=datetime.now(timezone.utc).isoformat(),
            memory_mb=get_current_memory_mb(),
            metadata=metadata,
        )
        self.metrics.append(rec)

    def get_summary(self) -> Dict[str, Any]:
        """Aggregate recorded metrics by operation category."""
        summary: Dict[str, Dict[str, Any]] = {}
        for m in self.metrics:
            if m.name not in summary:
                summary[m.name] = {
                    "count": 0,
                    "total_seconds": 0.0,
                    "min_seconds": float("inf"),
                    "max_seconds": 0.0,
                }
            entry = summary[m.name]
            entry["count"] += 1
            entry["total_seconds"] += m.duration_seconds
            entry["min_seconds"] = min(entry["min_seconds"], m.duration_seconds)
            entry["max_seconds"] = max(entry["max_seconds"], m.duration_seconds)

        formatted: Dict[str, Any] = {}
        for name, data in summary.items():
            formatted[name] = {
                "count": data["count"],
                "avg_ms": round((data["total_seconds"] / data["count"]) * 1000.0, 2),
                "min_ms": round(data["min_seconds"] * 1000.0, 2),
                "max_ms": round(data["max_seconds"] * 1000.0, 2),
            }
        return formatted

    def get_records(self) -> List[MetricRecord]:
        """Return raw metric records."""
        return list(self.metrics)

    def profile_function(self, operation_name: str, **metadata: Any) -> Callable:
        """Decorator to profile a function execution."""
        def decorator(func: Callable) -> Callable:
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                with self.measure(operation_name, **metadata):
                    return func(*args, **kwargs)
            return wrapper
        return decorator

    def clear(self) -> None:
        """Clear metric history."""
        self.metrics.clear()


# Global singleton profiler
_GLOBAL_PROFILER = PerformanceProfiler()


def get_profiler() -> PerformanceProfiler:
    """Return the global PerformanceProfiler instance."""
    return _GLOBAL_PROFILER


def measure(operation_name: str, **metadata: Any):
    """Context manager for measuring execution duration using global profiler."""
    return _GLOBAL_PROFILER.measure(operation_name, **metadata)


def run_local_benchmark() -> Dict[str, Any]:
    """Execute non-destructive, non-LLM benchmarks measuring baseline engine latency."""
    results: Dict[str, Any] = {
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "benchmarks": {},
    }

    # 1. Math Tool Latency
    from codeagent.tools.calculator import safe_eval_arithmetic
    t0 = time.perf_counter()
    for _ in range(500):
        safe_eval_arithmetic("123 * 456 + 789 / 3")
    math_elapsed = (time.perf_counter() - t0) / 500.0
    results["benchmarks"]["calculator_tool_avg_ms"] = round(math_elapsed * 1000.0, 4)

    # 2. Path Safety Validation Latency
    from codeagent.safety.protected_paths import ProtectedPathsManager
    ppm = ProtectedPathsManager()
    t0 = time.perf_counter()
    for _ in range(200):
        ppm.validate_path_safety("codeagent/config/settings.py", allow_read=True)
    path_elapsed = (time.perf_counter() - t0) / 200.0
    results["benchmarks"]["path_safety_check_avg_ms"] = round(path_elapsed * 1000.0, 4)

    # 3. Memory Snapshot
    mem = get_current_memory_mb()
    results["benchmarks"]["current_process_rss_mb"] = round(mem, 2) if mem is not None else "N/A"

    return results
