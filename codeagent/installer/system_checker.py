"""Hardware, operating system, and storage validation for CodeAgent."""

import ctypes
from dataclasses import dataclass, field
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional


@dataclass
class SystemReport:
    """Consolidated hardware and platform readiness assessment."""

    os_name: str
    os_release: str
    architecture: str
    python_version: str
    python_compatible: bool
    total_ram_gb: float
    available_ram_gb: float
    free_disk_gb: float
    disk_path: str
    gpu_name: Optional[str] = None
    gpu_vram_gb: Optional[float] = None
    warnings: List[str] = field(default_factory=list)
    advisories: List[str] = field(default_factory=list)

    @property
    def is_compatible(self) -> bool:
        """Evaluate whether minimum requirements are satisfied."""
        return self.python_compatible and self.free_disk_gb >= 6.0


class SystemChecker:
    """Inspects platform, runtime version, memory capacity, disk headroom, and GPU."""

    def __init__(self, target_dir: Optional[Path] = None) -> None:
        self.target_dir = Path(target_dir or Path.home()).resolve()

    def check_python_version(self) -> tuple[str, bool]:
        """Validate Python runtime against minimum threshold (>= 3.12)."""
        ver_info = sys.version_info
        ver_str = f"{ver_info.major}.{ver_info.minor}.{ver_info.micro}"
        is_supported = (ver_info.major, ver_info.minor) >= (3, 12)
        return ver_str, is_supported

    def get_system_ram_gb(self) -> tuple[float, float]:
        """Determine total and available system memory in gigabytes."""
        # 1. Try psutil if installed
        try:
            import psutil
            vm = psutil.virtual_memory()
            return round(vm.total / (1024**3), 2), round(vm.available / (1024**3), 2)
        except Exception:
            pass

        # 2. Windows ctypes fallback (standard library)
        if sys.platform == "win32":
            try:
                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]
                stat = MEMORYSTATUSEX()
                stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                    total_gb = round(stat.ullTotalPhys / (1024**3), 2)
                    avail_gb = round(stat.ullAvailPhys / (1024**3), 2)
                    return total_gb, avail_gb
            except Exception:
                pass

        # 3. Linux /proc/meminfo fallback
        if os.path.exists("/proc/meminfo"):
            try:
                meminfo = Path("/proc/meminfo").read_text(encoding="utf-8")
                total_kb = 0
                avail_kb = 0
                for line in meminfo.splitlines():
                    if line.startswith("MemTotal:"):
                        total_kb = int(line.split()[1])
                    elif line.startswith("MemAvailable:"):
                        avail_kb = int(line.split()[1])
                if total_kb > 0:
                    return round(total_kb / (1024**2), 2), round(avail_kb / (1024**2), 2)
            except Exception:
                pass

        # Conservative safe fallback
        return 8.0, 4.0

    def get_free_disk_gb(self, target_path: Optional[Path] = None) -> float:
        """Measure available disk storage in gigabytes at target directory."""
        path = target_path or self.target_dir
        try:
            usage = shutil.disk_usage(str(path))
            return round(usage.free / (1024**3), 2)
        except Exception:
            return 10.0

    def detect_gpu(self) -> tuple[Optional[str], Optional[float]]:
        """Inspect available dedicated graphics hardware without stress tests."""
        # Check for nvidia-smi command
        nvidia_smi = shutil.which("nvidia-smi")
        if nvidia_smi:
            try:
                res = subprocess.run(
                    [nvidia_smi, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                    capture_output=True,
                    text=True,
                    timeout=3.0,
                    shell=False,
                )
                if res.returncode == 0 and res.stdout.strip():
                    line = res.stdout.strip().splitlines()[0]
                    parts = line.split(",")
                    name = parts[0].strip()
                    vram_mb = float(parts[1].strip()) if len(parts) > 1 else 0.0
                    return name, round(vram_mb / 1024.0, 2)
            except Exception:
                pass

        # Windows WMI query fallback for generic GPU
        if sys.platform == "win32":
            try:
                res = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"],
                    capture_output=True,
                    text=True,
                    timeout=3.0,
                    shell=False,
                )
                if res.returncode == 0 and res.stdout.strip():
                    first_gpu = res.stdout.strip().splitlines()[0]
                    return first_gpu.strip(), None
            except Exception:
                pass

        return None, None

    def run_full_check(self) -> SystemReport:
        """Execute complete hardware and platform inspection."""
        py_ver, py_compat = self.check_python_version()
        total_ram, avail_ram = self.get_system_ram_gb()
        free_disk = self.get_free_disk_gb()
        gpu_name, gpu_vram = self.detect_gpu()

        warnings: List[str] = []
        advisories: List[str] = []

        if not py_compat:
            warnings.append(f"Python {py_ver} is unsupported. CodeAgent requires Python 3.12 or newer.")

        if free_disk < 6.0:
            warnings.append(
                f"Low disk space: {free_disk} GB free on {self.target_dir.anchor}. "
                "Ollama and model downloads require at least 6-10 GB."
            )
        elif free_disk < 10.0:
            advisories.append(
                f"Available disk space is {free_disk} GB. Recommended headroom for model cache is 10+ GB."
            )

        if total_ram < 7.5:
            advisories.append(
                f"Detected {total_ram} GB total RAM. Qwen3 (5.2 GB) runs best with 12+ GB RAM. "
                "Ollama will utilize system swap if necessary."
            )

        if gpu_name:
            vram_str = f" ({gpu_vram} GB VRAM)" if gpu_vram else ""
            advisories.append(f"GPU detected: {gpu_name}{vram_str}. Ollama will leverage hardware acceleration.")
        else:
            advisories.append(
                "No discrete GPU detected. Ollama will run in optimized CPU inference mode using system RAM."
            )

        return SystemReport(
            os_name=platform.system(),
            os_release=platform.release(),
            architecture=platform.machine(),
            python_version=py_ver,
            python_compatible=py_compat,
            total_ram_gb=total_ram,
            available_ram_gb=avail_ram,
            free_disk_gb=free_disk,
            disk_path=str(self.target_dir),
            gpu_name=gpu_name,
            gpu_vram_gb=gpu_vram,
            warnings=warnings,
            advisories=advisories,
        )

