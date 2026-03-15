"""Telegram Gateway - Telegram Bot API integration for octopOS."""

from src.interfaces.telegram.bot import TelegramBot, TelegramConfig
from src.interfaces.telegram.message_adapter import TelegramAdapter
from src.interfaces.telegram.runtime import build_message_handler, run_telegram_polling
from src.interfaces.telegram.webhook_handler import TelegramWebhookHandler

__all__ = [
    "TelegramBot",
    "TelegramConfig",
    "TelegramAdapter",
    "build_message_handler",
    "run_telegram_polling",
    "TelegramWebhookHandler",
]
