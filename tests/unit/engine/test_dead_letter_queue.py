"""Unit tests for engine/dead_letter_queue.py module.

This module tests the Dead Letter Queue for failed messages.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
from uuid import UUID

import pytest

from src.engine.dead_letter_queue import DeadLetter, DeadLetterQueue, get_dead_letter_queue
from src.engine.message import MessageType, OctoMessage


class TestDeadLetter:
    """Test DeadLetter dataclass."""
    
    def test_create_dead_letter(self):
        """Test creating a dead letter entry."""
        entry = DeadLetter(
            id="entry-123",
            original_message={"sender": "AgentA", "payload": "test"},
            error_type="RuntimeError",
            error_message="Something went wrong",
            failed_at="2024-01-01T10:00:00",
            retry_count=2,
            agent_name="AgentA",
            status="pending"
        )
        
        assert entry.id == "entry-123"
        assert entry.error_type == "RuntimeError"
        assert entry.retry_count == 2
        assert entry.status == "pending"
        assert entry.analysis_result is None
        assert entry.resolved_at is None


class TestDeadLetterQueue:
    """Test DeadLetterQueue class."""
    
    @pytest.fixture
    def temp_storage(self, tmp_path):
        """Create temporary storage path."""
        return str(tmp_path / "dlq")
    
    @pytest.fixture
    def dlq(self, temp_storage):
        """Create DLQ instance."""
        with patch('src.engine.dead_letter_queue.get_logger'):
            return DeadLetterQueue(storage_path=temp_storage)
    
    @pytest.fixture
    def sample_message(self):
        """Create sample OctoMessage."""
        return OctoMessage(
            sender="TestAgent",
            receiver="TargetAgent",
            type=MessageType.TASK,
            payload={"action": "test"},
            correlation_id=UUID("12345678-1234-5678-1234-567812345678")
        )
    
    def test_initialization(self, dlq, temp_storage):
        """Test DLQ initialization."""
        assert dlq._storage_path == Path(temp_storage)
        assert dlq._storage_path.exists()
        assert isinstance(dlq._queue, list)
    
    def test_add_entry(self, dlq, sample_message):
        """Test adding a failed message to DLQ."""
        entry_id = dlq.add(
            message=sample_message,
            error_type="RuntimeError",
            error_message="Task failed",
            agent_name="TestAgent",
            retry_count=1
        )
        
        assert entry_id is not None
        assert len(dlq._queue) == 1
        
        entry = dlq._queue[0]
        assert entry.id == entry_id
        assert entry.error_type == "RuntimeError"
        assert entry.agent_name == "TestAgent"
        assert entry.status == "pending"
    
    def test_add_saves_to_file(self, dlq, sample_message, temp_storage):
        """Test that add operation persists to file."""
        dlq.add(
            message=sample_message,
            error_type="Error",
            error_message="Test",
            agent_name="Agent"
        )
        
        storage_file = Path(temp_storage) / "dead_letters.json"
        assert storage_file.exists()
        
        with open(storage_file) as f:
            data = json.load(f)
            assert len(data) == 1
    
    def test_get_pending(self, dlq, sample_message):
        """Test getting pending entries."""
        # Add entries with different statuses
        dlq.add(sample_message, "Error1", "Test1", "AgentA")
        dlq.add(sample_message, "Error2", "Test2", "AgentB")
        
        # Update one to resolved
        entry_id = dlq._queue[1].id
        dlq.update_status(entry_id, "resolved")
        
        pending = dlq.get_pending()
        
        assert len(pending) == 1
        assert pending[0].error_type == "Error1"
    
    def test_get_pending_with_limit(self, dlq, sample_message):
        """Test pending entries with limit."""
        # Add multiple entries
        for i in range(5):
            dlq.add(sample_message, f"Error{i}", f"Test{i}", f"Agent{i}")
        
        pending = dlq.get_pending(limit=3)
        
        assert len(pending) == 3
    
    def test_update_status(self, dlq, sample_message):
        """Test updating entry status."""
        entry_id = dlq.add(sample_message, "Error", "Test", "Agent")
        
        result = dlq.update_status(
            entry_id,
            "analyzing",
            analysis_result={"can_recover": True}
        )
        
        assert result is True
        
        entry = dlq.get_entry(entry_id)
        assert entry.status == "analyzing"
        assert entry.analysis_result["can_recover"] is True
    
    def test_update_status_to_resolved(self, dlq, sample_message):
        """Test updating status to resolved."""
        entry_id = dlq.add(sample_message, "Error", "Test", "Agent")
        
        dlq.update_status(entry_id, "resolved")
        
        entry = dlq.get_entry(entry_id)
        assert entry.status == "resolved"
        assert entry.resolved_at is not None
    
    def test_update_nonexistent_entry(self, dlq):
        """Test updating entry that doesn't exist."""
        result = dlq.update_status("nonexistent", "resolved")
        
        assert result is False
    
    def test_get_entry(self, dlq, sample_message):
        """Test getting specific entry."""
        entry_id = dlq.add(sample_message, "Error", "Test", "Agent")
        
        entry = dlq.get_entry(entry_id)
        
        assert entry is not None
        assert entry.id == entry_id
    
    def test_get_nonexistent_entry(self, dlq):
        """Test getting entry that doesn't exist."""
        entry = dlq.get_entry("nonexistent")
        
        assert entry is None
    
    def test_get_stats(self, dlq, sample_message):
        """Test getting DLQ statistics."""
        # Add entries with different statuses
        dlq.add(sample_message, "RuntimeError", "Test1", "AgentA")
        dlq.add(sample_message, "RuntimeError", "Test2", "AgentA")
        dlq.add(sample_message, "TimeoutError", "Test3", "AgentB")
        
        # Resolve one
        dlq.update_status(dlq._queue[0].id, "resolved")
        
        stats = dlq.get_stats()
        
        assert stats["total_entries"] == 3
        assert stats["pending"] == 2
        assert stats["resolved"] == 1
        assert stats["error_types"]["RuntimeError"] == 2
        assert stats["error_types"]["TimeoutError"] == 1
    
    def test_get_stats_empty(self, dlq):
        """Test stats with empty queue."""
        stats = dlq.get_stats()
        
        assert stats["total_entries"] == 0
        assert stats["pending"] == 0
        assert stats["error_types"] == {}
    
    @pytest.mark.asyncio
    async def test_process_with_healer(self, dlq, sample_message):
        """Test processing entries with Self-Healing Agent."""
        # Add pending entries
        dlq.add(sample_message, "Error1", "Test1", "AgentA")
        dlq.add(sample_message, "Error2", "Test2", "AgentB")
        
        # Create mock healer
        healer = MagicMock()
        healer.execute_task = MagicMock(return_value={
            "can_recover": True,
            "solution": "Fix applied"
        })
        
        result = await dlq.process_with_healer(healer, batch_size=10)
        
        assert result["processed"] == 2
        assert result["resolved"] == 2
        assert result["failed"] == 0
    
    @pytest.mark.asyncio
    async def test_process_with_healer_no_recovery(self, dlq, sample_message):
        """Test processing when recovery fails."""
        dlq.add(sample_message, "Error", "Test", "Agent")
        
        healer = MagicMock()
        healer.execute_task = MagicMock(return_value={
            "can_recover": False,
            "reason": "Not recoverable"
        })
        
        result = await dlq.process_with_healer(healer)
        
        assert result["processed"] == 1
        assert result["resolved"] == 0
        assert result["failed"] == 1
    
    @pytest.mark.asyncio
    async def test_process_with_healer_empty(self, dlq):
        """Test processing with no pending entries."""
        healer = MagicMock()
        
        result = await dlq.process_with_healer(healer)
        
        assert result["processed"] == 0
        assert "No pending" in result["message"]
    
    def test_clear_resolved(self, dlq, sample_message):
        """Test clearing resolved entries."""
        # Add entries
        dlq.add(sample_message, "Error1", "Test1", "AgentA")
        dlq.add(sample_message, "Error2", "Test2", "AgentB")
        
        # Resolve one
        entry_id = dlq._queue[0].id
        dlq.update_status(entry_id, "resolved")
        
        # Manually set resolved_at to be old enough
        dlq._queue[0].resolved_at = (datetime.utcnow() - timedelta(hours=25)).isoformat()
        
        count = dlq.clear_resolved(older_than_hours=24)
        
        assert count == 1
        assert len(dlq._queue) == 1
    
    def test_clear_resolved_none_old_enough(self, dlq, sample_message):
        """Test clearing when no entries are old enough."""
        dlq.add(sample_message, "Error", "Test", "Agent")
        dlq.update_status(dlq._queue[0].id, "resolved")
        # resolved_at is set to now by default
        
        count = dlq.clear_resolved(older_than_hours=24)
        
        assert count == 0
        assert len(dlq._queue) == 1


class TestGetDeadLetterQueue:
    """Test get_dead_letter_queue singleton function."""
    
    def test_creates_instance(self):
        """Test that function creates DLQ instance."""
        with patch('src.engine.dead_letter_queue.get_logger'):
            dlq = get_dead_letter_queue()
            
            assert isinstance(dlq, DeadLetterQueue)
    
    def test_returns_same_instance(self):
        """Test that function returns same instance (singleton-like)."""
        with patch('src.engine.dead_letter_queue.get_logger'):
            dlq1 = get_dead_letter_queue()
            dlq2 = get_dead_letter_queue()
            
            # Same instance should be returned
            assert dlq1 is dlq2
