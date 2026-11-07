"""Streaming response engine using Ollama streaming API and Rich display."""

import sys
from typing import Any, Callable, Iterator, Optional

import httpx
from ollama import Client as OllamaSDKClient
from ollama import RequestError, ResponseError
from rich.console import Console

from codeagent.llm.client import (
    ModelNotFoundError,
    OllamaClientError,
    OllamaConnectionError,
    OllamaTimeoutError,
)


class StreamingEngine:
    """Handles real-time streaming of tokens from Ollama to the terminal."""

    def __init__(self, console: Optional[Console] = None) -> None:
        """Initialize the streaming engine.

        Args:
            console: Rich console instance (defaults to a standard console).
        """
        self.console = console or Console()

    def iter_stream_chunks(
        self,
        client: OllamaSDKClient,
        messages: list[dict[str, Any]],
        model: str,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
    ) -> Iterator[str]:
        """Yield text delta chunks from Ollama streaming API.

        Args:
            client: Connected Ollama SDK client instance.
            messages: List of message dictionaries (role, content).
            model: Name of the Ollama model to query.
            temperature: Sampling temperature override.
            max_output_tokens: Maximum tokens to generate (num_predict).

        Yields:
            str: Each chunk of generated text as it arrives.

        Raises:
            OllamaConnectionError: If connection fails.
            ModelNotFoundError: If model is not installed.
            OllamaTimeoutError: If the stream times out.
            OllamaClientError: For any other API error.
        """
        options: dict[str, Any] = {}
        if temperature is not None:
            options["temperature"] = temperature
        if max_output_tokens is not None and max_output_tokens > 0:
            options["num_predict"] = max_output_tokens

        try:
            stream = client.chat(
                model=model,
                messages=messages,
                stream=True,
                options=options or None,
            )

            try:
                for chunk in stream:
                    content = ""
                    if hasattr(chunk, "message") and hasattr(chunk.message, "content"):
                        content = chunk.message.content or ""
                    elif isinstance(chunk, dict) and "message" in chunk:
                        content = chunk["message"].get("content", "") or ""

                    if not content and hasattr(chunk, "message"):
                        content = getattr(chunk.message, "thinking", "") or getattr(chunk.message, "reasoning_content", "") or ""
                    elif not content and isinstance(chunk, dict) and "message" in chunk:
                        msg_dict = chunk.get("message", {})
                        if isinstance(msg_dict, dict):
                            content = msg_dict.get("thinking", "") or msg_dict.get("reasoning_content", "") or ""

                    if content:
                        yield content
            finally:
                # Ensure generator / connection resource cleanup
                if hasattr(stream, "close") and callable(stream.close):
                    stream.close()

        except (httpx.ConnectError, httpx.ConnectTimeout, ConnectionRefusedError) as exc:
            raise OllamaConnectionError(
                f"Cannot connect to Ollama server while streaming from '{model}'."
            ) from exc

        except (httpx.ReadTimeout, httpx.WriteTimeout) as exc:
            raise OllamaTimeoutError(
                f"Stream connection timed out while waiting for model '{model}'."
            ) from exc

        except ResponseError as exc:
            if exc.status_code == 404 or "not found" in str(exc).lower():
                raise ModelNotFoundError(
                    f"Model '{model}' is not installed in Ollama. Pull it using 'ollama pull {model}'."
                ) from exc
            raise OllamaClientError(
                f"Ollama server returned error ({exc.status_code}): {exc.error}"
            ) from exc

        except RequestError as exc:
            raise OllamaClientError(f"Ollama streaming request error: {exc}") from exc

        except Exception as exc:
            if isinstance(exc, (OllamaClientError, KeyboardInterrupt)):
                raise
            raise OllamaClientError(f"Unexpected error during streaming: {exc}") from exc

    def stream_chat(
        self,
        client: OllamaSDKClient,
        messages: list[dict[str, Any]],
        model: str,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        display: bool = True,
        on_chunk: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Stream model generation to the terminal in real time and return accumulated text.

        Args:
            client: Connected Ollama SDK client.
            messages: Formatted conversation message sequence.
            model: Target model name.
            temperature: Sampling temperature.
            max_output_tokens: Maximum tokens to generate.
            display: Whether to print chunks to the terminal immediately.
            on_chunk: Optional callback invoked for every received chunk.

        Returns:
            str: The complete accumulated assistant response.

        Raises:
            KeyboardInterrupt: If interrupted by user during generation.
            OllamaClientError: If an LLM or connection failure occurs.
        """
        accumulated: list[str] = []

        try:
            for chunk in self.iter_stream_chunks(
                client=client,
                messages=messages,
                model=model,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            ):
                accumulated.append(chunk)

                if on_chunk:
                    on_chunk(chunk)

                if display:
                    self.console.print(chunk, end="", highlight=False)
                    # Flush stdout to ensure instant terminal rendering
                    if hasattr(self.console.file, "flush"):
                        self.console.file.flush()

            if display:
                self.console.print()  # Final newline after stream ends

            return "".join(accumulated)

        except KeyboardInterrupt:
            if display:
                self.console.print("\n[yellow][Interrupted by user][/yellow]")
            return "".join(accumulated)

