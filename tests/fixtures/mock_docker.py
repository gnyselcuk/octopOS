"""Mock Docker client for testing.

This module provides mock implementations of Docker client
used for container management in octopOS.
"""

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock


class MockDockerContainer:
    """Mock Docker container."""
    
    def __init__(
        self,
        container_id: str = "mock_container_id",
        status: str = "created",
        exit_code: int = 0,
        stdout: str = "",
        stderr: str = ""
    ):
        """Initialize mock container.
        
        Args:
            container_id: Container ID
            status: Container status
            exit_code: Exit code
            stdout: Standard output
            stderr: Standard error
        """
        self.id = container_id
        self.status = status
        self._exit_code = exit_code
        self._stdout = stdout
        self._stderr = stderr
        self.attrs = {
            "State": {
                "Status": status,
                "ExitCode": exit_code,
                "Running": status == "running",
            },
            "Config": {
                "Image": "mock_image",
                "Cmd": ["mock_cmd"],
            }
        }
        self._started = False
        self._removed = False
    
    def start(self) -> None:
        """Mock start container."""
        self.status = "running"
        self.attrs["State"]["Status"] = "running"
        self.attrs["State"]["Running"] = True
        self._started = True
    
    def stop(self, timeout: int = 10) -> None:
        """Mock stop container."""
        self.status = "exited"
        self.attrs["State"]["Status"] = "exited"
        self.attrs["State"]["Running"] = False
    
    def remove(self, force: bool = False) -> None:
        """Mock remove container."""
        self._removed = True
        self.status = "removed"
    
    def wait(self) -> Dict[str, Any]:
        """Mock wait for container."""
        return {"StatusCode": self._exit_code}
    
    def exec_run(
        self,
        cmd: List[str],
        **kwargs
    ) -> tuple:
        """Mock exec_run method.
        
        Returns:
            Tuple of (exit_code, output)
        """
        return (self._exit_code, self._stdout)
    
    def logs(self, **kwargs) -> bytes:
        """Mock logs method."""
        return self._stdout.encode() if self._stdout else b""
    
    def reload(self) -> None:
        """Mock reload container info."""
        pass


class MockDockerImage:
    """Mock Docker image."""
    
    def __init__(self, image_id: str = "mock_image_id", tags: Optional[List[str]] = None):
        """Initialize mock image.
        
        Args:
            image_id: Image ID
            tags: Image tags
        """
        self.id = image_id
        self.tags = tags or ["mock_image:latest"]
        self.attrs = {
            "Id": image_id,
            "RepoTags": self.tags,
            "Size": 1000000,
        }


class MockDockerClient:
    """Mock Docker client."""
    
    def __init__(self):
        """Initialize mock Docker client."""
        self.containers = MockContainerCollection()
        self.images = MockImageCollection()
        self.networks = MockNetworkCollection()
        self.volumes = MockVolumeCollection()
    
    def close(self) -> None:
        """Mock close client."""
        pass
    
    def ping(self) -> bool:
        """Mock ping Docker daemon."""
        return True
    
    def version(self) -> Dict[str, Any]:
        """Mock get Docker version."""
        return {
            "Version": "24.0.0",
            "ApiVersion": "1.43",
            "GitCommit": "mock"
        }


class MockContainerCollection:
    """Mock Docker containers collection."""
    
    def __init__(self):
        """Initialize mock container collection."""
        self._containers: Dict[str, MockDockerContainer] = {}
    
    def run(
        self,
        image: str,
        command: Optional[List[str]] = None,
        **kwargs
    ) -> MockDockerContainer:
        """Mock run container.
        
        Args:
            image: Image name
            command: Command to run
            **kwargs: Additional run options
            
        Returns:
            Mock container instance
        """
        container_id = f"container_{len(self._containers)}"
        container = MockDockerContainer(container_id=container_id)
        self._containers[container_id] = container
        
        # Auto-start if detach=True
        if kwargs.get("detach", False):
            container.start()
        
        return container
    
    def get(self, container_id: str) -> MockDockerContainer:
        """Mock get container by ID.
        
        Args:
            container_id: Container ID
            
        Returns:
            Mock container instance
            
        Raises:
            Exception: If container not found
        """
        if container_id not in self._containers:
            raise Exception(f"Container {container_id} not found")
        return self._containers[container_id]
    
    def list(self, **kwargs) -> List[MockDockerContainer]:
        """Mock list containers.
        
        Args:
            **kwargs: Filter options
            
        Returns:
            List of mock containers
        """
        all_containers = kwargs.get("all", False)
        
        containers = list(self._containers.values())
        if not all_containers:
            containers = [c for c in containers if c.status == "running"]
        
        return containers
    
    def prune(self) -> Dict[str, Any]:
        """Mock prune containers."""
        removed = []
        for cid, container in list(self._containers.items()):
            if container.status in ["exited", "dead"]:
                removed.append({"Id": cid})
                del self._containers[cid]
        
        return {"ContainersDeleted": removed, "SpaceReclaimed": 0}


class MockImageCollection:
    """Mock Docker images collection."""
    
    def __init__(self):
        """Initialize mock image collection."""
        self._images: Dict[str, MockDockerImage] = {}
    
    def pull(self, repository: str, **kwargs) -> MockDockerImage:
        """Mock pull image."""
        image = MockDockerImage(tags=[repository])
        self._images[repository] = image
        return image
    
    def get(self, name: str) -> MockDockerImage:
        """Mock get image by name."""
        if name not in self._images:
            raise Exception(f"Image {name} not found")
        return self._images[name]
    
    def list(self, **kwargs) -> List[MockDockerImage]:
        """Mock list images."""
        return list(self._images.values())


class MockNetworkCollection:
    """Mock Docker networks collection."""
    
    def __init__(self):
        """Initialize mock network collection."""
        self._networks: Dict[str, Any] = {}
    
    def create(self, name: str, **kwargs) -> Any:
        """Mock create network."""
        network = MagicMock()
        network.name = name
        network.id = f"network_{len(self._networks)}"
        self._networks[name] = network
        return network
    
    def get(self, network_id: str) -> Any:
        """Mock get network."""
        return self._networks.get(network_id)
    
    def list(self, **kwargs) -> List[Any]:
        """Mock list networks."""
        return list(self._networks.values())


class MockVolumeCollection:
    """Mock Docker volumes collection."""
    
    def __init__(self):
        """Initialize mock volume collection."""
        self._volumes: Dict[str, Any] = {}
    
    def create(self, name: str, **kwargs) -> Any:
        """Mock create volume."""
        volume = MagicMock()
        volume.name = name
        self._volumes[name] = volume
        return volume
    
    def get(self, name: str) -> Any:
        """Mock get volume."""
        return self._volumes.get(name)
    
    def list(self, **kwargs) -> List[Any]:
        """Mock list volumes."""
        return list(self._volumes.values())
