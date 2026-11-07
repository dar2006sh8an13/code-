"""Import relationship and module dependency graph analyzer with circular import detection."""

import ast
from pathlib import Path
import re
from typing import Dict, List, Optional, Set
from pydantic import BaseModel, Field


class ImportRelation(BaseModel):
    """Structured representation of a code import statement."""

    source_file: str
    imported_module: str
    imported_symbols: List[str] = Field(default_factory=list)
    line_number: int = 1


class ModuleDependencyGraph(BaseModel):
    """Project-wide module dependency graph with cycle detection."""

    nodes: List[str] = Field(default_factory=list)  # Module file paths
    edges: Dict[str, List[str]] = Field(default_factory=dict)  # source -> list of imported modules
    circular_dependencies: List[List[str]] = Field(default_factory=list)

    def add_dependency(self, source: str, target: str) -> None:
        """Add directed dependency edge from source to target."""
        if source not in self.nodes:
            self.nodes.append(source)
        if target not in self.nodes:
            self.nodes.append(target)
        if source not in self.edges:
            self.edges[source] = []
        if target not in self.edges[source]:
            self.edges[source].append(target)

    def find_circular_dependencies(self) -> List[List[str]]:
        """Identify and return all cycles in the graph."""
        analyzer = ImportAnalyzer()
        self.circular_dependencies = analyzer._find_cycles(self.edges)
        return self.circular_dependencies


class ImportAnalyzer:
    """Analyzes import relationships across project files and detects circular dependencies."""

    def __init__(self) -> None:
        """Initialize ImportAnalyzer."""
        pass

    def extract_imports(
        self,
        file_path: str = "",
        content: str = "",
        code: Optional[str] = None,
        language: Optional[str] = None,
    ) -> List[ImportRelation]:
        """Extract import relations from Python, JS, or TS source code."""
        text = code if code is not None else content
        ext = Path(file_path).suffix.lower()
        if ext == ".py" or language == "python":
            return self._extract_python_imports(file_path, text)
        elif ext in (".js", ".jsx", ".ts", ".tsx", ".mjs") or language in ("javascript", "typescript"):
            return self._extract_js_imports(file_path, text)
        return []

    def _extract_python_imports(self, file_path: str, content: str) -> List[ImportRelation]:
        """Extract Python import and import-from statements via AST."""
        relations: List[ImportRelation] = []
        try:
            tree = ast.parse(content, filename=file_path)
        except SyntaxError:
            # Fall back to regex on syntax failure
            for idx, line in enumerate(content.splitlines(), start=1):
                m_from = re.match(r"^from\s+([a-zA-Z0-9_\.]+)\s+import\s+(.+)$", line.strip())
                if m_from:
                    symbols = [s.strip() for s in m_from.group(2).split(",") if s.strip()]
                    relations.append(
                        ImportRelation(
                            source_file=file_path,
                            imported_module=m_from.group(1),
                            imported_symbols=symbols,
                            line_number=idx,
                        )
                    )
                else:
                    m_imp = re.match(r"^import\s+([a-zA-Z0-9_\.,\s]+)$", line.strip())
                    if m_imp:
                        for mod in m_imp.group(1).split(","):
                            clean_m = mod.strip().split(" as ")[0].strip()
                            if clean_m:
                                relations.append(
                                    ImportRelation(
                                        source_file=file_path,
                                        imported_module=clean_m,
                                        imported_symbols=[],
                                        line_number=idx,
                                    )
                                )
            return relations

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    relations.append(
                        ImportRelation(
                            source_file=file_path,
                            imported_module=alias.name,
                            imported_symbols=[alias.asname or alias.name],
                            line_number=node.lineno,
                        )
                    )
            elif isinstance(node, ast.ImportFrom):
                mod_name = "." * node.level + (node.module or "")
                symbols = [a.name for a in node.names]
                relations.append(
                    ImportRelation(
                        source_file=file_path,
                        imported_module=mod_name,
                        imported_symbols=symbols,
                        line_number=node.lineno,
                    )
                )

        return relations

    def _extract_js_imports(self, file_path: str, content: str) -> List[ImportRelation]:
        """Extract JavaScript / TypeScript import statements."""
        relations: List[ImportRelation] = []
        for idx, line in enumerate(content.splitlines(), start=1):
            clean = line.strip()
            # import { a, b } from './module' or import x from './module'
            m = re.match(r"import\s+(?:\{([^}]+)\}|([A-Za-z0-9_]+))\s+from\s+['\"]([^'\"]+)['\"]", clean)
            if m:
                symbols_raw = m.group(1) or m.group(2) or ""
                symbols = [s.strip() for s in symbols_raw.split(",") if s.strip()]
                module_name = m.group(3)
                relations.append(
                    ImportRelation(
                        source_file=file_path,
                        imported_module=module_name,
                        imported_symbols=symbols,
                        line_number=idx,
                    )
                )
            else:
                # const x = require('./module')
                m_req = re.match(r"(?:const|let|var)\s+([A-Za-z0-9_]+)\s*=\s*require\(['\"]([^'\"]+)['\"]\)", clean)
                if m_req:
                    relations.append(
                        ImportRelation(
                            source_file=file_path,
                            imported_module=m_req.group(2),
                            imported_symbols=[m_req.group(1)],
                            line_number=idx,
                        )
                    )

        return relations

    def build_dependency_graph(self, relations_by_file: Dict[str, List[ImportRelation]]) -> ModuleDependencyGraph:
        """Construct a module dependency graph and detect circular dependencies."""
        nodes = sorted(list(relations_by_file.keys()))
        edges: Dict[str, List[str]] = {node: [] for node in nodes}

        # Resolve imported modules to known node file paths
        for src_file, rels in relations_by_file.items():
            for rel in rels:
                mod_target = rel.imported_module
                # Normalize python package notation e.g. "my_pkg.util" -> "my_pkg/util.py"
                matched_target = self._resolve_module_to_file(mod_target, nodes, src_file)
                if matched_target and matched_target not in edges[src_file]:
                    edges[src_file].append(matched_target)

        # Cycle detection using DFS
        cycles = self._find_cycles(edges)

        return ModuleDependencyGraph(
            nodes=nodes,
            edges=edges,
            circular_dependencies=cycles,
        )

    def _resolve_module_to_file(self, module_name: str, known_files: List[str], source_file: str) -> Optional[str]:
        """Attempt to resolve an import path to a known workspace file path."""
        # Exact relative match
        clean_name = module_name.replace(".", "/")
        for candidate in known_files:
            c_stem = str(Path(candidate).with_suffix("")).replace("\\", "/")
            if c_stem.endswith(clean_name) or clean_name.endswith(c_stem):
                return candidate
        return None

    def _find_cycles(self, graph: Dict[str, List[str]]) -> List[List[str]]:
        """Identify circular dependency cycles using Depth-First Search."""
        visited: Set[str] = set()
        rec_stack: List[str] = []
        cycles: List[List[str]] = []

        def dfs(node: str) -> None:
            visited.add(node)
            rec_stack.append(node)

            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in rec_stack:
                    cycle_start = rec_stack.index(neighbor)
                    cycle = rec_stack[cycle_start:] + [neighbor]
                    cycles.append(cycle)

            rec_stack.pop()

        for n in graph:
            if n not in visited:
                dfs(n)

        return cycles
