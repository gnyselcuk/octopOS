"""Unit tests for tasks/task_queue.py module.

This module tests the persistent task queue (OctoQueue).
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.tasks.task_queue import Task, TaskPriority, TaskQueue, TaskState


class TestTaskPriority:
    """Test TaskPriority enum."""
    
    def test_priority_values(self):
        """Test that all expected priorities exist."""
        assert TaskPriority.CRITICAL.value == 1
        assert TaskPriority.HIGH.value == 3
        assert TaskPriority.NORMAL.value == 5
        assert TaskPriority.LOW.value == 7
        assert TaskPriority.BACKGROUND.value == 9
    
    def test_priority_ordering(self):
        """Test that priorities are ordered correctly."""
        assert TaskPriority.CRITICAL.value < TaskPriority.NORMAL.value
        assert TaskPriority.HIGH.value < TaskPriority.LOW.value


class TestTaskState:
    """Test TaskState enum."""
    
    def test_state_values(self):
        """Test that all expected states exist."""
        expected_states = {
            "pending", "scheduled", "in_progress", "completed",
            "failed", "cancelled", "paused"
        }
        actual_states = {s.value for s in TaskState}
        assert actual_states == expected_states


class TestTaskQueue:
    """Test TaskQueue class."""
    
    @pytest.fixture
    def temp_db(self, tmp_path):
        """Create temporary database path."""
        return str(tmp_path / "test_tasks.db")
    
    @pytest.fixture
    def queue(self, temp_db):
        """Create task queue with mocked config."""
        with patch('src.tasks.task_queue.get_config') as mock_config:
            config = MagicMock()
            config.task.db_path = temp_db
            mock_config.return_value = config
            
            with patch('src.tasks.task_queue.get_logger'):
                return TaskQueue(db_path=temp_db)
    
    def test_initialization(self, queue, temp_db):
        """Test queue initialization."""
        assert queue._db_path == temp_db
        assert queue._initialized is False
    
    def test_initialize_creates_tables(self, queue, temp_db):
        """Test that initialize creates database tables."""
        queue.initialize()
        
        assert queue._initialized is True
        
        # Verify tables exist
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'")
        result = cursor.fetchone()
        conn.close()
        
        assert result is not None
    
    def test_create_task(self, queue):
        """Test creating a task."""
        task_id = queue.create_task(
            title="Test Task",
            agent_type="CoderAgent",
            action="write_code",
            description="Write some code",
            params={"language": "python"}
        )
        
        assert task_id is not None
        assert isinstance(task_id, str)
        
        # Verify task was created
        task = queue.get_task(task_id)
        assert task is not None
        assert task.title == "Test Task"
        assert task.agent_type == "CoderAgent"
        assert task.action == "write_code"
        assert task.state == TaskState.PENDING
    
    def test_create_task_with_priority(self, queue):
        """Test creating task with specific priority."""
        task_id = queue.create_task(
            title="High Priority Task",
            agent_type="Agent",
            action="test",
            priority=TaskPriority.HIGH
        )
        
        task = queue.get_task(task_id)
        assert task.priority == TaskPriority.HIGH
    
    def test_create_task_with_schedule(self, queue):
        """Test creating scheduled task."""
        scheduled_time = datetime.utcnow().isoformat()
        
        task_id = queue.create_task(
            title="Scheduled Task",
            agent_type="Agent",
            action="test",
            scheduled_at=scheduled_time
        )
        
        task = queue.get_task(task_id)
        assert task.scheduled_at == scheduled_time
    
    def test_get_task_nonexistent(self, queue):
        """Test getting non-existent task."""
        task = queue.get_task("nonexistent-id")
        
        assert task is None
    
    def test_update_task_state(self, queue):
        """Test updating task state."""
        task_id = queue.create_task(
            title="Test Task",
            agent_type="Agent",
            action="test"
        )
        
        result = queue.update_task_state(task_id, TaskState.IN_PROGRESS)
        
        assert result is True
        
        task = queue.get_task(task_id)
        assert task.state == TaskState.IN_PROGRESS
        assert task.started_at is not None
    
    def test_update_task_state_to_completed(self, queue):
        """Test completing a task."""
        task_id = queue.create_task(
            title="Test Task",
            agent_type="Agent",
            action="test"
        )
        
        result = queue.update_task_state(
            task_id,
            TaskState.COMPLETED,
            result={"output": "success"}
        )
        
        assert result is True
        
        task = queue.get_task(task_id)
        assert task.state == TaskState.COMPLETED
        assert task.completed_at is not None
        assert task.result == {"output": "success"}
    
    def test_update_task_state_to_failed(self, queue):
        """Test marking task as failed."""
        task_id = queue.create_task(
            title="Test Task",
            agent_type="Agent",
            action="test"
        )
        
        result = queue.update_task_state(
            task_id,
            TaskState.FAILED,
            error="Something went wrong"
        )
        
        assert result is True
        
        task = queue.get_task(task_id)
        assert task.state == TaskState.FAILED
        assert task.error == "Something went wrong"
    
    def test_update_nonexistent_task(self, queue):
        """Test updating non-existent task."""
        result = queue.update_task_state("nonexistent", TaskState.IN_PROGRESS)
        
        assert result is False
    
    def test_get_pending_tasks(self, queue):
        """Test getting pending tasks."""
        # Create tasks with different priorities
        task1_id = queue.create_task(
            title="Low Priority",
            agent_type="Agent",
            action="test",
            priority=TaskPriority.LOW
        )
        task2_id = queue.create_task(
            title="High Priority",
            agent_type="Agent",
            action="test",
            priority=TaskPriority.HIGH
        )
        
        pending = queue.get_pending_tasks()
        
        assert len(pending) == 2
        # Should be ordered by priority (high first)
        assert pending[0].priority == TaskPriority.HIGH
        assert pending[1].priority == TaskPriority.LOW
    
    def test_get_pending_tasks_by_agent_type(self, queue):
        """Test filtering pending tasks by agent type."""
        queue.create_task(
            title="Coder Task",
            agent_type="CoderAgent",
            action="code"
        )
        queue.create_task(
            title="Browser Task",
            agent_type="BrowserAgent",
            action="browse"
        )
        
        coder_tasks = queue.get_pending_tasks(agent_type="CoderAgent")
        
        assert len(coder_tasks) == 1
        assert coder_tasks[0].agent_type == "CoderAgent"
    
    def test_get_pending_tasks_excludes_non_pending(self, queue):
        """Test that pending tasks excludes completed/failed."""
        task_id = queue.create_task(
            title="Test Task",
            agent_type="Agent",
            action="test"
        )
        queue.update_task_state(task_id, TaskState.COMPLETED)
        
        pending = queue.get_pending_tasks()
        
        assert len(pending) == 0
    
    def test_create_subtask(self, queue):
        """Test creating a subtask."""
        parent_id = queue.create_task(
            title="Parent Task",
            agent_type="Agent",
            action="parent"
        )
        
        child_id = queue.create_task(
            title="Child Task",
            agent_type="Agent",
            action="child",
            parent_id=parent_id
        )
        
        child = queue.get_task(child_id)
        assert child.parent_id == parent_id
    
    def test_task_metadata(self, queue):
        """Test task with metadata."""
        task_id = queue.create_task(
            title="Test Task",
            agent_type="Agent",
            action="test",
            metadata={"source": "webhook", "user_id": "123"}
        )
        
        task = queue.get_task(task_id)
        assert task.metadata == {"source": "webhook", "user_id": "123"}
    
    def test_task_params(self, queue):
        """Test task with parameters."""
        task_id = queue.create_task(
            title="Test Task",
            agent_type="Agent",
            action="test",
            params={"arg1": "value1", "arg2": 42}
        )
        
        task = queue.get_task(task_id)
        assert task.params == {"arg1": "value1", "arg2": 42}


class TestTaskQueueRecurrence:
    """Test recurring tasks functionality."""
    
    @pytest.fixture
    def temp_db(self, tmp_path):
        """Create temporary database path."""
        return str(tmp_path / "test_tasks.db")
    
    @pytest.fixture
    def queue(self, temp_db):
        """Create task queue."""
        with patch('src.tasks.task_queue.get_config') as mock_config:
            config = MagicMock()
            config.task.db_path = temp_db
            mock_config.return_value = config
            
            with patch('src.tasks.task_queue.get_logger'):
                return TaskQueue(db_path=temp_db)
    
    @patch('src.tasks.task_queue.croniter')
    def test_schedule_next_recurrence(self, mock_croniter, queue):
        """Test scheduling next occurrence of recurring task."""
        # Mock croniter
        mock_itr = MagicMock()
        mock_itr.get_next.return_value = datetime(2024, 12, 1, 10, 0, 0)
        mock_croniter.return_value = mock_itr
        
        # Create a recurring task
        task_id = queue.create_task(
            title="Recurring Task",
            agent_type="Agent",
            action="test",
            recurrence="0 10 * * *"  # Daily at 10am
        )
        
        # Complete the task
        queue.update_task_state(task_id, TaskState.COMPLETED)
        
        # Verify croniter was called to schedule next
        mock_croniter.assert_called_once()


class TestTaskDataConversion:
    """Test task data conversion."""
    
    @pytest.fixture
    def temp_db(self, tmp_path):
        """Create temporary database path."""
        return str(tmp_path / "test_tasks.db")
    
    @pytest.fixture
    def queue(self, temp_db):
        """Create task queue."""
        with patch('src.tasks.task_queue.get_config') as mock_config:
            config = MagicMock()
            config.task.db_path = temp_db
            mock_config.return_value = config
            
            with patch('src.tasks.task_queue.get_logger'):
                q = TaskQueue(db_path=temp_db)
                q.initialize()
                return q
    
    def test_row_to_task_conversion(self, queue):
        """Test converting database row to Task object."""
        # Create a task
        task_id = queue.create_task(
            title="Test Task",
            agent_type="Agent",
            action="test",
            params={"key": "value"},
            priority=TaskPriority.HIGH
        )
        
        # Get the task
        task = queue.get_task(task_id)
        
        # Verify all fields
        assert isinstance(task, Task)
        assert task.id == task_id
        assert task.title == "Test Task"
        assert task.params == {"key": "value"}
        assert task.priority == TaskPriority.HIGH
        assert task.state == TaskState.PENDING
