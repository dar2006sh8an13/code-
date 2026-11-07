"""Non-executing dependency manifest parser extracting packages and versions."""

import json
from pathlib import Path
import re
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class DiscoveredDependency(BaseModel):
    """Structured representation of a project dependency."""

    name: str
    version_spec: Optional[str] = None
    manifest_file: str
    is_dev: bool = False


class DependencyReport(BaseModel):
    """Comprehensive inventory of project dependencies."""

    manifest_files: List[str] = Field(default_factory=list)
    dependencies: List[DiscoveredDependency] = Field(default_factory=list)

    @property
    def total_count(self) -> int:
        """Total number of discovered dependencies."""
        return len(self.dependencies)

    def to_summary(self) -> str:
        """Format an informative summary of parsed dependencies."""
        manifest_str = ", ".join(self.manifest_files) if self.manifest_files else "None"
        sample = [f"{d.name} ({d.version_spec or 'any'})" for d in self.dependencies[:8]]
        if len(self.dependencies) > 8:
            sample.append(f"... +{len(self.dependencies) - 8} more")
        return f"Manifests: {manifest_str}\nPackages ({self.total_count}): {', '.join(sample)}"


class DependencyAnalyzer:
    """Analyzes package manifests without executing or installing packages."""

    def __init__(self) -> None:
        """Initialize DependencyAnalyzer."""
        pass

    def analyze_workspace(self, workspace_root: Path) -> DependencyReport:
        """Scan workspace for known manifests and extract dependencies safely."""
        discovered: List[DiscoveredDependency] = []
        manifests: List[str] = []

        # 1. Python requirements.txt & requirements-*.txt
        for p in workspace_root.glob("*requirement*.txt"):
            if p.is_file():
                rel_p = str(p.relative_to(workspace_root)).replace("\\", "/")
                manifests.append(rel_p)
                discovered.extend(self._parse_requirements_txt(p, rel_p))

        # 2. pyproject.toml
        pyproject_path = workspace_root / "pyproject.toml"
        if pyproject_path.exists() and pyproject_path.is_file():
            rel_p = str(pyproject_path.relative_to(workspace_root)).replace("\\", "/")
            manifests.append(rel_p)
            discovered.extend(self._parse_pyproject_toml(pyproject_path, rel_p))

        # 3. package.json
        pkg_json_path = workspace_root / "package.json"
        if pkg_json_path.exists() and pkg_json_path.is_file():
            rel_p = str(pkg_json_path.relative_to(workspace_root)).replace("\\", "/")
            manifests.append(rel_p)
            discovered.extend(self._parse_package_json(pkg_json_path, rel_p))

        # 4. Java pom.xml
        pom_path = workspace_root / "pom.xml"
        if pom_path.exists() and pom_path.is_file():
            rel_p = str(pom_path.relative_to(workspace_root)).replace("\\", "/")
            manifests.append(rel_p)
            discovered.extend(self._parse_pom_xml(pom_path, rel_p))

        # 5. Java build.gradle
        gradle_path = workspace_root / "build.gradle"
        if gradle_path.exists() and gradle_path.is_file():
            rel_p = str(gradle_path.relative_to(workspace_root)).replace("\\", "/")
            manifests.append(rel_p)
            discovered.extend(self._parse_gradle(gradle_path, rel_p))

        # 6. Rust Cargo.toml
        cargo_path = workspace_root / "Cargo.toml"
        if cargo_path.exists() and cargo_path.is_file():
            rel_p = str(cargo_path.relative_to(workspace_root)).replace("\\", "/")
            manifests.append(rel_p)
            discovered.extend(self._parse_cargo_toml(cargo_path, rel_p))

        # 7. Go go.mod
        go_mod_path = workspace_root / "go.mod"
        if go_mod_path.exists() and go_mod_path.is_file():
            rel_p = str(go_mod_path.relative_to(workspace_root)).replace("\\", "/")
            manifests.append(rel_p)
            discovered.extend(self._parse_go_mod(go_mod_path, rel_p))

        return DependencyReport(
            manifest_files=manifests,
            dependencies=discovered,
        )

    def parse_requirements_file(self, path: Path, rel_path: str = "") -> List[DiscoveredDependency]:
        """Public parser for requirements.txt."""
        return self._parse_requirements_txt(path, rel_path or str(path))

    def parse_package_json(self, path: Path, rel_path: str = "") -> List[DiscoveredDependency]:
        """Public parser for package.json."""
        return self._parse_package_json(path, rel_path or str(path))

    def parse_pyproject_toml(self, path: Path, rel_path: str = "") -> List[DiscoveredDependency]:
        """Public parser for pyproject.toml."""
        return self._parse_pyproject_toml(path, rel_path or str(path))

    def _parse_requirements_txt(self, path: Path, rel_path: str = "") -> List[DiscoveredDependency]:
        """Parse pip requirements.txt syntax."""
        deps = []
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            for line in content.splitlines():
                clean = line.strip().split("#")[0].strip()
                if not clean or clean.startswith(("-", "http://", "https://", "git+")):
                    continue
                # Match e.g. flask>=2.0.0, requests==2.31.0, or uvicorn[standard]==0.29.0
                m = re.match(r"^([a-zA-Z0-9_\-\.]+)(?:\[[^\]]*\])?\s*([~>=<!=~]+.+)?$", clean)
                if m:
                    pkg_name = m.group(1).lower()
                    ver = m.group(2).strip() if m.group(2) else None
                    deps.append(
                        DiscoveredDependency(
                            name=pkg_name,
                            version_spec=ver,
                            manifest_file=rel_path,
                            is_dev="dev" in rel_path.lower() or "test" in rel_path.lower(),
                        )
                    )
        except Exception:
            pass
        return deps

    def _parse_pyproject_toml(self, path: Path, rel_path: str = "") -> List[DiscoveredDependency]:
        """Extract dependencies from pyproject.toml."""
        deps = []
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            # Extract standard project.dependencies list
            in_deps = False
            for line in content.splitlines():
                clean = line.strip()
                if clean.startswith("dependencies = ["):
                    in_deps = True
                    continue
                elif in_deps:
                    if clean.startswith("]"):
                        in_deps = False
                        continue
                    m = re.search(r"['\"]([a-zA-Z0-9_\-\.]+)(?:\[[^\]]*\])?\s*([~>=<!=~]+[^'\"]+)?['\"]", clean)
                    if m:
                        deps.append(
                            DiscoveredDependency(
                                name=m.group(1),
                                version_spec=m.group(2).strip() if m.group(2) else None,
                                manifest_file=rel_path,
                                is_dev=False,
                            )
                        )
        except Exception:
            pass
        return deps

    def _parse_package_json(self, path: Path, rel_path: str = "") -> List[DiscoveredDependency]:
        """Extract dependencies from package.json."""
        deps = []
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            data = json.loads(content)
            for pkg, ver in data.get("dependencies", {}).items():
                deps.append(
                    DiscoveredDependency(
                        name=pkg,
                        version_spec=str(ver),
                        manifest_file=rel_path,
                        is_dev=False,
                    )
                )
            for pkg, ver in data.get("devDependencies", {}).items():
                deps.append(
                    DiscoveredDependency(
                        name=pkg,
                        version_spec=str(ver),
                        manifest_file=rel_path,
                        is_dev=True,
                    )
                )
        except Exception:
            pass
        return deps

    def _parse_pom_xml(self, path: Path, rel_path: str) -> List[DiscoveredDependency]:
        """Extract Maven dependencies from pom.xml."""
        deps = []
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            # Match <dependency> ... <artifactId>X</artifactId> ... <version>Y</version>
            dep_blocks = re.findall(r"<dependency>(.*?)</dependency>", content, re.DOTALL)
            for block in dep_blocks:
                art = re.search(r"<artifactId>(.*?)</artifactId>", block)
                ver = re.search(r"<version>(.*?)</version>", block)
                if art:
                    deps.append(
                        DiscoveredDependency(
                            name=art.group(1).strip(),
                            version_spec=ver.group(1).strip() if ver else None,
                            manifest_file=rel_path,
                        )
                    )
        except Exception:
            pass
        return deps

    def _parse_gradle(self, path: Path, rel_path: str) -> List[DiscoveredDependency]:
        """Extract dependencies from build.gradle."""
        deps = []
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            # implementation 'group:artifact:version'
            matches = re.findall(r"(?:implementation|compile|api|testImplementation)\s+['\"]([^'\"]+)['\"]", content)
            for m in matches:
                parts = m.split(":")
                name = parts[1] if len(parts) >= 2 else parts[0]
                ver = parts[2] if len(parts) >= 3 else None
                deps.append(
                    DiscoveredDependency(
                        name=name,
                        version_spec=ver,
                        manifest_file=rel_path,
                    )
                )
        except Exception:
            pass
        return deps

    def _parse_cargo_toml(self, path: Path, rel_path: str) -> List[DiscoveredDependency]:
        """Extract dependencies from Cargo.toml."""
        deps = []
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            in_deps = False
            for line in content.splitlines():
                clean = line.strip()
                if clean == "[dependencies]":
                    in_deps = True
                    continue
                elif clean.startswith("["):
                    in_deps = False
                    continue
                elif in_deps and "=" in clean:
                    parts = clean.split("=", 1)
                    pkg = parts[0].strip()
                    ver = parts[1].strip().strip('"\'')
                    deps.append(
                        DiscoveredDependency(
                            name=pkg,
                            version_spec=ver,
                            manifest_file=rel_path,
                        )
                    )
        except Exception:
            pass
        return deps

    def _parse_go_mod(self, path: Path, rel_path: str) -> List[DiscoveredDependency]:
        """Extract dependencies from go.mod."""
        deps = []
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            # require module v1.2.3
            matches = re.findall(r"require\s+([^\s]+)\s+([^\s]+)", content)
            for mod, ver in matches:
                deps.append(
                    DiscoveredDependency(
                        name=mod,
                        version_spec=ver,
                        manifest_file=rel_path,
                    )
                )
        except Exception:
            pass
        return deps
