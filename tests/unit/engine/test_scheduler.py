"""Unit tests for engine/scheduler.py module.

This module tests the Scheduler class for task scheduling.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, AsyncMock

from src.engine.scheduler import (
    ScheduledJob,
    Scheduler,
)


class TestScheduledJob:
    """Test ScheduledJob class."""
    
    def test_create_scheduled_job(self):
        """Test creating a scheduled job."""
        job = ScheduledJob(
            job_id="job_123",
            task_id="task_456",
            agent_type="Worker",
            action="process_data",
            params={"path": "/data"},
            schedule_type="cron",
            schedule_expr="0 */6 * * *",
            enabled=True,
            metadata={"priority": "high"}
        )
        
        assert job.job_id == "job_123"
        assert job.task_id == "task_456"
        assert job.agent_type == "Worker"
        assert job.action == "process_data"
        assert job.params == {"path": "/data"}
        assert job.schedule_type == "cron"
        assert job.schedule_expr == "0 */6 * * *"
        assert job.enabled is True
        assert job.metadata == {"priority": "high"}
        assert job.last_run is None
        assert job.next_run is None
        assert job.run_count == 0
    
    def test_scheduled_job_defaults(self):
        """Test ScheduledJob default values."""
        job = ScheduledJob(
            job_id="job_1",
            task_id="task_1",
            agent_type="Test",
            action="test",
            params={},
            schedule_type="interval",
            schedule_expr="3600"
        )
        
        assert job.enabled is True
        assert job.metadata == {}
        assert job.last_run is None
        assert job.next_run is None
        assert job.run_count == 0


class TestSchedulerInitialization:
    """Test Scheduler initialization."""
    
    @patch("src.engine.scheduler.get_config")
    @patch("src.engine.scheduler.TaskQueue")
    def test_scheduler_init_defaults(self, mock_task_queue, mock_get_config):
        """Test Scheduler initialization with defaults."""
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        
        scheduler = Scheduler()
        
        assert scheduler._config is mock_config
        assert scheduler._scheduler is None
        assert scheduler._jobs == {}
        assert scheduler._running is False
    
    @patch("src.engine.scheduler.get_config")
    def test_scheduler_init_with_task_queue(self, mock_get_config):
        """Test Scheduler initialization with custom task queue."""
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        mock_queue = MagicMock()
        
        scheduler = Scheduler(task_queue=mock_queue)
        
        assert scheduler._task_queue is mock_queue


class TestSchedulerLifecycle:
    """Test Scheduler lifecycle methods."""
    
    @pytest.fixture
    @patch("src.engine.scheduler.get_config")
    def scheduler(self, mock_get_config):
        """Create a Scheduler instance for testing."""
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        
        s = Scheduler()
        s._scheduler = MagicMock()
        s._task_queue = MagicMock()
        return s
    
    @pytest.mark.asyncio
    async def test_start_scheduler(self, scheduler):
        """Test starting the scheduler."""
        scheduler._task_queue.get_pending_tasks.return_value = []
        
        await scheduler.start()
        
        assert scheduler._running is True
        scheduler._scheduler.start.assert_called_once()
        scheduler._scheduler.add_listener.assert_called()
    
    @pytest.mark.asyncio
    async def test_start_already_running(self, scheduler):
        """Test starting when already running."""
        scheduler._running = True
        
        await scheduler.start()
        
        # Should not start again
        scheduler._scheduler.start.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_stop_scheduler(self, scheduler):
        """Test stopping the scheduler."""
        scheduler._running = True
        
        await scheduler.stop()
        
        assert scheduler._running is False
        scheduler._scheduler.shutdown.assert_called_once_with(wait=True)
    
    @pytest.mark.asyncio
    async def test_stop_not_running(self, scheduler):
        """Test stopping when not running."""
        scheduler._running = False
        
        await scheduler.stop()
        
        # Should not try to shutdown
        scheduler._scheduler.shutdown.assert_not_called()


class TestSchedulerCron:
    """Test Scheduler cron scheduling."""
    
    @pytest.fixture
    @patch("src.engine.scheduler.get_config")
    def scheduler(self, mock_get_config):
        """Create a Scheduler instance for testing."""
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        
        s = Scheduler()
        s._scheduler = MagicMock()
        s._task_queue = MagicMock()
        s._running = True
        s._task_queue.create_task.return_value = "task_id_123"
        return s
    
    @pytest.mark.asyncio
    async def test_schedule_cron_success(self, scheduler):
        """Test scheduling a cron job."""
        job_id = await scheduler.schedule_cron(
            agent_type="Worker",
            action="process",
            params={"path": "/data"},
            cron_expr="0 */6 * * *",
            title="Process data every 6 hours"
        )
        
        assert job_id is not None
        assert job_id in scheduler._jobs
        assert scheduler._jobs[job_id].schedule_type == "cron"
        assert scheduler._jobs[job_id].schedule_expr == "0 */6 * * *"
        scheduler._scheduler.add_job.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_schedule_cron_invalid_expression(self, scheduler):
        """Test scheduling with invalid cron expression."""
        with pytest.raises(ValueError, match="Invalid cron expression"):
            await scheduler.schedule_cron(
                agent_type="Worker",
                action="test",
                params={},
                cron_expr="invalid"
            )


class TestSchedulerInterval:
    """Test Scheduler interval scheduling."""
    
    @pytest.fixture
    @patch("src.engine.scheduler.get_config")
    def scheduler(self, mock_get_config):
        """Create a Scheduler instance for testing."""
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        
        s = Scheduler()
        s._scheduler = MagicMock()
        s._task_queue = MagicMock()
        s._running = True
        s._task_queue.create_task.return_value = "task_id_123"
        return s
    
    @pytest.mark.asyncio
    async def test_schedule_interval_seconds(self, scheduler):
        """Test scheduling interval in seconds."""
        job_id = await scheduler.schedule_interval(
            agent_type="Worker",
            action="check",
            params={},
            seconds=30
        )
        
        assert job_id is not None
        assert scheduler._jobs[job_id].schedule_type == "interval"
        scheduler._scheduler.add_job.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_schedule_interval_minutes(self, scheduler):
        """Test scheduling interval in minutes."""
        job_id = await scheduler.schedule_interval(
            agent_type="Worker",
            action="check",
            params={},
            minutes=5
        )
        
        assert job_id is not None
        scheduler._scheduler.add_job.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_schedule_interval_complex(self, scheduler):
        """Test scheduling interval with multiple units."""
        job_id = await scheduler.schedule_interval(
            agent_type="Worker",
            action="backup",
            params={},
            hours=1,
            minutes=30
        )
        
        assert job_id is not None
        scheduler._scheduler.add_job.assert_called_once()


class TestSchedulerOneTime:
    """Test Scheduler one-time scheduling."""
    
    @pytest.fixture
    @patch("src.engine.scheduler.get_config")
    def scheduler(self, mock_get_config):
        """Create a Scheduler instance for testing."""
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        
        s = Scheduler()
        s._scheduler = MagicMock()
        s._task_queue = MagicMock()
        s._running = True
        s._task_queue.create_task.return_value = "task_id_123"
        return s
    
    @pytest.mark.asyncio
    async def test_schedule_once(self, scheduler):
        """Test scheduling a one-time task."""
        run_at = datetime.now() + timedelta(hours=1)
        
        job_id = await scheduler.schedule_once(
            agent_type="Worker",
            action="cleanup",
            params={"temp": True},
            run_at=run_at
        )
        
        assert job_id is not None
        assert scheduler._jobs[job_id].schedule_type == "date"
        scheduler._scheduler.add_job.assert_called_once()


class TestSchedulerJobManagement:
    """Test Scheduler job management."""
    
    @pytest.fixture
    @patch("src.engine.scheduler.get_config")
    def scheduler(self, mock_get_config):
        """Create a Scheduler instance for testing."""
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        
        s = Scheduler()
        s._scheduler = MagicMock()
        s._task_queue = MagicMock()
        s._running = True
        
        # Add a test job
        s._jobs["job_123"] = ScheduledJob(
            job_id="job_123",
            task_id="task_456",
            agent_type="Worker",
            action="test",
            params={},
            schedule_type="cron",
            schedule_expr="* * * * *"
        )
        
        return s
    
    @pytest.mark.asyncio
    async def test_cancel_job_success(self, scheduler):
        """Test cancelling a job."""
        result = await scheduler.cancel_job("job_123")
        
        assert result is True
        assert "job_123" not in scheduler._jobs
        scheduler._scheduler.remove_job.assert_called_once_with("job_123")
        scheduler._task_queue.cancel_task.assert_called_once_with("task_456")
    
    @pytest.mark.asyncio
    async def test_cancel_job_not_found(self, scheduler):
        """Test cancelling a non-existent job."""
        result = await scheduler.cancel_job("nonexistent")
        
        assert result is False
    
    def test_get_job(self, scheduler):
        """Test getting a job by ID."""
        job = scheduler.get_job("job_123")
        
        assert job is not None
        assert job.job_id == "job_123"
    
    def test_get_job_not_found(self, scheduler):
        """Test getting a non-existent job."""
        job = scheduler.get_job("nonexistent")
        
        assert job is None
    
    def test_list_jobs(self, scheduler):
        """Test listing all jobs."""
        jobs = scheduler.list_jobs()
        
        assert len(jobs) == 1
        assert jobs[0].job_id == "job_123"
    
    @pytest.mark.asyncio
    async def test_pause_job_success(self, scheduler):
        """Test pausing a job."""
        result = await scheduler.pause_job("job_123")
        
        assert result is True
        scheduler._scheduler.pause_job.assert_called_once_with("job_123")
        assert scheduler._jobs["job_123"].enabled is False
    
    @pytest.mark.asyncio
    async def test_pause_job_not_found(self, scheduler):
        """Test pausing a non-existent job."""
        result = await scheduler.pause_job("nonexistent")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_resume_job_success(self, scheduler):
        """Test resuming a paused job."""
        scheduler._jobs["job_123"].enabled = False
        
        result = await scheduler.resume_job("job_123")
        
        assert result is True
        scheduler._scheduler.resume_job.assert_called_once_with("job_123")
        assert scheduler._jobs["job_123"].enabled is True
    
    @pytest.mark.asyncio
    async def test_resume_job_not_found(self, scheduler):
        """Test resuming a non-existent job."""
        result = await scheduler.resume_job("nonexistent")
        
        assert result is False
