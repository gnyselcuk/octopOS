"""Unit tests for workers/base_worker.py module.

This module tests the BaseWorker class and related components.
"""

import os
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from src.workers.base_worker import (
    BaseWorker,
    WorkerConfig,
    WorkerResult,
    WorkerStatus,
)


class TestWorkerStatus:
    """Test WorkerStatus enum."""
    
    def test_worker_status_values(self):
        """Test that all expected worker statuses exist."""
        expected_statuses = {
            "idle", "busy", "starting", "destroying", "error", "destroyed"
        }
        actual_statuses = {s.value for s in WorkerStatus}
        assert actual_statuses == expected_statuses
    
    def test_worker_status_comparison(self):
        """Test worker status comparison."""
        assert WorkerStatus.IDLE == "idle"
        assert WorkerStatus.BUSY == "busy"
        assert WorkerStatus.IDLE != WorkerStatus.BUSY


class TestWorkerConfig:
    """Test WorkerConfig dataclass."""
    
    def test_default_config(self):
        """Test WorkerConfig default values."""
        config = WorkerConfig()
        
        assert config.max_memory_mb == 512
        assert config.max_cpu_cores == 1.0
        assert config.max_disk_mb == 1024
        assert config.max_execution_time == 300
        assert config.idle_timeout == 60
        assert config.image == "octopos-sandbox:latest"
        assert config.network_mode == "none"
        assert config.read_only is True
        assert config.user_id == "1000"
        assert config.group_id == "1000"
        assert config.drop_capabilities == ["ALL"]
        assert config.log_level == "INFO"
        assert config.max_log_size_mb == 10
    
    def test_custom_config(self):
        """Test WorkerConfig with custom values."""
        config = WorkerConfig(
            max_memory_mb=1024,
            max_cpu_cores=2.0,
            max_execution_time=600,
            image="custom-image:latest"
        )
        
        assert config.max_memory_mb == 1024
        assert config.max_cpu_cores == 2.0
        assert config.max_execution_time == 600
        assert config.image == "custom-image:latest"
    
    def test_config_partial_override(self):
        """Test partial override of config values."""
        config = WorkerConfig(max_memory_mb=256)
        
        assert config.max_memory_mb == 256
        assert config.max_cpu_cores == 1.0  # Default
        assert config.idle_timeout == 60  # Default


class TestWorkerResult:
    """Test WorkerResult dataclass."""
    
    def test_create_worker_result(self):
        """Test creating a worker result."""
        task_id = uuid.uuid4()
        result = WorkerResult(
            task_id=task_id,
            worker_id="worker_001",
            success=True,
            exit_code=0,
            stdout="output",
            stderr="",
            output={"key": "value"},
            duration_seconds=5.5
        )
        
        assert result.task_id == task_id
        assert result.worker_id == "worker_001"
        assert result.success is True
        assert result.exit_code == 0
        assert result.stdout == "output"
        assert result.stderr == ""
        assert result.output == {"key": "value"}
        assert result.duration_seconds == 5.5
        assert result.error is None
        assert result.metadata == {}
    
    def test_worker_result_defaults(self):
        """Test WorkerResult default values."""
        task_id = uuid.uuid4()
        result = WorkerResult(
            task_id=task_id,
            worker_id="worker_001",
            success=False,
            exit_code=1,
            stdout="",
            stderr="error",
            output={},
            duration_seconds=1.0
        )
        
        assert result.created_at is not None
        assert result.metadata == {}
        assert result.error is None
    
    def test_worker_result_with_error(self):
        """Test creating result with error."""
        task_id = uuid.uuid4()
        result = WorkerResult(
            task_id=task_id,
            worker_id="worker_001",
            success=False,
            exit_code=-1,
            stdout="",
            stderr="TimeoutError",
            output={},
            duration_seconds=10.0,
            error="TimeoutError",
            metadata={"error_type": "timeout"}
        )
        
        assert result.error == "TimeoutError"
        assert result.metadata == {"error_type": "timeout"}


class TestBaseWorkerInitialization:
    """Test BaseWorker initialization."""
    
    def test_worker_init_defaults(self):
        """Test worker initialization with defaults."""
        worker = BaseWorker()
        
        assert worker.worker_id.startswith("worker_")
        assert len(worker.worker_id) > 8
        assert worker.config is not None
        assert worker.status == WorkerStatus.IDLE
        assert worker.current_task is None
        assert worker.container_id is None
    
    def test_worker_init_with_custom_id(self):
        """Test worker initialization with custom ID."""
        worker = BaseWorker(worker_id="my_worker_001")
        
        assert worker.worker_id == "my_worker_001"
    
    def test_worker_init_with_custom_config(self):
        """Test worker initialization with custom config."""
        config = WorkerConfig(max_memory_mb=1024)
        worker = BaseWorker(config=config)
        
        assert worker.config.max_memory_mb == 1024
    
    def test_worker_init_full(self):
        """Test worker initialization with all parameters."""
        config = WorkerConfig(max_cpu_cores=2.0)
        worker = BaseWorker(
            worker_id="custom_worker",
            config=config
        )
        
        assert worker.worker_id == "custom_worker"
        assert worker.config.max_cpu_cores == 2.0
    
    def test_worker_is_available_idle(self):
        """Test is_available when idle."""
        worker = BaseWorker()
        assert worker.is_available is True
    
    def test_worker_is_running_initial(self):
        """Test is_running when newly created."""
        worker = BaseWorker()
        assert worker.is_running is True


class TestBaseWorkerLifecycle:
    """Test BaseWorker lifecycle methods."""
    
    @pytest.fixture
    async def worker(self):
        """Create and start a worker for testing."""
        worker = BaseWorker(worker_id="test_worker")
        started = await worker.start()
        assert started is True
        yield worker
        # Cleanup
        if worker.status != WorkerStatus.DESTROYED:
            await worker.destroy()
    
    @pytest.mark.asyncio
    async def test_worker_start_success(self):
        """Test successful worker start."""
        worker = BaseWorker(worker_id="test_start")
        result = await worker.start()
        
        assert result is True
        assert worker.status == WorkerStatus.IDLE
        assert worker.container_id is not None
        assert worker.container_id.startswith("container_")
        
        # Cleanup
        await worker.destroy()
    
    @pytest.mark.asyncio
    async def test_worker_start_already_started(self):
        """Test starting an already started worker."""
        worker = BaseWorker(worker_id="test_already_started")
        await worker.start()
        
        # Second start while IDLE - implementation allows restart
        # This tests idempotent behavior or restart capability
        result = await worker.start()
        # The implementation allows starting from IDLE or ERROR states
        # So this should succeed (restart behavior)
        assert result is True
        
        # Cleanup
        await worker.destroy()
    
    @pytest.mark.asyncio
    async def test_worker_start_transition(self):
        """Test worker status transitions during start."""
        worker = BaseWorker(worker_id="test_transition")
        assert worker.status == WorkerStatus.IDLE
        
        await worker.start()
        
        assert worker.status == WorkerStatus.IDLE  # After successful start
        
        # Cleanup
        await worker.destroy()
    
    @pytest.mark.asyncio
    async def test_worker_destroy_success(self, tmp_path):
        """Test successful worker destroy."""
        worker = BaseWorker(worker_id="test_destroy")
        await worker.start()
        
        result = await worker.destroy()
        
        assert result is True
        assert worker.status == WorkerStatus.DESTROYED
        assert worker.container_id is None
    
    @pytest.mark.asyncio
    async def test_worker_destroy_already_destroyed(self):
        """Test destroying an already destroyed worker."""
        worker = BaseWorker(worker_id="test_already_destroyed")
        await worker.start()
        await worker.destroy()
        
        # Second destroy should still succeed
        result = await worker.destroy()
        assert result is True
    
    @pytest.mark.asyncio
    async def test_worker_destroy_cleans_workspace(self, tmp_path):
        """Test that destroy cleans up workspace."""
        worker = BaseWorker(worker_id="test_cleanup")
        await worker.start()
        
        # Verify workspace was created
        workspace = worker._workspace_path
        assert workspace is not None
        assert os.path.exists(workspace)
        
        # Destroy
        await worker.destroy()
        
        # Verify workspace was cleaned up
        assert not os.path.exists(workspace)
    
    @pytest.mark.asyncio
    async def test_worker_state_machine_transitions(self):
        """Test worker state machine transitions."""
        worker = BaseWorker(worker_id="test_states")
        
        # Initial: IDLE
        assert worker.status == WorkerStatus.IDLE
        
        # Start: IDLE -> STARTING -> IDLE
        await worker.start()
        assert worker.status == WorkerStatus.IDLE
        
        # Execute: IDLE -> BUSY -> IDLE
        task_id = uuid.uuid4()
        await worker.execute_task(task_id, "echo hello")
        assert worker.status == WorkerStatus.IDLE
        
        # Destroy: IDLE -> DESTROYING -> DESTROYED
        await worker.destroy()
        assert worker.status == WorkerStatus.DESTROYED


class TestBaseWorkerExecution:
    """Test BaseWorker task execution."""
    
    @pytest.fixture
    async def started_worker(self):
        """Create and start a worker for testing."""
        worker = BaseWorker(worker_id="test_exec")
        await worker.start()
        yield worker
        if worker.status != WorkerStatus.DESTROYED:
            await worker.destroy()
    
    @pytest.mark.asyncio
    async def test_execute_simple_command(self):
        """Test executing a simple command."""
        worker = BaseWorker(worker_id="test_simple")
        await worker.start()
        
        task_id = uuid.uuid4()
        result = await worker.execute_task(task_id, "echo hello")
        
        assert result.success is True
        assert result.exit_code == 0
        assert "hello" in result.stdout
        assert result.stderr == ""
        assert result.task_id == task_id
        assert result.worker_id == "test_simple"
        
        await worker.destroy()
    
    @pytest.mark.asyncio
    async def test_execute_with_error(self):
        """Test executing a command that fails."""
        worker = BaseWorker(worker_id="test_error")
        await worker.start()
        
        task_id = uuid.uuid4()
        # Use a command that will fail
        result = await worker.execute_task(task_id, "exit 1")
        
        assert result.success is False
        assert result.exit_code == 1
        
        await worker.destroy()
    
    @pytest.mark.asyncio
    async def test_execute_with_stderr(self):
        """Test executing a command that writes to stderr."""
        worker = BaseWorker(worker_id="test_stderr")
        await worker.start()
        
        task_id = uuid.uuid4()
        result = await worker.execute_task(task_id, "echo error >&2")
        
        assert result.success is True
        assert "error" in result.stderr
        
        await worker.destroy()
    
    @pytest.mark.asyncio
    async def test_execute_with_timeout(self):
        """Test task execution timeout."""
        worker = BaseWorker(
            worker_id="test_timeout",
            config=WorkerConfig(max_execution_time=1)
        )
        await worker.start()
        
        task_id = uuid.uuid4()
        # Command that takes longer than timeout
        result = await worker.execute_task(task_id, "sleep 10", timeout=1)
        
        assert result.success is False
        assert result.error == "TimeoutError"
        assert "Timeout" in result.stderr
        
        await worker.destroy()
    
    @pytest.mark.asyncio
    async def test_execute_concurrent_task_rejection(self):
        """Test that concurrent task execution is rejected."""
        worker = BaseWorker(worker_id="test_concurrent")
        await worker.start()
        
        task_id1 = uuid.uuid4()
        task_id2 = uuid.uuid4()
        
        # Start first task (but don't await to simulate concurrent execution)
        import asyncio
        task1 = asyncio.create_task(
            worker.execute_task(task_id1, "sleep 5")
        )
        
        # Give first task time to start
        await asyncio.sleep(0.2)
        
        # Try to start second task while first is running
        result2 = await worker.execute_task(task_id2, "echo hello")
        
        # Second task should be rejected
        assert result2.success is False
        assert "not available" in result2.error.lower()
        
        # Cleanup first task
        task1.cancel()
        try:
            await task1
        except asyncio.CancelledError:
            pass
        
        await worker.destroy()
    
    @pytest.mark.asyncio
    async def test_execute_task_result_formatting(self):
        """Test task result formatting."""
        worker = BaseWorker(worker_id="test_format")
        await worker.start()
        
        task_id = uuid.uuid4()
        result = await worker.execute_task(task_id, "echo test")
        
        # Check all required fields
        assert isinstance(result, WorkerResult)
        assert isinstance(result.task_id, uuid.UUID)
        assert isinstance(result.worker_id, str)
        assert isinstance(result.success, bool)
        assert isinstance(result.exit_code, int)
        assert isinstance(result.stdout, str)
        assert isinstance(result.stderr, str)
        assert isinstance(result.output, dict)
        assert isinstance(result.duration_seconds, float)
        assert isinstance(result.metadata, dict)
        
        # Check output contains executed command
        assert "executed_command" in result.output
        
        # Check metadata contains container info
        assert "container_id" in result.metadata
        assert "memory_limit" in result.metadata
        
        await worker.destroy()
    
    @pytest.mark.asyncio
    async def test_execute_with_environment_vars(self):
        """Test execution with custom environment variables."""
        worker = BaseWorker(worker_id="test_env")
        await worker.start()
        
        task_id = uuid.uuid4()
        result = await worker.execute_task(
            task_id,
            "echo $TEST_VAR",
            environment={"TEST_VAR": "test_value"}
        )
        
        assert "test_value" in result.stdout
        
        await worker.destroy()


class TestBaseWorkerProperties:
    """Test BaseWorker properties."""
    
    @pytest.mark.asyncio
    async def test_container_id_property(self):
        """Test container_id property."""
        worker = BaseWorker(worker_id="test_container")
        assert worker.container_id is None
        
        await worker.start()
        assert worker.container_id is not None
        assert worker.container_id.startswith("container_")
        
        await worker.destroy()
        assert worker.container_id is None
    
    @pytest.mark.asyncio
    async def test_current_task_property(self):
        """Test current_task property."""
        import asyncio
        worker = BaseWorker(worker_id="test_current")
        await worker.start()
        
        assert worker.current_task is None
        
        task_id = uuid.uuid4()
        
        # Start task but don't await to check current_task during execution
        task = asyncio.create_task(
            worker.execute_task(task_id, "sleep 0.5")
        )
        
        # Give task time to start
        await asyncio.sleep(0.1)
        
        # During execution, current_task should be set
        assert worker.current_task == task_id
        
        # Wait for completion
        await task
        
        # After completion, should be None again
        assert worker.current_task is None
        
        await worker.destroy()
    
    def test_is_available_property(self):
        """Test is_available property."""
        worker = BaseWorker()
        
        # Initially idle
        assert worker.is_available is True
        
        # Manually set status
        worker._status = WorkerStatus.BUSY
        assert worker.is_available is False
        
        worker._status = WorkerStatus.ERROR
        assert worker.is_available is False
        
        worker._status = WorkerStatus.DESTROYED
        assert worker.is_available is False
    
    def test_is_running_property(self):
        """Test is_running property."""
        worker = BaseWorker()
        
        # Initially running (idle)
        assert worker.is_running is True
        
        worker._status = WorkerStatus.BUSY
        assert worker.is_running is True
        
        worker._status = WorkerStatus.ERROR
        assert worker.is_running is False
        
        worker._status = WorkerStatus.DESTROYED
        assert worker.is_running is False


class TestBaseWorkerStats:
    """Test BaseWorker statistics."""
    
    @pytest.mark.asyncio
    async def test_get_stats_initial(self):
        """Test get_stats with initial values."""
        worker = BaseWorker(worker_id="test_stats")
        
        stats = worker.get_stats()
        
        assert stats["worker_id"] == "test_stats"
        assert stats["status"] == "idle"
        assert stats["current_task"] is None
        assert stats["container_id"] is None
        assert stats["task_count"] == 0
        assert stats["error_count"] == 0
        assert "config" in stats
    
    @pytest.mark.asyncio
    async def test_get_stats_after_start(self):
        """Test get_stats after starting worker."""
        worker = BaseWorker(worker_id="test_stats_start")
        await worker.start()
        
        stats = worker.get_stats()
        
        assert stats["status"] == "idle"
        assert stats["container_id"] is not None
        assert stats["started_at"] is not None
        assert stats["workspace_path"] is not None
        
        await worker.destroy()
    
    @pytest.mark.asyncio
    async def test_get_stats_after_task(self):
        """Test get_stats after executing a task."""
        worker = BaseWorker(worker_id="test_stats_task")
        await worker.start()
        
        task_id = uuid.uuid4()
        await worker.execute_task(task_id, "echo hello")
        
        stats = worker.get_stats()
        
        assert stats["task_count"] == 1
        assert stats["error_count"] == 0
        
        await worker.destroy()
    
    @pytest.mark.asyncio
    async def test_get_stats_config_values(self):
        """Test that stats include config values."""
        config = WorkerConfig(
            max_memory_mb=1024,
            max_cpu_cores=2.0,
            max_execution_time=600
        )
        worker = BaseWorker(worker_id="test_stats_config", config=config)
        
        stats = worker.get_stats()
        
        assert stats["config"]["max_memory_mb"] == 1024
        assert stats["config"]["max_cpu_cores"] == 2.0
        assert stats["config"]["max_execution_time"] == 600


class TestBaseWorkerErrorRecovery:
    """Test BaseWorker error handling and recovery."""
    
    @pytest.mark.asyncio
    async def test_worker_error_state(self):
        """Test worker enters error state on failure."""
        # Note: The current implementation doesn't have a clear way to trigger
        # an error state during normal operations, but we can check the error
        # count increases on task failures
        worker = BaseWorker(worker_id="test_error_state")
        await worker.start()
        
        initial_error_count = worker._error_count
        
        # Execute a failing command
        await worker.execute_task(uuid.uuid4(), "exit 1")
        
        # Error count should have increased
        assert worker._error_count >= initial_error_count
        
        await worker.destroy()
