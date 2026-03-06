"""
E2E Tests: CLI Interface (octo ask / octo chat)
================================================
Tests the Typer CLI commands end-to-end by running them via
typer.testing.CliRunner so no subprocess is needed.

Bedrock, LanceDB, and MCP connections are ALL mocked so the suite
runs completely offline.
"""

import json
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typer.testing import CliRunner

from src.interfaces.cli.main import app


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

runner = CliRunner()

# commands.py does `from src.engine.orchestrator import get_orchestrator`
# so we must patch the function at its *source* module.
ORCH_TARGET = "src.engine.orchestrator.get_orchestrator"


def make_orch(
    response_text: str = "🐙 Merhaba! Ben octopOS.",
    intent: str = "chat",
    status: str = "success",
) -> AsyncMock:
    """Return a fully mocked Orchestrator."""
    orch = AsyncMock()
    orch.on_start = AsyncMock()
    orch.process_user_input = AsyncMock(
        return_value={
            "status": status,
            "intent": intent,
            "response": response_text,
        }
    )
    return orch


# ---------------------------------------------------------------------------
# octo ask
# ---------------------------------------------------------------------------

class TestOctoAsk:
    """octo ask end-to-end via CliRunner."""

    def test_successful_chat_response(self):
        orch = make_orch("Harika soru! Cevap şu: 42")
        with patch(ORCH_TARGET, return_value=orch):
            result = runner.invoke(app, ["ask", "Anlam ne?"])

        assert result.exit_code == 0
        assert "octopOS" in result.output or "Harika" in result.output

    def test_query_response_shows_content(self):
        orch = make_orch("src/engine/orchestrator.py\ntests/", intent="query")
        with patch(ORCH_TARGET, return_value=orch):
            result = runner.invoke(app, ["ask", "Proje dosyalarını listele"])

        assert result.exit_code == 0

    def test_error_status_shows_error_message(self):
        orch = AsyncMock()
        orch.on_start = AsyncMock()
        orch.process_user_input = AsyncMock(
            return_value={"status": "error", "message": "Bedrock timeout"}
        )
        with patch(ORCH_TARGET, return_value=orch):
            result = runner.invoke(app, ["ask", "çöksün"])

        assert result.exit_code == 0
        assert "Error" in result.output or "Bedrock" in result.output

    def test_exception_during_processing(self):
        orch = AsyncMock()
        orch.on_start = AsyncMock()
        orch.process_user_input = AsyncMock(side_effect=Exception("AWS down"))
        with patch(ORCH_TARGET, return_value=orch):
            result = runner.invoke(app, ["ask", "crash test"])

        assert result.exit_code == 0
        assert "Failed" in result.output or "AWS" in result.output

    def test_unicode_and_turkish_input(self):
        orch = make_orch("Tabii! Türkçe anlıyorum.")
        with patch(ORCH_TARGET, return_value=orch):
            result = runner.invoke(app, ["ask", "Görevler nasıl atanır?"])

        assert result.exit_code == 0

    def test_task_result_without_response_key(self):
        """When status=success but no 'response' key → show Task Created."""
        orch = AsyncMock()
        orch.on_start = AsyncMock()
        orch.process_user_input = AsyncMock(
            return_value={"status": "success", "intent": "task", "task_id": "abc-123"}
        )
        with patch(ORCH_TARGET, return_value=orch):
            result = runner.invoke(app, ["ask", "S3'e logları yükle"])

        assert result.exit_code == 0
        assert "Task" in result.output or "abc-123" in result.output


# ---------------------------------------------------------------------------
# octo chat (interactive loop via stdin simulation)
# ---------------------------------------------------------------------------

class TestOctoChat:
    """octo chat end-to-end via CliRunner with simulated stdin."""

    def test_chat_exits_on_exit_command(self):
        orch = make_orch()
        with patch(ORCH_TARGET, return_value=orch):
            result = runner.invoke(app, ["chat"], input="exit\n")

        assert result.exit_code == 0
        assert "Ending" in result.output or "chat" in result.output.lower()

    def test_chat_exits_on_quit_alias(self):
        orch = make_orch()
        with patch(ORCH_TARGET, return_value=orch):
            result = runner.invoke(app, ["chat"], input="quit\n")

        assert result.exit_code == 0

    def test_chat_exits_on_colon_q(self):
        orch = make_orch()
        with patch(ORCH_TARGET, return_value=orch):
            result = runner.invoke(app, ["chat"], input=":q\n")

        assert result.exit_code == 0

    def test_chat_processes_one_message_then_exits(self):
        orch = make_orch("Harika! Devam edelim.")
        with patch(ORCH_TARGET, return_value=orch):
            result = runner.invoke(app, ["chat"], input="Merhaba!\nexit\n")

        assert result.exit_code == 0
        orch.process_user_input.assert_called_once_with("Merhaba!")

    def test_chat_skips_empty_lines(self):
        orch = make_orch()
        with patch(ORCH_TARGET, return_value=orch):
            result = runner.invoke(app, ["chat"], input="\n\n\nexit\n")

        assert result.exit_code == 0
        orch.process_user_input.assert_not_called()

    def test_chat_multi_turn_context(self):
        """Multiple messages processed in sequence within one chat session."""
        responses = [
            {"status": "success", "intent": "chat", "response": "Ben octopOS!"},
            {"status": "success", "intent": "chat", "response": "Python harika."},
            {"status": "success", "intent": "chat", "response": "Evet, yardımcı olurum."},
        ]
        orch = AsyncMock()
        orch.on_start = AsyncMock()
        orch.process_user_input = AsyncMock(side_effect=responses)

        with patch(ORCH_TARGET, return_value=orch):
            result = runner.invoke(
                app, ["chat"],
                input="Kimsin?\nPython nedir?\nYardımcı olur musun?\nexit\n"
            )

        assert result.exit_code == 0
        assert orch.process_user_input.call_count == 3

    def test_chat_handles_error_in_message_gracefully(self):
        """Error on one message should not crash the chat loop."""
        orch = AsyncMock()
        orch.on_start = AsyncMock()
        orch.process_user_input = AsyncMock(
            side_effect=[
                Exception("geçici API hatası"),
                {"status": "success", "intent": "chat", "response": "Tekrar çalışıyor!"},
            ]
        )

        with patch(ORCH_TARGET, return_value=orch):
            result = runner.invoke(
                app, ["chat"],
                input="crash\nbu çalışmalı\nexit\n"
            )

        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# octo status (smoke test)
# ---------------------------------------------------------------------------

class TestOctoStatus:
    """octo status smoke test — should not crash."""

    def test_status_command_runs(self):
        result = runner.invoke(app, ["status"])
        assert result.exit_code in (0, 1)


# ---------------------------------------------------------------------------
# CLI Stress: rapid sequential asks
# ---------------------------------------------------------------------------

class TestCLIStress:
    """Rapid-fire CLI invocations to check for state leakage between calls."""

    def test_20_sequential_asks_no_state_leak(self):
        """Each 'octo ask' is independent; no shared mutable state."""
        call_args_seen = []

        def make_orch_fn():
            orch = AsyncMock()
            orch.on_start = AsyncMock()

            async def process(text: str) -> dict:
                call_args_seen.append(text)
                return {"status": "success", "response": f"Yanıt: {text}"}

            orch.process_user_input = process
            return orch

        for i in range(20):
            with patch(ORCH_TARGET, side_effect=make_orch_fn):
                result = runner.invoke(app, ["ask", f"sorgu_{i}"])
            assert result.exit_code == 0

        assert len(call_args_seen) == 20
        for i in range(20):
            assert f"sorgu_{i}" in call_args_seen
