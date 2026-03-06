"""Unit tests for interfaces/message_adapter.py module.

This module tests the MessageAdapter base class and related classes
for platform message normalization.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.interfaces.message_adapter import (
    AdapterRegistry,
    Attachment,
    AttachmentType,
    MessageAdapter,
    PlatformMessage,
    PlatformResponse,
    PlatformType,
)
from src.engine.message import AgentContext, OctoMessage, MessageType


class TestAttachmentType:
    """Test AttachmentType enum."""
    
    def test_attachment_type_values(self):
        """Test that attachment types have correct values."""
        assert AttachmentType.TEXT == "text"
        assert AttachmentType.FILE == "file"
        assert AttachmentType.IMAGE == "image"
        assert AttachmentType.VOICE == "voice"
        assert AttachmentType.VIDEO == "video"
        assert AttachmentType.DOCUMENT == "document"
        assert AttachmentType.LOCATION == "location"
        assert AttachmentType.CONTACT == "contact"
        assert AttachmentType.STICKER == "sticker"


class TestPlatformType:
    """Test PlatformType enum."""
    
    def test_platform_type_values(self):
        """Test that platform types have correct values."""
        assert PlatformType.CLI == "cli"
        assert PlatformType.TELEGRAM == "telegram"
        assert PlatformType.SLACK == "slack"
        assert PlatformType.WHATSAPP == "whatsapp"
        assert PlatformType.DISCORD == "discord"
        assert PlatformType.EMAIL == "email"
        assert PlatformType.WEB == "web"
        assert PlatformType.VOICE == "voice"


class TestAttachment:
    """Test Attachment dataclass."""
    
    def test_create_attachment(self):
        """Test creating an attachment."""
        content = b"test content"
        attachment = Attachment(
            type=AttachmentType.FILE,
            content=content,
            filename="test.txt",
            mime_type="text/plain",
            size_bytes=len(content)
        )
        
        assert attachment.type == AttachmentType.FILE
        assert attachment.content == content
        assert attachment.filename == "test.txt"
        assert attachment.mime_type == "text/plain"
        assert attachment.size_bytes == len(content)
    
    def test_attachment_with_optional_fields(self):
        """Test creating attachment with optional fields."""
        attachment = Attachment(
            type=AttachmentType.IMAGE,
            content=b"image data",
            filename="photo.jpg",
            mime_type="image/jpeg",
            size_bytes=1024,
            caption="A beautiful photo",
            dimensions=(1920, 1080),
            url="https://example.com/photo.jpg"
        )
        
        assert attachment.caption == "A beautiful photo"
        assert attachment.dimensions == (1920, 1080)
        assert attachment.url == "https://example.com/photo.jpg"
    
    def test_attachment_defaults(self):
        """Test attachment default values."""
        attachment = Attachment(
            type=AttachmentType.TEXT,
            content=b"text"
        )
        
        assert attachment.filename is None
        assert attachment.mime_type == "application/octet-stream"
        assert attachment.size_bytes == 0
        assert attachment.metadata == {}
        assert attachment.caption is None
        assert attachment.duration_seconds is None
        assert attachment.dimensions is None
        assert attachment.location_lat is None
        assert attachment.location_lon is None


class TestPlatformMessage:
    """Test PlatformMessage dataclass."""
    
    def test_create_platform_message(self):
        """Test creating a platform message."""
        msg = PlatformMessage(
            message_id="msg_123",
            platform=PlatformType.TELEGRAM,
            user_id="user_456",
            user_name="testuser",
            content="Hello, world!",
            chat_id="chat_789"
        )
        
        assert msg.message_id == "msg_123"
        assert msg.platform == PlatformType.TELEGRAM
        assert msg.user_id == "user_456"
        assert msg.user_name == "testuser"
        assert msg.content == "Hello, world!"
        assert msg.chat_id == "chat_789"
    
    def test_platform_message_defaults(self):
        """Test PlatformMessage default values."""
        msg = PlatformMessage(
            message_id="msg_1",
            platform=PlatformType.SLACK,
            user_id="user_1"
        )
        
        assert msg.content == ""
        assert msg.content_type == "text"
        assert msg.attachments == []
        assert msg.chat_type == "private"
        assert msg.command_args == []
        assert msg.is_command is False
        assert msg.is_forwarded is False
        assert msg.metadata == {}
        assert msg.user_display_name is None
        assert msg.reply_to_message_id is None
        assert msg.thread_id is None
        assert msg.edited_at is None
        assert msg.raw_data is None


class TestPlatformResponse:
    """Test PlatformResponse dataclass."""
    
    def test_create_platform_response(self):
        """Test creating a platform response."""
        response = PlatformResponse(
            target_chat_id="chat_123",
            content="Response message",
            reply_to_message_id="msg_456",
            parse_mode="HTML"
        )
        
        assert response.target_chat_id == "chat_123"
        assert response.content == "Response message"
        assert response.reply_to_message_id == "msg_456"
        assert response.parse_mode == "HTML"
    
    def test_platform_response_defaults(self):
        """Test PlatformResponse default values."""
        response = PlatformResponse(
            target_chat_id="chat_1",
            content="Hello"
        )
        
        assert response.attachments == []
        assert response.parse_mode is None
        assert response.disable_notification is False
        assert response.buttons == []
        assert response.metadata == {}
        assert response.reply_to_message_id is None


class ConcreteMessageAdapter(MessageAdapter):
    """Concrete implementation of MessageAdapter for testing."""
    
    def normalize_message(self, raw_message):
        return PlatformMessage(
            message_id="test",
            platform=self.platform,
            user_id="user_1"
        )
    
    def to_octomessage(self, platform_message):
        return OctoMessage(
            sender="test_adapter",
            receiver="mainbrain",
            type=MessageType.TASK,
            payload=None
        )
    
    def from_octomessage(self, octo_message):
        return PlatformResponse(
            target_chat_id="chat_1",
            content="Response"
        )
    
    async def send_response(self, response):
        return True


class TestMessageAdapter:
    """Test MessageAdapter base class."""
    
    def test_adapter_initialization(self):
        """Test adapter initialization."""
        context = AgentContext(
            workspace_path="/tmp/test",
            session_id=uuid4(),
            user_id="test_user"
        )
        
        adapter = ConcreteMessageAdapter(
            platform=PlatformType.TELEGRAM,
            context=context
        )
        
        assert adapter.platform == PlatformType.TELEGRAM
        assert adapter.context == context
        assert adapter._message_count == 0
        assert adapter._error_count == 0
    
    def test_adapter_initialization_default_context(self):
        """Test adapter initialization with default context."""
        adapter = ConcreteMessageAdapter(platform=PlatformType.SLACK)
        
        assert adapter.platform == PlatformType.SLACK
        assert adapter.context is not None
        assert isinstance(adapter.context, AgentContext)
    
    def test_handle_file_upload(self):
        """Test handling file uploads."""
        adapter = ConcreteMessageAdapter(platform=PlatformType.TELEGRAM)
        
        file_data = b"file contents"
        attachment = adapter.handle_file_upload(
            file_data=file_data,
            filename="document.pdf",
            mime_type="application/pdf"
        )
        
        assert attachment.type == AttachmentType.DOCUMENT
        assert attachment.content == file_data
        assert attachment.filename == "document.pdf"
        assert attachment.mime_type == "application/pdf"
        assert attachment.size_bytes == len(file_data)
    
    def test_handle_voice_message(self):
        """Test handling voice messages."""
        adapter = ConcreteMessageAdapter(platform=PlatformType.TELEGRAM)
        
        voice_data = b"audio data"
        attachment = adapter.handle_voice_message(
            voice_data=voice_data,
            duration=15.5,
            mime_type="audio/ogg"
        )
        
        assert attachment.type == AttachmentType.VOICE
        assert attachment.content == voice_data
        assert attachment.duration_seconds == 15.5
        assert attachment.mime_type == "audio/ogg"
    
    def test_handle_image(self):
        """Test handling image uploads."""
        adapter = ConcreteMessageAdapter(platform=PlatformType.TELEGRAM)
        
        image_data = b"image data"
        attachment = adapter.handle_image(
            image_data=image_data,
            filename="photo.jpg",
            caption="Nice photo",
            dimensions=(1920, 1080),
            mime_type="image/jpeg"
        )
        
        assert attachment.type == AttachmentType.IMAGE
        assert attachment.content == image_data
        assert attachment.filename == "photo.jpg"
        assert attachment.caption == "Nice photo"
        assert attachment.dimensions == (1920, 1080)
    
    def test_handle_image_default_filename(self):
        """Test handling image with default filename."""
        adapter = ConcreteMessageAdapter(platform=PlatformType.SLACK)
        
        attachment = adapter.handle_image(
            image_data=b"img",
            mime_type="image/png"
        )
        
        assert attachment.filename.startswith("image_")
        assert attachment.filename.endswith(".jpg")
    
    def test_parse_command_with_args(self):
        """Test parsing command with arguments."""
        adapter = ConcreteMessageAdapter(platform=PlatformType.TELEGRAM)
        
        is_command, command, args = adapter.parse_command("/start arg1 arg2")
        
        assert is_command is True
        assert command == "start"
        assert args == ["arg1", "arg2"]
    
    def test_parse_command_without_args(self):
        """Test parsing command without arguments."""
        adapter = ConcreteMessageAdapter(platform=PlatformType.TELEGRAM)
        
        is_command, command, args = adapter.parse_command("/help")
        
        assert is_command is True
        assert command == "help"
        assert args == []
    
    def test_parse_command_not_a_command(self):
        """Test parsing non-command text."""
        adapter = ConcreteMessageAdapter(platform=PlatformType.TELEGRAM)
        
        is_command, command, args = adapter.parse_command("Hello, world!")
        
        assert is_command is False
        assert command is None
        assert args == []
    
    def test_parse_command_empty_message(self):
        """Test parsing empty message."""
        adapter = ConcreteMessageAdapter(platform=PlatformType.TELEGRAM)
        
        is_command, command, args = adapter.parse_command("")
        
        assert is_command is False
        assert command is None
        assert args == []
    
    def test_parse_command_just_slash(self):
        """Test parsing message with just a slash."""
        adapter = ConcreteMessageAdapter(platform=PlatformType.TELEGRAM)
        
        is_command, command, args = adapter.parse_command("/")
        
        assert is_command is False
        assert command is None
        assert args == []
    
    def test_detect_attachment_type_image(self):
        """Test detecting image attachment types."""
        adapter = ConcreteMessageAdapter(platform=PlatformType.TELEGRAM)
        
        # By MIME type
        assert adapter._detect_attachment_type("image/jpeg", "file.jpg") == AttachmentType.IMAGE
        assert adapter._detect_attachment_type("image/png", "file.png") == AttachmentType.IMAGE
        
        # By extension
        assert adapter._detect_attachment_type("application/octet-stream", "photo.gif") == AttachmentType.IMAGE
        assert adapter._detect_attachment_type("binary/data", "image.webp") == AttachmentType.IMAGE
    
    def test_detect_attachment_type_video(self):
        """Test detecting video attachment types."""
        adapter = ConcreteMessageAdapter(platform=PlatformType.TELEGRAM)
        
        assert adapter._detect_attachment_type("video/mp4", "file.mp4") == AttachmentType.VIDEO
        assert adapter._detect_attachment_type("binary/data", "movie.mov") == AttachmentType.VIDEO
    
    def test_detect_attachment_type_voice(self):
        """Test detecting voice/audio attachment types."""
        adapter = ConcreteMessageAdapter(platform=PlatformType.TELEGRAM)
        
        assert adapter._detect_attachment_type("audio/mpeg", "file.mp3") == AttachmentType.VOICE
        assert adapter._detect_attachment_type("binary/data", "sound.wav") == AttachmentType.VOICE
    
    def test_detect_attachment_type_document(self):
        """Test detecting document attachment types."""
        adapter = ConcreteMessageAdapter(platform=PlatformType.TELEGRAM)
        
        assert adapter._detect_attachment_type("application/pdf", "doc.pdf") == AttachmentType.DOCUMENT
        assert adapter._detect_attachment_type("text/plain", "notes.txt") == AttachmentType.DOCUMENT
        assert adapter._detect_attachment_type("binary/data", "sheet.xlsx") == AttachmentType.DOCUMENT
    
    def test_detect_attachment_type_file_default(self):
        """Test default attachment type is FILE."""
        adapter = ConcreteMessageAdapter(platform=PlatformType.TELEGRAM)
        
        assert adapter._detect_attachment_type("binary/data", "unknown.xyz") == AttachmentType.FILE
    
    def test_get_stats(self):
        """Test getting adapter statistics."""
        context = AgentContext(
            workspace_path="/tmp/test",
            session_id=uuid4(),
            user_id="test_user"
        )
        adapter = ConcreteMessageAdapter(
            platform=PlatformType.TELEGRAM,
            context=context
        )
        
        stats = adapter.get_stats()
        
        assert stats["platform"] == "telegram"
        assert stats["messages_processed"] == 0
        assert stats["errors"] == 0
        assert stats["context"]["workspace"] == "/tmp/test"
        assert stats["context"]["user_id"] == "test_user"


class TestAdapterRegistry:
    """Test AdapterRegistry class."""
    
    def test_registry_initialization(self):
        """Test registry initialization."""
        registry = AdapterRegistry()
        
        # Private attribute should exist
        assert hasattr(registry, '_adapters')
    
    def test_register_adapter(self):
        """Test registering an adapter."""
        registry = AdapterRegistry()
        adapter = ConcreteMessageAdapter(platform=PlatformType.TELEGRAM)
        
        result = registry.register_adapter(adapter)
        
        assert result is True
        assert registry._adapters[PlatformType.TELEGRAM] == adapter
    
    def test_register_multiple_adapters(self):
        """Test registering multiple adapters."""
        registry = AdapterRegistry()
        telegram_adapter = ConcreteMessageAdapter(platform=PlatformType.TELEGRAM)
        slack_adapter = ConcreteMessageAdapter(platform=PlatformType.SLACK)
        
        registry.register_adapter(telegram_adapter)
        registry.register_adapter(slack_adapter)
        
        assert registry._adapters[PlatformType.TELEGRAM] == telegram_adapter
        assert registry._adapters[PlatformType.SLACK] == slack_adapter
    
    def test_get_adapter(self):
        """Test getting an adapter by platform type."""
        registry = AdapterRegistry()
        adapter = ConcreteMessageAdapter(platform=PlatformType.TELEGRAM)
        registry.register_adapter(adapter)
        
        retrieved = registry.get_adapter(PlatformType.TELEGRAM)
        
        assert retrieved == adapter
    
    def test_get_adapter_not_found(self):
        """Test getting a non-existent adapter."""
        registry = AdapterRegistry()
        
        retrieved = registry.get_adapter(PlatformType.WHATSAPP)
        
        assert retrieved is None
    
    def test_unregister_adapter(self):
        """Test unregistering an adapter."""
        registry = AdapterRegistry()
        adapter = ConcreteMessageAdapter(platform=PlatformType.TELEGRAM)
        registry.register_adapter(adapter)
        
        result = registry.unregister_adapter(PlatformType.TELEGRAM)
        
        assert result is True
        assert PlatformType.TELEGRAM not in registry._adapters
    
    def test_unregister_nonexistent_adapter(self):
        """Test unregistering a non-existent adapter."""
        registry = AdapterRegistry()
        
        result = registry.unregister_adapter(PlatformType.DISCORD)
        
        assert result is False
    
    def test_get_all_adapters(self):
        """Test getting all registered adapters."""
        registry = AdapterRegistry()
        telegram_adapter = ConcreteMessageAdapter(platform=PlatformType.TELEGRAM)
        slack_adapter = ConcreteMessageAdapter(platform=PlatformType.SLACK)
        
        registry.register_adapter(telegram_adapter)
        registry.register_adapter(slack_adapter)
        
        adapters = registry.get_all_adapters()
        
        assert len(adapters) == 2
        assert telegram_adapter in adapters
        assert slack_adapter in adapters
    
    def test_get_all_adapters_empty(self):
        """Test getting adapters when none registered."""
        registry = AdapterRegistry()
        
        adapters = registry.get_all_adapters()
        
        assert adapters == []
    
    def test_get_supported_platforms(self):
        """Test getting list of supported platforms."""
        registry = AdapterRegistry()
        telegram_adapter = ConcreteMessageAdapter(platform=PlatformType.TELEGRAM)
        slack_adapter = ConcreteMessageAdapter(platform=PlatformType.SLACK)
        
        registry.register_adapter(telegram_adapter)
        registry.register_adapter(slack_adapter)
        
        platforms = registry.get_supported_platforms()
        
        assert len(platforms) == 2
        assert PlatformType.TELEGRAM in platforms
        assert PlatformType.SLACK in platforms
    
    def test_is_supported(self):
        """Test checking if platform is supported."""
        registry = AdapterRegistry()
        telegram_adapter = ConcreteMessageAdapter(platform=PlatformType.TELEGRAM)
        registry.register_adapter(telegram_adapter)
        
        assert registry.is_supported(PlatformType.TELEGRAM) is True
        assert registry.is_supported(PlatformType.SLACK) is False
