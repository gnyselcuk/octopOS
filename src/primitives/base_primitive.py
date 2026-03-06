"""Base Primitive - Base class for all primitive tools.

This module provides the foundation for creating primitive tools
that can be used by agents in the octopOS system.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass


@dataclass
class PrimitiveResult:
    """Result from executing a primitive."""
    
    success: bool
    data: Any
    message: str
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class BasePrimitive(ABC):
    """Base class for all primitive tools.
    
    All primitives must inherit from this class and implement
    the execute method. Primitives are the basic building blocks
    that agents use to perform tasks.
    
    Example:
        >>> class MyPrimitive(BasePrimitive):
        ...     @property
        ...     def name(self) -> str:
        ...         return "my_primitive"
        ...     
        ...     async def execute(self, **kwargs) -> PrimitiveResult:
        ...         # Implementation
        ...         return PrimitiveResult(success=True, data={}, message="Done")
    """
    
    def __init__(self) -> None:
        """Initialize the primitive."""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the primitive name.
        
        Returns:
            Unique name for this primitive
        """
        raise NotImplementedError("Subclasses must implement name property")
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Return the primitive description.
        
        Returns:
            Human-readable description
        """
        raise NotImplementedError("Subclasses must implement description property")
    
    @property
    def parameters(self) -> Dict[str, Dict[str, Any]]:
        """Return parameter schema.
        
        Returns:
            Dictionary mapping parameter names to their specs:
            {
                "param_name": {
                    "type": "string|integer|boolean|etc",
                    "description": "Parameter description",
                    "required": True|False,
                    "default": default_value
                }
            }
        """
        return {}
    
    @abstractmethod
    async def execute(self, **kwargs) -> PrimitiveResult:
        """Execute the primitive.
        
        Args:
            **kwargs: Parameters defined in parameters property
            
        Returns:
            PrimitiveResult with execution results
        """
        raise NotImplementedError("Subclasses must implement execute()")
    
    def validate_params(self, params: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate input parameters.
        
        Args:
            params: Parameters to validate
            
        Returns:
            Tuple of (valid, error_message)
        """
        schema = self.parameters
        
        for param_name, spec in schema.items():
            if spec.get("required", False) and param_name not in params:
                return False, f"Missing required parameter: {param_name}"
            
            if param_name in params:
                value = params[param_name]
                expected_type = spec.get("type", "any")
                
                type_map = {
                    "string": str,
                    "integer": int,
                    "boolean": bool,
                    "number": (int, float),
                    "array": list,
                    "object": dict
                }
                
                if expected_type in type_map and not isinstance(value, type_map[expected_type]):
                    return False, f"Parameter {param_name} must be of type {expected_type}"
        
        return True, None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert primitive to dictionary for registration.
        
        Returns:
            Dictionary representation
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters
        }


class PrimitiveRegistry:
    """Registry for primitive tools.
    
    Manages all available primitives and provides lookup functionality.
    """
    
    def __init__(self) -> None:
        """Initialize the registry."""
        self._primitives: Dict[str, BasePrimitive] = {}
    
    def register(self, primitive: BasePrimitive) -> None:
        """Register a primitive.
        
        Args:
            primitive: Primitive instance to register
        """
        self._primitives[primitive.name] = primitive
    
    def unregister(self, name: str) -> None:
        """Unregister a primitive.
        
        Args:
            name: Name of primitive to unregister
        """
        if name in self._primitives:
            del self._primitives[name]
    
    def get(self, name: str) -> Optional[BasePrimitive]:
        """Get a primitive by name.
        
        Args:
            name: Primitive name
            
        Returns:
            Primitive instance or None
        """
        return self._primitives.get(name)
    
    def list_primitives(self) -> List[Dict[str, Any]]:
        """List all registered primitives.
        
        Returns:
            List of primitive info dictionaries
        """
        return [p.to_dict() for p in self._primitives.values()]
    
    def clear(self) -> None:
        """Clear all registered primitives."""
        self._primitives.clear()


# Global registry
_registry = PrimitiveRegistry()


def get_registry() -> PrimitiveRegistry:
    """Get the global primitive registry.
    
    Returns:
        Global PrimitiveRegistry instance
    """
    return _registry


def register_primitive(primitive: BasePrimitive) -> None:
    """Register a primitive in the global registry.
    
    Args:
        primitive: Primitive to register
    """
    _registry.register(primitive)


def get_primitive(name: str) -> Optional[BasePrimitive]:
    """Get a primitive from the global registry.
    
    Args:
        name: Primitive name
        
    Returns:
        Primitive instance or None
    """
    return _registry.get(name)