"""CodeAgent - Local autonomous AI coding assistant.

Phase 1: CLI Foundation.
Phase 2: Advanced LLM Integration (Streaming, Conversation History, Context Budgeting, Tool Calling, Structured JSON).
"""

from codeagent.__version__ import __app_name__, __author__, __tagline__, __version__
from codeagent.config.settings import Settings, get_settings

__all__ = [
    "Settings",
    "get_settings",
    "__version__",
    "__app_name__",
    "__tagline__",
    "__author__",
]
