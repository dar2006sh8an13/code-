"""End-to-end installation validation and readiness verification for CodeAgent."""

from dataclasses import dataclass, field
import sys
from typing import Dict, List, Optional, Tuple

import httpx

from codeagent.installer.ollama_detector import OllamaDetector, OllamaStatus
from codeagent.installer.model_manager import ModelManager


@dataclass
class ValidationStep:
    """Status record for an individual validation test."""

    name: str
    passed: bool
    message: str


@dataclass
class ValidationReport:
    """Comprehensive readiness assessment report."""

    all_passed: bool
    steps: List[ValidationStep] = field(default_factory=list)

    def to_summary(self) -> str:
        """Produce a human-readable one-line summary."""
        passed_count = sum(1 for s in self.steps if s.passed)
        return f"{passed_count}/{len(self.steps)} verification checks passed."


class InstallationValidator:
    """Verifies end-to-end readiness across Python, Ollama executable, daemon, and model."""

    def __init__(
        self,
        api_url: str = "http://localhost:11434",
        detector: Optional[OllamaDetector] = None,
        model_manager: Optional[ModelManager] = None,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.detector = detector or OllamaDetector(api_url=self.api_url)
        self.model_mgr = model_manager or ModelManager(api_url=self.api_url)

    def validate_python(self) -> ValidationStep:
        """Verify Python 3.12+ compatibility."""
        ver = sys.version_info
        ver_str = f"{ver.major}.{ver.minor}.{ver.micro}"
        is_ok = (ver.major, ver.minor) >= (3, 12)
        msg = f"Python {ver_str} is compatible." if is_ok else f"Python {ver_str} is unsupported (requires >= 3.12)."
        return ValidationStep(name="Python Runtime", passed=is_ok, message=msg)

    def validate_ollama_binary(self) -> ValidationStep:
        """Verify Ollama executable exists and is discoverable."""
        path = self.detector.find_executable()
        if path:
            ver = self.detector.query_binary_version(path)
            ver_str = f" v{ver}" if ver else ""
            return ValidationStep(
                name="Ollama Binary",
                passed=True,
                message=f"Found Ollama{ver_str} at '{path}'.",
            )
        return ValidationStep(
            name="Ollama Binary",
            passed=False,
            message="Ollama executable not found in PATH or standard installation directories.",
        )

    def validate_ollama_service(self) -> ValidationStep:
        """Verify Ollama background daemon is responding to HTTP queries."""
        is_online, ver, _ = self.detector.probe_http_api()
        if is_online:
            return ValidationStep(
                name="Ollama Service",
                passed=True,
                message=f"Ollama server is active at {self.api_url} (version: {ver or 'unknown'}).",
            )
        return ValidationStep(
            name="Ollama Service",
            passed=False,
            message=f"Ollama server is not responding at {self.api_url}.",
        )

    def validate_model(self, model_name: str = "qwen3:latest") -> ValidationStep:
        """Verify configured model is downloaded and registered."""
        is_installed = self.model_mgr.is_model_installed(model_name)
        if is_installed:
            return ValidationStep(
                name="Configured Model",
                passed=True,
                message=f"Model '{model_name}' is installed and registered locally.",
            )
        return ValidationStep(
            name="Configured Model",
            passed=False,
            message=f"Model '{model_name}' is missing from local Ollama storage.",
        )

    def run_all_validations(self, model_name: str = "qwen3:latest", check_model: bool = True) -> ValidationReport:
        """Execute complete suite of operational checks."""
        steps: List[ValidationStep] = []
        steps.append(self.validate_python())
        steps.append(self.validate_ollama_binary())
        steps.append(self.validate_ollama_service())

        if check_model:
            steps.append(self.validate_model(model_name))

        all_passed = all(s.passed for s in steps)
        return ValidationReport(all_passed=all_passed, steps=steps)

