"""Project intelligence subsystem providing language detection, dependency analysis, architecture mapping, and context building."""

from codeagent.intelligence.architecture_mapper import ArchitectureMap, ArchitectureMapper, ProjectLayer
from codeagent.intelligence.context_builder import ContextBuilder, ProjectContextBundle
from codeagent.intelligence.dependency_analyzer import DependencyAnalyzer, DependencyReport, DiscoveredDependency
from codeagent.intelligence.language_detector import LanguageDetector, LanguageDistribution, LanguageStats
from codeagent.intelligence.project_analyzer import ComprehensiveProjectAnalysis, ProjectAnalyzer
from codeagent.intelligence.project_manager import ProjectManager, ProjectRecord

__all__ = [
    "ArchitectureMap",
    "ArchitectureMapper",
    "ComprehensiveProjectAnalysis",
    "ContextBuilder",
    "DependencyAnalyzer",
    "DependencyReport",
    "DiscoveredDependency",
    "LanguageDetector",
    "LanguageDistribution",
    "LanguageStats",
    "ProjectAnalyzer",
    "ProjectContextBundle",
    "ProjectLayer",
    "ProjectManager",
    "ProjectRecord",
]

