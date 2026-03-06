"""MCP Adapter - Model Context Protocol integration for octopOS.

This module provides full MCP (Model Context Protocol) support:
- stdio transport (local processes)
- SSE transport (HTTP server-sent events)
- Tool/resource/prompt discovery
- Automatic primitive registration
- Multi-server management
"""

from typing import Optional

"""Example:
    >>> from src.primitives.mcp_adapter import MCPManager
    >>> manager = MCPManager()
    >>> 
    >>> # Add stdio server
    >>> await manager.add_server_stdio(
    ...     name="github",
    ...     command="npx",
    ...     args=["-y", "@modelcontextprotocol/server-github"],
    ...     env={"GITHUB_TOKEN": "ghp_xxx"}
    ... )
    >>> 
    >>> # List discovered tools
    >>> tools = manager.list_all_tools()
    >>> 
    >>> # Add SSE server
    >>> await manager.add_server_sse(
    ...     name="custom",
    ...     url="http://localhost:3000/sse",
    ...     headers={"Authorization": "Bearer token"}
    ... )
"""

from src.primitives.mcp_adapter.mcp_transport import (
    MCPTransport,
    MCPMessage,
    StdioTransport,
    SSETransport,
)

from src.primitives.mcp_adapter.mcp_client import (
    MCPClient,
    MCPTool,
    MCPResource,
    MCPPrompt,
    MCPConnectionConfig,
)

from src.primitives.mcp_adapter.mcp_tool_wrapper import (
    MCPToolPrimitive,
    MCPManager,
)

__all__ = [
    # Transport
    "MCPTransport",
    "MCPMessage",
    "StdioTransport",
    "SSETransport",
    # Client
    "MCPClient",
    "MCPTool",
    "MCPResource",
    "MCPPrompt",
    "MCPConnectionConfig",
    # Tool Wrapper
    "MCPToolPrimitive",
    "MCPManager",
]


def register_all() -> None:
    """Register MCP adapter.
    
    Note: MCP tools are registered dynamically when servers connect via MCPManager.
    This function is called during module initialization but doesn't register
    any tools yet - they will be added when servers are configured in profile.yaml.
    """
    pass  # MCP tools are registered dynamically


# Global MCP manager instance
_mcp_manager: Optional[MCPManager] = None


def get_mcp_manager() -> MCPManager:
    """Get or create the global MCP manager instance.
    
    Returns:
        MCPManager singleton
    """
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = MCPManager()
    return _mcp_manager
