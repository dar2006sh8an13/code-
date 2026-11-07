"""Unit tests for structured JSON response generation and Pydantic validation."""

from unittest.mock import MagicMock

import pytest

from codeagent.llm.structured import (
    ErrorAnalysis,
    StructuredResponseEngine,
    StructuredValidationError,
    extract_json_payload,
)


class TestStructuredResponseEngine:
    """Test suite for structured JSON response validation."""

    def test_extract_json_payload_from_markdown(self) -> None:
        """Verify JSON is cleanly extracted from markdown code fences."""
        fenced = '```json\n{"error_type": "KeyError", "cause": "Missing key", "solution": "Check key", "severity": "low"}\n```'
        payload = extract_json_payload(fenced)
        assert payload.startswith("{") and payload.endswith("}")

        raw = 'Some text before {"a": 1} some text after'
        assert extract_json_payload(raw) == '{"a": 1}'

    def test_valid_structured_response_generation(self) -> None:
        """Verify successful generation and parsing into Pydantic model."""
        valid_json = """
        {
            "error_type": "IndexError",
            "cause": "Attempted to access index 5 in a list of length 3",
            "solution": "Verify list length using len() before accessing index",
            "severity": "medium"
        }
        """
        mock_client = MagicMock()
        mock_client.chat.return_value = MagicMock(message=MagicMock(content=valid_json))

        engine = StructuredResponseEngine()
        result = engine.generate_structured(
            client=mock_client,
            prompt="Analyze list index error",
            schema_class=ErrorAnalysis,
            model="qwen3:latest",
        )

        assert isinstance(result, ErrorAnalysis)
        assert result.error_type == "IndexError"
        assert result.severity == "medium"
        assert "len()" in result.solution

    def test_malformed_json_raises_validation_error(self) -> None:
        """Verify malformed JSON raises StructuredValidationError."""
        malformed = "This is not JSON at all."
        mock_client = MagicMock()
        mock_client.chat.return_value = MagicMock(message=MagicMock(content=malformed))

        engine = StructuredResponseEngine()
        with pytest.raises(StructuredValidationError):
            engine.generate_structured(
                client=mock_client,
                prompt="test",
                schema_class=ErrorAnalysis,
                model="qwen3:latest",
            )

    def test_missing_required_fields_raises_validation_error(self) -> None:
        """Verify incomplete JSON schema raises StructuredValidationError with error details."""
        incomplete_json = '{"error_type": "TypeError"}'  # missing cause and solution
        mock_client = MagicMock()
        mock_client.chat.return_value = MagicMock(message=MagicMock(content=incomplete_json))

        engine = StructuredResponseEngine()
        with pytest.raises(StructuredValidationError) as exc_info:
            engine.generate_structured(
                client=mock_client,
                prompt="test",
                schema_class=ErrorAnalysis,
                model="qwen3:latest",
            )

        assert "cause" in str(exc_info.value) or "Field required" in str(exc_info.value)

