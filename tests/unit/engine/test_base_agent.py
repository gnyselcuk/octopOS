"""Unit tests for engine/base_agent.py module.

This module tests the BaseAgent abstract class and its functionality.
"""

from typing import Any, Dict
from unittest.mock import MagicMock, Mock, patch
from uuid import UUID

import pytest

from src.engine.base_agent import BaseAgent
from src.engine.message import (
    AgentContext,
    ErrorPayload,
    ErrorSeverity,
    MessageType,
    OctoMessage,
    TaskPayload,
    TaskStatus,
)


class ConcreteAgent(BaseAgent):
    """Concrete implementation of BaseAgent for testing."""
    
    async def execute_task(self, task: TaskPayload) -> Dict[str, Any]:
        """Execute a task - test implementation."""
        return {"status": "success", "result": task.action}


class FailingAgent(BaseAgent):
    """Agent that fails for testing error handling."""
    
    async def execute_task(self, task: TaskPayload) -> Dict[str, Any]:
        """Execute a task - always fails."""
        raise RuntimeError("Task execution failed")


class TestBaseAgent:
    """Test BaseAgent class."""
    
    @pytest.fixture
    def mock_message_queue(self):
        """Create mock message queue."""
        with patch('src.engine.base_agent.get_message_queue') as mock_get:
            queue = MagicMock()
            mock_get.return_value = queue
            yield queue
    
    @pytest.fixture
    def agent(self, mock_message_queue):
        """Create test agent."""
        return ConcreteAgent(name="TestAgent")
    
    def test_initialization(self, agent, mock_message_queue):
        """Test agent initialization."""
        assert agent.name == "TestAgent"
        assert agent.state == TaskStatus.PENDING
        assert agent.is_running is False
        assert agent._current_task is None
        assert isinstance(agent.context, AgentContext)
        
        # Should subscribe to message queue
        mock_message_queue.subscribe.assert_called_once_with("TestAgent", agent._on_message)
    
    def test_initialization_with_context(self, mock_message_queue):
        """Test agent initialization with custom context."""
        context = AgentContext(workspace_path="/tmp/test", aws_region="eu-west-1")
        agent = ConcreteAgent(name="CustomAgent", context=context)
        
        assert agent.context.workspace_path == "/tmp/test"
        assert agent.context.aws_region == "eu-west-1"
    
    @pytest.mark.asyncio
    async def test_start(self, agent):
        """Test starting the agent."""
        await agent.start()
        
        assert agent.is_running is True
        assert agent.state == TaskStatus.IN_PROGRESS
    
    @pytest.mark.asyncio
    async def test_stop(self, agent):
        """Test stopping the agent."""
        await agent.start()
        await agent.stop()
        
        assert agent.is_running is False
        assert agent.state == TaskStatus.COMPLETED
    
    @pytest.mark.asyncio
    async def test_pause_resume(self, agent):
        """Test pausing and resuming the agent."""
        await agent.start()
        
        # Pause
        await agent.pause()
        assert agent.state == TaskStatus.PAUSED
        
        # Resume
        await agent.resume()
        assert agent.state == TaskStatus.IN_PROGRESS
    
    @pytest.mark.asyncio
    async def test_resume_not_paused(self, agent):
        """Test resuming when not paused."""
        await agent.start()
        
        # Should not change state if not paused
        original_state = agent.state
        await agent.resume()
        assert agent.state == original_state
    
    @pytest.mark.asyncio
    async def test_execute_task(self, agent):
        """Test executing a task."""
        task = TaskPayload(action="test_action", params={"key": "value"})
        
        result = await agent.execute_task(task)
        
        assert result["status"] == "success"
        assert result["result"] == "test_action"
    
    def test_send_message(self, agent, mock_message_queue):
        """Test sending a message."""
        payload = {"data": "test"}
        
        message = agent.send_message(
            receiver="OtherAgent",
            msg_type=MessageType.TASK,
            payload=payload
        )
        
        assert isinstance(message, OctoMessage)
        assert message.sender == "TestAgent"
        assert message.receiver == "OtherAgent"
        assert message.type == MessageType.TASK
        mock_message_queue.publish.assert_called_with(message)
    
    def test_send_error(self, agent, mock_message_queue):
        """Test sending an error message."""
        message = agent.send_error(
            receiver="SelfHealing",
            error_type="RuntimeError",
            error_message="Something went wrong",
            severity=ErrorSeverity.HIGH,
            suggestion="Check the logs"
        )
        
        assert isinstance(message, OctoMessage)
        assert message.type == MessageType.ERROR
        assert message.sender == "TestAgent"
        assert message.receiver == "SelfHealing"
        
        payload = message.payload
        assert isinstance(payload, ErrorPayload)
        assert payload.error_type == "RuntimeError"
        assert payload.error_message == "Something went wrong"
        assert payload.severity == ErrorSeverity.HIGH
        assert payload.suggestion == "Check the logs"
    
    def test_send_message_with_correlation_id(self, agent, mock_message_queue):
        """Test sending message with correlation ID."""
        correlation_id = UUID("12345678-1234-5678-1234-567812345678")
        
        message = agent.send_message(
            receiver="OtherAgent",
            msg_type=MessageType.TASK,
            payload={},
            correlation_id=correlation_id
        )
        
        assert message.correlation_id == correlation_id
    
    @pytest.mark.asyncio
    async def test_on_message(self, agent, mock_message_queue):
        """Test message handler callback."""
        task = TaskPayload(action="do_something", params={})
        message = OctoMessage(
            sender="OtherAgent",
            receiver="TestAgent",
            type=MessageType.TASK,
            payload=task,
            context=AgentContext()
        )
        
        # Start agent first
        await agent.start()

        # Call message handler
        agent._on_message(message)

        # Task should be processed (implementation-specific)
    
    @pytest.mark.asyncio
    async def test_lifecycle_hooks(self, agent):
        """Test lifecycle hook methods."""
        # These should be overridable and not raise
        await agent.on_start()
        await agent.on_stop()
        await agent.on_pause()
        await agent.on_resume()


class TestBaseAgentEdgeCases:
    """Test edge cases and error handling."""
    
    @pytest.fixture
    def mock_message_queue(self):
        """Create mock message queue."""
        with patch('src.engine.base_agent.get_message_queue') as mock_get:
            queue = MagicMock()
            mock_get.return_value = queue
            yield queue
    
    @pytest.mark.asyncio
    async def test_execute_task_error(self, mock_message_queue):
        """Test task execution with error."""
        agent = FailingAgent(name="FailingAgent")
        task = TaskPayload(action="fail", params={})
        
        with pytest.raises(RuntimeError, match="Task execution failed"):
            await agent.execute_task(task)
    
    def test_state_property(self, mock_message_queue):
        """Test state property access."""
        agent = ConcreteAgent(name="StateAgent")
        
        # Should be accessible as property
        assert agent.state == TaskStatus.PENDING
        
        # Internal state should be private
        assert hasattr(agent, '_state')
