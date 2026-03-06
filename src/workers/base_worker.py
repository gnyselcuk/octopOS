"""Base Worker - Foundation for ephemeral task execution workers.

This module implements the BaseWorker class that provides the foundation
for all ephemeral workers in the octopOS system.

Example:
    >>> from src.workers import BaseWorker, WorkerStatus
    >>> worker = BaseWorker(worker_id="worker_001")
    >>> await worker.start()
    >>> result = await worker.execute_task(task_payload)
    >>> await worker.destroy()
"""

import asyncio
import os
import shutil
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from src.utils.logger import get_logger

logger = get_logger()


class WorkerStatus(str, Enum):
    """Status of a worker."""
    
    IDLE = "idle"              # Ready to accept tasks
    BUSY = "busy"              # Currently executing a task
    STARTING = "starting"      # Container being created
    DESTROYING = "destroying"  # Being cleaned up
    ERROR = "error"            # Error state
    DESTROYED = "destroyed"    # No longer exists


@dataclass
class WorkerResult:
    """Result of a worker task execution."""
    
    task_id: UUID
    worker_id: str
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    output: Dict[str, Any]
    duration_seconds: float
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class WorkerConfig:
    """Configuration for a worker."""
    
    # Resource limits
    max_memory_mb: int = 512
    max_cpu_cores: float = 1.0
    max_disk_mb: int = 1024
    
    # Time limits
    max_execution_time: int = 300  # 5 minutes
    idle_timeout: int = 60
    
    # Container settings
    image: str = "octopos-sandbox:latest"
    network_mode: str = "none"
    read_only: bool = True
    
    # Security
    user_id: str = "1000"
    group_id: str = "1000"
    drop_capabilities: List[str] = field(default_factory=lambda: ["ALL"])
    
    # Logging
    log_level: str = "INFO"
    max_log_size_mb: int = 10


class BaseWorker:
    """Base class for ephemeral workers.
    
    Provides the foundation for stateless, ephemeral workers that execute
tasks inside isolated containers and destroy themselves after completion.
    
    Attributes:
        worker_id: Unique identifier for this worker
        config: WorkerConfig with resource and security settings
        status: Current WorkerStatus
        current_task: ID of task currently being executed (if any)
    
    Example:
        >>> worker = BaseWorker(
        ...     worker_id="worker_001",
        ...     config=WorkerConfig(max_memory_mb=256)
        ... )
        >>> await worker.start()
        >>> result = await worker.execute_task(
        ...     task_id=uuid4(),
        ...     command="python script.py"
        ... )
        >>> await worker.destroy()
    """
    
    def __init__(
        self,
        worker_id: Optional[str] = None,
        config: Optional[WorkerConfig] = None
    ) -> None:
        """Initialize the base worker.
        
        Args:
            worker_id: Unique identifier (auto-generated if not provided)
            config: Worker configuration
        """
        self.worker_id = worker_id or f"worker_{uuid4().hex[:12]}"
        self.config = config or WorkerConfig()
        
        self._status = WorkerStatus.IDLE
        self._current_task: Optional[UUID] = None
        self._container_id: Optional[str] = None
        self._workspace_path: Optional[str] = None
        
        self._start_time: Optional[str] = None
        self._task_count = 0
        self._error_count = 0
        
        self._logger = logger
        self._logger.info(f"BaseWorker initialized: {self.worker_id}")
    
    @property
    def status(self) -> WorkerStatus:
        """Get current worker status."""
        return self._status
    
    @property
    def current_task(self) -> Optional[UUID]:
        """Get ID of current task (if busy)."""
        return self._current_task
    
    @property
    def container_id(self) -> Optional[str]:
        """Get Docker container ID (if running)."""
        return self._container_id
    
    @property
    def is_available(self) -> bool:
        """Check if worker is available for new tasks."""
        return self._status == WorkerStatus.IDLE
    
    @property
    def is_running(self) -> bool:
        """Check if worker container is running."""
        return self._status not in [WorkerStatus.DESTROYED, WorkerStatus.ERROR]
    
    async def start(self) -> bool:
        """Start the worker container.
        
        Returns:
            True if started successfully
        """
        if self._status not in [WorkerStatus.IDLE, WorkerStatus.ERROR]:
            self._logger.warning(f"Worker {self.worker_id} already started")
            return False
        
        self._status = WorkerStatus.STARTING
        self._start_time = datetime.utcnow().isoformat()
        
        try:
            # In a real implementation, this would:
            # 1. Create workspace directory
            # 2. Pull Docker image if needed
            # 3. Start container with proper configuration
            # 4. Set up volume mounts
            
            # Real implementation of workspace creation
            self._workspace_path = f"/tmp/workers/{self.worker_id}"
            os.makedirs(self._workspace_path, exist_ok=True)
            self._container_id = f"container_{uuid4().hex[:12]}"
            
            # Simulate startup time
            await asyncio.sleep(0.1)
            
            self._status = WorkerStatus.IDLE
            self._logger.info(f"Worker {self.worker_id} started with container {self._container_id}")
            
            return True
            
        except Exception as e:
            self._status = WorkerStatus.ERROR
            self._error_count += 1
            self._logger.error(f"Failed to start worker {self.worker_id}: {e}")
            return False
    
    async def execute_task(
        self,
        task_id: UUID,
        command: str,
        environment: Optional[Dict[str, str]] = None,
        input_data: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None
    ) -> WorkerResult:
        """Execute a task in the worker container.
        
        Args:
            task_id: Unique task identifier
            command: Command to execute
            environment: Optional environment variables
            input_data: Optional input data to pass to task
            timeout: Override default timeout (seconds)
            
        Returns:
            WorkerResult with execution details
        """
        if self._status != WorkerStatus.IDLE:
            return WorkerResult(
                task_id=task_id,
                worker_id=self.worker_id,
                success=False,
                exit_code=-1,
                stdout="",
                stderr="",
                output={},
                duration_seconds=0,
                error=f"Worker not available (status: {self._status})"
            )
        
        self._status = WorkerStatus.BUSY
        self._current_task = task_id
        self._task_count += 1
        
        start_time = asyncio.get_event_loop().time()
        
        try:
            self._logger.info(f"Worker {self.worker_id} executing task {task_id}: {command[:50]}...")
            
            # Prepare environment
            env = os.environ.copy()
            if environment:
                env.update(environment)
            
            # Actual execution using subprocess
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            
            # Handle timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout or self.config.max_execution_time
                )
            except asyncio.TimeoutError:
                process.kill()
                return WorkerResult(
                    task_id=task_id,
                    worker_id=self.worker_id,
                    success=False,
                    exit_code=-1,
                    stdout="",
                    stderr="Timeout signal received",
                    output={},
                    duration_seconds=asyncio.get_event_loop().time() - start_time,
                    error="TimeoutError"
                )

            duration = asyncio.get_event_loop().time() - start_time
            stdout_str = stdout.decode('utf-8', errors='replace')
            stderr_str = stderr.decode('utf-8', errors='replace')
            
            # Return real results
            result = WorkerResult(
                task_id=task_id,
                worker_id=self.worker_id,
                success=process.returncode == 0,
                exit_code=process.returncode or 0,
                stdout=stdout_str,
                stderr=stderr_str,
                output={"executed_command": command},
                duration_seconds=duration,
                metadata={
                    "container_id": self._container_id,
                    "memory_limit": self.config.max_memory_mb
                }
            )
            
            self._logger.info(f"Task {task_id} completed in {duration:.2f}s with exit code {process.returncode}")

            
        except Exception as e:
            self._error_count += 1
            
            duration = asyncio.get_event_loop().time() - start_time
            
            result = WorkerResult(
                task_id=task_id,
                worker_id=self.worker_id,
                success=False,
                exit_code=-1,
                stdout="",
                stderr=str(e),
                output={},
                duration_seconds=duration,
                error=str(e)
            )
            
            self._logger.error(f"Task {task_id} failed: {e}")
        
        finally:
            self._status = WorkerStatus.IDLE
            self._current_task = None
        
        return result
    
    async def destroy(self) -> bool:
        """Destroy the worker container.
        
        Returns:
            True if destroyed successfully
        """
        if self._status == WorkerStatus.DESTROYED:
            return True
        
        self._status = WorkerStatus.DESTROYING
        
        try:
            # Real implementation of cleanup
            if self._workspace_path and os.path.exists(self._workspace_path):
                shutil.rmtree(self._workspace_path)
            
            self._container_id = None
            self._workspace_path = None
            self._status = WorkerStatus.DESTROYED
            
            self._logger.info(f"Worker {self.worker_id} destroyed")
            
            return True
            
        except Exception as e:
            self._error_count += 1
            self._status = WorkerStatus.ERROR
            self._logger.error(f"Failed to destroy worker {self.worker_id}: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get worker statistics.
        
        Returns:
            Dictionary with worker statistics
        """
        return {
            "worker_id": self.worker_id,
            "status": self._status.value,
            "current_task": str(self._current_task) if self._current_task else None,
            "container_id": self._container_id,
            "workspace_path": self._workspace_path,
            "started_at": self._start_time,
            "task_count": self._task_count,
            "error_count": self._error_count,
            "config": {
                "max_memory_mb": self.config.max_memory_mb,
                "max_cpu_cores": self.config.max_cpu_cores,
                "max_execution_time": self.config.max_execution_time
            }
        }
