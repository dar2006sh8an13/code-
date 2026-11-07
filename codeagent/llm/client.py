"""Ollama LLM client integration module for CodeAgent."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

import httpx
import ollama
from ollama import Client as OllamaSDKClient
from ollama import ResponseError, RequestError

from codeagent.config.settings import Settings, get_settings


class OllamaClientError(Exception):
    """Base exception for Ollama client errors."""
    pass


class OllamaConnectionError(OllamaClientError):
    """Raised when CodeAgent cannot establish a connection to the Ollama server."""
    pass


class ModelNotFoundError(OllamaClientError):
    """Raised when the requested model is not installed in Ollama."""
    pass


class OllamaTimeoutError(OllamaClientError):
    """Raised when an Ollama request times out."""
    pass


@dataclass
class ModelInfo:
    """Structured information about an installed Ollama model."""

    name: str
    size_bytes: int = 0
    size_formatted: str = "Unknown"
    family: str = "Unknown"
    parameter_size: str = "Unknown"
    quantization: str = "Unknown"
    modified_at: Optional[str] = None


def format_bytes(size_bytes: int | float | None) -> str:
    """Format byte counts into human-readable strings (e.g., 5.2 GB)."""
    if size_bytes is None or size_bytes <= 0:
        return "Unknown"
    # Using 1000 base to match Ollama's CLI reporting conventions
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size_bytes)
    for unit in units:
        if size < 1000.0:
            return f"{size:.1f} {unit}"
        size /= 1000.0
    return f"{size:.1f} PB"


class LLMClient:
    """Client for interacting with local Ollama server and LLM models."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        host: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout: Optional[float] = None,
        temperature: Optional[float] = None,
    ) -> None:
        """Initialize the LLM client with settings or explicit overrides."""
        cfg = settings or get_settings()
        self.host = host or cfg.ollama_host
        self.default_model = model_name or cfg.model_name
        self.timeout = timeout if timeout is not None else cfg.request_timeout
        self.temperature = temperature if temperature is not None else cfg.temperature

        # Initialize the official Ollama SDK Client
        self._client = OllamaSDKClient(host=self.host, timeout=self.timeout)

    def check_connection(self, timeout: float = 5.0) -> tuple[bool, str]:
        """Check whether the Ollama server is reachable.

        Args:
            timeout: Quick connection timeout in seconds (defaults to 5.0).

        Returns:
            tuple[bool, str]: (is_connected, status_message)
        """
        try:
            probe_client = OllamaSDKClient(host=self.host, timeout=timeout)
            probe_client.list()
            return True, "Online"
        except (httpx.ConnectError, httpx.ConnectTimeout, ConnectionRefusedError) as exc:
            return (
                False,
                f"Cannot connect to Ollama server at {self.host}. "
                "Please verify that Ollama is running ('ollama serve').",
            )
        except httpx.ReadTimeout:
            return (
                False,
                f"Connection to Ollama server at {self.host} timed out after {timeout}s.",
            )
        except Exception as exc:
            return False, f"Ollama connection check failed: {exc}"

    def list_models(self) -> list[str]:
        """Retrieve names of all installed models in Ollama.

        Returns:
            list[str]: List of model tags (e.g., ['qwen3:latest', 'gemma:latest']).

        Raises:
            OllamaConnectionError: If Ollama server is unreachable.
            OllamaClientError: For other unexpected API errors.
        """
        try:
            response = self._client.list()
            models_list: list[str] = []
            if hasattr(response, "models"):
                for m in response.models:
                    model_name = getattr(m, "model", None) or getattr(m, "name", None)
                    if model_name:
                        models_list.append(str(model_name))
            return models_list
        except (httpx.ConnectError, httpx.ConnectTimeout, ConnectionRefusedError) as exc:
            raise OllamaConnectionError(
                f"Cannot connect to Ollama server at {self.host}. "
                "Please ensure Ollama is running ('ollama serve')."
            ) from exc
        except httpx.ReadTimeout as exc:
            raise OllamaTimeoutError(
                f"Timed out fetching model list from Ollama server at {self.host}."
            ) from exc
        except Exception as exc:
            raise OllamaClientError(f"Failed to list Ollama models: {exc}") from exc

    def get_installed_models(self) -> list[ModelInfo]:
        """Retrieve detailed information about all installed models.

        Returns:
            list[ModelInfo]: List of detailed ModelInfo instances.

        Raises:
            OllamaConnectionError: If Ollama server is unreachable.
            OllamaClientError: For other API errors.
        """
        try:
            response = self._client.list()
            model_infos: list[ModelInfo] = []
            if hasattr(response, "models"):
                for m in response.models:
                    name = getattr(m, "model", None) or getattr(m, "name", "unknown")
                    size = getattr(m, "size", 0) or 0
                    details = getattr(m, "details", None)

                    family = "Unknown"
                    param_size = "Unknown"
                    quant = "Unknown"
                    if details:
                        family = getattr(details, "family", "Unknown") or "Unknown"
                        param_size = getattr(details, "parameter_size", "Unknown") or "Unknown"
                        quant = getattr(details, "quantization_level", "Unknown") or "Unknown"

                    modified = getattr(m, "modified_at", None)
                    mod_str = None
                    if isinstance(modified, datetime):
                        mod_str = modified.strftime("%Y-%m-%d %H:%M")
                    elif modified:
                        mod_str = str(modified)[:19]

                    model_infos.append(
                        ModelInfo(
                            name=str(name),
                            size_bytes=int(size),
                            size_formatted=format_bytes(size),
                            family=str(family),
                            parameter_size=str(param_size),
                            quantization=str(quant),
                            modified_at=mod_str,
                        )
                    )
            return model_infos
        except (httpx.ConnectError, httpx.ConnectTimeout, ConnectionRefusedError) as exc:
            raise OllamaConnectionError(
                f"Cannot connect to Ollama server at {self.host}. "
                "Please verify that Ollama is running ('ollama serve')."
            ) from exc
        except httpx.ReadTimeout as exc:
            raise OllamaTimeoutError(
                f"Timed out querying Ollama server at {self.host}."
            ) from exc
        except Exception as exc:
            raise OllamaClientError(f"Failed to query installed models: {exc}") from exc

    def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Send a user prompt to the specified model and return the generated response.

        Args:
            prompt: User prompt string (cannot be empty).
            model: Optional model name override. Defaults to self.default_model.
            system_prompt: Optional system prompt to instruct the model.

        Returns:
            str: The generated assistant response text.

        Raises:
            ValueError: If the prompt is empty or only whitespace.
            OllamaConnectionError: If the Ollama server is unreachable.
            ModelNotFoundError: If the specified model is not installed.
            OllamaTimeoutError: If generation times out.
            OllamaClientError: For any unexpected API errors.
        """
        clean_prompt = prompt.strip() if prompt else ""
        if not clean_prompt:
            raise ValueError("Prompt cannot be empty.")

        target_model = model or self.default_model
        messages: list[dict[str, str]] = []

        if system_prompt and system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt.strip()})

        messages.append({"role": "user", "content": clean_prompt})

        options: dict[str, Any] = {
            "temperature": self.temperature,
        }

        try:
            response = self._client.chat(
                model=target_model,
                messages=messages,
                options=options,
            )

            # Extract message content from chat response
            if hasattr(response, "message") and hasattr(response.message, "content"):
                return str(response.message.content)
            if isinstance(response, dict) and "message" in response:
                return str(response["message"].get("content", ""))
            return str(response)

        except (httpx.ConnectError, httpx.ConnectTimeout, ConnectionRefusedError) as exc:
            raise OllamaConnectionError(
                f"Unable to connect to Ollama server at {self.host}. "
                "Please verify that Ollama is running ('ollama serve')."
            ) from exc

        except (httpx.ReadTimeout, httpx.WriteTimeout) as exc:
            raise OllamaTimeoutError(
                f"Request timed out after {self.timeout:.0f} seconds while waiting for "
                f"model '{target_model}'. You can increase REQUEST_TIMEOUT in your .env file."
            ) from exc

        except ResponseError as exc:
            # Check for model not found (status 404 or specific message)
            if exc.status_code == 404 or "not found" in str(exc).lower():
                raise ModelNotFoundError(
                    f"Model '{target_model}' is not installed in Ollama. "
                    f"Run 'ollama pull {target_model}' or specify an installed model using --model."
                ) from exc
            raise OllamaClientError(
                f"Ollama server returned error ({exc.status_code}): {exc.error}"
            ) from exc

        except RequestError as exc:
            raise OllamaClientError(f"Ollama request error: {exc}") from exc

        except Exception as exc:
            raise OllamaClientError(f"Unexpected error communicating with Ollama: {exc}") from exc

    def stream_chat(
        self,
        messages: list[dict[str, Any]],
        model: Optional[str] = None,
        max_output_tokens: Optional[int] = None,
        display: bool = True,
        on_chunk: Optional[Any] = None,
    ) -> str:
        """Stream a conversation message sequence to the terminal.

        Args:
            messages: List of message dictionaries ({'role': ..., 'content': ...}).
            model: Optional model name override.
            max_output_tokens: Optional token generation limit.
            display: Whether to print streaming tokens to terminal.
            on_chunk: Optional callback invoked for every chunk.

        Returns:
            str: Full generated assistant response text.
        """
        from codeagent.llm.streaming import StreamingEngine

        target_model = model or self.default_model
        engine = StreamingEngine()
        return engine.stream_chat(
            client=self._client,
            messages=messages,
            model=target_model,
            temperature=self.temperature,
            max_output_tokens=max_output_tokens,
            display=display,
            on_chunk=on_chunk,
        )
