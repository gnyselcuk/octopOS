"""Tests for Slack runtime helpers."""

import pytest
from unittest.mock import AsyncMock

from src.interfaces.slack.bot import SlackBot, SlackConfig
from src.interfaces.slack.runtime import HELP_TEXT, build_event_handler


def make_event(text: str, channel: str = "C123", user: str = "U123", event_type: str = "app_mention") -> dict:
    return {
        "event": {
            "type": event_type,
            "text": text,
            "channel": channel,
            "user": user,
            "ts": "1710000000.000100",
        }
    }


@pytest.fixture
def bot():
    return SlackBot(SlackConfig(bot_token="xoxb-token", signing_secret="secret", app_token="xapp-token"))


@pytest.mark.asyncio
async def test_app_mention_flows_to_orchestrator(bot):
    orchestrator = AsyncMock()
    orchestrator.process_user_input = AsyncMock(return_value={"status": "success", "response": "BTC is 71500"})
    bot.send_message = AsyncMock(return_value=True)

    handler = build_event_handler(bot, orchestrator, bot_user_id="U_BOT")
    await handler(make_event("<@U_BOT> get current btc price"))

    orchestrator.process_user_input.assert_awaited_once_with("get current btc price")
    bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_bot_messages_are_ignored(bot):
    orchestrator = AsyncMock()
    orchestrator.process_user_input = AsyncMock()
    bot.send_message = AsyncMock(return_value=True)
    event = make_event("hello")
    event["event"]["subtype"] = "bot_message"

    handler = build_event_handler(bot, orchestrator)
    await handler(event)

    orchestrator.process_user_input.assert_not_awaited()
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_unauthorized_channel_is_rejected(bot):
    orchestrator = AsyncMock()
    orchestrator.process_user_input = AsyncMock()
    bot.send_message = AsyncMock(return_value=True)

    handler = build_event_handler(bot, orchestrator, allowed_channels={"C999"})
    await handler(make_event("hello", channel="C123"))

    orchestrator.process_user_input.assert_not_awaited()
    sent_text = bot.send_message.await_args.kwargs["text"]
    assert "not authorized" in sent_text.lower()


@pytest.mark.asyncio
async def test_empty_prompt_returns_help(bot):
    orchestrator = AsyncMock()
    orchestrator.process_user_input = AsyncMock()
    bot.send_message = AsyncMock(return_value=True)

    handler = build_event_handler(bot, orchestrator, bot_user_id="U_BOT")
    await handler(make_event("<@U_BOT>"))

    orchestrator.process_user_input.assert_not_awaited()
    assert bot.send_message.await_args.kwargs["text"] == HELP_TEXT
