"""Telegram Bot - Telegram Bot API implementation.

Provides integration with Telegram Bot API for receiving and sending messages.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Callable
import asyncio
import aiohttp

from src.utils.logger import get_logger

logger = get_logger()


@dataclass
class TelegramConfig:
    """Configuration for Telegram Bot."""
    
    bot_token: str
    webhook_url: Optional[str] = None
    polling_interval: int = 1
    polling_timeout: int = 30
    allowed_updates: List[str] = None
    
    def __post_init__(self):
        if self.allowed_updates is None:
            self.allowed_updates = ["message", "callback_query"]


class TelegramBot:
    """Telegram Bot API client.
    
    Handles communication with Telegram Bot API for sending messages,
    receiving updates via webhooks or polling.
    """
    
    API_BASE = "https://api.telegram.org/bot{token}/{method}"
    
    def __init__(self, config: TelegramConfig):
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None
        self._running = False
        self._message_handlers: List[Callable] = []
        self._update_offset = 0
        
    async def start(self):
        """Start the bot."""
        if self._running and self._session and not self._session.closed:
            return
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()
        self._running = True
        logger.info("Telegram bot started")
        
    async def stop(self):
        """Stop the bot."""
        self._running = False
        if self._session:
            await self._session.close()
            self._session = None
        logger.info("Telegram bot stopped")
        
    async def send_message(
        self,
        chat_id: str,
        text: str,
        reply_to: Optional[str] = None,
        parse_mode: Optional[str] = "HTML"
    ) -> bool:
        """Send a text message."""
        if not self._session:
            return False
            
        url = self.API_BASE.format(token=self.config.bot_token, method="sendMessage")
        payload = {
            "chat_id": chat_id,
            "text": text,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_to:
            payload["reply_to_message_id"] = reply_to
            
        try:
            async with self._session.post(url, json=payload) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return False
            
    async def send_document(
        self,
        chat_id: str,
        file_bytes: bytes,
        filename: str,
        caption: str = "",
        parse_mode: str = "HTML",
        reply_to: Optional[str] = None,
    ) -> bool:
        """Send a file/document to a Telegram chat.

        Args:
            chat_id: Target chat identifier
            file_bytes: Raw file content
            filename: File name shown to the user
            caption: Optional caption (supports HTML/Markdown)
            parse_mode: Caption parse mode
            reply_to: Optional message id to reply to
        """
        if not self._session:
            return False

        url = self.API_BASE.format(token=self.config.bot_token, method="sendDocument")
        form = aiohttp.FormData()
        form.add_field("chat_id", str(chat_id))
        form.add_field("document", file_bytes, filename=filename,
                       content_type="application/octet-stream")
        if caption:
            form.add_field("caption", caption)
            form.add_field("parse_mode", parse_mode)
        if reply_to:
            form.add_field("reply_to_message_id", str(reply_to))

        try:
            async with self._session.post(url, data=form) as resp:
                ok = resp.status == 200
                if not ok:
                    body = await resp.text()
                    logger.error(f"send_document failed {resp.status}: {body[:200]}")
                return ok
        except Exception as e:
            logger.error(f"send_document exception: {e}")
            return False

    async def send_photo(
        self,
        chat_id: str,
        photo_bytes: bytes,
        caption: str = "",
        parse_mode: str = "HTML",
        reply_to: Optional[str] = None,
    ) -> bool:
        """Send a photo to a Telegram chat."""
        if not self._session:
            return False

        url = self.API_BASE.format(token=self.config.bot_token, method="sendPhoto")
        form = aiohttp.FormData()
        form.add_field("chat_id", str(chat_id))
        form.add_field("photo", photo_bytes, filename="image.png",
                       content_type="image/png")
        if caption:
            form.add_field("caption", caption)
            form.add_field("parse_mode", parse_mode)
        if reply_to:
            form.add_field("reply_to_message_id", str(reply_to))

        try:
            async with self._session.post(url, data=form) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(f"send_photo exception: {e}")
            return False

    async def send_voice(
        self,
        chat_id: str,
        voice_bytes: bytes,
        caption: str = "",
        duration: int = 0,
        reply_to: Optional[str] = None,
    ) -> bool:
        """Send a voice note (OGG/OPUS) to a Telegram chat."""
        if not self._session:
            return False

        url = self.API_BASE.format(token=self.config.bot_token, method="sendVoice")
        form = aiohttp.FormData()
        form.add_field("chat_id", str(chat_id))
        form.add_field("voice", voice_bytes, filename="voice.ogg",
                       content_type="audio/ogg")
        if caption:
            form.add_field("caption", caption)
        if duration:
            form.add_field("duration", str(duration))
        if reply_to:
            form.add_field("reply_to_message_id", str(reply_to))

        try:
            async with self._session.post(url, data=form) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(f"send_voice exception: {e}")
            return False

    async def get_file(self, file_id: str) -> Optional[bytes]:
        """Download a file from Telegram servers by file_id.

        Args:
            file_id: Telegram file identifier (from voice/document/photo updates)

        Returns:
            Raw file bytes or None on failure
        """
        if not self._session:
            return None

        # Step 1: resolve file_path
        url = self.API_BASE.format(token=self.config.bot_token, method="getFile")
        try:
            async with self._session.get(url, params={"file_id": file_id}) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                file_path = data.get("result", {}).get("file_path")
                if not file_path:
                    return None
        except Exception as e:
            logger.error(f"getFile failed: {e}")
            return None

        # Step 2: download content
        download_url = (
            f"https://api.telegram.org/file/bot{self.config.bot_token}/{file_path}"
        )
        try:
            async with self._session.get(download_url) as resp:
                if resp.status == 200:
                    return await resp.read()
                return None
        except Exception as e:
            logger.error(f"File download failed: {e}")
            return None

    async def send_action(self, chat_id: str, action: str = "typing") -> bool:
        """Show a chat action (typing, upload_document, etc.)."""
        if not self._session:
            return False
        url = self.API_BASE.format(token=self.config.bot_token, method="sendChatAction")
        try:
            async with self._session.post(url, json={"chat_id": chat_id, "action": action}) as resp:
                return resp.status == 200
        except Exception:
            return False

    def on_message(self, handler: Callable):
        """Register message handler."""
        self._message_handlers.append(handler)

    async def get_updates(
        self,
        offset: Optional[int] = None,
        timeout: Optional[int] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Fetch updates from Telegram using long polling."""
        if not self._session:
            return []

        url = self.API_BASE.format(token=self.config.bot_token, method="getUpdates")
        payload: Dict[str, Any] = {
            "timeout": timeout if timeout is not None else self.config.polling_timeout,
            "limit": limit,
            "allowed_updates": self.config.allowed_updates,
        }
        if offset is not None:
            payload["offset"] = offset

        try:
            async with self._session.get(url, params=payload) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error(f"get_updates failed {resp.status}: {body[:200]}")
                    return []

                data = await resp.json()
                if not data.get("ok"):
                    logger.error(f"get_updates returned non-ok payload: {data}")
                    return []
                return data.get("result", [])
        except Exception as e:
            logger.error(f"Failed to get updates: {e}")
            return []

    async def process_update(self, update: Dict[str, Any]) -> None:
        """Dispatch a single update to registered handlers."""
        for handler in self._message_handlers:
            try:
                await handler(update)
            except Exception as e:
                logger.error(f"Telegram message handler failed: {e}")

    async def poll_once(self, timeout: Optional[int] = None) -> int:
        """Fetch one long-poll batch and process received updates."""
        updates = await self.get_updates(offset=self._update_offset, timeout=timeout)
        next_offset = self._update_offset

        for update in updates:
            update_id = int(update.get("update_id", 0))
            next_offset = max(next_offset, update_id + 1)
            await self.process_update(update)

        self._update_offset = next_offset
        return next_offset

    async def poll_forever(self) -> None:
        """Run the long-poll loop until the bot is stopped."""
        if not self._running:
            await self.start()

        while self._running:
            await self.poll_once(timeout=self.config.polling_timeout)
            if self.config.polling_interval > 0:
                await asyncio.sleep(self.config.polling_interval)
