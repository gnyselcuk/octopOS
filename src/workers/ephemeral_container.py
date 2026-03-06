"""Ephemeral Container - Docker container lifecycle management.

This module implements Docker container management for ephemeral workers,
providing secure container creation, execution, and cleanup.

Example:
    >>> from src.workers import EphemeralContainer, ContainerConfig
    >>> config = ContainerConfig(image="octopos-sandbox:latest", network_mode="none")
    >>> container = EphemeralContainer(config)
    >>> await container.create()
    >>> result = await container.execute("python script.py")
    >>> await container.destroy()
"""

import asyncio
import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from src.utils.logger import get_logger

logger = get_logger()


@dataclass
class ContainerConfig:
    """Configuration for ephemeral container."""
    
    # Image settings
    image: str = "octopos-sandbox:latest"
    pull_policy: str = "if_not_present"  # always, never, if_not_present
    
    # Resource limits
    memory_limit: str = "512m"
    memory_swap: str = "512m"
    cpu_limit: float = 1.0
    cpu_shares: int = 1024
    pids_limit: int = 100
    
    # Storage
    storage_size: str = "1G"
    tmpfs_size: str = "100m"
    
    # Network
    network_mode: str = "none"  # none, bridge, host
    dns_servers: List[str] = field(default_factory=list)
    
    # Security
    user: str = "1000:1000"
    read_only: bool = True
    no_new_privileges: bool = True
    drop_capabilities: List[str] = field(default_factory=lambda: ["ALL"])
    add_capabilities: List[str] = field(default_factory=list)
    security_opt: List[str] = field(default_factory=lambda: ["no-new-privileges:true"])
    
    # Environment
    environment: Dict[str, str] = field(default_factory=dict)
    labels: Dict[str, str] = field(default_factory=dict)
    
    # Volumes
    workspace_path: Optional[str] = None
    
    # Timeouts
    creation_timeout: int = 60
    execution_timeout: int = 300


@dataclass
class ExecutionResult:
    """Result of container execution."""
    
    container_id: str
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    success: bool
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class EphemeralContainer:
    """Manages Docker container lifecycle for ephemeral workers.
    
    Provides secure container creation, command execution, and cleanup.
    All containers run with restricted privileges and resource limits.
    
    Attributes:
        config: ContainerConfig with resource and security settings
        container_id: Docker container ID (set after create())
        workspace_path: Path to workspace volume
    
    Example:
        >>> container = EphemeralContainer(ContainerConfig(network_mode="none"))
        >>> await container.create()
        >>> result = await container.execute("echo 'Hello World'")
        >>> print(result.stdout)  # "Hello World"
        >>> await container.destroy()
    """
    
    def __init__(self, config: Optional[ContainerConfig] = None) -> None:
        """Initialize ephemeral container manager.
        
        Args:
            config: Container configuration (uses defaults if not provided)
        """
        self.config = config or ContainerConfig()
        
        self._container_id: Optional[str] = None
        self._container_name: str = f"octopos-worker-{uuid4().hex[:12]}"
        self._workspace_path: Optional[str] = None
        self._created_at: Optional[str] = None
        
        self._logger = logger
        self._logger.info(f"EphemeralContainer initialized: {self._container_name}")
    
    @property
    def container_id(self) -> Optional[str]:
        """Get Docker container ID."""
        return self._container_id
    
    @property
    def container_name(self) -> str:
        """Get container name."""
        return self._container_name
    
    @property
    def is_running(self) -> bool:
        """Check if container is running."""
        return self._container_id is not None
    
    async def create(self) -> bool:
        """Create and start the container.
        
        Returns:
            True if created successfully
        """
        if self._container_id:
            self._logger.warning(f"Container {self._container_name} already exists")
            return False
        
        try:
            # Create temporary workspace if not specified
            if not self.config.workspace_path:
                self._workspace_path = tempfile.mkdtemp(prefix=f"octopos_{self._container_name}_")
            else:
                self._workspace_path = self.config.workspace_path
                os.makedirs(self._workspace_path, exist_ok=True)
            
            # Create subdirectories
            for subdir in ["input", "output", "temp", "logs"]:
                os.makedirs(os.path.join(self._workspace_path, subdir), exist_ok=True)
            
            # Build docker run command
            cmd = self._build_create_command()
            
            self._logger.info(f"Creating container: {self._container_name}")
            
            # Execute docker create
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.config.creation_timeout
            )
            
            if proc.returncode != 0:
                error_msg = stderr.decode().strip()
                self._logger.error(f"Failed to create container: {error_msg}")
                return False
            
            self._container_id = stdout.decode().strip()
            self._created_at = datetime.utcnow().isoformat()
            
            # Start the container
            start_proc = await asyncio.create_subprocess_exec(
                "docker", "start", self._container_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await start_proc.communicate()
            
            if start_proc.returncode != 0:
                self._logger.error("Failed to start container")
                await self.destroy()
                return False
            
            self._logger.info(f"Container {self._container_name} created: {self._container_id[:12]}")
            
            return True
            
        except asyncio.TimeoutError:
            self._logger.error(f"Container creation timed out after {self.config.creation_timeout}s")
            await self.destroy()
            return False
            
        except Exception as e:
            self._logger.error(f"Failed to create container: {e}")
            await self.destroy()
            return False
    
    def _build_create_command(self) -> List[str]:
        """Build docker create command with security options.
        
        Returns:
            List of command arguments
        """
        cmd = [
            "docker", "create",
            "--name", self._container_name,
            "--hostname", self._container_name,
        ]
        
        # Resource limits
        cmd.extend([
            "--memory", self.config.memory_limit,
            "--memory-swap", self.config.memory_swap,
            "--cpus", str(self.config.cpu_limit),
            "--cpu-shares", str(self.config.cpu_shares),
            "--pids-limit", str(self.config.pids_limit),
            "--storage-opt", f"size={self.config.storage_size}",
        ])
        
        # Network
        if self.config.network_mode == "none":
            cmd.extend(["--network", "none"])
        else:
            cmd.extend(["--network", self.config.network_mode])
        
        # Security options
        cmd.extend([
            "--user", self.config.user,
            "--read-only" if self.config.read_only else "",
            "--security-opt", "no-new-privileges:true",
        ])
        
        # Drop all capabilities
        cmd.extend(["--cap-drop", "ALL"])
        
        # Add specific capabilities if needed
        for cap in self.config.add_capabilities:
            cmd.extend(["--cap-add", cap])
        
        # Additional security options
        for opt in self.config.security_opt:
            cmd.extend(["--security-opt", opt])
        
        # Environment variables
        for key, value in self.config.environment.items():
            cmd.extend(["-e", f"{key}={value}"])
        
        # Labels
        for key, value in self.config.labels.items():
            cmd.extend(["--label", f"{key}={value}"])
        
        # Add octopos labels
        cmd.extend([
            "--label", f"octopos.container_name={self._container_name}",
            "--label", f"octopos.created_at={datetime.utcnow().isoformat()}",
        ])
        
        # Volumes
        if self._workspace_path:
            cmd.extend([
                "-v", f"{self._workspace_path}:/workspace:rw",
                "--tmpfs", f"/tmp:{self.config.tmpfs_size},noexec,nosuid",
            ])
        
        # Remove empty strings from command
        cmd = [arg for arg in cmd if arg]
        
        # Image
        cmd.append(self.config.image)
        
        # Default command (tail to keep container running)
        cmd.extend(["tail", "-f", "/dev/null"])
        
        return cmd
    
    async def execute(
        self,
        command: str,
        environment: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None
    ) -> ExecutionResult:
        """Execute a command in the container.
        
        Args:
            command: Command to execute
            environment: Additional environment variables
            timeout: Override default timeout
            
        Returns:
            ExecutionResult with output and status
        """
        if not self._container_id:
            return ExecutionResult(
                container_id="",
                command=command,
                exit_code=-1,
                stdout="",
                stderr="",
                duration_seconds=0,
                success=False,
                error="Container not created"
            )
        
        start_time = asyncio.get_event_loop().time()
        timeout_val = timeout or self.config.execution_timeout
        
        try:
            self._logger.info(f"Executing in {self._container_name}: {command[:50]}...")
            
            # Build exec command
            exec_cmd = ["docker", "exec"]
            
            # Add environment variables
            if environment:
                for key, value in environment.items():
                    exec_cmd.extend(["-e", f"{key}={value}"])
            
            exec_cmd.extend([self._container_id, "/bin/bash", "-c", command])
            
            # Execute command
            proc = await asyncio.create_subprocess_exec(
                *exec_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout_val
                )
                
                duration = asyncio.get_event_loop().time() - start_time
                
                return ExecutionResult(
                    container_id=self._container_id,
                    command=command,
                    exit_code=proc.returncode or 0,
                    stdout=stdout.decode('utf-8', errors='replace'),
                    stderr=stderr.decode('utf-8', errors='replace'),
                    duration_seconds=duration,
                    success=proc.returncode == 0,
                    metadata={
                        "container_name": self._container_name,
                        "workspace": self._workspace_path
                    }
                )
                
            except asyncio.TimeoutError:
                # Kill the process
                proc.kill()
                await proc.communicate()
                
                duration = asyncio.get_event_loop().time() - start_time
                
                self._logger.error(f"Command timed out after {timeout_val}s")
                
                return ExecutionResult(
                    container_id=self._container_id,
                    command=command,
                    exit_code=-1,
                    stdout="",
                    stderr="",
                    duration_seconds=duration,
                    success=False,
                    error=f"Timeout after {timeout_val}s"
                )
                
        except Exception as e:
            duration = asyncio.get_event_loop().time() - start_time
            
            self._logger.error(f"Execution failed: {e}")
            
            return ExecutionResult(
                container_id=self._container_id or "",
                command=command,
                exit_code=-1,
                stdout="",
                stderr=str(e),
                duration_seconds=duration,
                success=False,
                error=str(e)
            )
    
    async def destroy(self) -> bool:
        """Destroy the container and cleanup.
        
        Returns:
            True if destroyed successfully
        """
        if not self._container_id:
            return True
        
        try:
            self._logger.info(f"Destroying container: {self._container_name}")
            
            # Stop container (force after 10 seconds)
            stop_proc = await asyncio.create_subprocess_exec(
                "docker", "stop", "-t", "10", self._container_id,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await stop_proc.communicate()
            
            # Remove container
            rm_proc = await asyncio.create_subprocess_exec(
                "docker", "rm", "-f", "-v", self._container_id,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await rm_proc.communicate()
            
            # Cleanup workspace
            if self._workspace_path and os.path.exists(self._workspace_path):
                import shutil
                shutil.rmtree(self._workspace_path, ignore_errors=True)
            
            self._container_id = None
            self._workspace_path = None
            
            self._logger.info(f"Container {self._container_name} destroyed")
            
            return True
            
        except Exception as e:
            self._logger.error(f"Failed to destroy container: {e}")
            return False
    
    async def get_logs(self, tail: int = 100) -> str:
        """Get container logs.
        
        Args:
            tail: Number of lines to return
            
        Returns:
            Log output
        """
        if not self._container_id:
            return ""
        
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "logs", "--tail", str(tail), self._container_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT
            )
            
            stdout, _ = await proc.communicate()
            return stdout.decode('utf-8', errors='replace')
            
        except Exception as e:
            self._logger.error(f"Failed to get logs: {e}")
            return ""
    
    async def copy_to(self, source: str, dest: str) -> bool:
        """Copy file into container.
        
        Args:
            source: Source path on host
            dest: Destination path in container
            
        Returns:
            True if successful
        """
        if not self._container_id:
            return False
        
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "cp", source, f"{self._container_id}:{dest}",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE
            )
            
            _, stderr = await proc.communicate()
            
            if proc.returncode != 0:
                self._logger.error(f"Failed to copy file: {stderr.decode()}")
                return False
            
            return True
            
        except Exception as e:
            self._logger.error(f"Failed to copy file: {e}")
            return False
    
    async def copy_from(self, source: str, dest: str) -> bool:
        """Copy file from container.
        
        Args:
            source: Source path in container
            dest: Destination path on host
            
        Returns:
            True if successful
        """
        if not self._container_id:
            return False
        
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "cp", f"{self._container_id}:{source}", dest,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE
            )
            
            _, stderr = await proc.communicate()
            
            if proc.returncode != 0:
                self._logger.error(f"Failed to copy file: {stderr.decode()}")
                return False
            
            return True
            
        except Exception as e:
            self._logger.error(f"Failed to copy file: {e}")
            return False
    
    def get_info(self) -> Dict[str, Any]:
        """Get container information.
        
        Returns:
            Container info dictionary
        """
        return {
            "container_id": self._container_id,
            "container_name": self._container_name,
            "workspace_path": self._workspace_path,
            "created_at": self._created_at,
            "config": {
                "image": self.config.image,
                "network_mode": self.config.network_mode,
                "memory_limit": self.config.memory_limit,
                "cpu_limit": self.config.cpu_limit,
            }
        }
