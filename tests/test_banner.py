"""Unit and integration tests for Code AG startup banner."""

from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from rich.console import Console

from codeagent.banner import (
    CODEAGENT_ASCII_LOGO,
    PROMPT_MESSAGE,
    TAGLINE,
    build_banner_renderable,
    display_startup_banner,
)
from codeagent.cli import one_shot_mode
from codeagent.config.settings import Settings


def _render_to_text(renderable, width: int = 100) -> str:
    """Helper to render a Rich renderable to a plain string."""
    buffer = StringIO()
    console = Console(file=buffer, width=width, force_terminal=True, color_system=None)
    console.print(renderable)
    return buffer.getvalue()


def test_banner_rendering_contains_core_elements():
    """Verify that banner includes the ASCII logo, tagline, and readiness prompt."""
    settings = Settings(APP_NAME="Code AG", APP_VERSION="0.1.0")
    panel = build_banner_renderable(settings=settings, active_model="qwen3:latest", is_online=True)
    text = _render_to_text(panel, width=100)

    # ASCII logo lines verification
    assert "/ ___|___" in text
    assert "| |__|" in text
    assert r"\____\___/" in text

    # Tagline and prompt
    assert TAGLINE in text
    assert PROMPT_MESSAGE in text

    # Title
    assert "Code AG" in text


def test_banner_dynamic_version():
    """Verify that the version displayed dynamically reflects settings.app_version."""
    settings = Settings(APP_VERSION="3.7.9")
    panel = build_banner_renderable(settings=settings, active_model="qwen3:latest", is_online=True)
    text = _render_to_text(panel)

    assert "v3.7.9" in text


def test_banner_model_and_provider_display():
    """Verify that model and provider are dynamically rendered and not hardcoded."""
    settings = Settings(OLLAMA_HOST="http://custom-host:11434")
    panel = build_banner_renderable(
        settings=settings,
        active_model="deepseek-coder:6.7b",
        provider_name="Custom Ollama Server",
        is_online=True,
    )
    text = _render_to_text(panel)

    assert "deepseek-coder:6.7b" in text
    assert "Custom Ollama Server" in text
    assert "http://custom-host:11434" in text


def test_banner_workspace_display():
    """Verify that current workspace path is dynamically displayed."""
    custom_workspace = r"C:\Custom\Projects\TestWorkspace"
    panel = build_banner_renderable(
        workspace_root=custom_workspace,
        active_model="qwen3:latest",
        is_online=True,
    )
    text = _render_to_text(panel)

    assert custom_workspace in text


def test_banner_ollama_unavailable_state():
    """Verify that offline state clearly indicates unavailability without false claims."""
    settings = Settings(OLLAMA_HOST="http://offline-ollama:11434")
    panel = build_banner_renderable(
        settings=settings,
        active_model="qwen3:latest",
        is_online=False,
    )
    text = _render_to_text(panel)

    assert "Offline (Ollama unavailable)" in text
    assert "Warning: Ollama server is unreachable at http://offline-ollama:11434" in text
    assert "ollama serve" in text
    assert "Connected (Online)" not in text


def test_banner_disabled_state():
    """Verify that when SHOW_STARTUP_BANNER=false, banner is not displayed."""
    settings = Settings(SHOW_STARTUP_BANNER=False)
    buffer = StringIO()
    console = Console(file=buffer, force_terminal=True, width=100)

    display_startup_banner(console=console, settings=settings, is_online=True)
    assert buffer.getvalue().strip() == ""


def test_banner_forced_display_when_disabled():
    """Verify that force=True overrides SHOW_STARTUP_BANNER=false."""
    settings = Settings(SHOW_STARTUP_BANNER=False)
    buffer = StringIO()
    console = Console(file=buffer, force_terminal=True, width=100)

    display_startup_banner(console=console, settings=settings, is_online=True, force=True)
    text = buffer.getvalue()
    assert settings.app_name in text
    assert TAGLINE in text


def test_banner_narrow_terminal_graceful_handling():
    """Verify that narrow terminals (< 45 cols) adapt cleanly without ASCII wrap distortion."""
    settings = Settings(APP_NAME="Code AG", APP_VERSION="0.1.0")
    narrow_panel = build_banner_renderable(
        settings=settings,
        active_model="qwen3:latest",
        is_online=True,
        terminal_width=40,
    )
    narrow_text = _render_to_text(narrow_panel, width=40)

    # In narrow mode, full ASCII art is omitted to avoid ugly wrapping
    assert "/ ___|___" not in narrow_text
    assert "Code AG v0.1.0" in narrow_text
    assert "Built in India" in narrow_text
    assert "Ready" in narrow_text
    assert "build?" in narrow_text

    # In wide mode, ASCII art is included
    wide_panel = build_banner_renderable(
        settings=settings,
        active_model="qwen3:latest",
        is_online=True,
        terminal_width=80,
    )
    wide_text = _render_to_text(wide_panel, width=80)
    assert "/ ___|___" in wide_text


def test_non_interactive_execution_is_clean():
    """Verify that one-shot commands do not display the banner by default."""
    buffer = StringIO()
    test_console = Console(file=buffer, force_terminal=True, width=100)

    mock_client = MagicMock()
    mock_client.generate.return_value = "Result for test query"

    with patch("codeagent.cli.console", test_console):
        one_shot_mode(
            client=mock_client,
            prompt="tell me a joke",
            model_name="qwen3:latest",
            stream=False,
            show_banner=False,
        )

    output = buffer.getvalue()
    assert TAGLINE not in output
    assert "/ ___|___" not in output
    assert "Result for test query" in output


def test_non_interactive_execution_with_banner_flag():
    """Verify that one-shot mode displays banner when explicitly requested with show_banner=True."""
    buffer = StringIO()
    test_console = Console(file=buffer, force_terminal=True, width=100)

    mock_client = MagicMock()
    mock_client.generate.return_value = "Result for test query"
    mock_client.check_connection.return_value = (True, "Online")

    with patch("codeagent.cli.console", test_console):
        one_shot_mode(
            client=mock_client,
            prompt="tell me a joke",
            model_name="qwen3:latest",
            stream=False,
            show_banner=True,
        )

    output = buffer.getvalue()
    assert TAGLINE in output
    assert "Result for test query" in output
