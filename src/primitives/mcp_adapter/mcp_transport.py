"""MCP Transport - Transport layer for Model Context Protocol.

Implements stdio and SSE (Server-Sent Events) transports for MCP communication.
Follows the MCP specification for message framing and transport.

Example:
    >>> from src.primitives.mcp_adapter.mcp_transport import StdioTransport
    >>> transport = StdioTransport(command="npx", args=["-y", "@modelcontextprotocol/server-github"])
    >>> await transport.connect()
    >>> await transport.send({"jsonrpc": "2.0", "method": "initialize", ...})
    >>> response = await transport.receive()
"""

import asyncio
import json
import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional, List
from urllib.parse import urlparse
import uuid

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

from src.utils.logger import get_logger

logger = get_logger()


@dataclass
class MCPMessage:
    """An MCP protocol message."""
    jsonrpc: str = "2.0"
    id: Optional[str] = None
    method: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = {"jsonrpc": self.jsonrpc}
        if self.id is not None:
            data["id"] = self.id
        if self.method:
            data["method"] = self.method
            if self.params:
                data["params"] = self.params
        if self.result is not None:
            data["result"] = self.result
        if self.error:
            data["error"] = self.error
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPMessage":
        """Create from dictionary."""
        return cls(
            jsonrpc=data.get("jsonrpc", "2.0"),
            id=data.get("id"),
            method=data.get("method"),
            params=data.get("params"),
            result=data.get("result"),
            error=data.get("error")
        )
    
    def is_request(self) -> bool:
        """Check if this is a request message."""
        return self.method is not None and self.id is not None
    
    def is_notification(self) -> bool:
        """Check if this is a notification (no response expected)."""
        return self.method is not None and self.id is None
    
    def is_response(self) -> bool:
        """Check if this is a response message."""
        return self.id is not None and (self.result is not None or self.error is not None)


class MCPTransport(ABC):
    """Abstract base class for MCP transports."""
    
    def __init__(self) -> None:
        """Initialize transport."""
        self._connected = False
        self._message_queue: asyncio.Queue[MCPMessage] = asyncio.Queue()
    
    @property
    def is_connected(self) -> bool:
        """Check if transport is connected."""
        return self._connected
    
    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection.
        
        Returns:
            True if connected successfully
        """
        raise NotImplementedError
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection."""
        raise NotImplementedError
    
    @abstractmethod
    async def send(self, message: MCPMessage) -> bool:
        """Send a message.
        
        Args:
            message: Message to send
            
        Returns:
            True if sent successfully
        """
        raise NotImplementedError
    
    @abstractmethod
    async def receive(self, timeout: Optional[float] = None) -> Optional[MCPMessage]:
        """Receive a message.
        
        Args:
            timeout: Maximum time to wait
            
        Returns:
            Received message or None if timeout
        """
        raise NotImplementedError
    
    def create_request(self, method: str, params: Optional[Dict] = None) -> MCPMessage:
        """Create a request message with auto-generated ID."""
        return MCPMessage(
            id=str(uuid.uuid4()),
            method=method,
            params=params or {}
        )


class StdioTransport(MCPTransport):
    """stdio-based transport for MCP.
    
    Spawns a subprocess and communicates via stdin/stdout.
    Used for local MCP servers (e.g., npx, python scripts).
    
    Example:
        transport = StdioTransport(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"],
            env={"GITHUB_TOKEN": "xxx"}
        )
    """
    
    # Whitelist of allowed environment variables for subprocess
    ALLOWED_ENV_VARS = {
        'PATH', 'HOME', 'USER', 'WORKDIR', 'LANG', 'LC_ALL',
        'PYTHONPATH', 'PYTHONUNBUFFERED', 'TERM', 'TMPDIR',
    }
    
    def __init__(
        self,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None
    ) -> None:
        """Initialize stdio transport.
        
        Args:
            command: Command to execute
            args: Command arguments
            env: Environment variables
            cwd: Working directory
        """
        super().__init__()
        self.command = command
        self.args = args or []
        self.env = env
        self.cwd = cwd
        self._process: Optional[asyncio.subprocess.Process] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._shutdown = False
    
    async def connect(self) -> bool:
        """Start subprocess and establish communication."""
        try:
            # Prepare sanitized environment for subprocess
            # Only include whitelisted parent environment variables
            env = {k: v for k, v in os.environ.items() 
                   if k in self.ALLOWED_ENV_VARS}
            
            # Add explicitly provided env vars (for MCP server credentials)
            if self.env:
                env.update(self.env)
            
            # Start subprocess
            self._process = await asyncio.create_subprocess_exec(
                self.command,
                *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=self.cwd
            )
            
            # Start reader task
            self._reader_task = asyncio.create_task(self._read_messages())
            
            self._connected = True
            logger.info(f"Stdio transport connected: {self.command} {' '.join(self.args)}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start subprocess: {e}")
            return False
    
    async def disconnect(self) -> None:
        """Stop subprocess and cleanup."""
        self._shutdown = True
        self._connected = False
        
        # Cancel reader task
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        
        # Terminate process
        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
            except Exception as e:
                logger.warning(f"Error terminating process: {e}")
        
        logger.info("Stdio transport disconnected")
    
    async def send(self, message: MCPMessage) -> bool:
        """Send message via stdin."""
        if not self._process or not self._process.stdin:
            return False
        
        try:
            # MCP uses newline-delimited JSON (NDJSON)
            data = json.dumps(message.to_dict()) + "\n"
            self._process.stdin.write(data.encode())
            await self._process.stdin.drain()
            return True
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return False
    
    async def receive(self, timeout: Optional[float] = None) -> Optional[MCPMessage]:
        """Receive message from queue."""
        try:
            return await asyncio.wait_for(
                self._message_queue.get(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            return None
    
    async def _read_messages(self) -> None:
        """Background task to read messages from stdout."""
        if not self._process or not self._process.stdout:
            return
        
        try:
            while not self._shutdown:
                # Read line
                line = await self._process.stdout.readline()
                if not line:
                    break
                
                try:
                    data = json.loads(line.decode().strip())
                    message = MCPMessage.from_dict(data)
                    await self._message_queue.put(message)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON: {line[:100]}")
                    continue
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Reader error: {e}")
    
    async def read_stderr(self) -> str:
        """Read any error output from stderr."""
        if not self._process or not self._process.stderr:
            return ""
        
        try:
            data = await self._process.stderr.read()
            return data.decode()
        except Exception:
            return ""


class SSETransport(MCPTransport):
    """HTTP Server-Sent Events transport for MCP.
    
    Connects to remote MCP servers via HTTP/SSE.
    Used for hosted MCP servers.
    
    Example:
        >>> import os
        >>> transport = SSETransport(
        ...     url="http://localhost:3000/sse",
        ...     headers={"Authorization": f"Bearer {os.environ.get('MCP_TOKEN')}"}
        ... )
    """
    
    def __init__(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 30.0
    ) -> None:
        """Initialize SSE transport.
        
        Args:
            url: Server URL
            headers: HTTP headers
            timeout: Connection timeout
        """
        super().__init__()
        self.url = url
        self.headers = headers or {}
        self.timeout = timeout
        self._client: Optional[Any] = None
        self._session_id: Optional[str] = None
        self._event_source: Optional[Any] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._shutdown = False
        self._post_url: Optional[str] = None
    
    async def connect(self) -> bool:
        """Establish SSE connection."""
        if not HAS_HTTPX:
            logger.error("httpx is required for SSE transport")
            return False
        
        try:
            # Connect to SSE endpoint
            self._client = httpx.AsyncClient(
                headers=self.headers,
                timeout=self.timeout
            )
            
            # Start SSE connection
            response = await self._client.get(
                self.url,
                headers={"Accept": "text/event-stream"}
            )
            response.raise_for_status()
            
            # Get session ID from endpoint event
            # MCP spec: first event contains endpoint URL
            self._event_source = response
            
            # Start reader
            self._reader_task = asyncio.create_task(self._read_sse())
            
            self._connected = True
            logger.info(f"SSE transport connected: {self.url}")
            return True
            
        except Exception as e:
            logger.error(f"SSE connection failed: {e}")
            return False
    
    async def disconnect(self) -> None:
        """Close SSE connection."""
        self._shutdown = True
        self._connected = False
        
        # Cancel reader
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        
        # Close client
        if self._client:
            await self._client.aclose()
        
        logger.info("SSE transport disconnected")
    
    async def send(self, message: MCPMessage) -> bool:
        """Send message via HTTP POST."""
        if not self._client or not self._post_url:
            return False
        
        try:
            response = await self._client.post(
                self._post_url,
                json=message.to_dict()
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return False
    
    async def receive(self, timeout: Optional[float] = None) -> Optional[MCPMessage]:
        """Receive message from queue."""
        try:
            return await asyncio.wait_for(
                self._message_queue.get(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            return None
    
    async def _read_sse(self) -> None:
        """Background task to read SSE events."""
        try:
            async for line in self._event_source.aiter_lines():
                if self._shutdown:
                    break
                
                # Parse SSE format: "data: <json>"
                if line.startswith("data: "):
                    data_str = line[6:]  # Remove "data: " prefix
                    
                    try:
                        data = json.loads(data_str)
                        
                        # Check for endpoint event
                        if "endpoint" in data:
                            self._post_url = data["endpoint"]
                            continue
                        
                        message = MCPMessage.from_dict(data)
                        await self._message_queue.put(message)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid SSE data: {data_str[:100]}")
                        continue
                        
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"SSE reader error: {e}")


# Import os for stdio transport
import os
