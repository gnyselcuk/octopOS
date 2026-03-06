"""Native Primitives - Core system and file operation tools."""

from src.primitives.native.bash_executor import BashExecutor
from src.primitives.native.file_search import FileSearch
from src.primitives.native.file_editor import FileEditor

# Re-export existing file operations for backward compatibility
from src.primitives.file_operations import (
    ReadFilePrimitive,
    WriteFilePrimitive,
    ListDirectoryPrimitive,
    CreateDirectoryPrimitive,
    DeletePathPrimitive,
)

__all__ = [
    # New primitives
    "BashExecutor",
    "FileSearch",
    "FileEditor",
    # Existing primitives (backward compatibility)
    "ReadFilePrimitive",
    "WriteFilePrimitive",
    "ListDirectoryPrimitive",
    "CreateDirectoryPrimitive",
    "DeletePathPrimitive",
]


def register_all() -> None:
    """Register all native primitives with the tool registry."""
    from src.primitives.tool_registry import register_primitive
    
    # New primitives
    register_primitive(BashExecutor(), category='native', tags=['system', 'execution'])
    register_primitive(FileSearch(), category='native', tags=['file', 'search'])
    register_primitive(FileEditor(), category='native', tags=['file', 'edit'])
    
    # Existing primitives
    register_primitive(ReadFilePrimitive(), category='native', tags=['file', 'read'])
    register_primitive(WriteFilePrimitive(), category='native', tags=['file', 'write'])
    register_primitive(ListDirectoryPrimitive(), category='native', tags=['file', 'list'])
    register_primitive(CreateDirectoryPrimitive(), category='native', tags=['file', 'directory'])
    register_primitive(DeletePathPrimitive(), category='native', tags=['file', 'delete'])
