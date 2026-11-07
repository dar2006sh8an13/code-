"""Comprehensive unit tests for CodeAgent automatic Ollama and Qwen3 setup subsystem."""

import json
from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from codeagent.cli import app
from codeagent.installer.download_manager import ChecksumMismatchError, DownloadError, DownloadManager
from codeagent.installer.installation_validator import InstallationValidator, ValidationReport, ValidationStep
from codeagent.installer.model_manager import ModelManager, ModelPullError
from codeagent.installer.ollama_detector import OllamaDetectionResult, OllamaDetector, OllamaStatus
from codeagent.installer.ollama_installer import OllamaInstaller
from codeagent.installer.setup_manager import SetupManager
from codeagent.installer.setup_state import SetupState, SetupStateManager
from codeagent.installer.system_checker import SystemChecker, SystemReport


# ===========================================================================
# 1. Setup State Persistence Tests
# ===========================================================================


def test_setup_state_persistence_and_reset():
    with tempfile.TemporaryDirectory() as tmp_dir:
        state_file = Path(tmp_dir) / "setup_state.json"
        mgr = SetupStateManager(state_file=state_file)

        # 1. Fresh state is uninitialized
        state = mgr.load()
        assert state.setup_completed is False
        assert state.setup_skipped is False
        assert mgr.is_setup_needed() is True

        # 2. Mark completed
        mgr.mark_completed(ollama_version="0.3.14", model_name="qwen3:latest")
        updated = mgr.load()
        assert updated.setup_completed is True
        assert updated.setup_skipped is False
        assert updated.ollama_version == "0.3.14"
        assert updated.configured_model == "qwen3:latest"
        assert updated.last_verified_at is not None
        assert mgr.is_setup_needed() is False

        # 3. Reset
        mgr.reset()
        reset_state = mgr.load()
        assert reset_state.setup_completed is False
        assert mgr.is_setup_needed() is True


def test_setup_state_skip():
    with tempfile.TemporaryDirectory() as tmp_dir:
        state_file = Path(tmp_dir) / "setup_state.json"
        mgr = SetupStateManager(state_file=state_file)

        mgr.mark_skipped(model_name="qwen3:latest")
        state = mgr.load()
        assert state.setup_completed is False
        assert state.setup_skipped is True
        assert mgr.is_setup_needed() is False


# ===========================================================================
# 2. Hardware and System Checker Tests
# ===========================================================================


def test_system_checker_report():
    checker = SystemChecker()
    report = checker.run_full_check()

    assert isinstance(report, SystemReport)
    assert report.python_version != ""
    assert report.total_ram_gb > 0
    assert report.free_disk_gb >= 0
    assert report.os_name != ""


def test_system_checker_insufficient_disk_warning():
    checker = SystemChecker()
    with patch.object(checker, "get_free_disk_gb", return_value=3.5):
        report = checker.run_full_check()
        assert any("Low disk space" in w for w in report.warnings)
        assert report.is_compatible is False


# ===========================================================================
# 3. Ollama Detector Probes (Mocked HTTP & Filesystem)
# ===========================================================================


def test_ollama_detector_running():
    detector = OllamaDetector()
    with patch.object(detector, "probe_http_api", return_value=(True, "0.3.14", ["qwen3:latest", "gemma:latest"])):
        with patch.object(detector, "find_executable", return_value="/usr/local/bin/ollama"):
            res = detector.detect()
            assert res.status == OllamaStatus.RUNNING
            assert res.is_running is True
            assert res.is_installed is True
            assert "qwen3:latest" in res.installed_models
            assert res.version == "0.3.14"


def test_ollama_detector_installed_stopped():
    detector = OllamaDetector()
    with patch.object(detector, "probe_http_api", return_value=(False, None, [])):
        with patch.object(detector, "find_executable", return_value="C:\\Programs\\Ollama\\ollama.exe"):
            with patch.object(detector, "query_binary_version", return_value="0.3.12"):
                res = detector.detect()
                assert res.status == OllamaStatus.INSTALLED_STOPPED
                assert res.is_running is False
                assert res.is_installed is True
                assert res.executable_path == "C:\\Programs\\Ollama\\ollama.exe"
                assert res.version == "0.3.12"


def test_ollama_detector_not_installed():
    detector = OllamaDetector()
    with patch.object(detector, "probe_http_api", return_value=(False, None, [])):
        with patch.object(detector, "find_executable", return_value=None):
            res = detector.detect()
            assert res.status == OllamaStatus.NOT_INSTALLED
            assert res.is_running is False
            assert res.is_installed is False
            assert res.executable_path is None


# ===========================================================================
# 4. Model Manager Tests (Mocked Ollama API)
# ===========================================================================


def test_model_manager_installed_check():
    mgr = ModelManager()
    with patch.object(mgr, "list_installed_models", return_value=["qwen3:latest", "llama3:latest"]):
        assert mgr.is_model_installed("qwen3:latest") is True
        assert mgr.is_model_installed("qwen3") is True
        assert mgr.is_model_installed("missing_model:latest") is False


def test_model_manager_pull_streaming_mock():
    mgr = ModelManager()
    mock_lines = [
        b'{"status": "pulling manifest"}',
        b'{"status": "downloading", "total": 1000, "completed": 500}',
        b'{"status": "downloading", "total": 1000, "completed": 1000}',
        b'{"status": "success"}',
    ]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.iter_lines.return_value = mock_lines

    with patch.object(mgr, "is_model_installed", side_effect=[False, True]):
        with patch("httpx.stream") as mock_stream:
            mock_stream.return_value.__enter__.return_value = mock_response
            ok, msg = mgr.pull_model(model_name="qwen3:latest", show_progress=False)
            assert ok is True
            assert "verified and ready" in msg or "downloaded successfully" in msg


def test_model_manager_pull_failure_mock():
    mgr = ModelManager()
    mock_response = MagicMock()
    mock_response.status_code = 500

    with patch.object(mgr, "is_model_installed", return_value=False):
        with patch("httpx.stream") as mock_stream:
            mock_stream.return_value.__enter__.return_value = mock_response
            ok, msg = mgr.pull_model(model_name="qwen3:latest", show_progress=False, max_retries=1)
            assert ok is False
            assert "Failed to pull" in msg or "status 500" in msg


# ===========================================================================
# 5. Download Manager & Checksum Validation
# ===========================================================================


def test_download_manager_file_and_checksum():
    with tempfile.TemporaryDirectory() as tmp_dir:
        dest_file = Path(tmp_dir) / "test_download.bin"
        downloader = DownloadManager()

        sample_bytes = b"Hello CodeAgent Installer"
        expected_hash = downloader.calculate_sha256(
            Path(tmp_dir) / "dummy.bin"
            if (Path(tmp_dir) / "dummy.bin").write_bytes(sample_bytes)
            else Path(tmp_dir) / "dummy.bin"
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Length": str(len(sample_bytes))}
        mock_resp.iter_bytes.return_value = [sample_bytes]

        with patch("httpx.stream") as mock_stream:
            mock_stream.return_value.__enter__.return_value = mock_resp
            result_path = downloader.download_file(
                url="https://example.com/test.bin",
                destination_path=dest_file,
                expected_sha256=expected_hash,
                show_progress=False,
            )
            assert result_path.exists()
            assert result_path.read_bytes() == sample_bytes


def test_download_manager_checksum_mismatch():
    with tempfile.TemporaryDirectory() as tmp_dir:
        dest_file = Path(tmp_dir) / "bad_checksum.bin"
        downloader = DownloadManager()
        sample_bytes = b"Corrupted Data"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Length": str(len(sample_bytes))}
        mock_resp.iter_bytes.return_value = [sample_bytes]

        with patch("httpx.stream") as mock_stream:
            mock_stream.return_value.__enter__.return_value = mock_resp
            with pytest.raises(ChecksumMismatchError):
                downloader.download_file(
                    url="https://example.com/corrupt.bin",
                    destination_path=dest_file,
                    expected_sha256="0000000000000000000000000000000000000000000000000000000000000000",
                    show_progress=False,
                )


# ===========================================================================
# 6. Installation Validator Multi-Point Checks
# ===========================================================================


def test_installation_validator_success():
    validator = InstallationValidator()
    with patch.object(validator, "validate_python", return_value=ValidationStep("Python", True, "OK")):
        with patch.object(validator, "validate_ollama_binary", return_value=ValidationStep("Binary", True, "OK")):
            with patch.object(validator, "validate_ollama_service", return_value=ValidationStep("Service", True, "OK")):
                with patch.object(validator, "validate_model", return_value=ValidationStep("Model", True, "OK")):
                    report = validator.run_all_validations("qwen3:latest")
                    assert report.all_passed is True
                    assert len(report.steps) == 4


def test_installation_validator_partial_failure():
    validator = InstallationValidator()
    with patch.object(validator, "validate_python", return_value=ValidationStep("Python", True, "OK")):
        with patch.object(validator, "validate_ollama_binary", return_value=ValidationStep("Binary", True, "OK")):
            with patch.object(validator, "validate_ollama_service", return_value=ValidationStep("Service", False, "Offline")):
                with patch.object(validator, "validate_model", return_value=ValidationStep("Model", False, "Missing")):
                    report = validator.run_all_validations("qwen3:latest")
                    assert report.all_passed is False
                    assert any(not s.passed for s in report.steps)


# ===========================================================================
# 7. Setup Manager Workflow Tests
# ===========================================================================


def test_setup_manager_check_only_workflow():
    with tempfile.TemporaryDirectory() as tmp_dir:
        state_mgr = SetupStateManager(state_file=Path(tmp_dir) / "state.json")
        setup_mgr = SetupManager(state_manager=state_mgr)

        with patch.object(setup_mgr.system_checker, "check_python_version", return_value=("3.12.9", True)):
            with patch.object(setup_mgr.validator, "run_all_validations") as mock_val:
                mock_val.return_value = ValidationReport(all_passed=True, steps=[ValidationStep("All", True, "OK")])
                passed = setup_mgr.run_setup(check_only=True)
                assert passed is True


def test_setup_manager_skip_model_flag():
    with tempfile.TemporaryDirectory() as tmp_dir:
        state_mgr = SetupStateManager(state_file=Path(tmp_dir) / "state.json")
        setup_mgr = SetupManager(state_manager=state_mgr)

        with patch.object(setup_mgr.system_checker, "check_python_version", return_value=("3.12.9", True)):
            with patch.object(setup_mgr.detector, "detect", return_value=OllamaDetectionResult(OllamaStatus.RUNNING, version="0.3.14")):
                with patch.object(setup_mgr.validator, "run_all_validations") as mock_val:
                    mock_val.return_value = ValidationReport(all_passed=True, steps=[ValidationStep("Runtime", True, "OK")])
                    passed = setup_mgr.run_setup(skip_model=True, auto_confirm=True)
                    assert passed is True
                    state = state_mgr.load()
                    assert state.setup_completed is True


# ===========================================================================
# 8. CLI Commands (setup, models) Integration Tests
# ===========================================================================


def test_cli_setup_check_command():
    runner = CliRunner()
    result = runner.invoke(app, ["setup", "--check"])
    assert "[1/6] Checking Python runtime..." in result.stdout
    assert "System Readiness Verification" in result.stdout


def test_cli_models_current_command():
    runner = CliRunner()
    result = runner.invoke(app, ["models", "current"])
    assert result.exit_code == 0
    assert "Configured model:" in result.stdout
    assert "qwen3:latest" in result.stdout

