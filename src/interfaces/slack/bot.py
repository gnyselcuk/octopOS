"""Slack Bot - Slack API implementation."""

import json
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
    signing_secret: str = ""
    app_token: Optional[str] = None
    socket_retry_delay: int = 5


class SlackBot:
    """Slack Bot API client."""
    
    API_BASE = "https://slack.com/api/{method}"
    
    def __init__(self, config: SlackConfig):
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None
        self._socket: Optional[aiohttp.ClientWebSocketResponse] = None
        self._running = False
        self._event_handlers: List[Callable] = []
        
    async def start(self):
        """Start the bot."""
        if self._running and self._session and not self._session.closed:
            return
        self._session = aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {self.config.bot_token}"}
        )
        self._running = True
        logger.info("Slack bot started")
        
    async def stop(self):
        """Stop the bot."""
        self._running = False
        if self._socket and not self._socket.closed:
            await self._socket.close()
        self._socket = None
        if self._session:
            await self._session.close()
            self._session = None
        logger.info("Slack bot stopped")

    async def _request_json(
        self,
        method: str,
        payload: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Perform a Slack Web API POST and return its JSON payload."""
        if not self._session:
            return None

        url = self.API_BASE.format(method=method)
        try:
            request = self._session.post(url, json=payload or {}, headers=headers)

            # Unit tests patch session.post to return a plain response-like mock.
            if hasattr(request, "json") and not asyncio.iscoroutine(request):
                return await request.json()

            if asyncio.iscoroutine(request):
                request = await request

            if hasattr(request, "json") and not hasattr(request, "__aenter__"):
                return await request.json()

            if hasattr(request, "__aenter__"):
                async with request as resp:
                    return await resp.json()

            return None
        except Exception as e:
            logger.error(f"Slack API request failed for {method}: {e}")
            return None
        
    async def send_message(
        self,
        channel: str,
        text: str,
        thread_ts: Optional[str] = None
    ) -> bool:
        """Send a message to a channel."""
        if not self._session:
            return False
            
        payload = {
            "channel": channel,
            "text": text
        }
        if thread_ts:
            payload["thread_ts"] = thread_ts
            
        result = await self._request_json("chat.postMessage", payload=payload)
        if result is None:
            return False
        return result.get("ok", False)

    async def get_auth_info(self) -> Optional[Dict[str, Any]]:
        """Resolve bot auth metadata such as user/team IDs."""
        if not self._session:
            return None
        return await self._request_json("auth.test")

    async def open_socket_mode_connection(self) -> bool:
        """Open a Slack Socket Mode websocket connection."""
        if not self._session or not self.config.app_token:
            return False

        result = await self._request_json(
            "apps.connections.open",
            headers={"Authorization": f"Bearer {self.config.app_token}"},
        )
        if not result or not result.get("ok"):
            logger.error(f"Failed to open Slack Socket Mode connection: {result}")
            return False

        socket_url = result.get("url")
        if not socket_url:
            logger.error("Slack Socket Mode response missing websocket URL")
            return False

        try:
            self._socket = await self._session.ws_connect(socket_url, heartbeat=30)
            logger.info("Slack Socket Mode connected")
            return True
        except Exception as e:
            logger.error(f"Failed to connect Slack websocket: {e}")
            self._socket = None
            return False

    async def _ack_socket_envelope(self, envelope_id: str) -> None:
        """Acknowledge a Socket Mode envelope."""
        if self._socket and not self._socket.closed:
            await self._socket.send_json({"envelope_id": envelope_id})

    async def process_socket_envelope(self, envelope: Dict[str, Any]) -> bool:
        """Process a Socket Mode envelope and dispatch events."""
        envelope_type = envelope.get("type")
        if envelope_type == "hello":
            return True
        if envelope_type == "disconnect":
            logger.warning(f"Slack Socket Mode disconnect received: {envelope}")
            return False

        envelope_id = envelope.get("envelope_id")
        if envelope_id:
            await self._ack_socket_envelope(envelope_id)

        if envelope_type == "events_api":
            payload = envelope.get("payload", {})
            for handler in self._event_handlers:
                await handler(payload)
        return True

    async def socket_mode_loop(self) -> None:
        """Run the Slack Socket Mode event loop until stopped."""
        if not self._running:
            await self.start()

        while self._running:
            if not self._socket or self._socket.closed:
                if not await self.open_socket_mode_connection():
                    await asyncio.sleep(self.config.socket_retry_delay)
                    continue

            try:
                message = await self._socket.receive()
                if message.type == aiohttp.WSMsgType.TEXT:
                    envelope = json.loads(message.data)
                    keep_running = await self.process_socket_envelope(envelope)
                    if not keep_running and self._socket:
                        await self._socket.close()
                        self._socket = None
                elif message.type in {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR}:
                    logger.warning("Slack websocket closed; reconnecting")
                    if self._socket and not self._socket.closed:
                        await self._socket.close()
                    self._socket = None
                    await asyncio.sleep(self.config.socket_retry_delay)
            except Exception as e:
                logger.error(f"Slack Socket Mode loop error: {e}")
                if self._socket and not self._socket.closed:
                    await self._socket.close()
                self._socket = None
                await asyncio.sleep(self.config.socket_retry_delay)
            
    def on_event(self, handler: Callable):
        """Register event handler."""
        self._event_handlers.append(handler)
