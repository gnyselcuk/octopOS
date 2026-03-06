"""Unit tests for workers/worker_pool.py module.

This module tests the WorkerPool class for managing pools of workers.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock

from src.workers.worker_pool import (
    PoolConfig,
    WorkerInfo,
    WorkerPool,
)
from src.workers.base_worker import WorkerStatus


class TestPoolConfig:
    """Test PoolConfig dataclass."""
    
    def test_default_config(self):
        """Test PoolConfig default values."""
        config = PoolConfig()
        
        assert config.min_workers == 1
        assert config.max_workers == 10
        assert config.idle_timeout == 300
        assert config.scale_up_threshold == 0.8
        assert config.scale_down_threshold == 0.3
        assert config.scale_cooldown == 60
        assert config.health_check_interval == 30
        assert config.max_task_failures == 3
        assert config.max_queue_size == 100
    
    def test_custom_config(self):
        """Test PoolConfig with custom values."""
        config = PoolConfig(
            min_workers=2,
            max_workers=20,
            scale_up_threshold=0.9
        )
        
        assert config.min_workers == 2
        assert config.max_workers == 20
        assert config.scale_up_threshold == 0.9


class TestWorkerInfo:
    """Test WorkerInfo dataclass."""
    
    def test_create_worker_info(self):
        """Test creating WorkerInfo."""
        mock_worker = MagicMock()
        info = WorkerInfo(
            worker_id="worker_123",
            worker=mock_worker,
            status=WorkerStatus.IDLE,
            created_at="2024-01-01T00:00:00",
            last_used="2024-01-01T01:00:00",
            task_count=5,
            error_count=1,
            current_task=None
        )
        
        assert info.worker_id == "worker_123"
        assert info.worker is mock_worker
        assert info.status == WorkerStatus.IDLE
        assert info.task_count == 5
        assert info.error_count == 1


class TestWorkerPoolInitialization:
    """Test WorkerPool initialization."""
    
    @patch("src.workers.worker_pool.get_config")
    def test_pool_init_defaults(self, mock_get_config):
        """Test WorkerPool initialization with defaults."""
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        
        pool = WorkerPool()
        
        assert pool.config.min_workers == 1
        assert pool.config.max_workers == 10
        assert pool._workers == {}
        assert pool._available_workers == set()
        assert pool._busy_workers == set()
        assert pool._shutdown is False
    
    @patch("src.workers.worker_pool.get_config")
    def test_pool_init_custom_config(self, mock_get_config):
        """Test WorkerPool initialization with custom config."""
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        
        custom_config = PoolConfig(min_workers=5, max_workers=50)
        pool = WorkerPool(config=custom_config)
        
        assert pool.config.min_workers == 5
        assert pool.config.max_workers == 50


class TestWorkerPoolLifecycle:
    """Test WorkerPool lifecycle methods."""
    
    @pytest.fixture
    @patch("src.workers.worker_pool.get_config")
    def pool(self, mock_get_config):
        """Create a WorkerPool for testing."""
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        
        p = WorkerPool(PoolConfig(min_workers=1, max_workers=3))
        return p
    
    @pytest.mark.asyncio
    async def test_initialize_creates_min_workers(self, pool):
        """Test initialize creates minimum workers."""
        with patch.object(pool, '_create_worker', new_callable=AsyncMock) as mock_create:
            await pool.initialize()
            
            assert mock_create.call_count == pool.config.min_workers
            assert pool._health_check_task is not None
            assert pool._scaling_task is not None
    
    @pytest.mark.asyncio
    async def test_shutdown_cleans_up_workers(self, pool):
        """Test shutdown cleans up all workers."""
        # Add mock workers
        mock_worker = MagicMock()
        mock_worker.destroy = AsyncMock()
        
        pool._workers["worker_1"] = WorkerInfo(
            worker_id="worker_1",
            worker=mock_worker,
            status=WorkerStatus.IDLE,
            created_at="2024-01-01",
            last_used="2024-01-01"
        )
        
        await pool.shutdown()
        
        assert pool._shutdown is True
        mock_worker.destroy.assert_called_once()
        assert len(pool._workers) == 0


class TestWorkerPoolWorkerManagement:
    """Test WorkerPool worker management."""
    
    @pytest.fixture
    @patch("src.workers.worker_pool.get_config")
    def pool(self, mock_get_config):
        """Create a WorkerPool for testing."""
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        
        return WorkerPool(PoolConfig(min_workers=1, max_workers=3))
    
    @pytest.mark.asyncio
    async def test_create_worker_success(self, pool):
        """Test successful worker creation."""
        with patch("src.workers.worker_pool.BaseWorker") as mock_worker_class:
            mock_worker = MagicMock()
            mock_worker.worker_id = "worker_123"
            mock_worker.start = AsyncMock(return_value=True)
            mock_worker.is_running = True
            mock_worker_class.return_value = mock_worker
            
            worker_id = await pool._create_worker()
            
            assert worker_id == "worker_123"
            assert worker_id in pool._workers
            assert worker_id in pool._available_workers
    
    @pytest.mark.asyncio
    async def test_create_worker_max_reached(self, pool):
        """Test worker creation when max reached."""
        # Fill pool to max
        pool._workers = {"1": MagicMock(), "2": MagicMock(), "3": MagicMock()}
        
        worker_id = await pool._create_worker()
        
        assert worker_id is None
    
    @pytest.mark.asyncio
    async def test_create_worker_start_failure(self, pool):
        """Test worker creation when start fails."""
        with patch("src.workers.worker_pool.BaseWorker") as mock_worker_class:
            mock_worker = MagicMock()
            mock_worker.start = AsyncMock(return_value=False)
            mock_worker_class.return_value = mock_worker
            
            worker_id = await pool._create_worker()
            
            assert worker_id is None
    
    @pytest.mark.asyncio
    async def test_destroy_worker_success(self, pool):
        """Test successful worker destruction."""
        mock_worker = MagicMock()
        mock_worker.destroy = AsyncMock(return_value=True)
        
        pool._workers["worker_1"] = WorkerInfo(
            worker_id="worker_1",
            worker=mock_worker,
            status=WorkerStatus.IDLE,
            created_at="2024-01-01",
            last_used="2024-01-01"
        )
        pool._available_workers.add("worker_1")
        
        result = await pool._destroy_worker("worker_1")
        
        assert result is True
        assert "worker_1" not in pool._workers
        assert "worker_1" not in pool._available_workers
    
    @pytest.mark.asyncio
    async def test_destroy_worker_not_found(self, pool):
        """Test destroying non-existent worker."""
        result = await pool._destroy_worker("nonexistent")
        
        assert result is False


class TestWorkerPoolAcquireRelease:
    """Test WorkerPool acquire and release."""
    
    @pytest.fixture
    @patch("src.workers.worker_pool.get_config")
    def pool(self, mock_get_config):
        """Create a WorkerPool for testing."""
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        
        p = WorkerPool(PoolConfig(min_workers=1, max_workers=3))
        
        # Add available worker
        mock_worker = MagicMock()
        mock_worker.is_running = True
        p._workers["worker_1"] = WorkerInfo(
            worker_id="worker_1",
            worker=mock_worker,
            status=WorkerStatus.IDLE,
            created_at="2024-01-01",
            last_used="2024-01-01"
        )
        p._available_workers.add("worker_1")
        
        return p
    
    @pytest.mark.asyncio
    async def test_acquire_worker_success(self, pool):
        """Test acquiring a worker."""
        worker_id = await pool.acquire_worker()
        
        assert worker_id == "worker_1"
        assert worker_id not in pool._available_workers
        assert worker_id in pool._busy_workers
        assert pool._workers[worker_id].status == WorkerStatus.BUSY
    
    @pytest.mark.asyncio
    async def test_acquire_worker_timeout(self, pool):
        """Test acquiring worker with timeout."""
        # Remove all workers
        pool._available_workers.clear()
        pool._workers.clear()
        
        worker_id = await pool.acquire_worker(timeout=0.1)
        
        assert worker_id is None
    
    @pytest.mark.asyncio
    async def test_release_worker_success(self, pool):
        """Test releasing a worker."""
        # First acquire
        worker_id = await pool.acquire_worker()
        
        # Then release
        pool.release_worker(worker_id)
        
        assert worker_id in pool._available_workers
        assert worker_id not in pool._busy_workers
        assert pool._workers[worker_id].status == WorkerStatus.IDLE
    
    def test_release_worker_not_found(self, pool):
        """Test releasing non-existent worker."""
        # Should not raise error
        pool.release_worker("nonexistent")


class TestWorkerPoolScaling:
    """Test WorkerPool scaling."""
    
    @pytest.fixture
    @patch("src.workers.worker_pool.get_config")
    def pool(self, mock_get_config):
        """Create a WorkerPool for testing."""
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        
        p = WorkerPool(PoolConfig(min_workers=1, max_workers=5))
        return p
    
    @pytest.mark.asyncio
    async def test_scale_up_needed(self, pool):
        """Test scale up when busy threshold exceeded."""
        # Fill with busy workers (above 80% threshold)
        for i in range(4):
            mock_worker = MagicMock()
            mock_worker.is_running = True
            pool._workers[f"worker_{i}"] = WorkerInfo(
                worker_id=f"worker_{i}",
                worker=mock_worker,
                status=WorkerStatus.BUSY,
                created_at="2024-01-01",
                last_used="2024-01-01"
            )
            pool._busy_workers.add(f"worker_{i}")
        
        with patch.object(pool, '_create_worker', new_callable=AsyncMock) as mock_create:
            await pool._scale()
            
            # Should scale up
            assert mock_create.called
    
    @pytest.mark.asyncio
    async def test_scale_down_needed(self, pool):
        """Test scale down when below threshold."""
        # Add idle workers above minimum
        for i in range(3):
            mock_worker = MagicMock()
            mock_worker.is_running = True
            pool._workers[f"worker_{i}"] = WorkerInfo(
                worker_id=f"worker_{i}",
                worker=mock_worker,
                status=WorkerStatus.IDLE,
                created_at="2024-01-01",
                last_used="2024-01-01"
            )
            pool._available_workers.add(f"worker_{i}")
        
        with patch.object(pool, '_destroy_worker', new_callable=AsyncMock) as mock_destroy:
            await pool._scale()
            
            # Should scale down to min_workers
            assert mock_destroy.called
    
    @pytest.mark.asyncio
    async def test_scale_respects_cooldown(self, pool):
        """Test scaling respects cooldown period."""
        from datetime import datetime
        pool._last_scale_time = datetime.utcnow().isoformat()
        
        with patch.object(pool, '_create_worker') as mock_create:
            await pool._scale()
            
            # Should not scale due to cooldown
            assert not mock_create.called


class TestWorkerPoolHealthChecks:
    """Test WorkerPool health checking."""
    
    @pytest.fixture
    @patch("src.workers.worker_pool.get_config")
    def pool(self, mock_get_config):
        """Create a WorkerPool for testing."""
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        
        p = WorkerPool(PoolConfig(min_workers=1, max_workers=3))
        
        # Add a worker
        mock_worker = MagicMock()
        mock_worker.is_running = True
        p._workers["worker_1"] = WorkerInfo(
            worker_id="worker_1",
            worker=mock_worker,
            status=WorkerStatus.IDLE,
            created_at="2024-01-01",
            last_used="2024-01-01"
        )
        p._available_workers.add("worker_1")
        
        return p
    
    @pytest.mark.asyncio
    async def test_health_check_detects_unhealthy(self, pool):
        """Test health check detects unhealthy workers."""
        # Make worker unhealthy
        pool._workers["worker_1"].worker.is_running = False
        
        with patch.object(pool, '_destroy_worker', new_callable=AsyncMock) as mock_destroy:
            with patch.object(pool, '_create_worker', new_callable=AsyncMock) as mock_create:
                await pool._check_health()
                
                # Should destroy and recreate
                mock_destroy.assert_called_once_with("worker_1")
                mock_create.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_health_check_replaces_failed_workers(self, pool):
        """Test health check replaces workers with too many failures."""
        pool._workers["worker_1"].error_count = 5  # Above max_task_failures
        
        with patch.object(pool, '_destroy_worker', new_callable=AsyncMock) as mock_destroy:
            with patch.object(pool, '_create_worker', new_callable=AsyncMock) as mock_create:
                await pool._check_health()
                
                mock_destroy.assert_called_once_with("worker_1")
                mock_create.assert_called_once()


class TestWorkerPoolStats:
    """Test WorkerPool statistics."""
    
    @pytest.fixture
    @patch("src.workers.worker_pool.get_config")
    def pool(self, mock_get_config):
        """Create a WorkerPool for testing."""
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        
        p = WorkerPool(PoolConfig(min_workers=1, max_workers=5))
        
        # Add workers
        for i in range(3):
            mock_worker = MagicMock()
            mock_worker.is_running = True
            p._workers[f"worker_{i}"] = WorkerInfo(
                worker_id=f"worker_{i}",
                worker=mock_worker,
                status=WorkerStatus.IDLE if i < 2 else WorkerStatus.BUSY,
                created_at="2024-01-01",
                last_used="2024-01-01",
                task_count=i
            )
            if i < 2:
                p._available_workers.add(f"worker_{i}")
            else:
                p._busy_workers.add(f"worker_{i}")
        
        return p
    
    def test_get_stats(self, pool):
        """Test getting pool statistics."""
        stats = pool.get_stats()
        
        assert stats["total_workers"] == 3
        assert stats["available_workers"] == 2
        assert stats["busy_workers"] == 1
        assert stats["utilization"] == 1/3
        assert stats["config"]["min_workers"] == 1
        assert stats["config"]["max_workers"] == 5
    
    def test_get_worker_stats(self, pool):
        """Test getting individual worker stats."""
        worker_stats = pool.get_worker_stats()
        
        assert len(worker_stats) == 3
        assert worker_stats[0]["worker_id"] == "worker_0"
        assert worker_stats[0]["status"] == "idle"
