"""Bash Executor - Sandboxed command execution primitive.

This module provides secure command execution within Docker containers
or approved local directories. It integrates with the existing Worker Pool
and Ephemeral Container infrastructure.

Example:
    >>> from src.primitives.native.bash_executor import BashExecutor
    >>> executor = BashExecutor()
    >>> result = await executor.execute(
    ...     command="ls -la",
    ...     working_dir="/workspace"
    ... )
"""

import re
import shlex
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass
from pathlib import Path

from src.primitives.base_primitive import BasePrimitive, PrimitiveResult, register_primitive
from src.workers.worker_pool import get_worker_pool, WorkerPool
from src.utils.config import get_config
from src.utils.logger import get_logger

logger = get_logger()


@dataclass
class CommandConstraints:
    """Security constraints for command execution."""
    max_timeout: int = 300  # 5 minutes
    max_output_size: int = 10 * 1024 * 1024  # 10MB
    allowed_paths: Optional[List[str]] = None
    blocked_commands: Optional[Set[str]] = None
    network_enabled: bool = False


class BashExecutor(BasePrimitive):
    """Execute bash commands in sandboxed environment.
    
    This primitive provides secure command execution by:
    1. Running commands in ephemeral Docker containers (default)
    2. Validating commands against allow/block lists
    3. Enforcing timeouts and output limits
    4. Restricting filesystem access to approved paths
    
    Attributes:
        use_docker: Whether to use Docker sandbox (True) or local execution (False)
        constraints: Security constraints for execution
    """
    
    # Dangerous commands that are blocked by default
    DEFAULT_BLOCKED_COMMANDS = {
        # File destruction
        'rm', 'rmdir', 'mkfs', 'fdisk', 'dd',
        'format', 'del', 'erase', 'shred',
        # Fork bombs and resource exhaustion
        ':(){ :|:& };:',  # Fork bomb
        'yes',  # Resource exhaustion
        # System control
        'shutdown', 'reboot', 'halt', 'poweroff', 'init',
        # Process control
        'kill', 'pkill', 'killall', 'xkill',
        # Network (can be used for data exfiltration)
        'nc', 'netcat', 'ncat', 'socat',
        'telnet', 'ftp', 'sftp', 'scp',
        # Privilege escalation
        'sudo', 'su', 'chmod', 'chown', 'chgrp',
    }
    
    # Commands that require extra validation
    SENSITIVE_COMMANDS = {
        'curl', 'wget', 'fetch', 'nc', 'netcat',
        'ssh', 'scp', 'sftp', 'telnet',
        'mysql', 'psql', 'mongo', 'redis-cli',
    }
    
    def __init__(
        self,
        use_docker: bool = True,
        constraints: Optional[CommandConstraints] = None
    ) -> None:
        """Initialize the Bash Executor.
        
        Args:
            use_docker: Whether to use Docker sandbox (recommended)
            constraints: Security constraints (uses defaults if None)
        """
        super().__init__()
        self.use_docker = use_docker
        self.constraints = constraints or self._default_constraints()
        self._worker_pool: Optional[WorkerPool] = None
        
    def _default_constraints(self) -> CommandConstraints:
        """Get default constraints from config."""
        config = get_config()
        
        # Get allowed paths from config or use defaults
        allowed_paths = getattr(config, 'bash_executor_allowed_paths', None)
        if allowed_paths is None:
            allowed_paths = [
                str(Path.home() / 'workspace'),
                '/tmp',
                '/workspace'
            ]
        
        return CommandConstraints(
            max_timeout=getattr(config, 'bash_executor_timeout', 300),
            max_output_size=getattr(config, 'bash_executor_max_output', 10 * 1024 * 1024),
            allowed_paths=allowed_paths,
            blocked_commands=self.DEFAULT_BLOCKED_COMMANDS,
            network_enabled=getattr(config, 'bash_executor_network', False)
        )
    
    @property
    def name(self) -> str:
        return "bash_execute"
    
    @property
    def description(self) -> str:
        return (
            "Execute bash commands in a sandboxed environment. "
            "Commands run in isolated Docker containers with resource limits. "
            "Use for building, testing, or system administration tasks."
        )
    
    @property
    def parameters(self) -> Dict[str, Dict[str, Any]]:
        return {
            "command": {
                "type": "string",
                "description": "The bash command to execute",
                "required": True
            },
            "working_dir": {
                "type": "string",
                "description": "Working directory for command execution",
                "required": False,
                "default": "/workspace"
            },
            "timeout": {
                "type": "integer",
                "description": "Maximum execution time in seconds (default: 300)",
                "required": False,
                "default": 300
            },
            "environment": {
                "type": "object",
                "description": "Environment variables to set",
                "required": False,
                "default": {}
            },
            "capture_output": {
                "type": "boolean",
                "description": "Whether to capture stdout/stderr",
                "required": False,
                "default": True
            }
        }
    
    async def execute(self, **kwargs) -> PrimitiveResult:
        """Execute a bash command.
        
        Args:
            command: The command to execute
            working_dir: Working directory (default: /workspace)
            timeout: Timeout in seconds (default: 300)
            environment: Environment variables dict
            capture_output: Whether to capture output
            
        Returns:
            PrimitiveResult with execution results
        """
        command = kwargs.get("command", "").strip()
        working_dir = kwargs.get("working_dir", "/workspace")
        timeout = kwargs.get("timeout", self.constraints.max_timeout)
        environment = kwargs.get("environment", {})
        capture_output = kwargs.get("capture_output", True)
        
        # Validate command
        valid, error = self._validate_command(command)
        if not valid:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Command validation failed: {error}",
                error=error
            )
        
        # Sanitize timeout
        timeout = min(timeout, self.constraints.max_timeout)
        
        try:
            if self.use_docker:
                return await self._execute_in_docker(
                    command, working_dir, timeout, environment, capture_output
                )
            else:
                return await self._execute_local(
                    command, working_dir, timeout, environment, capture_output
                )
                
        except Exception as e:
            logger.error(f"Bash execution error: {e}")
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Execution failed: {e}",
                error=str(e)
            )
    
    def _validate_command(self, command: str) -> tuple[bool, Optional[str]]:
        """Validate command for security.
        
        Args:
            command: Command to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not command:
            return False, "Empty command"
        
        # Check for obvious injection attempts
        dangerous_patterns = [
            # Command substitution
            r'\$\(',           
            r'`[^`]*`',        # Backtick substitution
            # Process substitution
            r'\$\{?\w+\}?\|\s*\w+',
            # Piping to shells
            r'\|\s*bash',     
            r'\|\s*sh',       
            r'\|\s*zsh',
            # Dangerous functions
            r'\beval\s',         
            r'\bexec\s',         
            # Output redirection
            r'>&/dev/',
            r'>>/dev/',
            r'</dev/',
            # File destruction
            r'rm\s+-rf\s+/',
            r'rmdir\s+',
            # Command chaining (potential bypass)
            r'&&\s*\w+',
            r'\|\|\s*\w+',
            r';\s*\w+',
            # Network connections
            r'\bcurl\s+',
            r'\bwget\s+',
            # Process control
            r'\bkill\s+',
            r'\bpkill\s+',
            # Privilege escalation
            r'\bsudo\s+',
            r'\bchmod\s+777',
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return False, f"Command contains dangerous pattern: {pattern}"
        
        # Parse command to check for blocked commands
        try:
            tokens = shlex.split(command)
            if not tokens:
                return False, "Empty command after parsing"
            
            base_cmd = tokens[0].split('/')[-1]  # Get command name without path
            
            # Check blocked commands
            if base_cmd in self.constraints.blocked_commands:
                return False, f"Command '{base_cmd}' is blocked for security"
            
            # Warn about sensitive commands
            if base_cmd in self.SENSITIVE_COMMANDS:
                logger.warning(f"Sensitive command used: {base_cmd}")
            
        except ValueError as e:
            return False, f"Failed to parse command: {e}"
        
        return True, None
    
    async def _execute_in_docker(
        self,
        command: str,
        working_dir: str,
        timeout: int,
        environment: Dict[str, str],
        capture_output: bool
    ) -> PrimitiveResult:
        """Execute command in Docker sandbox.
        
        Uses the Worker Pool to spawn ephemeral containers.
        """
        try:
            # Get or initialize worker pool
            if self._worker_pool is None:
                self._worker_pool = get_worker_pool()
            
            # Prepare task for worker (this line was not used, removed as per instruction)
            
            # Execute via worker pool
            worker_result = await self._worker_pool.execute_task(
                command=command,
                working_dir=working_dir,
                environment=environment,
                timeout=timeout
            )
            
            # Handle worker result
            if not worker_result.success:
                return PrimitiveResult(
                    success=False,
                    data=None,
                    message=f"Worker execution failed: {worker_result.error}",
                    error=worker_result.error
                )
            
            # Truncate output if too large
            stdout = worker_result.stdout
            stderr = worker_result.stderr
            
            total_size = len(stdout) + len(stderr)
            if total_size > self.constraints.max_output_size:
                stdout = stdout[:self.constraints.max_output_size // 2]
                stderr = stderr[:self.constraints.max_output_size // 2]
                truncated = True
            else:
                truncated = False
            
            return PrimitiveResult(
                success=worker_result.exit_code == 0,
                data={
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": worker_result.exit_code,
                    "truncated": truncated
                },
                message=f"Command executed (exit code: {worker_result.exit_code})",
                metadata={
                    "duration_seconds": worker_result.duration_seconds,
                    "worker_id": worker_result.worker_id
                }
            )
                
        except Exception as e:
            logger.error(f"Docker execution error: {e}")
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Docker execution failed: {e}",
                error=str(e)
            )
    
    async def _execute_local(
        self,
        command: str,
        working_dir: str,
        timeout: int,
        environment: Dict[str, str],
        capture_output: bool
    ) -> PrimitiveResult:
        """Execute command locally (fallback mode).
        
        Only allowed if working_dir is in allowed_paths.
        """
        import subprocess
        import os
        
        # Validate working directory
        working_path = Path(working_dir).resolve()
        allowed = False
        
        for allowed_path_str in self.constraints.allowed_paths:
            allowed_path = Path(allowed_path_str).resolve()
            try:
                working_path.relative_to(allowed_path)
                allowed = True
                break
            except ValueError:
                continue
        
        if not allowed:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Working directory '{working_dir}' is not in allowed paths",
                error="PathNotAllowed"
            )
        
        # Ensure directory exists
        working_path.mkdir(parents=True, exist_ok=True)
        
        try:
            # Prepare environment
            env = os.environ.copy()
            env.update(environment)
            
            # Execute command
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE if capture_output else None,
                stderr=asyncio.subprocess.PIPE if capture_output else None,
                cwd=str(working_path),
                env=env
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return PrimitiveResult(
                    success=False,
                    data=None,
                    message=f"Command timed out after {timeout} seconds",
                    error="TimeoutError"
                )
            
            # Decode output
            stdout_str = stdout.decode('utf-8', errors='replace') if stdout else ""
            stderr_str = stderr.decode('utf-8', errors='replace') if stderr else ""
            
            # Check output size
            total_size = len(stdout_str) + len(stderr_str)
            truncated = total_size > self.constraints.max_output_size
            
            if truncated:
                stdout_str = stdout_str[:self.constraints.max_output_size // 2]
                stderr_str = stderr_str[:self.constraints.max_output_size // 2]
            
            return PrimitiveResult(
                success=process.returncode == 0,
                data={
                    "stdout": stdout_str,
                    "stderr": stderr_str,
                    "exit_code": process.returncode,
                    "truncated": truncated
                },
                message=f"Command executed (exit code: {process.returncode})"
            )
            
        except Exception as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Local execution failed: {e}",
                error=str(e)
            )


# Import asyncio for local execution
import asyncio


def register_all() -> None:
    """Register all native bash primitives."""
    register_primitive(BashExecutor())
