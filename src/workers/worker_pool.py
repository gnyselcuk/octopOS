"""Worker Pool - Manages pool of ephemeral workers.

This module implements worker pool management for scaling and
coordinating multiple ephemeral container-based workers.

Example:
    >>> from src.workers import WorkerPool, PoolConfig
    >>> config = PoolConfig(max_workers=5)
    >>> pool = WorkerPool(config)
    >>> await pool.initialize()
    >>> worker = await pool.get_worker()
    >>> result = await pool.execute_task(worker.worker_id, task)
    >>> await pool.return_worker(worker.worker_id)
    >>> await pool.shutdown()
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from uuid import UUID, uuid4

from src.workers.base_worker import BaseWorker, WorkerConfig, WorkerResult, WorkerStatus
from src.workers.ephemeral_container import ContainerConfig, EphemeralContainer
from src.utils.logger import get_logger

logger = get_logger()


@dataclass
class PoolConfig:
    """Configuration for worker pool."""
    
    # Pool size
    min_workers: int = 1
    max_workers: int = 10
    idle_timeout: int = 300  # Seconds before idle worker is destroyed
    
    # Scaling
    scale_up_threshold: float = 0.8  # Scale up when 80% workers busy
    scale_down_threshold: float = 0.3  # Scale down when 30% workers busy
    scale_cooldown: int = 60  # Seconds between scaling operations
    
    # Container config
    container_config: ContainerConfig = field(default_factory=ContainerConfig)
    
    # Worker config
    worker_config: WorkerConfig = field(default_factory=WorkerConfig)
    
    # Health
    health_check_interval: int = 30
    max_task_failures: int = 3
    
    # Queue
    max_queue_size: int = 100
    queue_timeout: int = 60


@dataclass
class WorkerInfo:
    """Information about a worker in the pool."""
    
    worker_id: str
    worker: BaseWorker
    status: WorkerStatus
    created_at: str
    last_used: str
    task_count: int = 0
    error_count: int = 0
    current_task: Optional[UUID] = None


class WorkerPool:
    """Manages a pool of ephemeral workers for task execution.
    
    Provides automatic scaling, health monitoring, and task distribution
    across multiple container-based workers.
    
    Example:
        >>> pool = WorkerPool(PoolConfig(max_workers=5))
        >>> await pool.initialize()
        >>> 
        >>> # Get a worker for task execution
        >>> worker_id = await pool.acquire_worker()
        >>> result = await pool.execute_on_worker(worker_id, "python script.py")
        >>> await pool.release_worker(worker_id)
        >>> 
        >>> # Or use the convenience method
        >>> result = await pool.execute_task("python script.py")
        >>> 
        >>> await pool.shutdown()
    """
    
    def __init__(self, config: Optional[PoolConfig] = None) -> None:
        """Initialize worker pool.
        
        Args:
            config: Pool configuration
        """
        self.config = config or PoolConfig()
        
        self._workers: Dict[str, WorkerInfo] = {}
        self._available_workers: Set[str] = set()
        self._busy_workers: Set[str] = set()
        
        self._task_queue: asyncio.Queue = asyncio.Queue(
            maxsize=self.config.max_queue_size
        )
        self._shutdown: bool = False
        
        self._scaling_lock = asyncio.Lock()
        self._last_scale_time: Optional[str] = None
        
        self._health_check_task: Optional[asyncio.Task] = None
        self._scaling_task: Optional[asyncio.Task] = None
        self._processing_task: Optional[asyncio.Task] = None
        
        self._logger = logger
        self._logger.info(f"WorkerPool initialized (max: {self.config.max_workers})")
    
    async def initialize(self) -> bool:
        """Initialize the pool with minimum workers.
        
        Returns:
            True if initialized successfully
        """
        self._logger.info(f"Initializing pool with {self.config.min_workers} workers")
        
        # Create minimum workers
        for _ in range(self.config.min_workers):
            await self._create_worker()
        
        # Start background tasks
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        self._scaling_task = asyncio.create_task(self._scaling_loop())
        self._processing_task = asyncio.create_task(self._process_task_queue())
        
        self._logger.info("WorkerPool initialized and ready")
        return True
    
    async def shutdown(self) -> None:
        """Shutdown the pool and cleanup all workers."""
        self._logger.info("Shutting down WorkerPool")
        self._shutdown = True
        
        # Cancel background tasks
        for task in [self._health_check_task, self._scaling_task, self._processing_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Destroy all workers
        destroy_tasks = [
            worker_info.worker.destroy()
            for worker_info in self._workers.values()
        ]
        
        if destroy_tasks:
            await asyncio.gather(*destroy_tasks, return_exceptions=True)
        
        self._workers.clear()
        self._available_workers.clear()
        self._busy_workers.clear()
        
        self._logger.info("WorkerPool shutdown complete")
    
    async def _create_worker(self) -> Optional[str]:
        """Create a new worker.
        
        Returns:
            Worker ID if created, None otherwise
        """
        if len(self._workers) >= self.config.max_workers:
            return None
        
        try:
            worker = BaseWorker(config=self.config.worker_config)
            
            if await worker.start():
                worker_info = WorkerInfo(
                    worker_id=worker.worker_id,
                    worker=worker,
                    status=WorkerStatus.IDLE,
                    created_at=datetime.utcnow().isoformat(),
                    last_used=datetime.utcnow().isoformat()
                )
                
                self._workers[worker.worker_id] = worker_info
                self._available_workers.add(worker.worker_id)
                
                self._logger.info(f"Created worker: {worker.worker_id}")
                return worker.worker_id
            else:
                self._logger.error(f"Failed to start worker")
                return None
                
        except Exception as e:
            self._logger.error(f"Failed to create worker: {e}")
            return None
    
    async def _destroy_worker(self, worker_id: str) -> bool:
        """Destroy a specific worker.
        
        Args:
            worker_id: Worker to destroy
            
        Returns:
            True if destroyed successfully
        """
        if worker_id not in self._workers:
            return False
        
        worker_info = self._workers[worker_id]
        
        try:
            await worker_info.worker.destroy()
            
            del self._workers[worker_id]
            self._available_workers.discard(worker_id)
            self._busy_workers.discard(worker_id)
            
            self._logger.info(f"Destroyed worker: {worker_id}")
            return True
            
        except Exception as e:
            self._logger.error(f"Failed to destroy worker {worker_id}: {e}")
            return False
    
    async def acquire_worker(self, timeout: float = 30.0) -> Optional[str]:
        """Acquire a worker from the pool.
        
        Args:
            timeout: Maximum time to wait for a worker
            
        Returns:
            Worker ID if acquired, None if timeout
        """
        start_time = asyncio.get_event_loop().time()
        
        while True:
            # Check for available worker
            if self._available_workers:
                worker_id = self._available_workers.pop()
                worker_info = self._workers[worker_id]
                
                if worker_info.worker.is_running:
                    worker_info.status = WorkerStatus.BUSY
                    worker_info.last_used = datetime.utcnow().isoformat()
                    self._busy_workers.add(worker_id)
                    
                    return worker_id
                else:
                    # Worker died, remove it
                    await self._destroy_worker(worker_id)
            
            # Try to create new worker if under max
            if len(self._workers) < self.config.max_workers:
                worker_id = await self._create_worker()
                if worker_id:
                    self._available_workers.discard(worker_id)
                    self._busy_workers.add(worker_id)
                    self._workers[worker_id].status = WorkerStatus.BUSY
                    return worker_id
            
            # Check timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                self._logger.warning("Timeout waiting for available worker")
                return None
            
            # Wait and retry
            await asyncio.sleep(0.1)
    
    async def release_worker(self, worker_id: str) -> bool:
        """Release a worker back to the pool.
        
        Args:
            worker_id: Worker to release
            
        Returns:
            True if released successfully
        """
        if worker_id not in self._workers:
            return False
        
        if worker_id not in self._busy_workers:
            return False
        
        worker_info = self._workers[worker_id]
        worker_info.status = WorkerStatus.IDLE
        worker_info.last_used = datetime.utcnow().isoformat()
        
        self._busy_workers.discard(worker_id)
        self._available_workers.add(worker_id)
        
        return True
    
    async def execute_on_worker(
        self,
        worker_id: str,
        command: str,
        task_id: Optional[UUID] = None,
        timeout: Optional[int] = None,
        environment: Optional[Dict[str, str]] = None,
        working_dir: Optional[str] = None
    ) -> WorkerResult:
        """Execute a command on a specific worker.
        
        Args:
            worker_id: Worker to use
            command: Command to execute
            task_id: Optional task ID
            timeout: Execution timeout
            environment: Optional environment variables
            working_dir: Optional working directory
            
        Returns:
            WorkerResult with execution results
        """
        task_id = task_id or uuid4()
        
        if worker_id not in self._workers:
            return WorkerResult(
                task_id=task_id,
                worker_id=worker_id,
                success=False,
                exit_code=-1,
                stdout="",
                stderr="",
                output={},
                duration_seconds=0,
                error="Worker not found"
            )
        
        worker_info = self._workers[worker_id]
        
        try:
            # Map working_dir to environment or task payload 
            # In BaseWorker, execute_task doesn't take working_dir yet, but it can be prepended to command or passed in environment
            
            result = await worker_info.worker.execute_task(
                task_id=task_id,
                command=command,
                environment=environment,
                timeout=timeout
            )
            
            # Update stats
            worker_info.task_count += 1
            if not result.success:
                worker_info.error_count += 1
            
            return result
            
        except Exception as e:
            worker_info.error_count += 1
            
            return WorkerResult(
                task_id=task_id,
                worker_id=worker_id,
                success=False,
                exit_code=-1,
                stdout="",
                stderr=str(e),
                output={},
                duration_seconds=0,
                error=str(e)
            )
    
    async def execute_task(
        self,
        command: str,
        task_id: Optional[UUID] = None,
        timeout: Optional[int] = None,
        wait_for_worker: float = 30.0,
        environment: Optional[Dict[str, str]] = None,
        working_dir: Optional[str] = None
    ) -> WorkerResult:
        """Execute a task using a worker from the pool.
        
        Args:
            command: Command to execute
            task_id: Optional task ID
            timeout: Execution timeout
            wait_for_worker: Timeout wait for worker
            environment: Optional environment variables
            working_dir: Optional working directory
            
        Returns:
            WorkerResult with execution results
        """
        task_id = task_id or uuid4()
        
        # Acquire worker
        worker_id = await self.acquire_worker(timeout=wait_for_worker)
        
        if not worker_id:
            return WorkerResult(
                task_id=task_id,
                worker_id="",
                success=False,
                exit_code=-1,
                stdout="",
                stderr="",
                output={},
                duration_seconds=0,
                error="No worker available"
            )
        
        try:
            # Execute task
            result = await self.execute_on_worker(
                worker_id=worker_id,
                command=command,
                task_id=task_id,
                timeout=timeout,
                environment=environment,
                working_dir=working_dir
            )
            
            return result
            
        finally:
            # Always release worker
            await self.release_worker(worker_id)
    
    async def _health_check_loop(self) -> None:
        """Background task for health checking workers."""
        while not self._shutdown:
            try:
                await asyncio.sleep(self.config.health_check_interval)
                
                dead_workers = []
                
                for worker_id, worker_info in self._workers.items():
                    # Check if worker is still running
                    if not worker_info.worker.is_running:
                        dead_workers.append(worker_id)
                        continue
                    
                    # Check for workers with too many errors
                    if worker_info.error_count >= self.config.max_task_failures:
                        self._logger.warning(
                            f"Worker {worker_id} has too many errors, marking for removal"
                        )
                        dead_workers.append(worker_id)
                        continue
                    
                    # Check for idle timeout
                    if worker_id in self._available_workers:
                        last_used = datetime.fromisoformat(worker_info.last_used)
                        idle_time = (datetime.utcnow() - last_used).total_seconds()
                        
                        if idle_time > self.config.idle_timeout:
                            if len(self._workers) > self.config.min_workers:
                                dead_workers.append(worker_id)
                
                # Remove dead workers
                for worker_id in dead_workers:
                    await self._destroy_worker(worker_id)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Health check error: {e}")
    
    async def _scaling_loop(self) -> None:
        """Background task for auto-scaling workers."""
        while not self._shutdown:
            try:
                await asyncio.sleep(self.config.scale_cooldown)
                
                async with self._scaling_lock:
                    total_workers = len(self._workers)
                    busy_workers = len(self._busy_workers)
                    utilization = busy_workers / total_workers if total_workers > 0 else 0
                    
                    # Scale up
                    if utilization >= self.config.scale_up_threshold:
                        if total_workers < self.config.max_workers:
                            workers_to_add = min(
                                2,  # Add at most 2 at a time
                                self.config.max_workers - total_workers
                            )
                            
                            self._logger.info(f"Scaling up: adding {workers_to_add} workers")
                            
                            for _ in range(workers_to_add):
                                await self._create_worker()
                    
                    # Scale down
                    elif utilization <= self.config.scale_down_threshold:
                        available = len(self._available_workers)
                        
                        if available > 0 and total_workers > self.config.min_workers:
                            workers_to_remove = min(
                                available,
                                total_workers - self.config.min_workers
                            )
                            
                            self._logger.info(f"Scaling down: removing {workers_to_remove} workers")
                            
                            for _ in range(workers_to_remove):
                                if self._available_workers:
                                    worker_id = self._available_workers.pop()
                                    await self._destroy_worker(worker_id)
                                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Scaling error: {e}")
    
    async def _process_task_queue(self) -> None:
        """Background task for processing queued tasks."""
        while not self._shutdown:
            try:
                # Get task from queue (with timeout to allow checking shutdown)
                try:
                    task = await asyncio.wait_for(
                        self._task_queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                # Execute task
                await self.execute_task(
                    command=task["command"],
                    task_id=task.get("task_id"),
                    timeout=task.get("timeout")
                )
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Task processing error: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics.
        
        Returns:
            Pool statistics dictionary
        """
        total_workers = len(self._workers)
        available = len(self._available_workers)
        busy = len(self._busy_workers)
        
        return {
            "total_workers": total_workers,
            "available_workers": available,
            "busy_workers": busy,
            "utilization": busy / total_workers if total_workers > 0 else 0,
            "queue_size": self._task_queue.qsize(),
            "config": {
                "min_workers": self.config.min_workers,
                "max_workers": self.config.max_workers
            }
        }


# Singleton instance
_pool_instance: Optional[WorkerPool] = None


def get_worker_pool(config: Optional[PoolConfig] = None) -> WorkerPool:
    """Get or create singleton WorkerPool instance.
    
    Args:
        config: Pool configuration (only used on first call)
        
    Returns:
        WorkerPool singleton
    """
    global _pool_instance
    if _pool_instance is None:
        _pool_instance = WorkerPool(config)
    return _pool_instance
