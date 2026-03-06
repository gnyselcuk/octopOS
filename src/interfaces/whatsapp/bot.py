"""WhatsApp Bot - WhatsApp Business API client."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Callable
import aiohttp

from src.utils.logger import get_logger

logger = get_logger()


@dataclass
class WhatsAppConfig:
    """Configuration for WhatsApp Business API."""
    
    phone_number_id: str
    access_token: str
    api_version: str = "v18.0"
    verify_token: Optional[str] = None


class WhatsAppBot:
    """WhatsApp Business API client."""
    
    API_BASE = "https://graph.facebook.com/{version}/{phone_id}"
    
    def __init__(self, config: WhatsAppConfig):
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None
        self._message_handlers: List[Callable] = []
        
    async def start(self):
        """Start the bot."""
        self._session = aiohttp.ClientSession()
        logger.info("WhatsApp bot started")
        
    async def stop(self):
        """Stop the bot."""
        if self._session:
            await self._session.close()
        logger.info("WhatsApp bot stopped")
        
    async def send_message(
        self,
        to: str,
        text: str
    ) -> bool:
        """Send a text message."""
        if not self._session:
            return False
            
        url = self.API_BASE.format(
            version=self.config.api_version,
            phone_id=self.config.phone_number_id
        ) + "/messages"
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"body": text}
        }
            
        try:
            async with self._session.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {self.config.access_token}"}
            ) as resp:
                result = await resp.json()
                return "messages" in result
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return False
            
    def on_message(self, handler: Callable):
        """Register message handler."""
        self._message_handlers.append(handler)
