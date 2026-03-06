"""Unit tests for workers/ephemeral_container.py module.

This module tests the EphemeralContainer class for Docker container management.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock

from src.workers.ephemeral_container import (
    ContainerConfig,
    EphemeralContainer,
    ExecutionResult,
)


class TestContainerConfig:
    """Test ContainerConfig dataclass."""
    
    def test_default_config(self):
        """Test ContainerConfig default values."""
        config = ContainerConfig()
        
        assert config.image == "octopos-sandbox:latest"
        assert config.pull_policy == "if_not_present"
        assert config.memory_limit == "512m"
        assert config.memory_swap == "512m"
        assert config.cpu_limit == 1.0
        assert config.cpu_shares == 1024
        assert config.pids_limit == 100
        assert config.network_mode == "none"
        assert config.user == "1000:1000"
        assert config.read_only is True
        assert config.no_new_privileges is True
        assert config.drop_capabilities == ["ALL"]
    
    def test_custom_config(self):
        """Test ContainerConfig with custom values."""
        config = ContainerConfig(
            image="custom-image:latest",
            memory_limit="1g",
            cpu_limit=2.0,
            network_mode="bridge"
        )
        
        assert config.image == "custom-image:latest"
        assert config.memory_limit == "1g"
        assert config.cpu_limit == 2.0
        assert config.network_mode == "bridge"


class TestExecutionResult:
    """Test ExecutionResult dataclass."""
    
    def test_create_execution_result(self):
        """Test creating an execution result."""
        result = ExecutionResult(
            container_id="abc123",
            command="echo hello",
            exit_code=0,
            stdout="hello",
            stderr="",
            duration_seconds=1.5,
            success=True
        )
        
        assert result.container_id == "abc123"
        assert result.command == "echo hello"
        assert result.exit_code == 0
        assert result.stdout == "hello"
        assert result.stderr == ""
        assert result.duration_seconds == 1.5
        assert result.success is True
        assert result.error is None
    
    def test_execution_result_failure(self):
        """Test creating a failed execution result."""
        result = ExecutionResult(
            container_id="abc123",
            command="exit 1",
            exit_code=1,
            stdout="",
            stderr="error",
            duration_seconds=0.5,
            success=False,
            error="Command failed"
        )
        
        assert result.success is False
        assert result.error == "Command failed"


class TestEphemeralContainerInitialization:
    """Test EphemeralContainer initialization."""
    
    def test_init_defaults(self):
        """Test initialization with defaults."""
        container = EphemeralContainer()
        
        assert container.config.image == "octopos-sandbox:latest"
        assert container._container_id is None
        assert container._container_name.startswith("octopos-worker-")
        assert container._workspace_path is None
    
    def test_init_custom_config(self):
        """Test initialization with custom config."""
        config = ContainerConfig(image="custom:latest")
        container = EphemeralContainer(config=config)
        
        assert container.config.image == "custom:latest"
    
    def test_container_id_property(self):
        """Test container_id property."""
        container = EphemeralContainer()
        assert container.container_id is None
        
        container._container_id = "test_id"
        assert container.container_id == "test_id"
    
    def test_container_name_property(self):
        """Test container_name property."""
        container = EphemeralContainer()
        assert container.container_name.startswith("octopos-worker-")
    
    def test_is_running_property(self):
        """Test is_running property."""
        container = EphemeralContainer()
        assert container.is_running is False
        
        container._container_id = "test_id"
        assert container.is_running is True


class TestEphemeralContainerCreate:
    """Test EphemeralContainer create method."""
    
    @pytest.fixture
    def container(self):
        """Create an EphemeralContainer for testing."""
        return EphemeralContainer()
    
    @pytest.mark.asyncio
    async def test_create_success(self, container, tmp_path):
        """Test successful container creation."""
        container.config.workspace_path = str(tmp_path)
        
        # Mock subprocess
        mock_proc_create = MagicMock()
        mock_proc_create.returncode = 0
        mock_proc_create.communicate = AsyncMock(return_value=(b"container_id_123\n", b""))
        
        mock_proc_start = MagicMock()
        mock_proc_start.returncode = 0
        mock_proc_start.communicate = AsyncMock(return_value=(b"", b""))
        
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_subprocess.side_effect = [mock_proc_create, mock_proc_start]
            
            result = await container.create()
            
            assert result is True
            assert container._container_id == "container_id_123"
            assert container._workspace_path is not None
    
    @pytest.mark.asyncio
    async def test_create_already_exists(self, container):
        """Test create when container already exists."""
        container._container_id = "existing_id"
        
        result = await container.create()
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_create_failure(self, container):
        """Test container creation failure."""
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"Error creating container"))
        
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await container.create()
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_create_timeout(self, container):
        """Test container creation timeout."""
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await container.create()
            
            assert result is False


class TestEphemeralContainerBuildCommand:
    """Test EphemeralContainer command building."""
    
    @pytest.fixture
    def container(self):
        """Create an EphemeralContainer for testing."""
        config = ContainerConfig(
            image="test-image",
            memory_limit="1g",
            cpu_limit=2.0,
            network_mode="none",
            user="1000:1000",
            read_only=True
        )
        return EphemeralContainer(config=config)
    
    def test_build_create_command_basic(self, container):
        """Test building basic create command."""
        container._workspace_path = "/tmp/test_workspace"
        cmd = container._build_create_command()
        
        assert "docker" in cmd
        assert "create" in cmd
        assert "--name" in cmd
        assert container._container_name in cmd
        assert "--memory" in cmd
        assert "1g" in cmd
        assert "--cpus" in cmd
        assert "2.0" in cmd
        assert "--network" in cmd
        assert "none" in cmd
    
    def test_build_create_command_security(self, container):
        """Test security options in create command."""
        container._workspace_path = "/tmp/test_workspace"
        cmd = container._build_create_command()
        
        assert "--user" in cmd
        assert "1000:1000" in cmd
        assert "--read-only" in cmd
        assert "--security-opt" in cmd
        assert "no-new-privileges:true" in cmd
        assert "--cap-drop" in cmd
        assert "ALL" in cmd


class TestEphemeralContainerExecute:
    """Test EphemeralContainer execute method."""
    
    @pytest.fixture
    def container(self):
        """Create an EphemeralContainer for testing."""
        c = EphemeralContainer()
        c._container_id = "test_container_id"
        c._container_name = "test_container"
        return c
    
    @pytest.mark.asyncio
    async def test_execute_success(self, container):
        """Test successful command execution."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"hello world\n", b""))
        
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await container.execute("echo hello world")
            
            assert result.success is True
            assert result.exit_code == 0
            assert result.stdout == "hello world\n"
            assert result.stderr == ""
            assert result.container_id == "test_container_id"
    
    @pytest.mark.asyncio
    async def test_execute_failure(self, container):
        """Test command execution failure."""
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"error message"))
        
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await container.execute("exit 1")
            
            assert result.success is False
            assert result.exit_code == 1
            assert result.stderr == "error message"
    
    @pytest.mark.asyncio
    async def test_execute_no_container(self):
        """Test execution without container created."""
        container = EphemeralContainer()
        # No container_id set
        
        result = await container.execute("echo test")
        
        assert result.success is False
        assert result.error == "Container not created"
    
    @pytest.mark.asyncio
    async def test_execute_timeout(self, container):
        """Test command execution timeout."""
        mock_proc = MagicMock()
        mock_proc.kill = MagicMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await container.execute("sleep 10", timeout=1)
            
            assert result.success is False
            assert "Timeout" in result.error
            mock_proc.kill.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_with_environment(self, container):
        """Test execution with environment variables."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_subprocess:
            await container.execute("echo test", environment={"VAR": "value"})
            
            # Check that environment variable was passed
            call_args = mock_subprocess.call_args[0]
            assert "-e" in call_args
            assert "VAR=value" in call_args


class TestEphemeralContainerDestroy:
    """Test EphemeralContainer destroy method."""
    
    @pytest.fixture
    def container(self, tmp_path):
        """Create an EphemeralContainer for testing."""
        c = EphemeralContainer()
        c._container_id = "test_container_id"
        c._workspace_path = str(tmp_path / "workspace")
        return c
    
    @pytest.mark.asyncio
    async def test_destroy_success(self, container):
        """Test successful container destruction."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await container.destroy()
            
            assert result is True
            assert container._container_id is None
            assert container._workspace_path is None
    
    @pytest.mark.asyncio
    async def test_destroy_no_container(self):
        """Test destroy when no container exists."""
        container = EphemeralContainer()
        
        result = await container.destroy()
        
        assert result is True  # Already destroyed
    
    @pytest.mark.asyncio
    async def test_destroy_failure(self, container):
        """Test container destruction failure."""
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"Error"))
        
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await container.destroy()
            
            # Should still return True if we tried to clean up
            assert result is True


class TestEphemeralContainerLogs:
    """Test EphemeralContainer logs method."""
    
    @pytest.fixture
    def container(self):
        """Create an EphemeralContainer for testing."""
        c = EphemeralContainer()
        c._container_id = "test_container_id"
        return c
    
    @pytest.mark.asyncio
    async def test_get_logs_success(self, container):
        """Test getting container logs."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"log line 1\nlog line 2\n", b""))
        
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            logs = await container.get_logs(tail=10)
            
            assert "log line 1" in logs
            assert "log line 2" in logs
    
    @pytest.mark.asyncio
    async def test_get_logs_failure(self, container):
        """Test getting logs failure."""
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"Error"))
        
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            logs = await container.get_logs()
            
            assert logs == ""  # Empty on error
    
    @pytest.mark.asyncio
    async def test_get_logs_no_container(self):
        """Test getting logs without container."""
        container = EphemeralContainer()
        
        logs = await container.get_logs()
        
        assert logs == ""


class TestEphemeralContainerCopy:
    """Test EphemeralContainer file copy methods."""
    
    @pytest.fixture
    def container(self):
        """Create an EphemeralContainer for testing."""
        c = EphemeralContainer()
        c._container_id = "test_container_id"
        c._workspace_path = "/tmp/workspace"
        return c
    
    @pytest.mark.asyncio
    async def test_copy_to_container_success(self, container, tmp_path):
        """Test copying file to container."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")
        
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await container.copy_to_container(
                str(test_file),
                "/workspace/test.txt"
            )
            
            assert result is True
    
    @pytest.mark.asyncio
    async def test_copy_from_container_success(self, container, tmp_path):
        """Test copying file from container."""
        dest_file = tmp_path / "output.txt"
        
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await container.copy_from_container(
                "/workspace/output.txt",
                str(dest_file)
            )
            
            assert result is True
