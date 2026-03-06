"""Telegram Webhook Handler - FastAPI endpoint for Telegram webhooks."""

import hmac
from typing import Any, Dict
from fastapi import FastAPI, Request, HTTPException
from src.interfaces.telegram.bot import TelegramBot
from src.utils.logger import get_logger
from src.utils.rate_limiter import get_ip_limiter

logger = get_logger()


class TelegramWebhookHandler:
    """Handle incoming Telegram webhook requests."""
    
    def __init__(self, bot: TelegramBot):
        self.bot = bot
        self.app = FastAPI()
        self._rate_limiter = get_ip_limiter()
        self._setup_routes()
        
    def _setup_routes(self):
        """Setup FastAPI routes."""
        
        @self.app.post("/webhook/{bot_token}")
        async def webhook(bot_token: str, request: Request):
            """Handle incoming webhook."""
            # Rate limiting check
            client_ip = request.client.host
            if not self._rate_limiter.is_allowed(client_ip):
                logger.warning(f"Rate limit exceeded for IP: {client_ip}")
                raise HTTPException(status_code=429, detail="Rate limit exceeded")
            
            # Use constant-time comparison to prevent timing attacks
            expected_token = self.bot.config.bot_token.split(":")[1]
            if not hmac.compare_digest(bot_token, expected_token):
                raise HTTPException(status_code=403, detail="Invalid token")
            
            data = await request.json()
            logger.info(f"Received webhook: {data}")
            
            # Process update
            if "message" in data:
                for handler in self.bot._message_handlers:
                    await handler(data)
            
            return {"ok": True}
        
        @self.app.get("/health")
        async def health():
            """Health check endpoint."""
            return {"status": "healthy", "bot": self.bot.config.bot_token.split(":")[0]}
    
    async def set_webhook(self, url: str) -> bool:
        """Set webhook URL with Telegram."""
        import aiohttp
        
        api_url = f"https://api.telegram.org/bot{self.bot.config.bot_token}/setWebhook"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, json={"url": url}) as resp:
                    result = await resp.json()
                    return result.get("ok", False)
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}")
            return False
