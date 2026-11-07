"""First-time setup, Ollama installation, and model management subsystem for CodeAgent."""

from codeagent.installer.download_manager import (
    ChecksumMismatchError,
    DownloadError,
    DownloadManager,
)
from codeagent.installer.installation_validator import (
    InstallationValidator,
    ValidationReport,
    ValidationStep,
)
from codeagent.installer.model_manager import (
    ModelManager,
    ModelPullError,
)
from codeagent.installer.ollama_detector import (
    OllamaDetectionResult,
    OllamaDetector,
    OllamaStatus,
)
from codeagent.installer.ollama_installer import (
    OllamaInstaller,
)
from codeagent.installer.setup_manager import (
    SetupManager,
)
from codeagent.installer.setup_state import (
    SetupState,
    SetupStateManager,
)
from codeagent.installer.system_checker import (
    SystemChecker,
    SystemReport,
)

__all__ = [
    "ChecksumMismatchError",
    "DownloadError",
    "DownloadManager",
    "InstallationValidator",
    "ModelManager",
    "ModelPullError",
    "OllamaDetectionResult",
    "OllamaDetector",
    "OllamaInstaller",
    "OllamaStatus",
    "SetupManager",
    "SetupState",
    "SetupStateManager",
    "SystemChecker",
    "SystemReport",
    "ValidationReport",
    "ValidationStep",
]

