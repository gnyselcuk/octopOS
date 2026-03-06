"""MCP Client - Model Context Protocol client implementation.

Provides high-level client for MCP servers with:
- Connection management (stdio and SSE transports)
- Tool/resource/prompt discovery
- Request/response handling
- Health checking

Example:
    >>> from src.primitives.mcp_adapter.mcp_client import MCPClient
    >>> client = MCPClient.from_stdio(
    ...     command="npx",
    ...     args=["-y", "@modelcontextprotocol/server-github"]
    ... )
    >>> await client.connect()
    >>> tools = await client.discover_tools()
    >>> result = await client.call_tool("search_repositories", {"query": "python"})
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from enum import Enum
import json

from src.primitives.mcp_adapter.mcp_transport import (
    MCPTransport,
    MCPMessage,
    StdioTransport,
    SSETransport
)
from src.utils.config import get_config
from src.utils.logger import get_logger

logger = get_logger()


class MCPCapability(str, Enum):
    """MCP server capabilities."""
    TOOLS = "tools"
    RESOURCES = "resources"
    PROMPTS = "prompts"


@dataclass
class MCPTool:
    """An MCP tool definition."""
    name: str
    description: str
    input_schema: Dict[str, Any]
    server_name: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema
        }


@dataclass
class MCPResource:
    """An MCP resource definition."""
    uri: str
    name: str
    mime_type: str
    description: Optional[str] = None


@dataclass
class MCPPrompt:
    """An MCP prompt definition."""
    name: str
    description: str
    arguments: Optional[List[Dict]] = None


@dataclass
class MCPConnectionConfig:
    """Configuration for MCP server connection."""
    name: str
    transport: str  # "stdio" or "sse"
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
    cwd: Optional[str] = None
    url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None


class MCPClient:
    """High-level MCP client for interacting with MCP servers.
    
    Manages the full lifecycle:
    1. Connection establishment
    2. Protocol initialization
    3. Capability discovery
    4. Tool/resource/prompt operations
    5. Graceful shutdown
    """
    
    PROTOCOL_VERSION = "2024-11-05"
    
    def __init__(
        self,
        config: MCPConnectionConfig,
        transport: Optional[MCPTransport] = None
    ) -> None:
        """Initialize MCP client.
        
        Args:
            config: Connection configuration
            transport: Optional pre-configured transport
        """
        self.config = config
        self._transport = transport
        self._connected = False
        self._initialized = False
        self._server_capabilities: Dict[str, Any] = {}
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._message_handler: Optional[asyncio.Task] = None
        
        # Discovered entities
        self._tools: Dict[str, MCPTool] = {}
        self._resources: Dict[str, MCPResource] = {}
        self._prompts: Dict[str, MCPPrompt] = {}
    
    @classmethod
    def from_stdio(
        cls,
        name: str,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None
    ) -> "MCPClient":
        """Create client for stdio transport.
        
        Args:
            name: Server name
            command: Command to execute
            args: Command arguments
            env: Environment variables
            cwd: Working directory
            
        Returns:
            Configured MCP client
        """
        config = MCPConnectionConfig(
            name=name,
            transport="stdio",
            command=command,
            args=args,
            env=env,
            cwd=cwd
        )
        transport = StdioTransport(
            command=command,
            args=args or [],
            env=env,
            cwd=cwd
        )
        return cls(config, transport)
    
    @classmethod
    def from_sse(
        cls,
        name: str,
        url: str,
        headers: Optional[Dict[str, str]] = None
    ) -> "MCPClient":
        """Create client for SSE transport.
        
        Args:
            name: Server name
            url: Server URL
            headers: HTTP headers
            
        Returns:
            Configured MCP client
        """
        config = MCPConnectionConfig(
            name=name,
            transport="sse",
            url=url,
            headers=headers
        )
        transport = SSETransport(url=url, headers=headers)
        return cls(config, transport)
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to server."""
        return self._connected and self._transport and self._transport.is_connected
    
    @property
    def server_name(self) -> str:
        """Get server name."""
        return self.config.name
    
    @property
    def tools(self) -> List[MCPTool]:
        """Get discovered tools."""
        return list(self._tools.values())
    
    @property
    def resources(self) -> List[MCPResource]:
        """Get discovered resources."""
        return list(self._resources.values())
    
    @property
    def prompts(self) -> List[MCPPrompt]:
        """Get discovered prompts."""
        return list(self._prompts.values())
    
    async def connect(self) -> bool:
        """Connect and initialize MCP session.
        
        Returns:
            True if successful
        """
        if self._connected:
            return True
        
        try:
            # Connect transport
            if not self._transport:
                raise ValueError("No transport configured")
            
            if not await self._transport.connect():
                logger.error("Transport connection failed")
                return False
            
            self._connected = True
            
            # Start message handler
            self._message_handler = asyncio.create_task(self._handle_messages())
            
            # Initialize protocol
            if not await self._initialize():
                await self.disconnect()
                return False
            
            logger.info(f"MCP client connected: {self.config.name}")
            return True
            
        except Exception as e:
            logger.error(f"MCP connection error: {e}")
            await self.disconnect()
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from server."""
        self._connected = False
        self._initialized = False
        
        # Cancel message handler
        if self._message_handler:
            self._message_handler.cancel()
            try:
                await self._message_handler
            except asyncio.CancelledError:
                pass
        
        # Cancel pending requests
        for future in self._pending_requests.values():
            if not future.done():
                future.cancel()
        self._pending_requests.clear()
        
        # Disconnect transport
        if self._transport:
            await self._transport.disconnect()
        
        logger.info(f"MCP client disconnected: {self.config.name}")
    
    async def _initialize(self) -> bool:
        """Perform MCP protocol initialization."""
        try:
            init_request = self._transport.create_request(
                "initialize",
                {
                    "protocolVersion": self.PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {},
                        "resources": {},
                        "prompts": {}
                    },
                    "clientInfo": {
                        "name": "octopos-mcp-client",
                        "version": "1.0.0"
                    }
                }
            )
            
            response = await self._send_request(init_request)
            
            if not response:
                logger.error("Initialization timeout")
                return False
            
            if response.error:
                logger.error(f"Initialization error: {response.error}")
                return False
            
            result = response.result or {}
            self._server_capabilities = result.get("capabilities", {})
            
            # Send initialized notification
            await self._send_notification("initialized")
            
            self._initialized = True
            logger.info(f"MCP protocol initialized: {self.config.name}")
            return True
            
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            return False
    
    async def _send_request(self, message: MCPMessage, timeout: float = 30.0) -> Optional[MCPMessage]:
        """Send request and wait for response."""
        if not self._transport:
            return None
        
        # Create future for response
        future = asyncio.get_event_loop().create_future()
        self._pending_requests[message.id] = future
        
        try:
            # Send message
            if not await self._transport.send(message):
                self._pending_requests.pop(message.id, None)
                return None
            
            # Wait for response
            return await asyncio.wait_for(future, timeout=timeout)
            
        except asyncio.TimeoutError:
            logger.warning(f"Request timeout: {message.method}")
            self._pending_requests.pop(message.id, None)
            return None
        except Exception as e:
            logger.error(f"Request error: {e}")
            self._pending_requests.pop(message.id, None)
            return None
    
    async def _send_notification(self, method: str, params: Optional[Dict] = None) -> bool:
        """Send notification (no response expected)."""
        if not self._transport:
            return False
        
        message = MCPMessage(
            method=method,
            params=params
        )
        
        return await self._transport.send(message)
    
    async def _handle_messages(self) -> None:
        """Background task to handle incoming messages."""
        try:
            while self._connected:
                message = await self._transport.receive(timeout=1.0)
                if not message:
                    continue
                
                # Handle responses
                if message.id and message.id in self._pending_requests:
                    future = self._pending_requests.pop(message.id)
                    if not future.done():
                        future.set_result(message)
                
                # Handle notifications
                elif message.is_notification():
                    await self._handle_notification(message)
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Message handler error: {e}")
    
    async def _handle_notification(self, message: MCPMessage) -> None:
        """Handle incoming notifications."""
        logger.debug(f"Notification: {message.method}")
        # Handle server notifications if needed
    
    # ==================== Discovery ====================
    
    async def discover_tools(self, force: bool = False) -> List[MCPTool]:
        """Discover available tools from server.
        
        Args:
            force: Force re-discovery even if already cached
            
        Returns:
            List of discovered tools
        """
        if not force and self._tools:
            return self.tools
        
        if not self._server_capabilities.get("tools"):
            logger.debug(f"Server {self.config.name} doesn't support tools")
            return []
        
        try:
            request = self._transport.create_request("tools/list")
            response = await self._send_request(request)
            
            if not response or response.error:
                logger.warning(f"Tool discovery failed: {response.error if response else 'timeout'}")
                return []
            
            tools_data = response.result.get("tools", [])
            
            self._tools.clear()
            for tool_data in tools_data:
                tool = MCPTool(
                    name=tool_data["name"],
                    description=tool_data.get("description", ""),
                    input_schema=tool_data.get("inputSchema", {}),
                    server_name=self.config.name
                )
                self._tools[tool.name] = tool
            
            logger.info(f"Discovered {len(self._tools)} tools from {self.config.name}")
            return self.tools
            
        except Exception as e:
            logger.error(f"Tool discovery error: {e}")
            return []
    
    async def discover_resources(self, force: bool = False) -> List[MCPResource]:
        """Discover available resources."""
        if not force and self._resources:
            return self.resources
        
        if not self._server_capabilities.get("resources"):
            return []
        
        try:
            request = self._transport.create_request("resources/list")
            response = await self._send_request(request)
            
            if not response or response.error:
                return []
            
            resources_data = response.result.get("resources", [])
            
            self._resources.clear()
            for res_data in resources_data:
                resource = MCPResource(
                    uri=res_data["uri"],
                    name=res_data.get("name", ""),
                    mime_type=res_data.get("mimeType", "text/plain"),
                    description=res_data.get("description")
                )
                self._resources[resource.uri] = resource
            
            return self.resources
            
        except Exception as e:
            logger.error(f"Resource discovery error: {e}")
            return []
    
    async def discover_prompts(self, force: bool = False) -> List[MCPPrompt]:
        """Discover available prompts."""
        if not force and self._prompts:
            return self.prompts
        
        if not self._server_capabilities.get("prompts"):
            return []
        
        try:
            request = self._transport.create_request("prompts/list")
            response = await self._send_request(request)
            
            if not response or response.error:
                return []
            
            prompts_data = response.result.get("prompts", [])
            
            self._prompts.clear()
            for prompt_data in prompts_data:
                prompt = MCPPrompt(
                    name=prompt_data["name"],
                    description=prompt_data.get("description", ""),
                    arguments=prompt_data.get("arguments")
                )
                self._prompts[prompt.name] = prompt
            
            return self.prompts
            
        except Exception as e:
            logger.error(f"Prompt discovery error: {e}")
            return []
    
    # ==================== Operations ====================
    
    async def call_tool(
        self,
        name: str,
        arguments: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Call a tool on the MCP server.
        
        Args:
            name: Tool name
            arguments: Tool arguments
            
        Returns:
            Tool result or None if failed
        """
        try:
            request = self._transport.create_request(
                "tools/call",
                {"name": name, "arguments": arguments}
            )
            
            response = await self._send_request(request)
            
            if not response:
                return None
            
            if response.error:
                logger.error(f"Tool call error: {response.error}")
                return None
            
            return response.result
            
        except Exception as e:
            logger.error(f"Tool call error: {e}")
            return None
    
    async def read_resource(self, uri: str) -> Optional[str]:
        """Read a resource from the server."""
        try:
            request = self._transport.create_request(
                "resources/read",
                {"uri": uri}
            )
            
            response = await self._send_request(request)
            
            if not response or response.error:
                return None
            
            contents = response.result.get("contents", [])
            if contents:
                return contents[0].get("text", "")
            
            return None
            
        except Exception as e:
            logger.error(f"Resource read error: {e}")
            return None
    
    async def get_prompt(self, name: str, arguments: Optional[Dict] = None) -> Optional[str]:
        """Get a prompt from the server."""
        try:
            request = self._transport.create_request(
                "prompts/get",
                {"name": name, "arguments": arguments or {}}
            )
            
            response = await self._send_request(request)
            
            if not response or response.error:
                return None
            
            messages = response.result.get("messages", [])
            if messages:
                return messages[0].get("content", {}).get("text", "")
            
            return None
            
        except Exception as e:
            logger.error(f"Prompt get error: {e}")
            return None
    
    async def health_check(self) -> bool:
        """Check if server is responsive."""
        try:
            # Simple ping - list tools with short timeout
            old_timeout = 30.0  # Default
            request = self._transport.create_request("tools/list")
            response = await self._send_request(request, timeout=5.0)
            return response is not None and not response.error
        except Exception:
            return False
