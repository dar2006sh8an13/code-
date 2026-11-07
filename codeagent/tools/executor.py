"""Tool executor for validating, executing, and orchestrating LLM tool-calling loops."""

import json
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import httpx
from ollama import Client as OllamaSDKClient

from codeagent.llm.client import OllamaClientError, OllamaConnectionError, OllamaTimeoutError
from codeagent.tools.registry import ToolRegistry, get_default_registry


class ToolExecutionError(Exception):
    """Raised when tool execution fails unexpectedly."""
    pass


class MaxIterationsExceededError(Exception):
    """Raised when the tool loop exceeds the maximum permitted iterations."""
    pass


@dataclass
class ToolExecutionResult:
    """Outcome of a single tool execution."""

    tool_name: str
    arguments: dict[str, Any]
    result: Any = None
    success: bool = True
    error: Optional[str] = None
    verified: bool = False
    verified_path: Optional[str] = None

    def to_message_content(self) -> str:
        """Format the result as a string suitable for LLM tool message content."""
        if not self.success:
            return f"Error executing tool '{self.tool_name}': {self.error}"
        if isinstance(self.result, (dict, list)):
            return json.dumps(self.result)
        return str(self.result)


class ToolExecutor:
    """Validates arguments, executes registered tools, and manages tool calling loops."""

    def __init__(self, registry: Optional[ToolRegistry] = None) -> None:
        """Initialize the executor with a tool registry."""
        self.registry = registry or get_default_registry()

    def validate_arguments(self, tool_name: str, arguments: Any) -> tuple[bool, Optional[str]]:
        """Validate provided arguments against the tool's registered JSON schema.

        Args:
            tool_name: Name of the target tool.
            arguments: Dictionary or JSON string of arguments supplied by LLM.

        Returns:
            tuple[bool, Optional[str]]: (is_valid, error_message)
        """
        tool = self.registry.get(tool_name)
        if not tool:
            return False, f"Tool '{tool_name}' is not registered in the system."

        # Parse string arguments if model supplied JSON string
        parsed_args = arguments
        if isinstance(parsed_args, str):
            try:
                parsed_args = json.loads(parsed_args)
            except Exception as exc:
                return False, f"Invalid JSON arguments string: {exc}"

        if not isinstance(parsed_args, dict):
            return False, f"Tool arguments must be a dictionary, got {type(parsed_args).__name__}."

        schema = tool.parameters or {}
        required_fields = schema.get("required", [])

        # Check for missing required arguments
        for req in required_fields:
            if req not in parsed_args:
                return False, f"Missing required parameter '{req}' for tool '{tool_name}'."

        properties = schema.get("properties", {})
        for key, val in parsed_args.items():
            if key in properties:
                if val is None and key not in required_fields:
                    continue
                expected_type = properties[key].get("type")
                if expected_type == "number":
                    if not isinstance(val, (int, float)) or isinstance(val, bool):
                        return False, f"Parameter '{key}' must be a number, got {type(val).__name__}."
                elif expected_type == "string":
                    if not isinstance(val, str):
                        return False, f"Parameter '{key}' must be a string, got {type(val).__name__}."
                elif expected_type == "integer":
                    if not isinstance(val, int) or isinstance(val, bool):
                        return False, f"Parameter '{key}' must be an integer, got {type(val).__name__}."
                elif expected_type == "boolean":
                    if not isinstance(val, bool):
                        return False, f"Parameter '{key}' must be a boolean, got {type(val).__name__}."
                elif expected_type == "array":
                    if not isinstance(val, list):
                        return False, f"Parameter '{key}' must be an array, got {type(val).__name__}."

        return True, None

    def execute(self, tool_name: str, arguments: Any) -> ToolExecutionResult:
        """Execute a registered tool with argument validation and disk verification.

        Args:
            tool_name: Name of tool to run.
            arguments: Dict or JSON string of arguments.

        Returns:
            ToolExecutionResult: Result data or error details with verification.
        """
        tool = self.registry.get(tool_name)
        if not tool:
            return ToolExecutionResult(
                tool_name=tool_name,
                arguments=arguments if isinstance(arguments, dict) else {},
                success=False,
                error=f"Disallowed tool: '{tool_name}' is not in the safe tool registry.",
            )

        parsed_args = arguments
        if isinstance(parsed_args, str):
            try:
                parsed_args = json.loads(parsed_args)
            except Exception as exc:
                return ToolExecutionResult(
                    tool_name=tool_name,
                    arguments={},
                    success=False,
                    error=f"Failed to parse arguments JSON: {exc}",
                )

        if not isinstance(parsed_args, dict):
            return ToolExecutionResult(
                tool_name=tool_name,
                arguments={},
                success=False,
                error=f"Expected argument dictionary, got {type(parsed_args).__name__}",
            )

        is_valid, val_err = self.validate_arguments(tool_name, parsed_args)
        if not is_valid:
            return ToolExecutionResult(
                tool_name=tool_name,
                arguments=parsed_args,
                success=False,
                error=val_err,
            )

        try:
            result = tool.handler(**parsed_args)
            verified = False
            verified_path = None
            if isinstance(result, dict):
                verified = result.get("verified", False)
                verified_path = result.get("absolute_path") or result.get("path")

            return ToolExecutionResult(
                tool_name=tool_name,
                arguments=parsed_args,
                result=result,
                success=True,
                verified=verified,
                verified_path=verified_path,
            )
        except Exception as exc:
            return ToolExecutionResult(
                tool_name=tool_name,
                arguments=parsed_args,
                success=False,
                error=str(exc),
            )

    def run_tool_loop(
        self,
        client: OllamaSDKClient,
        model: str,
        messages: list[dict[str, Any]],
        max_iterations: int = 5,
        temperature: Optional[float] = None,
        on_tool_call: Optional[Callable[[str, dict[str, Any]], None]] = None,
        on_tool_result: Optional[Callable[[ToolExecutionResult], None]] = None,
        tool_names: Optional[list[str]] = None,
        on_status: Optional[Callable[[str, str], None]] = None,
        timeout: Optional[float] = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Run a multi-step conversation loop allowing Qwen3 to call tools and receive results.

        Distinguishes execution states: Planning, Generating, Tool selected, Executing,
        Execution successful, Execution failed, and File verified. Detects repeated tool calls
        and verifies filesystem outputs directly on disk.

        Args:
            client: Ollama SDK Client.
            model: Model name.
            messages: Conversation message history.
            max_iterations: Loop ceiling to prevent infinite loops.
            temperature: Sampling temperature.
            on_tool_call: Optional hook invoked when a tool call is received.
            on_tool_result: Optional hook invoked after a tool executes.
            tool_names: Optional list of tool names to expose to the model.
            on_status: Optional hook invoked on phase changes (Planning, Generating, etc.).
            timeout: Optional per-call request timeout override.

        Returns:
            tuple[str, list[dict[str, Any]]]: (final_assistant_text, updated_messages)

        Raises:
            MaxIterationsExceededError: If loop ceiling is reached without completion.
            OllamaTimeoutError: On model or request timeout.
            OllamaClientError: On network or server failure.
        """
        current_messages = list(messages)
        tools_schema = self.registry.get_ollama_tools(tool_names=tool_names)
        options: dict[str, Any] = {}
        if temperature is not None:
            options["temperature"] = temperature

        executed_signatures: set[tuple[str, str]] = set()

        for iteration in range(max_iterations):
            if on_status:
                on_status("Planning", f"Step {iteration + 1}/{max_iterations}: Evaluating task requirements with {model}...")

            if on_status:
                on_status("Generating", f"Awaiting model output from {model}...")

            try:
                response = client.chat(
                    model=model,
                    messages=current_messages,
                    tools=tools_schema,
                    options=options or None,
                )
            except KeyboardInterrupt:
                if on_status:
                    on_status("Execution failed", "Operation cancelled by user.")
                raise
            except (httpx.TimeoutException, TimeoutError, socket.timeout) as exc:
                if on_status:
                    on_status("Execution failed", f"Request timed out waiting for model '{model}'.")
                raise OllamaTimeoutError(
                    f"Request timed out while waiting for model '{model}'. "
                    f"You can increase REQUEST_TIMEOUT in your .env file."
                ) from exc
            except (httpx.ConnectError, httpx.ConnectTimeout, ConnectionRefusedError) as exc:
                if on_status:
                    on_status("Execution failed", f"Cannot connect to Ollama server at {getattr(client, '_client', client)}.")
                raise OllamaConnectionError(
                    f"Failed to connect to Ollama server while evaluating tools for model '{model}'. "
                    f"Please verify that Ollama is running ('ollama serve')."
                ) from exc

            msg = response.message
            tool_calls = getattr(msg, "tool_calls", None)

            # Check if model requested tool execution
            if tool_calls and len(tool_calls) > 0:
                normalized_tool_calls: list[dict[str, Any]] = []

                for tc in tool_calls:
                    func = getattr(tc, "function", None)
                    if not func:
                        continue
                    fname = getattr(func, "name", "")
                    fargs = getattr(func, "arguments", {})
                    if isinstance(fargs, str):
                        try:
                            fargs = json.loads(fargs)
                        except Exception:
                            pass
                    normalized_tool_calls.append({"name": fname, "arguments": fargs})

                asst_turn: dict[str, Any] = {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": ntc["name"],
                                "arguments": ntc["arguments"],
                            }
                        }
                        for ntc in normalized_tool_calls
                    ],
                }
                current_messages.append(asst_turn)

                # Execute each tool call and append the tool results
                for ntc in normalized_tool_calls:
                    fname = ntc["name"]
                    fargs = ntc["arguments"] or {}

                    if on_status:
                        args_preview = f"path='{fargs.get('path')}'" if isinstance(fargs, dict) and "path" in fargs else str(fargs)[:60]
                        on_status("Tool selected", f"{fname}({args_preview})")

                    # Check for repeated identical tool calls (prevent infinite loop)
                    sig_args = json.dumps(fargs, sort_keys=True) if isinstance(fargs, dict) else str(fargs)
                    call_sig = (fname, sig_args)

                    if call_sig in executed_signatures:
                        if on_status:
                            on_status("Execution failed", f"Duplicate call blocked: '{fname}' already ran with identical parameters.")
                        exec_res = ToolExecutionResult(
                            tool_name=fname,
                            arguments=fargs,
                            success=False,
                            error=f"Tool '{fname}' was already executed with identical arguments in this session. Do not repeat identical calls.",
                        )
                    else:
                        executed_signatures.add(call_sig)

                        if on_status:
                            on_status("Executing", f"Running safe tool '{fname}'...")

                        if on_tool_call:
                            on_tool_call(fname, fargs)

                        exec_res = self.execute(fname, fargs)

                        if exec_res.success:
                            if on_status:
                                summary = exec_res.to_message_content()
                                if len(summary) > 120:
                                    summary = summary[:117] + "..."
                                on_status("Execution successful", summary)

                            # Verify file directly on disk if create_file or edit_file
                            if fname in ("create_file", "edit_file") and isinstance(fargs, dict) and "path" in fargs:
                                target_path = Path(fargs["path"])
                                if target_path.exists() and target_path.stat().st_size > 0:
                                    if on_status:
                                        on_status("File verified", f"Confirmed '{target_path}' on disk ({target_path.stat().st_size} bytes)")
                        else:
                            if on_status:
                                on_status("Execution failed", str(exec_res.error))

                    if on_tool_result:
                        on_tool_result(exec_res)

                    # Return result to model using standard Ollama tool role
                    current_messages.append({
                        "role": "tool",
                        "tool_name": fname,
                        "name": fname,
                        "content": exec_res.to_message_content(),
                    })
                # Loop continues to send tool responses back to Qwen3
                continue

            # No tool calls: model returned final assistant text
            final_content = msg.content or ""
            current_messages.append({"role": "assistant", "content": final_content})
            return final_content, current_messages

        raise MaxIterationsExceededError(
            f"Tool execution loop exceeded the maximum limit of {max_iterations} iterations without concluding."
        )

