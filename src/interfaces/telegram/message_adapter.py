"""Telegram Message Adapter - Converts Telegram messages to OctoMessage format."""

from typing import Any, Dict, Optional
from src.interfaces.message_adapter import (
    MessageAdapter, PlatformMessage, PlatformResponse, 
    PlatformType, Attachment, AttachmentType, OctoMessage, MessageType
)
from src.utils.logger import get_logger

logger = get_logger()


class TelegramAdapter(MessageAdapter):
    """Adapter for Telegram messages."""
    
    def __init__(self, context=None):
        super().__init__(PlatformType.TELEGRAM, context)
        
    def normalize_message(self, raw_message: Dict[str, Any]) -> PlatformMessage:
        """Convert Telegram message to PlatformMessage."""
        msg = raw_message.get("message", raw_message)
        
        chat = msg.get("chat", {})
        from_user = msg.get("from", {})
        
        # Extract content
        content = msg.get("text", "")
        is_command = content.startswith("/")
        command_name = None
        command_args = []
        
        if is_command:
            parts = content[1:].split()
            command_name = parts[0] if parts else None
            command_args = parts[1:] if len(parts) > 1 else []
        
        # Handle attachments
        attachments = []
        if "photo" in msg:
            attachments.append(Attachment(
                type=AttachmentType.IMAGE,
                content=b"",  # Would download actual image
                filename=f"photo_{msg.get('message_id')}.jpg",
                mime_type="image/jpeg"
            ))
        
        if "voice" in msg:
            attachments.append(Attachment(
                type=AttachmentType.VOICE,
                content=b"",
                filename="voice.ogg",
                mime_type="audio/ogg",
                duration_seconds=msg["voice"].get("duration")
            ))
        
        return PlatformMessage(
            message_id=str(msg.get("message_id", "")),
            platform=PlatformType.TELEGRAM,
            user_id=str(from_user.get("id", "")),
            user_name=from_user.get("username"),
            user_display_name=f"{from_user.get('first_name', '')} {from_user.get('last_name', '')}".strip(),
            content=content,
            content_type="command" if is_command else "text",
            attachments=attachments,
            chat_id=str(chat.get("id", "")),
            chat_type=chat.get("type", "private"),
            reply_to_message_id=str(msg.get("reply_to_message", {}).get("message_id")) if msg.get("reply_to_message") else None,
            is_command=is_command,
            command_name=command_name,
            command_args=command_args,
            raw_data=raw_message
        )
    
    def to_octomessage(self, platform_message: PlatformMessage) -> OctoMessage:
        """Convert PlatformMessage to OctoMessage."""
        return OctoMessage(
            sender=f"telegram_user_{platform_message.user_id}",
            receiver="Orchestrator",
            type=MessageType.CHAT if not platform_message.is_command else MessageType.TASK,
            payload={
                "content": platform_message.content,
                "user_id": platform_message.user_id,
                "chat_id": platform_message.chat_id,
                "is_command": platform_message.is_command,
                "command_name": platform_message.command_name,
                "command_args": platform_message.command_args
            },
            context=self.context
        )
    
    def from_octomessage(self, octo_message: OctoMessage) -> PlatformResponse:
        """Convert OctoMessage to PlatformResponse."""
        payload = octo_message.payload if isinstance(octo_message.payload, dict) else {}
        
        return PlatformResponse(
            target_chat_id=payload.get("chat_id", ""),
            content=payload.get("content", ""),
            reply_to_message_id=payload.get("reply_to_message_id"),
            parse_mode="HTML"
        )
    
    async def send_response(self, response: PlatformResponse) -> bool:
        """Send response via Telegram."""
        # Would integrate with TelegramBot here
        logger.info(f"Sending Telegram response to {response.target_chat_id}")
        return True
