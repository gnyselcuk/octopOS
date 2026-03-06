"""WhatsApp Message Adapter."""

from typing import Any, Dict, Optional
from src.interfaces.message_adapter import (
    MessageAdapter, PlatformMessage, PlatformResponse, 
    PlatformType, Attachment, AttachmentType, OctoMessage, MessageType
)
from src.utils.logger import get_logger

logger = get_logger()


class WhatsAppAdapter(MessageAdapter):
    """Adapter for WhatsApp Business API messages."""
    
    def __init__(self, context=None):
        super().__init__(PlatformType.WHATSAPP, context)
        
    def normalize_message(self, raw_message: Dict[str, Any]) -> PlatformMessage:
        """Convert WhatsApp webhook to PlatformMessage."""
        entry = raw_message.get("entry", [{}])[0]
        change = entry.get("changes", [{}])[0]
        value = change.get("value", {})
        message = value.get("messages", [{}])[0]
        contact = value.get("contacts", [{}])[0]
        
        # Extract text
        text = ""
        msg_type = message.get("type", "text")
        if msg_type == "text":
            text = message.get("text", {}).get("body", "")
        elif msg_type == "image":
            text = message.get("image", {}).get("caption", "")
        elif msg_type == "voice":
            text = "[Voice message]"
        
        # Handle attachments
        attachments = []
        if msg_type == "image":
            attachments.append(Attachment(
                type=AttachmentType.IMAGE,
                content=b"",
                filename=f"image_{message.get('id')}.jpg",
                mime_type="image/jpeg",
                caption=text
            ))
        elif msg_type == "voice":
            attachments.append(Attachment(
                type=AttachmentType.VOICE,
                content=b"",
                filename="voice.ogg",
                mime_type="audio/ogg",
                duration_seconds=message.get("voice", {}).get("seconds")
            ))
        
        return PlatformMessage(
            message_id=message.get("id", ""),
            platform=PlatformType.WHATSAPP,
            user_id=message.get("from", ""),
            user_name=contact.get("profile", {}).get("name"),
            user_display_name=contact.get("profile", {}).get("name"),
            content=text,
            attachments=attachments,
            chat_id=message.get("from", ""),  # WhatsApp uses phone number as chat_id
            chat_type="private",
            raw_data=raw_message
        )
    
    def to_octomessage(self, platform_message: PlatformMessage) -> OctoMessage:
        """Convert PlatformMessage to OctoMessage."""
        return OctoMessage(
            sender=f"whatsapp_user_{platform_message.user_id}",
            receiver="Orchestrator",
            type=MessageType.CHAT,
            payload={
                "content": platform_message.content,
                "user_id": platform_message.user_id,
                "phone": platform_message.chat_id
            },
            context=self.context
        )
    
    def from_octomessage(self, octo_message: OctoMessage) -> PlatformResponse:
        """Convert OctoMessage to PlatformResponse."""
        payload = octo_message.payload if isinstance(octo_message.payload, dict) else {}
        return PlatformResponse(
            target_chat_id=payload.get("phone", ""),
            content=payload.get("content", "")
        )
    
    async def send_response(self, response: PlatformResponse) -> bool:
        """Send response via WhatsApp."""
        logger.info(f"Sending WhatsApp response to {response.target_chat_id}")
        return True
