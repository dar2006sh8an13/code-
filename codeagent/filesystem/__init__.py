"""Filesystem Intelligence package for CodeAgent."""

from codeagent.filesystem.backup import BackupManager, BackupMetadata
from codeagent.filesystem.deleter import DeleteResult, FileDeleter
from codeagent.filesystem.editor import EditProposal, EditResult, FileEditor
from codeagent.filesystem.manager import FilesystemManager
from codeagent.filesystem.path_validator import (
    InvalidPathError,
    PathTraversalError,
    PathValidationError,
    PathValidator,
    SensitiveFileError,
    WorkspaceSecurityError,
)
from codeagent.filesystem.project_analyzer import ProjectAnalysis, ProjectAnalyzer
from codeagent.filesystem.reader import FileReader, ReadResult
from codeagent.filesystem.scanner import DirectoryEntry, DirectoryScanner, ScanResult
from codeagent.filesystem.writer import FileWriter, WriteResult

__all__ = [
    "BackupManager",
    "BackupMetadata",
    "DeleteResult",
    "DirectoryEntry",
    "DirectoryScanner",
    "EditProposal",
    "EditResult",
    "FileDeleter",
    "FileEditor",
    "FileReader",
    "FilesystemManager",
    "FileWriter",
    "InvalidPathError",
    "PathTraversalError",
    "PathValidationError",
    "PathValidator",
    "ProjectAnalysis",
    "ProjectAnalyzer",
    "ReadResult",
    "ScanResult",
    "SensitiveFileError",
    "WorkspaceSecurityError",
    "WriteResult",
]

