"""OctoMessage Protocol - Standardized messaging for octopOS agents.

This module defines the core message types and structures used for
inter-agent communication within the octopOS system.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class MessageType(str, Enum):
    """Types of messages that can be exchanged between agents."""
    
    TASK = "task"  # Standard task assignment
    ERROR = "error"  # Error reporting with suggestions
    APPROVAL_REQUEST = "approval_request"  # Request for supervisor approval
    APPROVAL_GRANTED = "approval_granted"  # Approval response
    APPROVAL_DENIED = "approval_denied"  # Denial response
    STATUS_UPDATE = "status_update"  # Progress reporting
    SYSTEM = "system"  # Internal system messages
    CHAT = "chat"  # User-facing chat messages
    QUERY = "query"  # Information retrieval requests
    RESPONSE = "response"  # Query responses


class TaskStatus(str, Enum):
    """Status values for task tracking."""
    
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class ErrorSeverity(str, Enum):
    """Severity levels for errors."""
    
    LOW = "low"  # Non-critical, can continue
    MEDIUM = "medium"  # Issue requires attention
    HIGH = "high"  # Significant problem, needs resolution
    CRITICAL = "critical"  # System-affecting error


class AgentContext(BaseModel):
    """Context information shared between agents."""
    
    workspace_path: str = Field(
        default=".",
        description="Path to the current workspace"
    )
    aws_region: str = Field(
        default="us-east-1",
        description="AWS region for operations"
    )
    session_id: UUID = Field(
        default_factory=uuid4,
        description="Unique session identifier"
    )
    user_id: Optional[str] = Field(
        default=None,
        description="Identifier for the current user"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context metadata"
    )


class ErrorPayload(BaseModel):
    """Detailed error information for error messages."""
    
    error_type: str = Field(
        ...,
        description="Type/classification of the error"
    )
    error_message: str = Field(
        ...,
        description="Human-readable error description"
    )
    severity: ErrorSeverity = Field(
        default=ErrorSeverity.MEDIUM,
        description="Error severity level"
    )
    suggestion: Optional[str] = Field(
        default=None,
        description="Suggested fix or workaround"
    )
    stack_trace: Optional[str] = Field(
        default=None,
        description="Full stack trace if available"
    )
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional error context"
    )


class TaskPayload(BaseModel):
    """Payload for task assignment messages."""
    
    task_id: UUID = Field(
        default_factory=uuid4,
        description="Unique task identifier"
    )
    action: str = Field(
        ...,
        description="Action to be performed"
    )
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Action parameters"
    )
    priority: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Task priority (1-10, higher = more important)"
    )
    deadline: Optional[datetime] = Field(
        default=None,
        description="Optional deadline for task completion"
    )
    dependencies: List[UUID] = Field(
        default_factory=list,
        description="Task IDs that must complete before this task"
    )


class StatusPayload(BaseModel):
    """Payload for status update messages."""
    
    task_id: UUID = Field(
        ...,
        description="Task being reported on"
    )
    status: TaskStatus = Field(
        ...,
        description="Current task status"
    )
    progress: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Progress percentage (0-100)"
    )
    message: Optional[str] = Field(
        default=None,
        description="Status description or update"
    )
    result: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Partial or final results"
    )


class ApprovalPayload(BaseModel):
    """Payload for approval request/grant/denial messages."""
    
    request_id: UUID = Field(
        default_factory=uuid4,
        description="Unique approval request ID"
    )
    action_type: str = Field(
        ...,
        description="Type of action requiring approval"
    )
    action_description: str = Field(
        ...,
        description="Human-readable description of the action"
    )
    security_scan: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Security scan results if applicable"
    )
    code_changes: Optional[str] = Field(
        default=None,
        description="Code diff or changes for review"
    )
    approved: Optional[bool] = Field(
        default=None,
        description="Approval decision (for responses)"
    )
    reason: Optional[str] = Field(
        default=None,
        description="Reason for denial or conditions"
    )


class OctoMessage(BaseModel):
    """Standard message format for octopOS inter-agent communication.
    
    This is the core protocol that all agents use to communicate. Messages
    are validated using Pydantic and can be serialized to JSON for transport.
    """
    
    message_id: UUID = Field(
        default_factory=uuid4,
        description="Unique message identifier"
    )
    sender: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Agent or system component sending the message"
    )
    receiver: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Target agent or system component"
    )
    type: MessageType = Field(
        ...,
        description="Type of message"
    )
    payload: Union[
        TaskPayload,
        ErrorPayload,
        StatusPayload,
        ApprovalPayload,
        Dict[str, Any]
    ] = Field(
        default_factory=dict,
        description="Message payload (type-specific)"
    )
    context: AgentContext = Field(
        default_factory=AgentContext,
        description="Shared context information"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp of message creation"
    )
    correlation_id: Optional[UUID] = Field(
        default=None,
        description="Links related messages (e.g., request/response pairs)"
    )
    reply_to: Optional[UUID] = Field(
        default=None,
        description="ID of message this is a reply to"
    )
    
    @field_validator("timestamp")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        """Ensure timestamp is UTC."""
        if v.tzinfo is None:
            return v.replace(tzinfo=None)
        return v.replace(tzinfo=None)
    
    def is_reply_to(self, message: "OctoMessage") -> bool:
        """Check if this message is a reply to another message."""
        return self.reply_to == message.message_id
    
    def create_reply(
        self,
        sender: str,
        payload: Union[TaskPayload, ErrorPayload, StatusPayload, ApprovalPayload, Dict[str, Any]],
        msg_type: Optional[MessageType] = None
    ) -> "OctoMessage":
        """Create a reply message with proper correlation."""
        return OctoMessage(
            sender=sender,
            receiver=self.sender,
            type=msg_type or MessageType.RESPONSE,
            payload=payload,
            context=self.context,
            correlation_id=self.correlation_id or self.message_id,
            reply_to=self.message_id
        )
    
    def model_dump_json_safe(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict with string UUIDs."""
        return self.model_dump(mode="json")


class MessageQueue:
    """Simple in-memory message queue for agent communication."""
    
    def __init__(self) -> None:
        """Initialize empty message queue."""
        self._messages: List[OctoMessage] = []
        self._subscribers: Dict[str, List[callable]] = {}
    
    def publish(self, message: OctoMessage) -> None:
        """Publish a message to the queue."""
        self._messages.append(message)
        
        # Notify subscribers
        if message.receiver in self._subscribers:
            for callback in self._subscribers[message.receiver]:
                try:
                    callback(message)
                except Exception as e:
                    print(f"Error notifying subscriber: {e}")
    
    def subscribe(self, agent_name: str, callback: callable) -> None:
        """Subscribe to messages for a specific agent."""
        if agent_name not in self._subscribers:
            self._subscribers[agent_name] = []
        self._subscribers[agent_name].append(callback)
    
    def get_messages_for(self, agent_name: str) -> List[OctoMessage]:
        """Get all pending messages for an agent."""
        return [m for m in self._messages if m.receiver == agent_name]
    
    def clear(self) -> None:
        """Clear all messages from the queue."""
        self._messages.clear()


# Global message queue instance
_message_queue: Optional[MessageQueue] = None


def get_message_queue() -> MessageQueue:
    """Get the global message queue instance."""
    global _message_queue
    if _message_queue is None:
        _message_queue = MessageQueue()
    return _message_queue
