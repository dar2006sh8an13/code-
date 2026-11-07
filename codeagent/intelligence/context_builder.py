"""Context builder synthesizing project facts, architecture, memories, and code chunks for Qwen3."""

from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from codeagent.context.manager import ContextManager
from codeagent.context.token_counter import estimate_tokens
from codeagent.indexing.search_engine import SearchEngine, SearchResult
from codeagent.intelligence.architecture_mapper import ArchitectureMap, ArchitectureMapper
from codeagent.intelligence.project_analyzer import ComprehensiveProjectAnalysis, ProjectAnalyzer
from codeagent.memory.memory_manager import MemoryManager, RetrievedMemory


class ProjectContextBundle(BaseModel):
    """Synthesized context components formatted for model prompt inclusion."""

    project_id: str
    project_name: str = ""
    project_summary: str = ""
    architecture_overview: str = ""
    retrieved_memories: List[str] = Field(default_factory=list)
    relevant_symbols: List[str] = Field(default_factory=list)
    relevant_chunks: List[str] = Field(default_factory=list)
    total_estimated_tokens: int = 0

    @property
    def facts(self) -> List[str]:
        return self.retrieved_memories

    def to_system_prompt_extension(self) -> str:
        """Format the context bundle as a structured markdown section."""
        sections = [
            "### Project Intelligence & Persistent Context",
            f"**Project Summary:**\n{self.project_summary}",
        ]
        if self.architecture_overview:
            sections.append(f"**Architecture & Layout:**\n{self.architecture_overview}")
        if self.retrieved_memories:
            mem_text = "\n".join(f"- {m}" for m in self.retrieved_memories)
            sections.append(f"**Project Memories & Conventions:**\n{mem_text}")
        if self.relevant_symbols:
            sym_text = "\n".join(f"- {s}" for s in self.relevant_symbols)
            sections.append(f"**Relevant Code Symbols:**\n{sym_text}")
        if self.relevant_chunks:
            chunk_text = "\n\n".join(self.relevant_chunks)
            sections.append(f"**Relevant Code Snippets:**\n{chunk_text}")

        return "\n\n".join(sections)

    def to_prompt_context(self, max_tokens: Optional[int] = None) -> str:
        """Format the context bundle as a structured markdown section."""
        body = self.to_system_prompt_extension()
        return f"[PROJECT CONTEXT] ({self.project_name or self.project_id})\n\n{body}"


class ContextBuilder:
    """Builds token-budgeted, project-aware context for LLM conversations."""

    def __init__(
        self,
        memory_manager: MemoryManager,
        search_engine: SearchEngine,
        context_manager: Optional[ContextManager] = None,
        max_context_tokens: int = 2500,
    ) -> None:
        """Initialize ContextBuilder.

        Args:
            memory_manager: MemoryManager instance.
            search_engine: SearchEngine instance.
            context_manager: Optional ContextManager for token counting.
            max_context_tokens: Strict ceiling for project context tokens (defaults to 2500).
        """
        self.memory_manager = memory_manager
        self.search_engine = search_engine
        self.context_manager = context_manager or ContextManager()
        self.max_context_tokens = max_context_tokens
        self.project_analyzer = ProjectAnalyzer()
        self.arch_mapper = ArchitectureMapper(store=memory_manager.store)

    def build_context(
        self,
        project_id: str,
        workspace_root: Path,
        user_query: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> ProjectContextBundle:
        """Construct a project-aware context bundle respecting token budgets."""
        budget = max_tokens or self.max_context_tokens
        allocated_tokens = 0

        # Resolve project name
        proj_name = workspace_root.name
        row = self.memory_manager.store.execute_query_one("SELECT name FROM projects WHERE id = ?;", (project_id,))
        if row and row["name"]:
            proj_name = row["name"]

        # 1. Quick Project Facts from ProjectAnalyzer
        analysis = self.project_analyzer.analyze(workspace_root)
        proj_summary = analysis.to_summary()
        summary_tokens = estimate_tokens(proj_summary)
        allocated_tokens += summary_tokens

        # 2. Architecture overview
        arch_map = self.arch_mapper.build_architecture_map(
            workspace_root=workspace_root,
            project_id=project_id,
            known_entry_points=analysis.entry_points,
            project_type=analysis.project_type,
        )
        arch_summary = arch_map.to_summary()
        arch_tokens = estimate_tokens(arch_summary)
        if allocated_tokens + arch_tokens < budget:
            allocated_tokens += arch_tokens
        else:
            arch_summary = ""

        # 3. Relevant Memories
        memories = self.memory_manager.retrieve_context_memories(
            project_id=project_id,
            query=user_query,
            max_results=8,
        )
        included_mems: List[str] = []
        for m in memories:
            m_text = m.content
            t_count = estimate_tokens(m_text)
            if allocated_tokens + t_count < budget:
                included_mems.append(m_text)
                allocated_tokens += t_count
            else:
                break

        # 4. Relevant Symbols and Chunks (if query provided)
        included_symbols: List[str] = []
        included_chunks: List[str] = []

        if user_query and user_query.strip():
            # Search symbols
            sym_results = self.search_engine.search_symbol(project_id=project_id, name=user_query.strip(), limit=5)
            for s in sym_results:
                s_text = f"{s.file_path}:{s.line_number} -> {s.matched_content}"
                t_count = estimate_tokens(s_text)
                if allocated_tokens + t_count < budget:
                    included_symbols.append(s_text)
                    allocated_tokens += t_count
                else:
                    break

            # Search chunks
            chunk_results = self.search_engine.search_content_chunks(project_id=project_id, query=user_query.strip(), limit=3)
            for c in chunk_results:
                c_block = f"```\n// File: {c.file_path}:{c.line_number}\n{c.matched_content}\n```"
                t_count = estimate_tokens(c_block)
                if allocated_tokens + t_count < budget:
                    included_chunks.append(c_block)
                    allocated_tokens += t_count
                else:
                    break

        return ProjectContextBundle(
            project_id=project_id,
            project_name=proj_name,
            project_summary=proj_summary,
            architecture_overview=arch_summary,
            retrieved_memories=included_mems,
            relevant_symbols=included_symbols,
            relevant_chunks=included_chunks,
            total_estimated_tokens=allocated_tokens,
        )
