"""Slack Message Adapter - Converts Slack messages to OctoMessage format."""

from typing import Any, Dict, Optional
from src.interfaces.message_adapter import (
    MessageAdapter, PlatformMessage, PlatformResponse, 
    PlatformType, Attachment, AttachmentType, OctoMessage, MessageType
)
from src.utils.logger import get_logger

logger = get_logger()


class SlackAdapter(MessageAdapter):
    """Adapter for Slack messages."""
    
    def __init__(self, context=None):
        super().__init__(PlatformType.SLACK, context)
        
    def normalize_message(self, raw_message: Dict[str, Any]) -> PlatformMessage:
        """Convert Slack event to PlatformMessage."""
        event = raw_message.get("event", raw_message)
        
        content = event.get("text", "")
        is_command = content.startswith("/")
        command_name = None
        command_args = []
        
        if is_command:
            parts = content.split()
            command_name = parts[0][1:] if parts else None
            command_args = parts[1:] if len(parts) > 1 else []
        
        # Handle files
        attachments = []
        if "files" in event:
            for f in event["files"]:
                att_type = AttachmentType.IMAGE if f.get("mimetype", "").startswith("image/") else AttachmentType.FILE
                attachments.append(Attachment(
                    type=att_type,
                    content=b"",
                    filename=f.get("name", "file"),
                    mime_type=f.get("mimetype", "application/octet-stream"),
                    url=f.get("url_private")
                ))
        
        return PlatformMessage(
            message_id=event.get("ts", ""),
            platform=PlatformType.SLACK,
            user_id=event.get("user", ""),
            user_name=event.get("username"),
            content=content,
            content_type="command" if is_command else "text",
            attachments=attachments,
            chat_id=event.get("channel", ""),
            chat_type="channel" if event.get("channel", "").startswith("C") else "private",
            thread_id=event.get("thread_ts"),
            reply_to_message_id=event.get("thread_ts"),
            is_command=is_command,
            command_name=command_name,
            command_args=command_args,
            raw_data=raw_message
        )
    
    def to_octomessage(self, platform_message: PlatformMessage) -> OctoMessage:
        """Convert PlatformMessage to OctoMessage."""
        return OctoMessage(
            sender=f"slack_user_{platform_message.user_id}",
            receiver="Orchestrator",
            type=MessageType.CHAT if not platform_message.is_command else MessageType.TASK,
            payload={
                "content": platform_message.content,
                "user_id": platform_message.user_id,
                "channel": platform_message.chat_id,
                "is_command": platform_message.is_command
            },
            context=self.context
        )
    
    def from_octomessage(self, octo_message: OctoMessage) -> PlatformResponse:
        """Convert OctoMessage to PlatformResponse."""
        payload = octo_message.payload if isinstance(octo_message.payload, dict) else {}
        return PlatformResponse(
            target_chat_id=payload.get("channel", ""),
            content=payload.get("content", ""),
            reply_to_message_id=payload.get("thread_ts")
        )
    
    async def send_response(self, response: PlatformResponse) -> bool:
        """Send response via Slack."""
        logger.info(f"Sending Slack response to {response.target_chat_id}")
        return True
