"""Structured JSON response engine using Pydantic schemas and Ollama structured output."""

import json
import re
from enum import Enum
from typing import Any, Optional, Type, TypeVar

from ollama import Client as OllamaSDKClient
from ollama import RequestError, ResponseError
from pydantic import BaseModel, Field, ValidationError

from codeagent.llm.client import (
    ModelNotFoundError,
    OllamaClientError,
    OllamaConnectionError,
    OllamaTimeoutError,
)

T = TypeVar("T", bound=BaseModel)


class StructuredValidationError(Exception):
    """Raised when model response cannot be parsed or validated against the requested Pydantic schema."""

    def __init__(self, message: str, raw_output: str, errors: Optional[Any] = None) -> None:
        super().__init__(message)
        self.raw_output = raw_output
        self.errors = errors


class ErrorSeverity(str, Enum):
    """Severity levels for error analysis."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorAnalysis(BaseModel):
    """Pydantic schema for structured software error and exception diagnosis."""

    error_type: str = Field(
        description="Type or classification of the error (e.g., IndexError, TimeoutError, LogicBug)"
    )
    cause: str = Field(
        description="Detailed explanation of the root cause behind the error"
    )
    solution: str = Field(
        description="Step-by-step resolution or code fix to resolve the error"
    )
    severity: str = Field(
        default="medium",
        description="Severity level: low, medium, high, or critical"
    )


def extract_json_payload(raw_text: str) -> str:
    """Extract raw JSON string from LLM output, stripping markdown code blocks if present."""
    clean = raw_text.strip()

    # Match ```json ... ``` or ``` ... ``` code blocks
    fence_pattern = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
    match = fence_pattern.search(clean)
    if match:
        return match.group(1).strip()

    # Match first '{' to last '}'
    start_idx = clean.find("{")
    end_idx = clean.rfind("}")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        return clean[start_idx : end_idx + 1]

    return clean


class StructuredResponseEngine:
    """Engine that enforces structured JSON generation and schema validation."""

    def generate_structured(
        self,
        client: OllamaSDKClient,
        prompt: str,
        schema_class: Type[T],
        model: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> T:
        """Prompt the model and validate the response against a Pydantic schema.

        Args:
            client: Connected Ollama SDK client.
            prompt: User instructions or input to analyze.
            schema_class: Target Pydantic model class.
            model: Model tag.
            system_prompt: Optional system prompt.
            temperature: Model sampling temperature.

        Returns:
            T: Validated instance of schema_class.

        Raises:
            StructuredValidationError: If output is invalid JSON or schema validation fails.
            OllamaClientError: On server or transport failures.
        """
        # Obtain JSON schema from Pydantic
        schema_dict = schema_class.model_json_schema()

        augmented_system = (
            "You are a precise structured data generator. "
            "You MUST respond ONLY with a valid JSON object matching the requested schema. "
            "Do not include any prose, conversational preamble, or markdown formatting outside the JSON."
        )
        if system_prompt and system_prompt.strip():
            augmented_system = f"{system_prompt.strip()}\n\n{augmented_system}"

        messages = [
            {"role": "system", "content": augmented_system},
            {"role": "user", "content": prompt},
        ]

        options: dict[str, Any] = {}
        if temperature is not None:
            options["temperature"] = temperature

        try:
            # Use Ollama's native structured JSON schema format enforcement
            response = client.chat(
                model=model,
                messages=messages,
                format=schema_dict,
                options=options or None,
            )

            raw_content = response.message.content or ""
            json_str = extract_json_payload(raw_content)

            try:
                validated_model = schema_class.model_validate_json(json_str)
                return validated_model
            except (ValidationError, json.JSONDecodeError) as val_exc:
                raise StructuredValidationError(
                    f"Model output failed schema validation for {schema_class.__name__}: {val_exc}",
                    raw_output=raw_content,
                    errors=getattr(val_exc, "errors", lambda: None)(),
                ) from val_exc

        except ResponseError as exc:
            if exc.status_code == 404 or "not found" in str(exc).lower():
                raise ModelNotFoundError(
                    f"Model '{model}' is not installed in Ollama. Pull it using 'ollama pull {model}'."
                ) from exc
            raise OllamaClientError(f"Ollama server error ({exc.status_code}): {exc.error}") from exc

        except RequestError as exc:
            raise OllamaClientError(f"Ollama request error: {exc}") from exc

        except Exception as exc:
            if isinstance(exc, (StructuredValidationError, OllamaClientError)):
                raise
            raise OllamaClientError(f"Unexpected error during structured generation: {exc}") from exc

