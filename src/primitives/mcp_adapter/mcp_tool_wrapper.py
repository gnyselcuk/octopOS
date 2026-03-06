"""MCP Tool Wrapper - Wrap MCP tools as octopOS primitives.

Converts MCP tool definitions into BasePrimitive implementations that can be
registered with the ToolRegistry and used by the orchestrator.

Example:
    >>> from src.primitives.mcp_adapter.mcp_tool_wrapper import MCPToolPrimitive
    >>> from src.primitives.mcp_adapter.mcp_client import MCPClient
    >>> 
    >>> client = MCPClient.from_stdio("github", "npx", ["@modelcontextprotocol/server-github"])
    >>> primitive = MCPToolPrimitive(client, tool_definition)
    >>> result = await primitive.execute(owner="octopos", repo="octopos")
"""

from typing import Any, Dict, List, Optional
import copy

from src.primitives.base_primitive import BasePrimitive, PrimitiveResult, register_primitive
from src.primitives.mcp_adapter.mcp_client import MCPClient, MCPTool
from src.primitives.tool_registry import get_registry
from src.utils.logger import get_logger

logger = get_logger()


class MCPToolPrimitive(BasePrimitive):
    """Wraps an MCP tool as an octopOS primitive.
    
    This allows MCP tools to be used seamlessly with the octopOS system,
    including registration with the ToolRegistry and Bedrock Tool Calling.
    """
    
    def __init__(
        self,
        client: MCPClient,
        tool: MCPTool,
        prefix_server_name: bool = True
    ) -> None:
        """Initialize MCP tool wrapper.
        
        Args:
            client: MCP client for executing the tool
            tool: MCP tool definition
            prefix_server_name: Whether to prefix tool name with server name
        """
        super().__init__()
        self._client = client
        self._tool = tool
        self._prefix_server_name = prefix_server_name
        self._original_name = tool.name
    
    @property
    def name(self) -> str:
        """Return the primitive name (may be prefixed with server name)."""
        if self._prefix_server_name and self._tool.server_name:
            return f"{self._tool.server_name}_{self._original_name}"
        return self._original_name
    
    @property
    def original_name(self) -> str:
        """Return the original MCP tool name."""
        return self._original_name
    
    @property
    def server_name(self) -> Optional[str]:
        """Return the server name."""
        return self._tool.server_name
    
    @property
    def description(self) -> str:
        """Return the tool description."""
        desc = self._tool.description
        if self._tool.server_name:
            desc += f" (via {self._tool.server_name} MCP server)"
        return desc
    
    @property
    def parameters(self) -> Dict[str, Dict[str, Any]]:
        """Return parameters from MCP tool schema."""
        schema = self._tool.input_schema
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        
        params = {}
        for prop_name, prop_def in properties.items():
            param_def = {
                "type": prop_def.get("type", "string"),
                "description": prop_def.get("description", ""),
                "required": prop_name in required
            }
            
            # Handle enum
            if "enum" in prop_def:
                param_def["enum"] = prop_def["enum"]
            
            # Handle default
            if "default" in prop_def:
                param_def["default"] = prop_def["default"]
            
            params[prop_name] = param_def
        
        return params
    
    @property
    def mcp_tool(self) -> MCPTool:
        """Get the underlying MCP tool definition."""
        return self._tool
    
    async def execute(self, **kwargs) -> PrimitiveResult:
        """Execute the MCP tool.
        
        Args:
            **kwargs: Tool arguments
            
        Returns:
            PrimitiveResult with tool output
        """
        try:
            # Validate parameters
            valid, error = self.validate_params(kwargs)
            if not valid:
                return PrimitiveResult(
                    success=False,
                    data=None,
                    message=f"Parameter validation failed: {error}",
                    error="InvalidParameters"
                )
            
            # Check client connection
            if not self._client.is_connected:
                return PrimitiveResult(
                    success=False,
                    data=None,
                    message="MCP client not connected",
                    error="NotConnected"
                )
            
            # Call the tool
            logger.debug(f"Calling MCP tool {self._original_name} on {self._tool.server_name}")
            result = await self._client.call_tool(self._original_name, kwargs)
            
            if result is None:
                return PrimitiveResult(
                    success=False,
                    data=None,
                    message=f"Tool {self._original_name} returned no result",
                    error="NoResult"
                )
            
            # Parse MCP tool result
            content = result.get("content", [])
            
            if not content:
                return PrimitiveResult(
                    success=True,
                    data={},
                    message=f"Tool {self._original_name} executed successfully (no content)"
                )
            
            # Extract text content
            text_items = []
            data_items = []
            
            for item in content:
                if item.get("type") == "text":
                    text_items.append(item.get("text", ""))
                elif item.get("type") == "image":
                    data_items.append({
                        "type": "image",
                        "data": item.get("data", ""),
                        "mime_type": item.get("mimeType", "image/png")
                    })
                elif item.get("type") == "resource":
                    resource = item.get("resource", {})
                    data_items.append({
                        "type": "resource",
                        "uri": resource.get("uri", ""),
                        "text": resource.get("text", "")
                    })
            
            # Build result data
            result_data = {
                "tool": self._original_name,
                "server": self._tool.server_name,
                "text": "\n".join(text_items) if text_items else None,
            }
            
            if data_items:
                result_data["data"] = data_items
            
            is_error = result.get("isError", False)
            
            return PrimitiveResult(
                success=not is_error,
                data=result_data,
                message=f"Tool {self._original_name} executed" + (" with error" if is_error else ""),
                error="ToolError" if is_error else None
            )
            
        except Exception as e:
            logger.error(f"MCP tool execution error ({self.name}): {e}")
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Execution failed: {e}",
                error=str(e)
            )


class MCPManager:
    """Manages multiple MCP server connections and tool registration.
    
    This is the high-level interface for integrating MCP servers into octopOS.
    It handles:
    - Server connection management
    - Tool discovery and registration
    - Health monitoring
    - Cleanup
    
    Example:
        >>> manager = MCPManager()
        >>> await manager.add_server("github", {
        ...     "command": "npx",
        ...     "args": ["-y", "@modelcontextprotocol/server-github"],
        ...     "env": {"GITHUB_TOKEN": "xxx"}
        ... })
        >>> tools = manager.list_all_tools()
    """
    
    def __init__(self) -> None:
        """Initialize MCP manager."""
        self._clients: Dict[str, MCPClient] = {}
        self._wrapped_tools: Dict[str, MCPToolPrimitive] = {}
        self._registry = get_registry()
    
    async def initialize_from_config(self) -> None:
        """Initialize MCP servers from global configuration."""
        from src.utils.config import get_config
        config = get_config()
        
        if not config.mcp.auto_connect:
            return
            
        for name, server in config.mcp.servers.items():
            if not server.enabled:
                continue
                
            logger.info(f"Auto-connecting to MCP server: {name}")
            if server.transport == "stdio":
                await self.add_server_stdio(
                    name=server.name,
                    command=server.command,
                    args=server.args,
                    env=server.env
                )
            elif server.transport == "sse":
                await self.add_server_sse(
                    name=server.name,
                    url=server.url
                )
    
    async def add_server_stdio(
        self,
        name: str,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
        auto_discover: bool = True
    ) -> bool:
        """Add an MCP server using stdio transport.
        
        Args:
            name: Server name
            command: Command to execute
            args: Command arguments
            env: Environment variables
            cwd: Working directory
            auto_discover: Auto-discover and register tools
            
        Returns:
            True if successful
        """
        try:
            client = MCPClient.from_stdio(name, command, args, env, cwd)
            
            if not await client.connect():
                logger.error(f"Failed to connect to MCP server: {name}")
                return False
            
            self._clients[name] = client
            
            if auto_discover:
                await self._discover_and_register(client)
            
            logger.info(f"MCP server added: {name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add MCP server {name}: {e}")
            return False
    
    async def add_server_sse(
        self,
        name: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        auto_discover: bool = True
    ) -> bool:
        """Add an MCP server using SSE transport.
        
        Args:
            name: Server name
            url: Server URL
            headers: HTTP headers
            auto_discover: Auto-discover and register tools
            
        Returns:
            True if successful
        """
        try:
            client = MCPClient.from_sse(name, url, headers)
            
            if not await client.connect():
                logger.error(f"Failed to connect to MCP server: {name}")
                return False
            
            self._clients[name] = client
            
            if auto_discover:
                await self._discover_and_register(client)
            
            logger.info(f"MCP server added: {name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add MCP server {name}: {e}")
            return False
    
    async def _discover_and_register(self, client: MCPClient) -> None:
        """Discover tools from client and register as primitives."""
        try:
            # Discover tools
            tools = await client.discover_tools()
            
            for tool in tools:
                # Create wrapper
                wrapper = MCPToolPrimitive(client, tool, prefix_server_name=True)
                
                # Register with ToolRegistry
                self._registry.register(wrapper, category='mcp', tags=['mcp', client.server_name])
                
                # Track wrapped tool
                self._wrapped_tools[wrapper.name] = wrapper
                
                logger.debug(f"Registered MCP tool: {wrapper.name}")
            
            logger.info(f"Registered {len(tools)} tools from {client.server_name}")
            
        except Exception as e:
            logger.error(f"Discovery error for {client.server_name}: {e}")
    
    def get_client(self, name: str) -> Optional[MCPClient]:
        """Get MCP client by name."""
        return self._clients.get(name)
    
    def list_servers(self) -> List[str]:
        """List all connected server names."""
        return list(self._clients.keys())
    
    def list_all_tools(self) -> List[MCPToolPrimitive]:
        """List all wrapped MCP tools."""
        return list(self._wrapped_tools.values())
    
    def get_tool(self, name: str) -> Optional[MCPToolPrimitive]:
        """Get wrapped tool by name."""
        return self._wrapped_tools.get(name)
    
    async def remove_server(self, name: str) -> bool:
        """Remove an MCP server and unregister its tools."""
        if name not in self._clients:
            return False
        
        try:
            client = self._clients[name]
            
            # Unregister tools
            tools_to_remove = [
                t.name for t in self._wrapped_tools.values()
                if t.server_name == name
            ]
            
            for tool_name in tools_to_remove:
                self._registry.unregister(tool_name)
                del self._wrapped_tools[tool_name]
            
            # Disconnect client
            await client.disconnect()
            del self._clients[name]
            
            logger.info(f"MCP server removed: {name}")
            return True
            
        except Exception as e:
            logger.error(f"Error removing server {name}: {e}")
            return False
    
    async def health_check_all(self) -> Dict[str, bool]:
        """Check health of all servers."""
        results = {}
        for name, client in self._clients.items():
            results[name] = await client.health_check()
        return results
    
    async def close_all(self) -> None:
        """Close all MCP connections."""
        for name in list(self._clients.keys()):
            await self.remove_server(name)
        
        logger.info("All MCP connections closed")


def register_all() -> None:
    """Register MCP adapter (called during module init).
    
    Note: Actual MCP tools are registered dynamically when servers connect.
    """
    pass  # MCP tools are registered dynamically via MCPManager
