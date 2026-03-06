"""Tool Registry - Unified registry for all primitives with Bedrock integration.

This module provides a centralized registry for all primitive tools in octopOS,
with support for both semantic search (IntentFinder) and Bedrock Tool Calling.

Example:
    >>> from src.primitives.tool_registry import ToolRegistry
    >>> registry = ToolRegistry()
    >>> registry.register(MyPrimitive())
    >>> 
    >>> # Get Bedrock tool configs
    >>> bedrock_tools = registry.to_bedrock_tool_config()
    >>> 
    >>> # Get IntentFinder schemas  
    >>> intent_schemas = registry.to_intent_finder_schema()
"""

from typing import Any, Dict, List, Optional, Type, Callable
from dataclasses import dataclass, field
import json
import inspect

from src.primitives.base_primitive import BasePrimitive, PrimitiveResult
from src.utils.logger import get_logger

logger = get_logger()


@dataclass
class ToolMetadata:
    """Metadata for a registered tool."""
    name: str
    description: str
    category: str  # native, web, cloud_aws, dev, mcp
    primitive: BasePrimitive
    parameters: Dict[str, Any]
    enabled: bool = True
    tags: List[str] = field(default_factory=list)


class ToolRegistry:
    """Unified registry for all primitive tools.
    
    Manages primitives and provides conversion to various formats:
    - Bedrock Tool Calling (toolConfig JSON)
    - IntentFinder (semantic search schemas)
    - OpenAPI schemas
    
    This is a singleton-style class - use get_registry() to get the global instance.
    """
    
    _instance: Optional['ToolRegistry'] = None
    _initialized: bool = False
    
    def __new__(cls) -> 'ToolRegistry':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self) -> None:
        if ToolRegistry._initialized:
            return
            
        self._tools: Dict[str, ToolMetadata] = {}
        self._categories: Dict[str, List[str]] = {
            'native': [],
            'web': [],
            'cloud_aws': [],
            'dev': [],
            'mcp': [],
        }
        self._hooks: Dict[str, List[Callable]] = {
            'on_register': [],
            'on_unregister': [],
        }
        ToolRegistry._initialized = True
        logger.info("ToolRegistry initialized")
    
    def register(
        self,
        primitive: BasePrimitive,
        category: str = 'native',
        tags: Optional[List[str]] = None
    ) -> None:
        """Register a primitive tool.
        
        Args:
            primitive: The primitive instance to register
            category: Tool category (native, web, cloud_aws, dev, mcp)
            tags: Optional list of tags for filtering
        """
        name = primitive.name
        
        if name in self._tools:
            logger.warning(f"Tool '{name}' already registered, updating")
        
        metadata = ToolMetadata(
            name=name,
            description=primitive.description,
            category=category,
            primitive=primitive,
            parameters=primitive.parameters,
            tags=tags or []
        )
        
        self._tools[name] = metadata
        
        if category not in self._categories:
            self._categories[category] = []
        if name not in self._categories[category]:
            self._categories[category].append(name)
        
        # Run hooks
        for hook in self._hooks['on_register']:
            try:
                hook(metadata)
            except Exception as e:
                logger.error(f"Register hook error: {e}")
        
        logger.debug(f"Registered tool: {name} (category: {category})")
    
    def unregister(self, name: str) -> bool:
        """Unregister a tool.
        
        Args:
            name: Name of the tool to unregister
            
        Returns:
            True if unregistered, False if not found
        """
        if name not in self._tools:
            return False
        
        metadata = self._tools[name]
        category = metadata.category
        
        del self._tools[name]
        
        if category in self._categories and name in self._categories[category]:
            self._categories[category].remove(name)
        
        # Run hooks
        for hook in self._hooks['on_unregister']:
            try:
                hook(metadata)
            except Exception as e:
                logger.error(f"Unregister hook error: {e}")
        
        logger.debug(f"Unregistered tool: {name}")
        return True
    
    def get(self, name: str) -> Optional[ToolMetadata]:
        """Get tool metadata by name.
        
        Args:
            name: Tool name
            
        Returns:
            ToolMetadata or None if not found
        """
        return self._tools.get(name)
    
    def get_primitive(self, name: str) -> Optional[BasePrimitive]:
        """Get the primitive instance by name.
        
        Args:
            name: Tool name
            
        Returns:
            BasePrimitive instance or None
        """
        metadata = self._tools.get(name)
        return metadata.primitive if metadata else None
    
    def list_tools(
        self,
        category: Optional[str] = None,
        enabled_only: bool = True
    ) -> List[ToolMetadata]:
        """List all registered tools.
        
        Args:
            category: Filter by category (optional)
            enabled_only: Only return enabled tools
            
        Returns:
            List of ToolMetadata
        """
        tools = []
        
        if category:
            names = self._categories.get(category, [])
            for name in names:
                if name in self._tools:
                    metadata = self._tools[name]
                    if not enabled_only or metadata.enabled:
                        tools.append(metadata)
        else:
            for metadata in self._tools.values():
                if not enabled_only or metadata.enabled:
                    tools.append(metadata)
        
        return tools
    
    def list_by_category(self) -> Dict[str, List[str]]:
        """Get tools organized by category.
        
        Returns:
            Dictionary mapping category names to tool name lists
        """
        return {
            cat: list(names) 
            for cat, names in self._categories.items()
            if names
        }
    
    def to_bedrock_tool_config(self, enabled_only: bool = True) -> List[Dict[str, Any]]:
        """Convert tools to Bedrock Tool Calling format.
        
        Generates toolConfig JSON schemas compatible with AWS Bedrock Nova models.
        
        Args:
            enabled_only: Only include enabled tools
            
        Returns:
            List of Bedrock tool specifications
        """
        tools = []
        
        for metadata in self._tools.values():
            if enabled_only and not metadata.enabled:
                continue
            
            tool_spec = self._convert_to_bedrock_schema(metadata)
            tools.append(tool_spec)
        
        return tools
    
    def _convert_to_bedrock_schema(self, metadata: ToolMetadata) -> Dict[str, Any]:
        """Convert ToolMetadata to Bedrock toolConfig schema.
        
        Bedrock format:
        {
            "toolSpec": {
                "name": "tool_name",
                "description": "Tool description",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {...},
                        "required": [...]
                    }
                }
            }
        }
        """
        properties = {}
        required = []
        
        for param_name, param_spec in metadata.parameters.items():
            prop = {
                "type": self._map_type_to_json_schema(param_spec.get("type", "string")),
                "description": param_spec.get("description", "")
            }
            
            # Add default if present
            if "default" in param_spec:
                prop["default"] = param_spec["default"]
            
            # Add enum if options present
            if "enum" in param_spec:
                prop["enum"] = param_spec["enum"]
            
            properties[param_name] = prop
            
            if param_spec.get("required", False):
                required.append(param_name)
        
        return {
            "toolSpec": {
                "name": metadata.name,
                "description": metadata.description,
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": properties,
                        "required": required
                    }
                }
            }
        }
    
    def _map_type_to_json_schema(self, type_name: str) -> str:
        """Map primitive type names to JSON Schema types."""
        type_mapping = {
            "string": "string",
            "integer": "integer",
            "number": "number",
            "boolean": "boolean",
            "array": "array",
            "object": "object",
            "any": "string"  # Default fallback
        }
        return type_mapping.get(type_name, "string")
    
    def to_intent_finder_schema(self, enabled_only: bool = True) -> List[Dict[str, Any]]:
        """Convert tools to IntentFinder format for semantic search.
        
        Args:
            enabled_only: Only include enabled tools
            
        Returns:
            List of IntentFinder schemas
        """
        schemas = []
        
        for metadata in self._tools.values():
            if enabled_only and not metadata.enabled:
                continue
            
            schema = {
                "name": metadata.name,
                "description": metadata.description,
                "category": metadata.category,
                "parameters": metadata.parameters,
                "tags": metadata.tags
            }
            schemas.append(schema)
        
        return schemas
    
    def to_openapi_schema(self, enabled_only: bool = True) -> Dict[str, Any]:
        """Convert tools to OpenAPI 3.0 schema format.
        
        Args:
            enabled_only: Only include enabled tools
            
        Returns:
            OpenAPI schema dictionary
        """
        paths = {}
        
        for metadata in self._tools.values():
            if enabled_only and not metadata.enabled:
                continue
            
            path = f"/tools/{metadata.name}"
            
            properties = {}
            required = []
            
            for param_name, param_spec in metadata.parameters.items():
                properties[param_name] = {
                    "type": self._map_type_to_json_schema(param_spec.get("type", "string")),
                    "description": param_spec.get("description", "")
                }
                if param_spec.get("required", False):
                    required.append(param_name)
            
            paths[path] = {
                "post": {
                    "summary": metadata.description,
                    "operationId": metadata.name,
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": properties,
                                    "required": required
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "Successful execution",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object"
                                    }
                                }
                            }
                        }
                    }
                }
            }
        
        return {
            "openapi": "3.0.0",
            "info": {
                "title": "octopOS Tool API",
                "version": "1.0.0"
            },
            "paths": paths
        }
    
    async def execute_tool(self, tool_name: str, **kwargs) -> PrimitiveResult:
        """Execute a tool by name.
        
        Args:
            tool_name: Tool name
            **kwargs: Parameters for the tool
            
        Returns:
            PrimitiveResult from execution
        """
        metadata = self.get(tool_name)
        if not metadata:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Tool not found: {tool_name}",
                error="ToolNotFound"
            )
        
        if not metadata.enabled:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Tool is disabled: {tool_name}",
                error="ToolDisabled"
            )
        
        try:
            return await metadata.primitive.execute(**kwargs)
        except Exception as e:
            logger.error(f"Tool execution error ({tool_name}): {e}")
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Execution failed: {e}",
                error=str(e)
            )
    
    def add_hook(self, event: str, callback: Callable) -> None:
        """Add a lifecycle hook.
        
        Args:
            event: Event name ('on_register', 'on_unregister')
            callback: Function to call
        """
        if event in self._hooks:
            self._hooks[event].append(callback)
    
    def clear(self) -> None:
        """Clear all registered tools."""
        self._tools.clear()
        for cat in self._categories:
            self._categories[cat].clear()
        logger.info("ToolRegistry cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics.
        
        Returns:
            Statistics dictionary
        """
        return {
            "total_tools": len(self._tools),
            "enabled_tools": sum(1 for t in self._tools.values() if t.enabled),
            "categories": {
                cat: len(names) for cat, names in self._categories.items()
            },
            "tool_names": list(self._tools.keys())
        }


# Global registry instance
_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """Get the global ToolRegistry instance.
    
    Returns:
        ToolRegistry singleton instance
    """
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def register_primitive(
    primitive: BasePrimitive,
    category: str = 'native',
    tags: Optional[List[str]] = None
) -> None:
    """Register a primitive with the global registry.
    
    Convenience function for registering primitives.
    
    Args:
        primitive: Primitive instance to register
        category: Tool category
        tags: Optional tags
    """
    registry = get_registry()
    registry.register(primitive, category, tags)


def unregister_primitive(name: str) -> bool:
    """Unregister a primitive from the global registry.
    
    Args:
        name: Name of the primitive to unregister
        
    Returns:
        True if unregistered, False if not found
    """
    registry = get_registry()
    return registry.unregister(name)
