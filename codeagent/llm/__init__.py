"""LLM client integration package."""

from codeagent.llm.client import (
    LLMClient,
    ModelInfo,
    ModelNotFoundError,
    OllamaClientError,
    OllamaConnectionError,
    OllamaTimeoutError,
)
from codeagent.llm.streaming import StreamingEngine
from codeagent.llm.structured import (
    ErrorAnalysis,
    ErrorSeverity,
    StructuredResponseEngine,
    StructuredValidationError,
)

__all__ = [
    "LLMClient",
    "ModelInfo",
    "StreamingEngine",
    "StructuredResponseEngine",
    "ErrorAnalysis",
    "ErrorSeverity",
    "StructuredValidationError",
    "OllamaClientError",
    "OllamaConnectionError",
    "ModelNotFoundError",
    "OllamaTimeoutError",
]
