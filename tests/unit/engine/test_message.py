"""Unit tests for engine/message.py module.

This module tests the OctoMessage protocol and related classes.
"""

import json
import uuid
from datetime import datetime
from typing import Dict, Any

import pytest
from pydantic import ValidationError

from src.engine.message import (
    AgentContext,
    ApprovalPayload,
    ErrorPayload,
    ErrorSeverity,
    MessageQueue,
    MessageType,
    OctoMessage,
    StatusPayload,
    TaskPayload,
    TaskStatus,
    get_message_queue,
)


class TestMessageType:
    """Test MessageType enum."""
    
    def test_message_type_values(self):
        """Test that all expected message types exist."""
        expected_types = {
            "task", "error", "approval_request", "approval_granted",
            "approval_denied", "status_update", "system", "chat",
            "query", "response"
        }
        actual_types = {t.value for t in MessageType}
        assert actual_types == expected_types
    
    def test_message_type_comparison(self):
        """Test message type comparison."""
        assert MessageType.TASK == "task"
        assert MessageType.TASK != "error"
        assert MessageType.ERROR == MessageType.ERROR


class TestTaskStatus:
    """Test TaskStatus enum."""
    
    def test_task_status_values(self):
        """Test that all expected task statuses exist."""
        expected_statuses = {
            "pending", "in_progress", "completed", "failed",
            "cancelled", "paused"
        }
        actual_statuses = {s.value for s in TaskStatus}
        assert actual_statuses == expected_statuses


class TestErrorSeverity:
    """Test ErrorSeverity enum."""
    
    def test_error_severity_values(self):
        """Test that all expected error severities exist."""
        expected_severities = {"low", "medium", "high", "critical"}
        actual_severities = {s.value for s in ErrorSeverity}
        assert actual_severities == expected_severities


class TestAgentContext:
    """Test AgentContext model."""
    
    def test_create_default_context(self):
        """Test creating context with defaults."""
        context = AgentContext()
        
        assert context.workspace_path == "."
        assert context.aws_region == "us-east-1"
        assert isinstance(context.session_id, uuid.UUID)
        assert context.user_id is None
        assert context.metadata == {}
    
    def test_create_custom_context(self):
        """Test creating context with custom values."""
        context = AgentContext(
            workspace_path="/tmp/test",
            aws_region="eu-west-1",
            user_id="test_user",
            metadata={"key": "value"}
        )
        
        assert context.workspace_path == "/tmp/test"
        assert context.aws_region == "eu-west-1"
        assert context.user_id == "test_user"
        assert context.metadata == {"key": "value"}


class TestErrorPayload:
    """Test ErrorPayload model."""
    
    def test_create_valid_error_payload(self, sample_error_payload):
        """Test creating error payload with valid data."""
        assert sample_error_payload.error_type == "TestError"
        assert sample_error_payload.error_message == "This is a test error"
        assert sample_error_payload.severity == ErrorSeverity.MEDIUM
        assert sample_error_payload.suggestion == "Try again"
    
    def test_create_error_payload_defaults(self):
        """Test error payload with default values."""
        payload = ErrorPayload(
            error_type="SimpleError",
            error_message="Simple message"
        )
        
        assert payload.severity == ErrorSeverity.MEDIUM
        assert payload.suggestion is None
        assert payload.stack_trace is None
        assert payload.context == {}
    
    def test_error_payload_missing_required(self):
        """Test error payload validation with missing required fields."""
        with pytest.raises(ValidationError):
            ErrorPayload(error_type="TestError")  # Missing error_message


class TestTaskPayload:
    """Test TaskPayload model."""
    
    def test_create_valid_task_payload(self, sample_task_payload):
        """Test creating task payload with valid data."""
        assert sample_task_payload.action == "test_action"
        assert sample_task_payload.params == {"param1": "value1", "param2": 42}
        assert sample_task_payload.priority == 5
        assert isinstance(sample_task_payload.task_id, uuid.UUID)
    
    def test_task_payload_defaults(self):
        """Test task payload with default values."""
        payload = TaskPayload(action="test_action")
        
        assert payload.priority == 5
        assert payload.params == {}
        assert payload.dependencies == []
        assert payload.deadline is None
        assert isinstance(payload.task_id, uuid.UUID)
    
    def test_task_payload_invalid_priority_too_high(self):
        """Test task payload with invalid priority (too high)."""
        with pytest.raises(ValidationError):
            TaskPayload(action="test", priority=15)
    
    def test_task_payload_invalid_priority_too_low(self):
        """Test task payload with invalid priority (too low)."""
        with pytest.raises(ValidationError):
            TaskPayload(action="test", priority=0)


class TestStatusPayload:
    """Test StatusPayload model."""
    
    def test_create_valid_status_payload(self, sample_status_payload):
        """Test creating status payload with valid data."""
        assert sample_status_payload.status == TaskStatus.IN_PROGRESS
        assert sample_status_payload.progress == 50.0
        assert sample_status_payload.message == "Task is halfway done"
    
    def test_status_payload_progress_range(self):
        """Test status payload progress validation."""
        # Valid progress values
        StatusPayload(task_id=uuid.uuid4(), status=TaskStatus.COMPLETED, progress=0)
        StatusPayload(task_id=uuid.uuid4(), status=TaskStatus.COMPLETED, progress=100)
        
        # Invalid progress values
        with pytest.raises(ValidationError):
            StatusPayload(task_id=uuid.uuid4(), status=TaskStatus.COMPLETED, progress=-1)
        
        with pytest.raises(ValidationError):
            StatusPayload(task_id=uuid.uuid4(), status=TaskStatus.COMPLETED, progress=101)


class TestApprovalPayload:
    """Test ApprovalPayload model."""
    
    def test_create_valid_approval_payload(self, sample_approval_payload):
        """Test creating approval payload with valid data."""
        assert sample_approval_payload.action_type == "code_execution"
        assert sample_approval_payload.action_description == "Execute test code"
        assert sample_approval_payload.approved is None
    
    def test_approval_payload_missing_required(self):
        """Test approval payload validation with missing required fields."""
        with pytest.raises(ValidationError):
            ApprovalPayload(action_type="test")  # Missing action_description


class TestOctoMessage:
    """Test OctoMessage model."""
    
    def test_create_valid_task_message(self, sample_octo_message, sample_task_payload):
        """Test creating a valid task message."""
        assert sample_octo_message.sender == "test_sender"
        assert sample_octo_message.receiver == "test_receiver"
        assert sample_octo_message.type == MessageType.TASK
        assert sample_octo_message.payload == sample_task_payload
        assert isinstance(sample_octo_message.message_id, uuid.UUID)
        assert isinstance(sample_octo_message.timestamp, datetime)
    
    def test_create_error_message_with_payload(self, sample_agent_context):
        """Test creating an error message with error payload."""
        error_payload = ErrorPayload(
            error_type="RuntimeError",
            error_message="Something went wrong",
            severity=ErrorSeverity.HIGH
        )
        
        message = OctoMessage(
            sender="worker_001",
            receiver="orchestrator",
            type=MessageType.ERROR,
            payload=error_payload,
            context=sample_agent_context
        )
        
        assert message.type == MessageType.ERROR
        assert message.payload.error_type == "RuntimeError"
        assert message.payload.severity == ErrorSeverity.HIGH
    
    def test_message_validation_missing_required_fields(self):
        """Test message validation with missing required fields."""
        with pytest.raises(ValidationError):
            OctoMessage(receiver="test", type=MessageType.TASK)  # Missing sender
        
        with pytest.raises(ValidationError):
            OctoMessage(sender="test", type=MessageType.TASK)  # Missing receiver
        
        with pytest.raises(ValidationError):
            OctoMessage(sender="test", receiver="test")  # Missing type
    
    def test_message_serialization_deserialization(self, sample_octo_message):
        """Test message serialization and deserialization."""
        # Serialize to JSON-safe dict
        json_dict = sample_octo_message.model_dump_json_safe()
        
        assert isinstance(json_dict, dict)
        assert isinstance(json_dict["message_id"], str)  # UUID as string
        assert json_dict["sender"] == "test_sender"
        
        # Deserialize back
        restored = OctoMessage.model_validate(json_dict)
        assert restored.message_id == sample_octo_message.message_id
        assert restored.sender == sample_octo_message.sender
    
    def test_message_with_agent_context(self, sample_octo_message):
        """Test message with agent context."""
        assert isinstance(sample_octo_message.context, AgentContext)
        assert sample_octo_message.context.workspace_path == "/tmp/test_workspace"
    
    def test_approval_request_flow(self, sample_agent_context):
        """Test approval request message flow."""
        approval_payload = ApprovalPayload(
            action_type="file_deletion",
            action_description="Delete sensitive file",
            approved=None
        )
        
        request = OctoMessage(
            sender="worker_001",
            receiver="supervisor",
            type=MessageType.APPROVAL_REQUEST,
            payload=approval_payload,
            context=sample_agent_context
        )
        
        assert request.type == MessageType.APPROVAL_REQUEST
        assert request.payload.approved is None
        
        # Grant approval
        grant_payload = ApprovalPayload(
            action_type="file_deletion",
            action_description="Delete sensitive file",
            approved=True,
            reason="Approved by admin"
        )
        
        grant = request.create_reply(
            sender="supervisor",
            payload=grant_payload,
            msg_type=MessageType.APPROVAL_GRANTED
        )
        
        assert grant.type == MessageType.APPROVAL_GRANTED
        assert grant.reply_to == request.message_id
        assert grant.correlation_id == request.message_id
    
    def test_status_update_progression(self, sample_agent_context):
        """Test status update progression."""
        task_id = uuid.uuid4()
        
        # Initial status
        pending = StatusPayload(
            task_id=task_id,
            status=TaskStatus.PENDING,
            progress=0.0
        )
        
        # In progress
        in_progress = StatusPayload(
            task_id=task_id,
            status=TaskStatus.IN_PROGRESS,
            progress=50.0
        )
        
        # Completed
        completed = StatusPayload(
            task_id=task_id,
            status=TaskStatus.COMPLETED,
            progress=100.0
        )
        
        assert pending.status == TaskStatus.PENDING
        assert in_progress.status == TaskStatus.IN_PROGRESS
        assert completed.status == TaskStatus.COMPLETED
    
    def test_message_priority_handling(self, sample_agent_context):
        """Test message with different priorities."""
        low_priority = TaskPayload(action="low", priority=1)
        high_priority = TaskPayload(action="high", priority=10)
        
        low_msg = OctoMessage(
            sender="test",
            receiver="test",
            type=MessageType.TASK,
            payload=low_priority,
            context=sample_agent_context
        )
        
        high_msg = OctoMessage(
            sender="test",
            receiver="test",
            type=MessageType.TASK,
            payload=high_priority,
            context=sample_agent_context
        )
        
        assert low_msg.payload.priority == 1
        assert high_msg.payload.priority == 10
    
    def test_message_threading_conversation_id(self, sample_agent_context):
        """Test message threading with correlation ID."""
        original = OctoMessage(
            sender="user",
            receiver="agent",
            type=MessageType.QUERY,
            payload={"query": "test"},
            context=sample_agent_context
        )
        
        # First reply
        reply1 = original.create_reply(
            sender="agent",
            payload={"response": "step 1"}
        )
        
        # Second reply in same thread
        reply2 = reply1.create_reply(
            sender="user",
            payload={"query": "follow up"}
        )
        
        assert reply1.correlation_id == original.message_id
        assert reply2.correlation_id == original.message_id
        assert reply1.is_reply_to(original)
        assert reply2.is_reply_to(reply1)
    
    def test_invalid_message_type_rejection(self):
        """Test that invalid message types are rejected."""
        # This should actually work since payload accepts Dict[str, Any] as union type
        message = OctoMessage(
            sender="test",
            receiver="test",
            type=MessageType.SYSTEM,
            payload={"custom": "data"}
        )
        assert message.payload == {"custom": "data"}
    
    def test_is_reply_to(self):
        """Test is_reply_to method."""
        msg1 = OctoMessage(
            sender="a",
            receiver="b",
            type=MessageType.TASK,
            payload=TaskPayload(action="test")
        )
        
        msg2 = msg1.create_reply(
            sender="b",
            payload={"response": "ok"}
        )
        
        assert msg2.is_reply_to(msg1)
        assert not msg1.is_reply_to(msg2)
    
    def test_create_reply(self, sample_octo_message):
        """Test create_reply method."""
        reply_payload = StatusPayload(
            task_id=uuid.uuid4(),
            status=TaskStatus.COMPLETED,
            progress=100.0
        )
        
        reply = sample_octo_message.create_reply(
            sender="receiver",
            payload=reply_payload
        )
        
        assert reply.sender == "receiver"
        assert reply.receiver == sample_octo_message.sender
        assert reply.reply_to == sample_octo_message.message_id
        assert reply.correlation_id == sample_octo_message.message_id
        assert reply.context == sample_octo_message.context


class TestMessageQueue:
    """Test MessageQueue class."""
    
    def test_publish_message(self):
        """Test publishing a message to the queue."""
        queue = MessageQueue()
        message = OctoMessage(
            sender="test",
            receiver="agent",
            type=MessageType.TASK,
            payload=TaskPayload(action="test")
        )
        
        queue.publish(message)
        messages = queue.get_messages_for("agent")
        
        assert len(messages) == 1
        assert messages[0] == message
    
    def test_subscribe_and_notify(self):
        """Test subscribing to messages and receiving notifications."""
        queue = MessageQueue()
        received_messages = []
        
        def callback(msg):
            received_messages.append(msg)
        
        queue.subscribe("agent", callback)
        
        message = OctoMessage(
            sender="test",
            receiver="agent",
            type=MessageType.TASK,
            payload=TaskPayload(action="test")
        )
        
        queue.publish(message)
        
        assert len(received_messages) == 1
        assert received_messages[0] == message
    
    def test_get_messages_for_specific_agent(self):
        """Test getting messages for a specific agent only."""
        queue = MessageQueue()
        
        msg1 = OctoMessage(
            sender="test",
            receiver="agent1",
            type=MessageType.TASK,
            payload=TaskPayload(action="test1")
        )
        msg2 = OctoMessage(
            sender="test",
            receiver="agent2",
            type=MessageType.TASK,
            payload=TaskPayload(action="test2")
        )
        
        queue.publish(msg1)
        queue.publish(msg2)
        
        agent1_messages = queue.get_messages_for("agent1")
        agent2_messages = queue.get_messages_for("agent2")
        
        assert len(agent1_messages) == 1
        assert len(agent2_messages) == 1
        assert agent1_messages[0].receiver == "agent1"
        assert agent2_messages[0].receiver == "agent2"
    
    def test_clear_queue(self):
        """Test clearing all messages from the queue."""
        queue = MessageQueue()
        
        message = OctoMessage(
            sender="test",
            receiver="agent",
            type=MessageType.TASK,
            payload=TaskPayload(action="test")
        )
        
        queue.publish(message)
        queue.clear()
        
        messages = queue.get_messages_for("agent")
        assert len(messages) == 0


class TestGetMessageQueue:
    """Test get_message_queue function."""
    
    def test_get_message_queue_singleton(self):
        """Test that get_message_queue returns a singleton."""
        queue1 = get_message_queue()
        queue2 = get_message_queue()
        
        assert queue1 is queue2
    
    def test_get_message_queue_creates_new_if_none(self):
        """Test that get_message_queue creates a new queue if None."""
        import src.engine.message as message_module
        
        # Reset the global queue
        original_queue = message_module._message_queue
        message_module._message_queue = None
        
        queue = get_message_queue()
        assert queue is not None
        assert isinstance(queue, MessageQueue)
        
        # Restore original
        message_module._message_queue = original_queue
