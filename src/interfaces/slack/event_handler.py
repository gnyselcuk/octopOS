"""Slack Event Handler - Handles Slack Events API requests."""

import hmac
import hashlib
from typing import Any, Dict
from fastapi import FastAPI, Request, HTTPException
from src.interfaces.slack.bot import SlackBot
from src.utils.logger import get_logger
from src.utils.rate_limiter import get_ip_limiter

logger = get_logger()


class SlackEventHandler:
    """Handle incoming Slack Events API requests."""
    
    def __init__(self, bot: SlackBot):
        self.bot = bot
        self.app = FastAPI()
        self._rate_limiter = get_ip_limiter()
        self._setup_routes()
        
    def _verify_signature(self, body: bytes, timestamp: str, signature: str) -> bool:
        """Verify Slack request signature with replay attack protection."""
        import time
        import logging
        
        # Validate timestamp to prevent replay attacks (5 minute window)
        try:
            request_time = int(timestamp)
            current_time = int(time.time())
            if abs(current_time - request_time) > 300:  # 5 minutes
                logger.warning("Slack request timestamp out of range - possible replay attack")
                return False
        except (ValueError, TypeError):
            logger.warning("Invalid Slack timestamp format")
            return False
        
        # Compute expected signature using constant-time comparison
        sig_basestring = f"v0:{timestamp}:{body.decode()}"
        my_signature = "v0=" + hmac.new(
            self.bot.config.signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(my_signature, signature)
        
    def _setup_routes(self):
        """Setup FastAPI routes."""
        
        @self.app.post("/slack/events")
        async def events(request: Request):
            """Handle incoming events."""
            # Rate limiting check
            client_ip = request.client.host
            if not self._rate_limiter.is_allowed(client_ip):
                logger.warning(f"Rate limit exceeded for IP: {client_ip}")
                raise HTTPException(status_code=429, detail="Rate limit exceeded")
            
            body = await request.body()
            timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
            signature = request.headers.get("X-Slack-Signature", "")
            
            if not self._verify_signature(body, timestamp, signature):
                raise HTTPException(status_code=403, detail="Invalid signature")
            
            data = await request.json()
            
            # Handle URL verification
            if data.get("type") == "url_verification":
                return {"challenge": data.get("challenge")}
            
            # Process event
            if "event" in data:
                for handler in self.bot._event_handlers:
                    await handler(data)
            
            return {"ok": True}
        
        @self.app.get("/health")
        async def health():
            """Health check endpoint."""
            return {"status": "healthy"}
