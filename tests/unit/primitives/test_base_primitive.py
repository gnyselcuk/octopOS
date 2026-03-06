"""Unit tests for primitives/base_primitive.py module.

This module tests the BasePrimitive class and PrimitiveRegistry.
"""

import pytest

from src.primitives.base_primitive import (
    BasePrimitive,
    PrimitiveRegistry,
    PrimitiveResult,
    get_primitive,
    get_registry,
    register_primitive,
)


class ConcretePrimitive(BasePrimitive):
    """Concrete implementation for testing."""
    
    @property
    def name(self) -> str:
        return "test_primitive"
    
    @property
    def description(self) -> str:
        return "A test primitive"
    
    @property
    def parameters(self):
        return {
            "input": {
                "type": "string",
                "description": "Input string",
                "required": True
            },
            "option": {
                "type": "boolean",
                "description": "Optional flag",
                "required": False,
                "default": False
            }
        }
    
    async def execute(self, **kwargs):
        return PrimitiveResult(
            success=True,
            data=kwargs.get("input", ""),
            message="Executed successfully"
        )


class MinimalPrimitive(BasePrimitive):
    """Minimal implementation for testing abstract methods."""
    
    @property
    def name(self) -> str:
        return "minimal"
    
    @property
    def description(self) -> str:
        return "Minimal primitive"
    
    async def execute(self, **kwargs):
        return PrimitiveResult(success=True, data=None, message="Done")


class TestPrimitiveResult:
    """Test PrimitiveResult dataclass."""
    
    def test_create_success_result(self):
        """Test creating a successful result."""
        result = PrimitiveResult(
            success=True,
            data={"key": "value"},
            message="Operation completed"
        )
        
        assert result.success is True
        assert result.data == {"key": "value"}
        assert result.message == "Operation completed"
        assert result.error is None
        assert result.metadata is None
    
    def test_create_error_result(self):
        """Test creating an error result."""
        result = PrimitiveResult(
            success=False,
            data=None,
            message="Operation failed",
            error="Something went wrong",
            metadata={"error_code": 500}
        )
        
        assert result.success is False
        assert result.error == "Something went wrong"
        assert result.metadata == {"error_code": 500}
    
    def test_result_defaults(self):
        """Test PrimitiveResult default values."""
        result = PrimitiveResult(
            success=True,
            data=None,
            message="Test"
        )
        
        assert result.error is None
        assert result.metadata is None


class TestBasePrimitive:
    """Test BasePrimitive abstract class."""
    
    @pytest.fixture
    def primitive(self):
        """Create a concrete primitive instance."""
        return ConcretePrimitive()
    
    def test_abstract_methods_require_implementation(self):
        """Test that abstract methods must be implemented."""
        with pytest.raises(TypeError):
            BasePrimitive()  # Cannot instantiate abstract class
    
    def test_name_property(self, primitive):
        """Test name property returns correct value."""
        assert primitive.name == "test_primitive"
    
    def test_description_property(self, primitive):
        """Test description property returns correct value."""
        assert primitive.description == "A test primitive"
    
    def test_execute_method_requirement(self, primitive):
        """Test that execute method is required and works."""
        import asyncio
        result = asyncio.run(primitive.execute(input="test"))
        
        assert isinstance(result, PrimitiveResult)
        assert result.success is True
    
    def test_parameters_default(self):
        """Test default parameters property."""
        minimal = MinimalPrimitive()
        assert minimal.parameters == {}
    
    def test_parameters_custom(self, primitive):
        """Test custom parameters property."""
        params = primitive.parameters
        
        assert "input" in params
        assert params["input"]["type"] == "string"
        assert params["input"]["required"] is True
        assert params["input"]["description"] == "Input string"
        
        assert "option" in params
        assert params["option"]["required"] is False
        assert params["option"]["default"] is False
    
    def test_validate_params_success(self, primitive):
        """Test parameter validation with valid params."""
        params = {"input": "test value", "option": True}
        valid, error = primitive.validate_params(params)
        
        assert valid is True
        assert error is None
    
    def test_validate_params_missing_required(self, primitive):
        """Test validation with missing required parameter."""
        params = {"option": True}  # Missing "input"
        valid, error = primitive.validate_params(params)
        
        assert valid is False
        assert "Missing required parameter" in error
        assert "input" in error
    
    def test_validate_params_wrong_type_string(self, primitive):
        """Test validation with wrong string type."""
        params = {"input": 123}  # Should be string
        valid, error = primitive.validate_params(params)
        
        assert valid is False
        assert "must be of type string" in error
    
    def test_validate_params_wrong_type_boolean(self, primitive):
        """Test validation with wrong boolean type."""
        params = {"input": "test", "option": "not_a_boolean"}
        valid, error = primitive.validate_params(params)
        
        assert valid is False
        assert "must be of type boolean" in error
    
    def test_validate_params_integer_type(self):
        """Test validation with integer type."""
        class IntPrimitive(BasePrimitive):
            @property
            def name(self): return "int_test"
            @property
            def description(self): return "Test"
            @property
            def parameters(self):
                return {"count": {"type": "integer", "required": True}}
            async def execute(self, **kwargs):
                return PrimitiveResult(True, None, "Done")
        
        prim = IntPrimitive()
        
        # Valid integer
        valid, _ = prim.validate_params({"count": 42})
        assert valid is True
        
        # Invalid type
        valid, error = prim.validate_params({"count": "42"})
        assert valid is False
        assert "integer" in error
    
    def test_validate_params_number_type(self):
        """Test validation with number type (int or float)."""
        class NumberPrimitive(BasePrimitive):
            @property
            def name(self): return "number_test"
            @property
            def description(self): return "Test"
            @property
            def parameters(self):
                return {"value": {"type": "number", "required": True}}
            async def execute(self, **kwargs):
                return PrimitiveResult(True, None, "Done")
        
        prim = NumberPrimitive()
        
        # Valid int
        valid, _ = prim.validate_params({"value": 42})
        assert valid is True
        
        # Valid float
        valid, _ = prim.validate_params({"value": 3.14})
        assert valid is True
        
        # Invalid type
        valid, error = prim.validate_params({"value": "3.14"})
        assert valid is False
        assert "number" in error
    
    def test_validate_params_array_type(self):
        """Test validation with array type."""
        class ArrayPrimitive(BasePrimitive):
            @property
            def name(self): return "array_test"
            @property
            def description(self): return "Test"
            @property
            def parameters(self):
                return {"items": {"type": "array", "required": True}}
            async def execute(self, **kwargs):
                return PrimitiveResult(True, None, "Done")
        
        prim = ArrayPrimitive()
        
        # Valid list
        valid, _ = prim.validate_params({"items": [1, 2, 3]})
        assert valid is True
        
        # Invalid type
        valid, error = prim.validate_params({"items": "not a list"})
        assert valid is False
        assert "array" in error
    
    def test_validate_params_object_type(self):
        """Test validation with object type."""
        class ObjectPrimitive(BasePrimitive):
            @property
            def name(self): return "object_test"
            @property
            def description(self): return "Test"
            @property
            def parameters(self):
                return {"config": {"type": "object", "required": True}}
            async def execute(self, **kwargs):
                return PrimitiveResult(True, None, "Done")
        
        prim = ObjectPrimitive()
        
        # Valid dict
        valid, _ = prim.validate_params({"config": {"key": "value"}})
        assert valid is True
        
        # Invalid type
        valid, error = prim.validate_params({"config": "not a dict"})
        assert valid is False
        assert "object" in error
    
    def test_validate_params_optional_not_required(self, primitive):
        """Test that optional parameters don't need to be provided."""
        params = {"input": "test"}  # Missing optional "option"
        valid, error = primitive.validate_params(params)
        
        assert valid is True
        assert error is None
    
    def test_validate_params_empty_schema(self):
        """Test validation with empty parameter schema."""
        minimal = MinimalPrimitive()
        valid, error = minimal.validate_params({})
        
        assert valid is True
        assert error is None
    
    def test_validate_params_any_type(self):
        """Test validation with any type (no type checking)."""
        class AnyPrimitive(BasePrimitive):
            @property
            def name(self): return "any_test"
            @property
            def description(self): return "Test"
            @property
            def parameters(self):
                return {"data": {"required": True}}  # No type specified
            async def execute(self, **kwargs):
                return PrimitiveResult(True, None, "Done")
        
        prim = AnyPrimitive()
        
        # Any type should be valid
        valid, _ = prim.validate_params({"data": "string"})
        assert valid is True
        
        valid, _ = prim.validate_params({"data": 123})
        assert valid is True
        
        valid, _ = prim.validate_params({"data": [1, 2, 3]})
        assert valid is True
    
    def test_to_dict(self, primitive):
        """Test converting primitive to dictionary."""
        result = primitive.to_dict()
        
        assert result["name"] == "test_primitive"
        assert result["description"] == "A test primitive"
        assert "parameters" in result
        assert "input" in result["parameters"]


class TestPrimitiveRegistry:
    """Test PrimitiveRegistry class."""
    
    @pytest.fixture
    def registry(self):
        """Create a fresh registry for testing."""
        return PrimitiveRegistry()
    
    @pytest.fixture
    def primitive(self):
        """Create a test primitive."""
        return ConcretePrimitive()
    
    def test_register_primitive(self, registry, primitive):
        """Test registering a primitive."""
        registry.register(primitive)
        
        retrieved = registry.get("test_primitive")
        assert retrieved is primitive
    
    def test_register_multiple_primitives(self, registry):
        """Test registering multiple primitives."""
        prim1 = ConcretePrimitive()
        prim2 = MinimalPrimitive()
        
        registry.register(prim1)
        registry.register(prim2)
        
        assert registry.get("test_primitive") is prim1
        assert registry.get("minimal") is prim2
    
    def test_unregister_primitive(self, registry, primitive):
        """Test unregistering a primitive."""
        registry.register(primitive)
        registry.unregister("test_primitive")
        
        assert registry.get("test_primitive") is None
    
    def test_unregister_nonexistent(self, registry):
        """Test unregistering a non-existent primitive."""
        # Should not raise an error
        registry.unregister("nonexistent")
    
    def test_get_nonexistent(self, registry):
        """Test getting a non-existent primitive."""
        result = registry.get("nonexistent")
        assert result is None
    
    def test_list_primitives(self, registry):
        """Test listing all registered primitives."""
        prim1 = ConcretePrimitive()
        prim2 = MinimalPrimitive()
        
        registry.register(prim1)
        registry.register(prim2)
        
        primitives = registry.list_primitives()
        
        assert len(primitives) == 2
        names = [p["name"] for p in primitives]
        assert "test_primitive" in names
        assert "minimal" in names
    
    def test_list_primitives_empty(self, registry):
        """Test listing primitives when none registered."""
        primitives = registry.list_primitives()
        assert primitives == []
    
    def test_clear_registry(self, registry, primitive):
        """Test clearing the registry."""
        registry.register(primitive)
        registry.clear()
        
        assert registry.get("test_primitive") is None
        assert registry.list_primitives() == []
    
    def test_register_overwrite(self, registry, primitive):
        """Test that registering with same name overwrites."""
        registry.register(primitive)
        
        # Create another primitive with same name
        class AnotherPrimitive(BasePrimitive):
            @property
            def name(self): return "test_primitive"
            @property
            def description(self): return "Another"
            async def execute(self, **kwargs):
                return PrimitiveResult(True, None, "Done")
        
        another = AnotherPrimitive()
        registry.register(another)
        
        # Should be the new one
        retrieved = registry.get("test_primitive")
        assert retrieved is another


class TestGlobalRegistryFunctions:
    """Test global registry helper functions."""
    
    def test_get_registry(self):
        """Test getting the global registry."""
        registry = get_registry()
        assert isinstance(registry, PrimitiveRegistry)
    
    def test_get_registry_singleton(self):
        """Test that get_registry returns same instance."""
        registry1 = get_registry()
        registry2 = get_registry()
        assert registry1 is registry2
    
    def test_register_and_get_primitive(self):
        """Test global register and get functions."""
        primitive = ConcretePrimitive()
        register_primitive(primitive)
        
        retrieved = get_primitive("test_primitive")
        assert retrieved is primitive
    
    def test_get_nonexistent_primitive(self):
        """Test getting non-existent primitive from global registry."""
        result = get_primitive("definitely_not_exists")
        assert result is None
