"""Unit tests for Phase 3: Filesystem Intelligence.

These tests run completely offline against isolated temporary directory fixtures (tmp_path).
No live Ollama server or network connection is required.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from codeagent.config.settings import Settings
from codeagent.filesystem.backup import BackupManager, BackupNotFoundError
from codeagent.filesystem.deleter import (
    DeleteResult,
    DeletionNotConfirmedError,
    DirectoryDeletionBlockedError,
    FileDeleter,
)
from codeagent.filesystem.editor import (
    EditNotApprovedError,
    EditProposal,
    EditResult,
    FileEditor,
    TargetNotFoundError,
)
from codeagent.filesystem.manager import FilesystemManager
from codeagent.filesystem.path_validator import (
    InvalidPathError,
    PathValidator,
    SensitiveFileError,
    WorkspaceSecurityError,
)
from codeagent.filesystem.project_analyzer import ProjectAnalyzer
from codeagent.filesystem.reader import (
    BinaryFileError,
    FileReader,
    FileTooLargeError,
)
from codeagent.filesystem.scanner import DirectoryScanner
from codeagent.filesystem.writer import FileAlreadyExistsError, FileWriter
from codeagent.tools.executor import ToolExecutor
from codeagent.tools.registry import get_default_registry


# ==============================================================================
# 1. Path Validator Tests
# ==============================================================================

class TestPathValidator:
    """Test suite for PathValidator workspace containment and security checks."""

    def test_safe_path_inside_workspace(self, tmp_path: Path) -> None:
        validator = PathValidator(workspace_root=tmp_path)
        safe_file = tmp_path / "hello.py"
        safe_file.write_text("print('hello')", encoding="utf-8")

        resolved = validator.validate_and_resolve("hello.py", allow_nonexistent=False)
        assert resolved == safe_file.resolve()
        assert validator.is_inside_workspace("hello.py") is True

    def test_path_traversal_escaping_workspace_rejected(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        validator = PathValidator(workspace_root=workspace)

        with pytest.raises(WorkspaceSecurityError):
            validator.validate_and_resolve("../outside.txt", allow_nonexistent=True)

        with pytest.raises(WorkspaceSecurityError):
            validator.validate_and_resolve("subdir/../../outside.txt", allow_nonexistent=True)

    def test_absolute_path_outside_workspace_rejected(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        outside = tmp_path / "outside_dir"
        workspace.mkdir()
        outside.mkdir()

        validator = PathValidator(workspace_root=workspace)
        outside_file = outside / "secret.txt"

        with pytest.raises(WorkspaceSecurityError):
            validator.validate_and_resolve(outside_file, allow_nonexistent=True)

    def test_null_byte_rejected(self, tmp_path: Path) -> None:
        validator = PathValidator(workspace_root=tmp_path)
        with pytest.raises(InvalidPathError):
            validator.validate_and_resolve("evil\0file.txt", allow_nonexistent=True)

    def test_windows_reserved_device_names_rejected(self, tmp_path: Path) -> None:
        validator = PathValidator(workspace_root=tmp_path)
        with pytest.raises(InvalidPathError):
            validator.validate_and_resolve("con.txt", allow_nonexistent=True)
        with pytest.raises(InvalidPathError):
            validator.validate_and_resolve("sub/NUL.py", allow_nonexistent=True)

    def test_sensitive_files_blocked(self, tmp_path: Path) -> None:
        validator = PathValidator(workspace_root=tmp_path)

        sensitive_names = [
            ".env",
            ".env.local",
            ".env.production",
            ".git/config",
            ".ssh/id_rsa",
            "server.key",
            "cert.pem",
            "wallet.kdbx",
            "user_credentials.json",
        ]

        for s_name in sensitive_names:
            target = tmp_path / s_name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("secret_data", encoding="utf-8")

            with pytest.raises(SensitiveFileError):
                validator.validate_and_resolve(s_name, check_sensitive=True)


# ==============================================================================
# 2. File Reader Tests
# ==============================================================================

class TestFileReader:
    """Test suite for safe text file reading and line slicing."""

    def test_read_full_text_file(self, tmp_path: Path) -> None:
        validator = PathValidator(workspace_root=tmp_path)
        reader = FileReader(validator=validator)

        file_p = tmp_path / "sample.py"
        content = "line 1\nline 2\nline 3\n"
        file_p.write_text(content, encoding="utf-8")

        res = reader.read("sample.py")
        assert res.content == content
        assert res.total_lines == 3
        assert res.start_line == 1
        assert res.end_line == 3
        assert res.size_bytes == file_p.stat().st_size

    def test_read_line_range_slicing(self, tmp_path: Path) -> None:
        validator = PathValidator(workspace_root=tmp_path)
        reader = FileReader(validator=validator)

        file_p = tmp_path / "range.txt"
        file_p.write_text("A\nB\nC\nD\nE\n", encoding="utf-8")

        res = reader.read("range.txt", start_line=2, end_line=4)
        assert res.content == "B\nC\nD\n"
        assert res.total_lines == 5
        assert res.start_line == 2
        assert res.end_line == 4

    def test_read_nonexistent_file_raises_error(self, tmp_path: Path) -> None:
        validator = PathValidator(workspace_root=tmp_path)
        reader = FileReader(validator=validator)

        with pytest.raises(FileNotFoundError):
            reader.read("missing.txt")

    def test_reject_binary_file_with_null_bytes(self, tmp_path: Path) -> None:
        validator = PathValidator(workspace_root=tmp_path)
        reader = FileReader(validator=validator)

        binary_file = tmp_path / "data.bin"
        binary_file.write_bytes(b"\x00\x01\x02\x03\x00")

        with pytest.raises(BinaryFileError):
            reader.read("data.bin")

    def test_reject_binary_extension(self, tmp_path: Path) -> None:
        validator = PathValidator(workspace_root=tmp_path)
        reader = FileReader(validator=validator)

        exe_file = tmp_path / "app.exe"
        exe_file.write_bytes(b"MZfakeexeheader")

        with pytest.raises(BinaryFileError):
            reader.read("app.exe")

    def test_reject_file_exceeding_size_limit(self, tmp_path: Path) -> None:
        validator = PathValidator(workspace_root=tmp_path)
        # Limit to 1 MB for testing
        reader = FileReader(validator=validator, max_file_size_mb=1)

        large_file = tmp_path / "large.txt"
        # Write 1.5 MB of data
        large_file.write_bytes(b"A" * int(1.5 * 1024 * 1024))

        with pytest.raises(FileTooLargeError):
            reader.read("large.txt")


# ==============================================================================
# 3. File Writer Tests
# ==============================================================================

class TestFileWriter:
    """Test suite for safe file writing and overwrite protection."""

    def test_create_new_file(self, tmp_path: Path) -> None:
        validator = PathValidator(workspace_root=tmp_path)
        writer = FileWriter(validator=validator)

        res = writer.write("src/utils/math.py", content="def add(a, b): return a + b\n")
        assert res.created_new is True
        assert res.overwritten is False
        assert (tmp_path / "src" / "utils" / "math.py").exists()

    def test_overwrite_protection_prevents_accidental_clobber(self, tmp_path: Path) -> None:
        validator = PathValidator(workspace_root=tmp_path)
        writer = FileWriter(validator=validator)

        f = tmp_path / "existing.txt"
        f.write_text("original content", encoding="utf-8")

        with pytest.raises(FileAlreadyExistsError):
            writer.write("existing.txt", content="new content", overwrite=False)

        # File content must remain original
        assert f.read_text(encoding="utf-8") == "original content"

    def test_explicit_overwrite_succeeds_with_backup(self, tmp_path: Path) -> None:
        validator = PathValidator(workspace_root=tmp_path)
        backup_mgr = BackupManager(workspace_root=tmp_path)
        writer = FileWriter(validator=validator, backup_manager=backup_mgr)

        f = tmp_path / "existing.txt"
        f.write_text("original content", encoding="utf-8")

        res = writer.write("existing.txt", content="overwritten content", overwrite=True)
        assert res.overwritten is True
        assert res.backup_id is not None
        assert f.read_text(encoding="utf-8") == "overwritten content"


# ==============================================================================
# 4. File Editor Tests
# ==============================================================================

class TestFileEditor:
    """Test suite for diff generation, user approvals, and atomic editing."""

    def test_generate_unified_diff(self) -> None:
        orig = "def old_func():\n    return 1\n"
        mod = "def old_func():\n    return 42\n"

        diff = FileEditor.generate_unified_diff(orig, mod, "test.py")
        assert "--- a/test.py" in diff
        assert "+++ b/test.py" in diff
        assert "-    return 1" in diff
        assert "+    return 42" in diff

    def test_propose_edit_with_search_and_replace(self, tmp_path: Path) -> None:
        validator = PathValidator(workspace_root=tmp_path)
        editor = FileEditor(validator=validator)

        code_file = tmp_path / "app.py"
        code_file.write_text("DEBUG = True\nPORT = 8000\n", encoding="utf-8")

        proposal = editor.propose_edit(
            "app.py",
            search_target="DEBUG = True",
            replacement="DEBUG = False",
        )

        assert proposal.has_changes is True
        assert "DEBUG = False" in proposal.modified_content
        assert "-DEBUG = True" in proposal.diff
        assert "+DEBUG = False" in proposal.diff

    def test_propose_edit_target_not_found(self, tmp_path: Path) -> None:
        validator = PathValidator(workspace_root=tmp_path)
        editor = FileEditor(validator=validator)

        code_file = tmp_path / "app.py"
        code_file.write_text("PORT = 8000\n", encoding="utf-8")

        with pytest.raises(TargetNotFoundError):
            editor.propose_edit("app.py", search_target="NONEXISTENT", replacement="FOO")

    def test_apply_edit_requires_approval(self, tmp_path: Path) -> None:
        validator = PathValidator(workspace_root=tmp_path)
        backup_mgr = BackupManager(workspace_root=tmp_path)
        editor = FileEditor(validator=validator, backup_manager=backup_mgr)

        code_file = tmp_path / "script.py"
        code_file.write_text("x = 10\n", encoding="utf-8")

        proposal = editor.propose_edit("script.py", new_content="x = 20\n")

        # Approval callback rejects edit
        with pytest.raises(EditNotApprovedError):
            editor.apply_proposal(proposal, approval_callback=lambda p: False)

        assert code_file.read_text(encoding="utf-8") == "x = 10\n"

    def test_apply_edit_approved_modifies_atomically_and_backs_up(self, tmp_path: Path) -> None:
        validator = PathValidator(workspace_root=tmp_path)
        backup_mgr = BackupManager(workspace_root=tmp_path)
        editor = FileEditor(validator=validator, backup_manager=backup_mgr)

        code_file = tmp_path / "script.py"
        code_file.write_text("x = 10\n", encoding="utf-8")

        proposal = editor.propose_edit("script.py", new_content="x = 20\n")
        res = editor.apply_proposal(proposal, approved=True)

        assert res.verified is True
        assert res.backup_id != ""
        assert code_file.read_text(encoding="utf-8") == "x = 20\n"

        # Verify backup exists
        backup_meta = backup_mgr.get_backup(res.backup_id)
        assert backup_meta is not None
        assert backup_meta.operation == "edit"


# ==============================================================================
# 5. File Deleter Tests
# ==============================================================================

class TestFileDeleter:
    """Test suite for single file deletion and confirmation guards."""

    def test_delete_file_approved(self, tmp_path: Path) -> None:
        validator = PathValidator(workspace_root=tmp_path)
        backup_mgr = BackupManager(workspace_root=tmp_path)
        deleter = FileDeleter(validator=validator, backup_manager=backup_mgr)

        target = tmp_path / "cleanup.txt"
        target.write_text("remove me", encoding="utf-8")

        res = deleter.delete("cleanup.txt", confirmed=True)
        assert res.deleted is True
        assert not target.exists()

        # Backup was preserved
        assert backup_mgr.get_backup(res.backup_id) is not None

    def test_delete_unconfirmed_raises_error(self, tmp_path: Path) -> None:
        validator = PathValidator(workspace_root=tmp_path)
        deleter = FileDeleter(validator=validator)

        target = tmp_path / "cleanup.txt"
        target.write_text("remove me", encoding="utf-8")

        with pytest.raises(DeletionNotConfirmedError):
            deleter.delete("cleanup.txt", confirmed=False)

        assert target.exists()

    def test_reject_directory_deletion(self, tmp_path: Path) -> None:
        validator = PathValidator(workspace_root=tmp_path)
        deleter = FileDeleter(validator=validator)

        folder = tmp_path / "my_dir"
        folder.mkdir()

        with pytest.raises(DirectoryDeletionBlockedError):
            deleter.delete("my_dir", confirmed=True)


# ==============================================================================
# 6. Directory Scanner Tests
# ==============================================================================

class TestDirectoryScanner:
    """Test suite for recursive scanning, ignoring rules, and depth limits."""

    def test_list_directory_shallow(self, tmp_path: Path) -> None:
        validator = PathValidator(workspace_root=tmp_path)
        scanner = DirectoryScanner(validator=validator)

        (tmp_path / "dir_a").mkdir()
        (tmp_path / "file1.py").write_text("print(1)", encoding="utf-8")
        (tmp_path / "file2.txt").write_text("text", encoding="utf-8")

        entries = scanner.list_directory(tmp_path)
        names = [e.name for e in entries]
        assert "dir_a" in names
        assert "file1.py" in names
        assert "file2.txt" in names

    def test_scanner_ignores_standard_directories(self, tmp_path: Path) -> None:
        validator = PathValidator(workspace_root=tmp_path)
        scanner = DirectoryScanner(validator=validator)

        # Create ignored dirs
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_text("git config", encoding="utf-8")
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "foo.pyc").write_text("pyc", encoding="utf-8")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "pkg").mkdir()

        # Create normal files
        (tmp_path / "main.py").write_text("print('ok')", encoding="utf-8")

        res = scanner.scan_tree(tmp_path)
        assert res.total_files == 1
        assert res.total_dirs == 0
        assert "main.py" in res.tree_view
        assert ".git" not in res.tree_view
        assert "node_modules" not in res.tree_view

    def test_scanner_respects_max_depth(self, tmp_path: Path) -> None:
        validator = PathValidator(workspace_root=tmp_path)
        scanner = DirectoryScanner(validator=validator, max_depth=1)

        (tmp_path / "lvl1").mkdir()
        (tmp_path / "lvl1" / "lvl2").mkdir()
        (tmp_path / "lvl1" / "lvl2" / "deep.py").write_text("deep", encoding="utf-8")

        res = scanner.scan_tree(tmp_path, max_depth=1)
        names = [e.name for e in res.entries]
        assert "lvl1" in names
        assert "deep.py" not in names


# ==============================================================================
# 7. Project Analyzer Tests
# ==============================================================================

class TestProjectAnalyzer:
    """Test suite for project framework and architecture detection."""

    def test_detect_python_fastapi_project(self, tmp_path: Path) -> None:
        validator = PathValidator(workspace_root=tmp_path)
        analyzer = ProjectAnalyzer(validator=validator)

        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapi"\ndependencies = ["fastapi", "uvicorn"]\n',
            encoding="utf-8",
        )
        (tmp_path / "main.py").write_text(
            "from fastapi import FastAPI\napp = FastAPI()\n",
            encoding="utf-8",
        )

        analysis = analyzer.analyze(tmp_path)
        assert "Python" in analysis.languages
        assert "FastAPI" in analysis.frameworks
        assert "pyproject.toml" in analysis.dependency_files
        assert "main.py" in analysis.entry_points
        assert "FastAPI" in analysis.project_type

    def test_detect_node_react_project(self, tmp_path: Path) -> None:
        validator = PathValidator(workspace_root=tmp_path)
        analyzer = ProjectAnalyzer(validator=validator)

        package_json = {
            "name": "frontend",
            "dependencies": {"react": "^18.2.0", "react-dom": "^18.2.0"},
            "devDependencies": {"vite": "^4.0.0"},
        }
        (tmp_path / "package.json").write_text(json.dumps(package_json), encoding="utf-8")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "App.tsx").write_text("export default function App() {}", encoding="utf-8")

        analysis = analyzer.analyze(tmp_path)
        assert "React" in analysis.frameworks
        assert "package.json" in analysis.dependency_files
        assert "React" in analysis.project_type


# ==============================================================================
# 8. Backup Manager Tests
# ==============================================================================

class TestBackupManager:
    """Test suite for automatic file backups and restores."""

    def test_create_and_restore_backup(self, tmp_path: Path) -> None:
        ws = tmp_path / "workspace"
        ws.mkdir()
        mgr = BackupManager(backup_dir=".codeagent/backups", workspace_root=ws)

        test_file = ws / "important.py"
        test_file.write_text("version 1", encoding="utf-8")

        meta = mgr.create_backup(test_file, operation="edit")
        assert meta.backup_id != ""
        assert meta.operation == "edit"
        assert meta.original_path == "important.py"

        # Modify file
        test_file.write_text("corrupted version", encoding="utf-8")

        # Restore from backup
        restored_path = mgr.restore_backup(meta.backup_id)
        assert restored_path == test_file
        assert test_file.read_text(encoding="utf-8") == "version 1"

    def test_restore_nonexistent_backup_raises_error(self, tmp_path: Path) -> None:
        mgr = BackupManager(workspace_root=tmp_path)
        with pytest.raises(BackupNotFoundError):
            mgr.restore_backup("nonexistent_backup_id")


# ==============================================================================
# 9. Filesystem Tools & Registry Integration Tests
# ==============================================================================

class TestFilesystemToolsIntegration:
    """Test suite for ToolRegistry and ToolExecutor filesystem tools."""

    def test_registry_contains_all_phase3_tools(self, tmp_path: Path) -> None:
        fs_mgr = FilesystemManager(workspace_root=tmp_path)
        registry = get_default_registry(filesystem_manager=fs_mgr)

        tool_names = [t.name for t in registry.list_tools()]
        expected_fs_tools = [
            "read_file",
            "create_file",
            "edit_file",
            "delete_file",
            "list_directory",
            "scan_project",
            "analyze_project",
        ]

        for expected in expected_fs_tools:
            assert expected in tool_names, f"Tool '{expected}' missing from registry."

    def test_execute_create_read_edit_delete_via_executor(self, tmp_path: Path) -> None:
        settings = Settings(_env_file=None, require_write_approval=False, require_delete_approval=False)
        fs_mgr = FilesystemManager(settings=settings, workspace_root=tmp_path)
        registry = get_default_registry(filesystem_manager=fs_mgr)
        executor = ToolExecutor(registry=registry)

        # 1. create_file
        res_create = executor.execute(
            "create_file",
            {"path": "greeting.py", "content": "print('hello world')\n", "overwrite": False},
        )
        assert res_create.success is True
        assert (tmp_path / "greeting.py").exists()

        # 2. read_file
        res_read = executor.execute(
            "read_file",
            {"path": "greeting.py", "start_line": 1, "end_line": 1},
        )
        assert res_read.success is True
        assert "hello world" in res_read.result["content"]

        # 3. edit_file
        res_edit = executor.execute(
            "edit_file",
            {
                "path": "greeting.py",
                "search_target": "hello world",
                "replacement": "hello Code AG",
            },
        )
        assert res_edit.success is True
        assert (tmp_path / "greeting.py").read_text(encoding="utf-8") == "print('hello Code AG')\n"

        # 4. list_directory
        res_list = executor.execute("list_directory", {"path": "."})
        assert res_list.success is True
        entry_names = [e["name"] for e in res_list.result["entries"]]
        assert "greeting.py" in entry_names

        # 5. scan_project
        res_scan = executor.execute("scan_project", {})
        assert res_scan.success is True
        assert res_scan.result["total_files"] >= 1

        # 6. analyze_project
        res_analyze = executor.execute("analyze_project", {})
        assert res_analyze.success is True
        assert "Python" in res_analyze.result["languages"]

        # 7. delete_file
        res_delete = executor.execute("delete_file", {"path": "greeting.py", "confirmed": True})
        assert res_delete.success is True
        assert not (tmp_path / "greeting.py").exists()
