"""Slack Bot - Slack API implementation."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Callable
import asyncio
import aiohttp

from src.utils.logger import get_logger

logger = get_logger()


@dataclass
class SlackConfig:
    """Configuration for Slack Bot."""
    
    bot_token: str
    signing_secret: str
    app_token: Optional[str] = None


class SlackBot:
    """Slack Bot API client."""
    
    API_BASE = "https://slack.com/api/{method}"
    
    def __init__(self, config: SlackConfig):
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None
        self._running = False
        self._event_handlers: List[Callable] = []
        
    async def start(self):
        """Start the bot."""
        self._session = aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {self.config.bot_token}"}
        )
        self._running = True
        logger.info("Slack bot started")
        
    async def stop(self):
        """Stop the bot."""
        self._running = False
        if self._session:
            await self._session.close()
        logger.info("Slack bot stopped")
        
    async def send_message(
        self,
        channel: str,
        text: str,
        thread_ts: Optional[str] = None
    ) -> bool:
        """Send a message to a channel."""
        if not self._session:
            return False
            
        url = self.API_BASE.format(method="chat.postMessage")
        payload = {
            "channel": channel,
            "text": text
        }
        if thread_ts:
            payload["thread_ts"] = thread_ts
            
        try:
            async with self._session.post(url, json=payload) as resp:
                result = await resp.json()
                return result.get("ok", False)
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return False
            
    def on_event(self, handler: Callable):
        """Register event handler."""
        self._event_handlers.append(handler)
