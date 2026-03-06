"""Interfaces module - User interfaces and communication channels."""

from src.interfaces.message_adapter import (
    MessageAdapter,
    AdapterRegistry,
    Attachment,
    AttachmentType,
    PlatformMessage,
    PlatformResponse,
    PlatformType,
    get_adapter_registry,
)

__all__ = [
    "MessageAdapter",
    "AdapterRegistry",
    "Attachment",
    "AttachmentType",
    "PlatformMessage",
    "PlatformResponse",
    "PlatformType",
    "get_adapter_registry",
]
