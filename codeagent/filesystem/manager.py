"""Central Filesystem Manager coordinating operations, permissions, and tool interfaces."""

from pathlib import Path
from typing import Any, Callable, Optional, Union

from codeagent.config.settings import Settings, get_settings
from codeagent.filesystem.backup import BackupManager, BackupMetadata
from codeagent.filesystem.deleter import DeleteResult, FileDeleter
from codeagent.filesystem.editor import EditProposal, EditResult, FileEditor
from codeagent.filesystem.path_validator import PathValidator
from codeagent.filesystem.project_analyzer import ProjectAnalysis, ProjectAnalyzer
from codeagent.filesystem.reader import FileReader, ReadResult
from codeagent.filesystem.scanner import DirectoryEntry, DirectoryScanner, ScanResult
from codeagent.filesystem.writer import FileWriter, WriteResult


class FilesystemManager:
    """Central coordinator mediating all filesystem access for CodeAgent."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        workspace_root: Optional[Union[str, Path]] = None,
        write_approval_callback: Optional[Callable[[EditProposal], bool]] = None,
        delete_confirmation_callback: Optional[Callable[[Path], bool]] = None,
    ) -> None:
        """Initialize FilesystemManager with settings and approval handlers."""
        self.settings = settings or get_settings()

        # Workspace root resolution
        ws_root = workspace_root or self.settings.workspace_root or Path.cwd()
        self.workspace_root = Path(ws_root).resolve()

        # Core subsystems
        self.validator = PathValidator(workspace_root=self.workspace_root)
        self.backup_manager = BackupManager(
            backup_dir=self.settings.backup_directory,
            workspace_root=self.workspace_root,
        )
        self.reader = FileReader(
            validator=self.validator,
            max_file_size_mb=self.settings.max_file_size_mb,
        )
        self.writer = FileWriter(
            validator=self.validator,
            backup_manager=self.backup_manager if self.settings.backup_enabled else None,
        )
        self.editor = FileEditor(
            validator=self.validator,
            backup_manager=self.backup_manager,
            reader=self.reader,
        )
        self.deleter = FileDeleter(
            validator=self.validator,
            backup_manager=self.backup_manager,
        )
        self.scanner = DirectoryScanner(
            validator=self.validator,
            max_depth=self.settings.max_scan_depth,
            max_entries=self.settings.max_scan_entries,
        )
        self.analyzer = ProjectAnalyzer(
            validator=self.validator,
            scanner=self.scanner,
        )

        # Callbacks
        self.write_approval_callback = write_approval_callback
        self.delete_confirmation_callback = delete_confirmation_callback

    def set_workspace_root(self, new_root: Union[str, Path]) -> Path:
        """Update the active workspace root and reconfigure subcomponents."""
        self.workspace_root = Path(new_root).resolve()
        self.validator = PathValidator(workspace_root=self.workspace_root)
        self.backup_manager = BackupManager(
            backup_dir=self.settings.backup_directory,
            workspace_root=self.workspace_root,
        )
        self.reader = FileReader(
            validator=self.validator,
            max_file_size_mb=self.settings.max_file_size_mb,
        )
        self.writer = FileWriter(
            validator=self.validator,
            backup_manager=self.backup_manager if self.settings.backup_enabled else None,
        )
        self.editor = FileEditor(
            validator=self.validator,
            backup_manager=self.backup_manager,
            reader=self.reader,
        )
        self.deleter = FileDeleter(
            validator=self.validator,
            backup_manager=self.backup_manager,
        )
        self.scanner = DirectoryScanner(
            validator=self.validator,
            max_depth=self.settings.max_scan_depth,
            max_entries=self.settings.max_scan_entries,
        )
        self.analyzer = ProjectAnalyzer(
            validator=self.validator,
            scanner=self.scanner,
        )
        return self.workspace_root

    def read_file(
        self,
        path: Union[str, Path],
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
    ) -> ReadResult:
        """Read a file safely within workspace bounds."""
        return self.reader.read(path, start_line=start_line, end_line=end_line)

    def create_file(
        self,
        path: Union[str, Path],
        content: str,
        overwrite: bool = False,
    ) -> WriteResult:
        """Create a file within the workspace."""
        return self.writer.write(path, content=content, overwrite=overwrite)

    def edit_file(
        self,
        path: Union[str, Path],
        new_content: Optional[str] = None,
        search_target: Optional[str] = None,
        replacement: Optional[str] = None,
        approved: bool = False,
    ) -> EditResult:
        """Propose and apply an edit with interactive approval support."""
        proposal = self.editor.propose_edit(
            target_path=path,
            new_content=new_content,
            search_target=search_target,
            replacement=replacement,
        )

        # Check if write approval is required by settings
        auto_approved = approved or (not self.settings.require_write_approval)

        return self.editor.apply_proposal(
            proposal=proposal,
            approved=auto_approved,
            approval_callback=self.write_approval_callback,
        )

    def delete_file(
        self,
        path: Union[str, Path],
        confirmed: bool = False,
    ) -> DeleteResult:
        """Delete an individual file with confirmation support."""
        auto_confirmed = confirmed or (not self.settings.require_delete_approval)
        return self.deleter.delete(
            target_path=path,
            confirmed=auto_confirmed,
            confirmation_callback=self.delete_confirmation_callback,
        )

    def list_directory(
        self,
        path: Optional[Union[str, Path]] = None,
        max_depth: int = 1,
    ) -> list[DirectoryEntry]:
        """List files and directories directly under target path."""
        return self.scanner.list_directory(target_path=path, max_depth=max_depth)

    def scan_project(
        self,
        path: Optional[Union[str, Path]] = None,
        max_depth: Optional[int] = None,
    ) -> ScanResult:
        """Scan project directory tree."""
        return self.scanner.scan_tree(target_path=path, max_depth=max_depth)

    def analyze_project(
        self,
        path: Optional[Union[str, Path]] = None,
    ) -> ProjectAnalysis:
        """Analyze project structure, dependencies, and frameworks."""
        return self.analyzer.analyze(target_path=path)

    def create_directory(
        self,
        path: Union[str, Path],
        parents: bool = True,
        exist_ok: bool = True,
    ) -> dict[str, Any]:
        """Create a directory safely within workspace boundary.

        Args:
            path: Target directory path within workspace.
            parents: If True, creates missing parent directories.
            exist_ok: If True, does not raise error if directory exists.

        Returns:
            dict[str, Any]: Creation summary containing relative and absolute paths.
        """
        target = self.validator.validate_and_resolve(path)
        existed = target.exists()
        target.mkdir(parents=parents, exist_ok=exist_ok)
        rel_path = str(target.relative_to(self.workspace_root))
        return {
            "path": rel_path,
            "absolute_path": str(target),
            "created": not existed,
            "message": f"{'Created' if not existed else 'Directory already exists:'} '{rel_path}'",
        }

    def list_backups(self) -> list[BackupMetadata]:
        """List all available backups."""
        return self.backup_manager.list_backups()

    def restore_backup(self, backup_id: str, destination: Optional[Path] = None) -> Path:
        """Restore a file from backup."""
        return self.backup_manager.restore_backup(backup_id, destination_path=destination)

