"""Telegram Gateway - Telegram Bot API integration for octopOS."""

from src.interfaces.telegram.bot import TelegramBot, TelegramConfig
from src.interfaces.telegram.message_adapter import TelegramAdapter
from src.interfaces.telegram.webhook_handler import TelegramWebhookHandler

__all__ = [
    "TelegramBot",
    "TelegramConfig",
    "TelegramAdapter",
    "TelegramWebhookHandler",
]
