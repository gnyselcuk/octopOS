"""Message Adapter - Unified interface for multi-channel communication.

This module provides the base message adapter that normalizes messages
from different platforms (Telegram, Slack, WhatsApp) into the OctoMessage
format. Supports text, files, images, voice, and documents.

Example:
    >>> from src.interfaces import MessageAdapter, PlatformMessage
    >>> adapter = MyPlatformAdapter(platform="telegram")
    >>> normalized = adapter.normalize_message(raw_telegram_message)
    >>> adapter.send_response(response_message)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from uuid import UUID, uuid4

from src.engine.message import AgentContext, MessageType, OctoMessage
from src.utils.logger import get_logger

logger = get_logger()


class AttachmentType(str, Enum):
    """Types of message attachments."""
    
    TEXT = "text"              # Plain text
    FILE = "file"              # Generic file
    IMAGE = "image"            # Image (jpg, png, gif, etc.)
    VOICE = "voice"            # Voice message/audio
    VIDEO = "video"            # Video file
    DOCUMENT = "document"      # Document (pdf, doc, etc.)
    LOCATION = "location"      # Geographic location
    CONTACT = "contact"        # Contact card
    STICKER = "sticker"        # Sticker/emoji


class PlatformType(str, Enum):
    """Supported messaging platforms."""
    
    CLI = "cli"                # Command Line Interface
    TELEGRAM = "telegram"      # Telegram
    SLACK = "slack"            # Slack
    WHATSAPP = "whatsapp"      # WhatsApp
    DISCORD = "discord"        # Discord
    EMAIL = "email"            # Email
    WEB = "web"                # Web UI
    VOICE = "voice"            # Voice interface (Nova Sonic)


@dataclass
class Attachment:
    """A message attachment."""
    
    type: AttachmentType
    content: bytes
    filename: Optional[str] = None
    mime_type: str = "application/octet-stream"
    size_bytes: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # For specific types
    url: Optional[str] = None           # External URL
    caption: Optional[str] = None        # Image/document caption
    duration_seconds: Optional[float] = None  # Voice/video duration
    dimensions: Optional[tuple] = None  # Image/video dimensions (width, height)
    location_lat: Optional[float] = None  # Location latitude
    location_lon: Optional[float] = None  # Location longitude


@dataclass
class PlatformMessage:
    """Normalized message from any platform.
    
    This is the intermediate format that all platform-specific
    messages are converted to before being processed by octopOS.
    """
    
    # Identifiers
    message_id: str
    platform: PlatformType
    user_id: str
    user_name: Optional[str] = None
    user_display_name: Optional[str] = None
    
    # Content
    content: str = ""
    content_type: str = "text"  # text, command, system
    
    # Attachments
    attachments: List[Attachment] = field(default_factory=list)
    
    # Context
    chat_id: Optional[str] = None
    chat_type: str = "private"  # private, group, channel
    thread_id: Optional[str] = None
    reply_to_message_id: Optional[str] = None
    
    # Timestamps
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    edited_at: Optional[str] = None
    
    # Metadata
    is_command: bool = False
    command_name: Optional[str] = None
    command_args: List[str] = field(default_factory=list)
    is_forwarded: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Platform-specific (for debugging)
    raw_data: Optional[Dict[str, Any]] = None


@dataclass
class PlatformResponse:
    """Response to be sent to a platform."""
    
    target_chat_id: str
    content: str
    reply_to_message_id: Optional[str] = None
    
    # Attachments to send
    attachments: List[Attachment] = field(default_factory=list)
    
    # Options
    parse_mode: Optional[str] = None  # HTML, Markdown, etc.
    disable_notification: bool = False
    buttons: List[Dict[str, Any]] = field(default_factory=list)  # Inline buttons
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)


class MessageAdapter(ABC):
    """Abstract base class for platform message adapters.
    
    All platform-specific adapters (Telegram, Slack, WhatsApp)
    must inherit from this class and implement the required methods.
    
    The adapter serves as a bridge between platform-specific APIs
    and the octopOS internal OctoMessage protocol.
    
    Attributes:
        platform: The PlatformType this adapter handles
        context: AgentContext shared across adapters
    
    Example:
        >>> class TelegramAdapter(MessageAdapter):
        ...     def __init__(self):
        ...         super().__init__(PlatformType.TELEGRAM)
        ...     
        ...     def normalize_message(self, raw_message):
        ...         # Convert Telegram message to PlatformMessage
        ...         pass
    """
    
    def __init__(
        self,
        platform: PlatformType,
        context: Optional[AgentContext] = None
    ) -> None:
        """Initialize the message adapter.
        
        Args:
            platform: The platform type this adapter handles
            context: Shared agent context
        """
        self.platform = platform
        self.context = context or AgentContext()
        self._logger = logger
        
        self._message_count = 0
        self._error_count = 0
        
        self._logger.info(f"MessageAdapter initialized for {platform.value}")
    
    @abstractmethod
    def normalize_message(self, raw_message: Dict[str, Any]) -> PlatformMessage:
        """Convert platform-specific message to PlatformMessage.
        
        This method must be implemented by each platform adapter
        to extract relevant information from the raw platform message
        and create a normalized PlatformMessage.
        
        Args:
            raw_message: Raw message from platform API/webhook
            
        Returns:
            Normalized PlatformMessage
        """
        raise NotImplementedError("Subclasses must implement normalize_message()")
    
    @abstractmethod
    def to_octomessage(self, platform_message: PlatformMessage) -> OctoMessage:
        """Convert PlatformMessage to OctoMessage.
        
        Creates an OctoMessage that can be processed by octopOS agents.
        
        Args:
            platform_message: Normalized platform message
            
        Returns:
            OctoMessage for internal processing
        """
        raise NotImplementedError("Subclasses must implement to_octomessage()")
    
    @abstractmethod
    def from_octomessage(self, octo_message: OctoMessage) -> PlatformResponse:
        """Convert OctoMessage to PlatformResponse.
        
        Creates a platform-specific response from an OctoMessage.
        
        Args:
            octo_message: Internal octopOS message
            
        Returns:
            PlatformResponse ready to send
        """
        raise NotImplementedError("Subclasses must implement from_octomessage()")
    
    @abstractmethod
    async def send_response(self, response: PlatformResponse) -> bool:
        """Send a response to the platform.
        
        Args:
            response: Response to send
            
        Returns:
            True if sent successfully
        """
        raise NotImplementedError("Subclasses must implement send_response()")
    
    def handle_file_upload(
        self,
        file_data: bytes,
        filename: str,
        mime_type: str
    ) -> Attachment:
        """Handle a file upload from the platform.
        
        Args:
            file_data: Raw file bytes
            filename: Original filename
            mime_type: MIME type of file
            
        Returns:
            Attachment object
        """
        # Determine attachment type from mime type
        attachment_type = self._detect_attachment_type(mime_type, filename)
        
        attachment = Attachment(
            type=attachment_type,
            content=file_data,
            filename=filename,
            mime_type=mime_type,
            size_bytes=len(file_data)
        )
        
        self._logger.info(f"Handled file upload: {filename} ({attachment_type.value})")
        
        return attachment
    
    def handle_voice_message(
        self,
        voice_data: bytes,
        duration: Optional[float] = None,
        mime_type: str = "audio/ogg"
    ) -> Attachment:
        """Handle a voice message from the platform.
        
        Args:
            voice_data: Raw audio bytes
            duration: Duration in seconds (if available)
            mime_type: MIME type of audio
            
        Returns:
            Voice attachment
        """
        attachment = Attachment(
            type=AttachmentType.VOICE,
            content=voice_data,
            mime_type=mime_type,
            size_bytes=len(voice_data),
            duration_seconds=duration
        )
        
        self._logger.info(f"Handled voice message: {len(voice_data)} bytes")
        
        return attachment
    
    def handle_image(
        self,
        image_data: bytes,
        filename: Optional[str] = None,
        caption: Optional[str] = None,
        dimensions: Optional[tuple] = None,
        mime_type: str = "image/jpeg"
    ) -> Attachment:
        """Handle an image upload from the platform.
        
        Args:
            image_data: Raw image bytes
            filename: Original filename
            caption: Image caption (if any)
            dimensions: (width, height) tuple
            mime_type: MIME type of image
            
        Returns:
            Image attachment
        """
        attachment = Attachment(
            type=AttachmentType.IMAGE,
            content=image_data,
            filename=filename or f"image_{uuid4().hex[:8]}.jpg",
            mime_type=mime_type,
            size_bytes=len(image_data),
            caption=caption,
            dimensions=dimensions
        )
        
        self._logger.info(f"Handled image: {filename or 'unnamed'} ({len(image_data)} bytes)")
        
        return attachment
    
    def parse_command(self, text: str) -> tuple:
        """Parse command from message text.
        
        Args:
            text: Message text
            
        Returns:
            Tuple of (is_command, command_name, command_args)
        """
        text = text.strip()
        
        # Check if message starts with command prefix
        if not text.startswith('/'):
            return (False, None, [])
        
        # Split into command and args
        parts = text[1:].split()
        
        if not parts:
            return (False, None, [])
        
        command = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        
        return (True, command, args)
    
    def _detect_attachment_type(self, mime_type: str, filename: str) -> AttachmentType:
        """Detect attachment type from MIME type and filename.
        
        Args:
            mime_type: MIME type
            filename: Filename
            
        Returns:
            AttachmentType
        """
        mime_type = mime_type.lower()
        filename = filename.lower()
        
        # Image types
        if mime_type.startswith('image/') or any(ext in filename for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg']):
            return AttachmentType.IMAGE
        
        # Video types
        if mime_type.startswith('video/') or any(ext in filename for ext in ['.mp4', '.avi', '.mov', '.mkv', '.webm']):
            return AttachmentType.VIDEO
        
        # Audio types
        if mime_type.startswith('audio/') or any(ext in filename for ext in ['.mp3', '.wav', '.ogg', '.m4a']):
            return AttachmentType.VOICE
        
        # Document types
        if any(ext in filename for ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.csv']):
            return AttachmentType.DOCUMENT
        
        # Default to file
        return AttachmentType.FILE
    
    def get_stats(self) -> Dict[str, Any]:
        """Get adapter statistics.
        
        Returns:
            Statistics dictionary
        """
        return {
            "platform": self.platform.value,
            "messages_processed": self._message_count,
            "errors": self._error_count,
            "context": {
                "workspace": self.context.workspace_path,
                "session_id": str(self.context.session_id),
                "user_id": self.context.user_id
            }
        }


class AdapterRegistry:
    """Registry for managing multiple message adapters.
    
    Provides a central registry for all platform adapters, allowing
dynamic lookup and message routing.
    
    Example:
        >>> registry = AdapterRegistry()
        >>> registry.register_adapter(telegram_adapter)
        >>> 
        >>> # Get adapter for platform
        >>> adapter = registry.get_adapter(PlatformType.TELEGRAM)
        >>> 
        >>> # Route message to appropriate adapter
        >>> for msg in messages:
        ...     adapter = registry.get_adapter_for_message(msg)
        ...     normalized = adapter.normalize_message(msg)
    """
    
    def __init__(self) -> None:
        """Initialize the adapter registry."""
        self._adapters: Dict[PlatformType, MessageAdapter] = {}
        self._logger = logger
    
    def register_adapter(self, adapter: MessageAdapter) -> bool:
        """Register a message adapter.
        
        Args:
            adapter: Adapter to register
            
        Returns:
            True if registered successfully
        """
        if adapter.platform in self._adapters:
            self._logger.warning(f"Adapter for {adapter.platform.value} already registered")
            return False
        
        self._adapters[adapter.platform] = adapter
        self._logger.info(f"Registered adapter for {adapter.platform.value}")
        
        return True
    
    def unregister_adapter(self, platform: PlatformType) -> bool:
        """Unregister a message adapter.
        
        Args:
            platform: Platform to unregister
            
        Returns:
            True if unregistered successfully
        """
        if platform not in self._adapters:
            return False
        
        del self._adapters[platform]
        self._logger.info(f"Unregistered adapter for {platform.value}")
        
        return True
    
    def get_adapter(self, platform: PlatformType) -> Optional[MessageAdapter]:
        """Get adapter for a platform.
        
        Args:
            platform: Platform type
            
        Returns:
            MessageAdapter if found, None otherwise
        """
        return self._adapters.get(platform)
    
    def get_all_adapters(self) -> List[MessageAdapter]:
        """Get all registered adapters.
        
        Returns:
            List of adapters
        """
        return list(self._adapters.values())
    
    def get_supported_platforms(self) -> List[PlatformType]:
        """Get list of supported platforms.
        
        Returns:
            List of platform types
        """
        return list(self._adapters.keys())
    
    def is_supported(self, platform: PlatformType) -> bool:
        """Check if a platform is supported.
        
        Args:
            platform: Platform to check
            
        Returns:
            True if platform has an adapter
        """
        return platform in self._adapters


# Singleton registry instance
_registry_instance: Optional[AdapterRegistry] = None


def get_adapter_registry() -> AdapterRegistry:
    """Get or create singleton AdapterRegistry.
    
    Returns:
        AdapterRegistry singleton
    """
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = AdapterRegistry()
    return _registry_instance
