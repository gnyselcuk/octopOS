"""Primitives module - Tool library for agents.

This module provides the complete tool/primitive library for octopOS,
organized into categories:

- native: Core system and file operations
- cloud_aws: AWS service operations
- web: Web search and API operations
- dev: Developer tools
- mcp_adapter: MCP server integration
"""

# Base classes
from src.primitives.base_primitive import (
    BasePrimitive,
    PrimitiveResult,
    PrimitiveRegistry,
    get_registry,
    get_primitive,
    register_primitive,
)

# Tool Registry (new unified registry)
from src.primitives.tool_registry import (
    ToolRegistry,
    ToolMetadata,
    get_registry as get_tool_registry,
    register_primitive as register_tool,
)

# Native primitives (both existing and new)
from src.primitives.file_operations import (
    ReadFilePrimitive,
    WriteFilePrimitive,
    ListDirectoryPrimitive,
    CreateDirectoryPrimitive,
    DeletePathPrimitive,
)

# New native primitives
from src.primitives.native.bash_executor import BashExecutor
from src.primitives.native.file_search import FileSearch
from src.primitives.native.file_editor import FileEditor

# AWS primitives
from src.primitives.cloud_aws.s3_manager import S3Manager
from src.primitives.cloud_aws.dynamodb_client import DynamoDBClient
from src.primitives.cloud_aws.bedrock_invoker import BedrockInvoker
from src.primitives.cloud_aws.cloudwatch_inspector import CloudWatchInspector

# Web primitives
from src.primitives.web.search_engine import SearchEngine
from src.primitives.web.public_api_caller import PublicAPICaller
from src.primitives.web.nova_act_scraper import NovaActScraper

# MCP adapter primitives
from src.primitives.mcp_adapter.mcp_client import MCPClient, MCPTool
from src.primitives.mcp_adapter.mcp_tool_wrapper import MCPToolPrimitive, MCPManager
from src.primitives.mcp_adapter.mcp_transport import MCPMessage

# Developer tools primitives
from src.primitives.dev.ast_parser import ASTParser
from src.primitives.dev.git_manipulator import GitManipulator

# Legacy imports for backward compatibility
from src.primitives.aws_operations import (
    S3UploadPrimitive,
    S3DownloadPrimitive,
    S3ListPrimitive,
    BedrockInvokePrimitive,
    DynamoDBGetItemPrimitive,
)

__all__ = [
    # Base classes
    "BasePrimitive",
    "PrimitiveResult",
    "PrimitiveRegistry",
    "get_registry",
    "get_primitive",
    "register_primitive",
    
    # Tool Registry (new)
    "ToolRegistry",
    "ToolMetadata",
    "get_tool_registry",
    "register_tool",
    
    # Existing file operations (backward compatibility)
    "ReadFilePrimitive",
    "WriteFilePrimitive",
    "ListDirectoryPrimitive",
    "CreateDirectoryPrimitive",
    "DeletePathPrimitive",
    
    # New native primitives
    "BashExecutor",
    "FileSearch",
    "FileEditor",
    
    # AWS primitives (new)
    "S3Manager",
    "DynamoDBClient",
    "BedrockInvoker",
    "CloudWatchInspector",
    
    # Web primitives
    "SearchEngine",
    "PublicAPICaller",
    "NovaActScraper",
    
    # MCP adapter primitives
    "MCPClient",
    "MCPTool",
    "MCPToolPrimitive",
    "MCPManager",
    "MCPMessage",
    
    # Developer tools primitives
    "ASTParser",
    "GitManipulator",
    
    # Legacy AWS primitives (backward compatibility)
    "S3UploadPrimitive",
    "S3DownloadPrimitive",
    "S3ListPrimitive",
    "BedrockInvokePrimitive",
    "DynamoDBGetItemPrimitive",
]


def register_all() -> None:
    """Register all primitives with the tool registry.
    
    This function registers all available primitives with the unified
    ToolRegistry for use with both IntentFinder and Bedrock Tool Calling.
    """
    # Native primitives
    from src.primitives.native import register_all as register_native
    register_native()
    
    # Cloud AWS primitives
    from src.primitives.cloud_aws import register_all as register_cloud_aws
    register_cloud_aws()
    
    # Web primitives
    from src.primitives.web import register_all as register_web
    register_web()
    
    # Developer tools primitives
    from src.primitives.dev import register_all as register_dev
    register_dev()
    
    # Legacy primitives (for backward compatibility)
    from src.primitives.file_operations import register_all as register_file_ops
    from src.primitives.aws_operations import register_all as register_aws_ops
    register_file_ops()
    register_aws_ops()


# Auto-register on import (for backward compatibility)
# Use the new unified registry
register_all()
