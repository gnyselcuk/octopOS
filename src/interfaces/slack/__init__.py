"""Slack Gateway - Slack API integration for octopOS."""

from src.interfaces.slack.bot import SlackBot, SlackConfig
from src.interfaces.slack.message_adapter import SlackAdapter
from src.interfaces.slack.event_handler import SlackEventHandler

__all__ = [
    "SlackBot",
    "SlackConfig", 
    "SlackAdapter",
    "SlackEventHandler",
]