"""Runtime helpers for Slack Socket Mode integration."""

from __future__ import annotations

import json
import os
import re
from typing import Optional, Set

from src.interfaces.slack.bot import SlackBot, SlackConfig
from src.interfaces.slack.message_adapter import SlackAdapter
from src.utils.logger import get_logger

logger = get_logger()

MAX_SLACK_MESSAGE_LENGTH = 3000
HELP_TEXT = (
    "octopOS Slack is ready.\n"
    "Mention the bot or send a DM to ask questions.\n"
    "Example: @octopOS get current btc price"
)


def _parse_allowed_channels(raw_value: Optional[str]) -> Set[str]:
    if not raw_value:
        return set()
    return {item.strip() for item in raw_value.split(",") if item.strip()}


def _strip_bot_mentions(text: str, bot_user_id: Optional[str]) -> str:
    if not text:
        return ""
    cleaned = text.strip()
    if bot_user_id:
        cleaned = cleaned.replace(f"<@{bot_user_id}>", " ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _extract_prompt(platform_message, bot_user_id: Optional[str]) -> Optional[str]:
    content = _strip_bot_mentions(platform_message.content, bot_user_id)
    if not content:
        return None
    if platform_message.is_command and platform_message.command_name == "ask":
        return " ".join(platform_message.command_args).strip() or None
    return content


def _format_response_text(result: object) -> str:
    if isinstance(result, dict):
        if result.get("response"):
            return str(result["response"])
        if result.get("message"):
            return str(result["message"])
        return json.dumps(result, ensure_ascii=False, indent=2)
    return str(result)


def _truncate_message(text: str) -> str:
    if len(text) <= MAX_SLACK_MESSAGE_LENGTH:
        return text
    return text[: MAX_SLACK_MESSAGE_LENGTH - 1].rstrip() + "…"


def build_event_handler(
    bot: SlackBot,
    orchestrator,
    adapter: Optional[SlackAdapter] = None,
    allowed_channels: Optional[Set[str]] = None,
    bot_user_id: Optional[str] = None,
):
    """Build a Slack event handler that forwards messages to octopOS."""
    adapter = adapter or SlackAdapter()
    allowed_channels = allowed_channels or set()

    async def handle_event(raw_event: dict) -> None:
        event = raw_event.get("event", {})
        if event.get("type") not in {"message", "app_mention"}:
            return
        if event.get("subtype") == "bot_message":
            return
        if not event.get("user"):
            return

        platform_message = adapter.normalize_message(raw_event)
        channel = platform_message.chat_id
        if allowed_channels and channel not in allowed_channels:
            logger.warning(f"Rejected Slack event from unauthorized channel={channel}")
            await bot.send_message(channel=channel, text="This bot is not authorized for this channel.", thread_ts=platform_message.thread_id or platform_message.message_id)
            return

        prompt = _extract_prompt(platform_message, bot_user_id)
        if not prompt:
            await bot.send_message(channel=channel, text=HELP_TEXT, thread_ts=platform_message.thread_id or platform_message.message_id)
            return

        try:
            result = await orchestrator.process_user_input(prompt)
            text = _format_response_text(result)
        except Exception as e:
            logger.error(f"Slack orchestrator request failed: {e}")
            text = f"An error occurred: {e}"

        await bot.send_message(
            channel=channel,
            text=_truncate_message(text),
            thread_ts=platform_message.thread_id or platform_message.message_id,
        )

    return handle_event


async def run_slack_socket_mode(
    bot_token: Optional[str] = None,
    app_token: Optional[str] = None,
    signing_secret: Optional[str] = None,
    allowed_channels: Optional[Set[str]] = None,
) -> None:
    """Start Slack Socket Mode and bridge messages into the orchestrator."""
    from src.engine.orchestrator import get_orchestrator

    resolved_bot_token = bot_token or os.getenv("SLACK_BOT_TOKEN")
    resolved_app_token = app_token or os.getenv("SLACK_APP_TOKEN")
    resolved_signing_secret = signing_secret or os.getenv("SLACK_SIGNING_SECRET", "")
    if not resolved_bot_token:
        raise ValueError("SLACK_BOT_TOKEN is required")
    if not resolved_app_token:
        raise ValueError("SLACK_APP_TOKEN is required for Socket Mode")

    resolved_allowed_channels = allowed_channels or _parse_allowed_channels(os.getenv("SLACK_ALLOWED_CHANNELS"))

    bot = SlackBot(
        SlackConfig(
            bot_token=resolved_bot_token,
            signing_secret=resolved_signing_secret,
            app_token=resolved_app_token,
        )
    )
    orchestrator = get_orchestrator()
    await orchestrator.on_start()
    await bot.start()

    auth_info = await bot.get_auth_info() or {}
    bot_user_id = auth_info.get("user_id")
    bot.on_event(
        build_event_handler(
            bot,
            orchestrator,
            allowed_channels=resolved_allowed_channels,
            bot_user_id=bot_user_id,
        )
    )

    try:
        await bot.socket_mode_loop()
    finally:
        await bot.stop()
