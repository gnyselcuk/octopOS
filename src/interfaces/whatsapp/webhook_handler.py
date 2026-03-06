"""WhatsApp Webhook Handler."""

import hmac
from typing import Any, Dict
from fastapi import FastAPI, Request, HTTPException, Query
from src.interfaces.whatsapp.bot import WhatsAppBot
from src.utils.logger import get_logger
from src.utils.rate_limiter import get_ip_limiter

logger = get_logger()


class WhatsAppWebhookHandler:
    """Handle incoming WhatsApp webhook requests."""
    
    def __init__(self, bot: WhatsAppBot):
        self.bot = bot
        self.app = FastAPI()
        self._rate_limiter = get_ip_limiter()
        self._setup_routes()
        
    def _setup_routes(self):
        """Setup FastAPI routes."""
        
        @self.app.get("/webhook/whatsapp")
        async def verify(
            hub_mode: str = Query(..., alias="hub.mode"),
            hub_verify_token: str = Query(..., alias="hub.verify_token"),
            hub_challenge: str = Query(..., alias="hub.challenge")
        ):
            """Handle webhook verification from Meta."""
            # Use constant-time comparison to prevent timing attacks
            if hub_mode == "subscribe" and hmac.compare_digest(hub_verify_token, self.bot.config.verify_token):
                return int(hub_challenge)
            raise HTTPException(status_code=403, detail="Verification failed")
        
        @self.app.post("/webhook/whatsapp")
        async def webhook(request: Request):
            """Handle incoming webhook."""
            # Rate limiting check
            client_ip = request.client.host
            if not self._rate_limiter.is_allowed(client_ip):
                logger.warning(f"Rate limit exceeded for IP: {client_ip}")
                raise HTTPException(status_code=429, detail="Rate limit exceeded")
            
            data = await request.json()
            logger.info(f"Received WhatsApp webhook: {data}")
            
            # Process messages
            entry = data.get("entry", [{}])[0]
            changes = entry.get("changes", [])
            
            for change in changes:
                value = change.get("value", {})
                if "messages" in value:
                    for handler in self.bot._message_handlers:
                        await handler(data)
            
            return {"status": "received"}
        
        @self.app.get("/health")
        async def health():
            """Health check endpoint."""
            return {"status": "healthy"}
