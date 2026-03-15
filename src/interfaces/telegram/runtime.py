"""Runtime helpers for Telegram polling integration."""

from __future__ import annotations

import json
import os
from typing import Optional

from src.interfaces.telegram.bot import TelegramBot, TelegramConfig
from src.interfaces.telegram.message_adapter import TelegramAdapter
from src.utils.logger import get_logger

logger = get_logger()

MAX_TELEGRAM_MESSAGE_LENGTH = 4000
HELP_TEXT = (
    "octopOS Telegram hazir.\n"
    "Mesaj gonderebilir veya /ask <soru> kullanabilirsiniz.\n"
    "Ornek: /ask Istanbul hava durumu bugun"
)


def _parse_allowed_chat_ids(raw_value: Optional[str]) -> set[str]:
    """Parse a comma-separated allowlist of Telegram chat IDs."""
    if not raw_value:
        return set()
    return {item.strip() for item in raw_value.split(",") if item.strip()}


def _extract_prompt(platform_message) -> Optional[str]:
    """Resolve the user prompt to send to the orchestrator."""
    if not platform_message.is_command:
        return platform_message.content.strip() or None

    command_name = (platform_message.command_name or "").lower()
    if command_name in {"start", "help"}:
        return None
    if command_name == "ask":
        prompt = " ".join(platform_message.command_args).strip()
        return prompt or None
    return platform_message.content.strip() or None


def _format_response_text(result: object) -> str:
    """Create a user-facing response from an orchestrator result."""
    if isinstance(result, dict):
        response = result.get("response")
        if response:
            return str(response)

        message = result.get("message")
        if message:
            return str(message)

        return json.dumps(result, ensure_ascii=False, indent=2)

    return str(result)


def _truncate_message(text: str) -> str:
    """Telegram messages have a hard limit; keep the end user text valid."""
    if len(text) <= MAX_TELEGRAM_MESSAGE_LENGTH:
        return text
    return text[: MAX_TELEGRAM_MESSAGE_LENGTH - 1].rstrip() + "…"


def build_message_handler(
    bot: TelegramBot,
    orchestrator,
    adapter: Optional[TelegramAdapter] = None,
    allowed_chat_ids: Optional[set[str]] = None,
):
    """Build a Telegram update handler that forwards messages to octopOS."""
    adapter = adapter or TelegramAdapter()

    async def handle_update(raw_update: dict) -> None:
        platform_message = adapter.normalize_message(raw_update)
        reply_to = platform_message.message_id or None
        chat_id = platform_message.chat_id
        command_name = (platform_message.command_name or "").lower()

        if allowed_chat_ids and chat_id not in allowed_chat_ids:
            logger.warning(f"Rejected Telegram message from unauthorized chat_id={chat_id}")
            await bot.send_message(
                chat_id=chat_id,
                text="Bu bot bu sohbet icin yetkili degil.",
                reply_to=reply_to,
                parse_mode=None,
            )
            return

        if platform_message.is_command and command_name in {"start", "help"}:
            await bot.send_message(chat_id=chat_id, text=HELP_TEXT, reply_to=reply_to, parse_mode=None)
            return

        if platform_message.is_command and command_name not in {"", "ask"}:
            await bot.send_message(
                chat_id=chat_id,
                text=f"Desteklenmeyen komut: /{command_name}\n\n{HELP_TEXT}",
                reply_to=reply_to,
                parse_mode=None,
            )
            return

        prompt = _extract_prompt(platform_message)
        if not prompt:
            if platform_message.attachments:
                text = "Bu demo surumunde sadece metin mesajlari destekleniyor."
            else:
                text = HELP_TEXT
            await bot.send_message(chat_id=chat_id, text=text, reply_to=reply_to, parse_mode=None)
            return

        await bot.send_action(chat_id=chat_id, action="typing")
        try:
            result = await orchestrator.process_user_input(prompt)
            text = _format_response_text(result)
        except Exception as e:
            logger.error(f"Telegram orchestrator request failed: {e}")
            text = f"Bir hata olustu: {e}"

        await bot.send_message(
            chat_id=chat_id,
            text=_truncate_message(text),
            reply_to=reply_to,
            parse_mode=None,
        )

    return handle_update


async def run_telegram_polling(
    bot_token: Optional[str] = None,
    chat_id: Optional[str] = None,
    allowed_chat_ids: Optional[set[str]] = None,
    polling_interval: int = 1,
    polling_timeout: int = 30,
) -> None:
    """Start Telegram long polling and bridge messages into the orchestrator."""
    from src.engine.orchestrator import get_orchestrator

    resolved_bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
    if not resolved_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is required")
    resolved_allowed_chat_ids = allowed_chat_ids or _parse_allowed_chat_ids(
        os.getenv("TELEGRAM_ALLOWED_CHAT_IDS")
    )
    if chat_id:
        resolved_allowed_chat_ids.add(str(chat_id))

    bot = TelegramBot(
        TelegramConfig(
            bot_token=resolved_bot_token,
            polling_interval=polling_interval,
            polling_timeout=polling_timeout,
        )
    )
    orchestrator = get_orchestrator()
    await orchestrator.on_start()
    await bot.start()
    bot.on_message(
        build_message_handler(bot, orchestrator, allowed_chat_ids=resolved_allowed_chat_ids)
    )

    if chat_id:
        await bot.send_message(chat_id=chat_id, text="octopOS Telegram baglantisi aktif.", parse_mode=None)

    try:
        await bot.poll_forever()
    finally:
        await bot.stop()
