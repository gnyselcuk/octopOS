"""Slack Gateway - Slack API integration for octopOS."""

from src.interfaces.slack.bot import SlackBot, SlackConfig
from src.interfaces.slack.message_adapter import SlackAdapter
from src.interfaces.slack.runtime import build_event_handler, run_slack_socket_mode
from src.interfaces.slack.event_handler import SlackEventHandler

__all__ = [
    "SlackBot",
    "SlackConfig", 
    "SlackAdapter",
    "build_event_handler",
    "run_slack_socket_mode",
    "SlackEventHandler",
]
