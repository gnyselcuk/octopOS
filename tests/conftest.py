"""Global test fixtures for octopOS test suite.

This module provides shared fixtures and utilities for all tests.
"""

import asyncio
import uuid
from datetime import datetime
from typing import Any, Dict, Generator
from unittest.mock import MagicMock, Mock

import pytest
from pytest import FixtureRequest

from src.engine.message import (
    AgentContext,
    ApprovalPayload,
    ErrorPayload,
    ErrorSeverity,
    MessageType,
    OctoMessage,
    StatusPayload,
    TaskPayload,
    TaskStatus,
)


# =============================================================================
# Event Loop Fixture
# =============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# Sample Data Fixtures
# =============================================================================

@pytest.fixture
def sample_agent_context() -> AgentContext:
    """Create a sample AgentContext for testing."""
    return AgentContext(
        workspace_path="/tmp/test_workspace",
        aws_region="us-east-1",
        session_id=uuid.uuid4(),
        user_id="test_user",
        metadata={"test": True}
    )


@pytest.fixture
def sample_task_payload() -> TaskPayload:
    """Create a sample TaskPayload for testing."""
    return TaskPayload(
        task_id=uuid.uuid4(),
        action="test_action",
        params={"param1": "value1", "param2": 42},
        priority=5,
        deadline=None,
        dependencies=[]
    )


@pytest.fixture
def sample_error_payload() -> ErrorPayload:
    """Create a sample ErrorPayload for testing."""
    return ErrorPayload(
        error_type="TestError",
        error_message="This is a test error",
        severity=ErrorSeverity.MEDIUM,
        suggestion="Try again",
        stack_trace=None,
        context={}
    )


@pytest.fixture
def sample_status_payload() -> StatusPayload:
    """Create a sample StatusPayload for testing."""
    return StatusPayload(
        task_id=uuid.uuid4(),
        status=TaskStatus.IN_PROGRESS,
        progress=50.0,
        message="Task is halfway done",
        result=None
    )


@pytest.fixture
def sample_approval_payload() -> ApprovalPayload:
    """Create a sample ApprovalPayload for testing."""
    return ApprovalPayload(
        request_id=uuid.uuid4(),
        action_type="code_execution",
        action_description="Execute test code",
        security_scan=None,
        code_changes=None,
        approved=None,
        reason=None
    )


@pytest.fixture
def sample_octo_message(
    sample_agent_context: AgentContext,
    sample_task_payload: TaskPayload
) -> OctoMessage:
    """Create a sample OctoMessage for testing."""
    return OctoMessage(
        message_id=uuid.uuid4(),
        sender="test_sender",
        receiver="test_receiver",
        type=MessageType.TASK,
        payload=sample_task_payload,
        context=sample_agent_context,
        timestamp=datetime.utcnow(),
        correlation_id=None,
        reply_to=None
    )


# =============================================================================
# Mock Fixtures
# =============================================================================

@pytest.fixture
def mock_bedrock_client() -> MagicMock:
    """Mock AWS Bedrock client."""
    mock = MagicMock()
    mock.invoke_model.return_value = {
        "body": MagicMock(read=lambda: b'{"content": "test response"}')
    }
    return mock


@pytest.fixture
def mock_docker_client() -> MagicMock:
    """Mock Docker client."""
    mock = MagicMock()
    mock.containers = MagicMock()
    mock.containers.run.return_value = MagicMock(
        id="test_container_id",
        status="running",
        exec_run=MagicMock(return_value=(0, "output")),
    )
    mock.containers.get.return_value = MagicMock(
        id="test_container_id",
        status="exited",
        attrs={"State": {"ExitCode": 0}},
    )
    return mock


@pytest.fixture
def mock_lancedb_connection() -> MagicMock:
    """Mock LanceDB connection."""
    mock = MagicMock()
    mock.open_table.return_value = MagicMock()
    mock.create_table.return_value = MagicMock()
    return mock


@pytest.fixture
def mock_aws_services() -> Dict[str, MagicMock]:
    """Mock AWS services (CloudWatch, DynamoDB, S3)."""
    return {
        "cloudwatch": MagicMock(),
        "dynamodb": MagicMock(),
        "s3": MagicMock(),
        "bedrock": MagicMock(),
    }


# =============================================================================
# Path Fixtures
# =============================================================================

@pytest.fixture
def temp_workspace(tmp_path) -> Generator:
    """Create a temporary workspace directory."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    yield workspace


# =============================================================================
# Utility Fixtures
# =============================================================================

@pytest.fixture
def unique_id() -> str:
    """Generate a unique identifier for test isolation."""
    return str(uuid.uuid4())


@pytest.fixture(autouse=True)
def reset_global_state():
    """Reset global state before each test."""
    # Reset message queue
    from src.engine import message
    message._message_queue = None
    yield
    # Cleanup after test
    message._message_queue = None
