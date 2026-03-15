"""Tests for Telegram runtime helpers."""

import pytest
from unittest.mock import AsyncMock

from src.interfaces.telegram.bot import TelegramBot, TelegramConfig
from src.interfaces.telegram.runtime import HELP_TEXT, build_message_handler


def make_update(text: str, message_id: int = 1, chat_id: int = 123456, user_id: int = 42) -> dict:
    return {
        "update_id": 100000 + message_id,
        "message": {
            "message_id": message_id,
            "from": {"id": user_id, "is_bot": False, "first_name": "Selocan", "username": "selocan"},
            "chat": {"id": chat_id, "type": "private"},
            "text": text,
            "date": 1700000000,
        },
    }


@pytest.fixture
def bot():
    return TelegramBot(TelegramConfig(bot_token="123456:TEST"))


@pytest.mark.asyncio
async def test_start_command_returns_help_without_orchestrator_call(bot):
    orchestrator = AsyncMock()
    orchestrator.process_user_input = AsyncMock()
    bot.send_message = AsyncMock(return_value=True)

    handler = build_message_handler(bot, orchestrator)
    await handler(make_update("/start"))

    orchestrator.process_user_input.assert_not_awaited()
    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.kwargs["text"] == HELP_TEXT


@pytest.mark.asyncio
async def test_ask_command_sends_only_prompt_text_to_orchestrator(bot):
    orchestrator = AsyncMock()
    orchestrator.process_user_input = AsyncMock(return_value={"status": "success", "response": "42"})
    bot.send_action = AsyncMock(return_value=True)
    bot.send_message = AsyncMock(return_value=True)

    handler = build_message_handler(bot, orchestrator)
    await handler(make_update("/ask btc current price"))

    orchestrator.process_user_input.assert_awaited_once_with("btc current price")
    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.kwargs["text"] == "42"
    assert bot.send_message.await_args.kwargs["parse_mode"] is None


@pytest.mark.asyncio
async def test_plain_text_message_flows_to_orchestrator(bot):
    orchestrator = AsyncMock()
    orchestrator.process_user_input = AsyncMock(return_value={"status": "success", "response": "Sunny"})
    bot.send_action = AsyncMock(return_value=True)
    bot.send_message = AsyncMock(return_value=True)

    handler = build_message_handler(bot, orchestrator)
    await handler(make_update("Istanbul weather today"))

    orchestrator.process_user_input.assert_awaited_once_with("Istanbul weather today")
    assert bot.send_message.await_args.kwargs["text"] == "Sunny"


@pytest.mark.asyncio
async def test_handler_returns_error_message_on_orchestrator_failure(bot):
    orchestrator = AsyncMock()
    orchestrator.process_user_input = AsyncMock(side_effect=RuntimeError("Bedrock timeout"))
    bot.send_action = AsyncMock(return_value=True)
    bot.send_message = AsyncMock(return_value=True)

    handler = build_message_handler(bot, orchestrator)
    await handler(make_update("crash please"))

    sent_text = bot.send_message.await_args.kwargs["text"]
    assert "hata" in sent_text.lower()


@pytest.mark.asyncio
async def test_attachment_only_message_gets_demo_notice(bot):
    orchestrator = AsyncMock()
    orchestrator.process_user_input = AsyncMock()
    bot.send_message = AsyncMock(return_value=True)

    update = make_update("")
    update["message"]["voice"] = {"file_id": "abc", "duration": 5}

    handler = build_message_handler(bot, orchestrator)
    await handler(update)

    orchestrator.process_user_input.assert_not_awaited()
    sent_text = bot.send_message.await_args.kwargs["text"]
    assert "sadece metin" in sent_text.lower()


@pytest.mark.asyncio
async def test_unauthorized_chat_is_rejected_before_orchestrator(bot):
    orchestrator = AsyncMock()
    orchestrator.process_user_input = AsyncMock()
    bot.send_message = AsyncMock(return_value=True)

    handler = build_message_handler(bot, orchestrator, allowed_chat_ids={"999999"})
    await handler(make_update("hello", chat_id=123456))

    orchestrator.process_user_input.assert_not_awaited()
    sent_text = bot.send_message.await_args.kwargs["text"]
    assert "yetkili degil" in sent_text.lower()
