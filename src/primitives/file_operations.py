"""File Operations Primitives - Basic file system operations.

This module provides primitives for common file operations like
reading, writing, listing, and managing files and directories.
"""

import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.primitives.base_primitive import BasePrimitive, PrimitiveResult, register_primitive


class ReadFilePrimitive(BasePrimitive):
    """Read contents of a file."""
    
    @property
    def name(self) -> str:
        return "read_file"
    
    @property
    def description(self) -> str:
        return "Read the contents of a text file"
    
    @property
    def parameters(self) -> Dict[str, Dict[str, Any]]:
        return {
            "path": {
                "type": "string",
                "description": "Path to the file to read",
                "required": True
            },
            "encoding": {
                "type": "string",
                "description": "File encoding",
                "required": False,
                "default": "utf-8"
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of lines to read (0 = all)",
                "required": False,
                "default": 0
            }
        }
    
    async def execute(self, **kwargs) -> PrimitiveResult:
        """Execute file read."""
        path = kwargs.get("path")
        encoding = kwargs.get("encoding", "utf-8")
        limit = kwargs.get("limit", 0)
        
        try:
            file_path = Path(path).expanduser()
            
            if not file_path.exists():
                return PrimitiveResult(
                    success=False,
                    data=None,
                    message=f"File not found: {path}",
                    error="FileNotFoundError"
                )
            
            if not file_path.is_file():
                return PrimitiveResult(
                    success=False,
                    data=None,
                    message=f"Path is not a file: {path}",
                    error="NotAFileError"
                )
            
            with open(file_path, 'r', encoding=encoding) as f:
                if limit > 0:
                    lines = []
                    for i, line in enumerate(f):
                        if i >= limit:
                            break
                        lines.append(line)
                    content = ''.join(lines)
                else:
                    content = f.read()
            
            return PrimitiveResult(
                success=True,
                data={
                    "content": content,
                    "path": str(file_path),
                    "size": len(content),
                    "lines": content.count('\n') + 1
                },
                message=f"Successfully read file: {path}"
            )
            
        except Exception as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Failed to read file: {e}",
                error=str(e)
            )


class WriteFilePrimitive(BasePrimitive):
    """Write contents to a file."""
    
    @property
    def name(self) -> str:
        return "write_file"
    
    @property
    def description(self) -> str:
        return "Write content to a text file"
    
    @property
    def parameters(self) -> Dict[str, Dict[str, Any]]:
        return {
            "path": {
                "type": "string",
                "description": "Path to the file to write",
                "required": True
            },
            "content": {
                "type": "string",
                "description": "Content to write",
                "required": True
            },
            "encoding": {
                "type": "string",
                "description": "File encoding",
                "required": False,
                "default": "utf-8"
            },
            "append": {
                "type": "boolean",
                "description": "Append to file instead of overwriting",
                "required": False,
                "default": False
            }
        }
    
    async def execute(self, **kwargs) -> PrimitiveResult:
        """Execute file write."""
        path = kwargs.get("path")
        content = kwargs.get("content")
        encoding = kwargs.get("encoding", "utf-8")
        append = kwargs.get("append", False)
        
        try:
            file_path = Path(path).expanduser()
            
            # Ensure directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            mode = 'a' if append else 'w'
            with open(file_path, mode, encoding=encoding) as f:
                f.write(content)
            
            return PrimitiveResult(
                success=True,
                data={
                    "path": str(file_path),
                    "bytes_written": len(content.encode(encoding))
                },
                message=f"Successfully {'appended to' if append else 'wrote'} file: {path}"
            )
            
        except Exception as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Failed to write file: {e}",
                error=str(e)
            )


class ListDirectoryPrimitive(BasePrimitive):
    """List contents of a directory."""
    
    @property
    def name(self) -> str:
        return "list_directory"
    
    @property
    def description(self) -> str:
        return "List files and directories in a path"
    
    @property
    def parameters(self) -> Dict[str, Dict[str, Any]]:
        return {
            "path": {
                "type": "string",
                "description": "Directory path to list",
                "required": True
            },
            "recursive": {
                "type": "boolean",
                "description": "List recursively",
                "required": False,
                "default": False
            },
            "pattern": {
                "type": "string",
                "description": "File pattern to match (e.g., '*.py')",
                "required": False,
                "default": "*"
            }
        }
    
    async def execute(self, **kwargs) -> PrimitiveResult:
        """Execute directory listing."""
        path = kwargs.get("path", ".")
        recursive = kwargs.get("recursive", False)
        pattern = kwargs.get("pattern", "*")
        
        try:
            dir_path = Path(path).expanduser()
            
            if not dir_path.exists():
                return PrimitiveResult(
                    success=False,
                    data=None,
                    message=f"Directory not found: {path}",
                    error="DirectoryNotFoundError"
                )
            
            if not dir_path.is_dir():
                return PrimitiveResult(
                    success=False,
                    data=None,
                    message=f"Path is not a directory: {path}",
                    error="NotADirectoryError"
                )
            
            items = []
            
            if recursive:
                for item in dir_path.rglob(pattern):
                    items.append({
                        "name": item.name,
                        "path": str(item),
                        "type": "directory" if item.is_dir() else "file",
                        "size": item.stat().st_size if item.is_file() else None
                    })
            else:
                for item in dir_path.glob(pattern):
                    items.append({
                        "name": item.name,
                        "path": str(item),
                        "type": "directory" if item.is_dir() else "file",
                        "size": item.stat().st_size if item.is_file() else None
                    })
            
            return PrimitiveResult(
                success=True,
                data={
                    "path": str(dir_path),
                    "items": items,
                    "count": len(items)
                },
                message=f"Listed {len(items)} items in {path}"
            )
            
        except Exception as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Failed to list directory: {e}",
                error=str(e)
            )


class CreateDirectoryPrimitive(BasePrimitive):
    """Create a directory."""
    
    @property
    def name(self) -> str:
        return "create_directory"
    
    @property
    def description(self) -> str:
        return "Create a new directory"
    
    @property
    def parameters(self) -> Dict[str, Dict[str, Any]]:
        return {
            "path": {
                "type": "string",
                "description": "Path of directory to create",
                "required": True
            },
            "parents": {
                "type": "boolean",
                "description": "Create parent directories if they don't exist",
                "required": False,
                "default": True
            }
        }
    
    async def execute(self, **kwargs) -> PrimitiveResult:
        """Execute directory creation."""
        path = kwargs.get("path")
        parents = kwargs.get("parents", True)
        
        try:
            dir_path = Path(path).expanduser()
            
            dir_path.mkdir(parents=parents, exist_ok=True)
            
            return PrimitiveResult(
                success=True,
                data={"path": str(dir_path)},
                message=f"Created directory: {path}"
            )
            
        except Exception as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Failed to create directory: {e}",
                error=str(e)
            )


class DeletePathPrimitive(BasePrimitive):
    """Delete a file or directory."""
    
    @property
    def name(self) -> str:
        return "delete_path"
    
    @property
    def description(self) -> str:
        return "Delete a file or directory"
    
    @property
    def parameters(self) -> Dict[str, Dict[str, Any]]:
        return {
            "path": {
                "type": "string",
                "description": "Path to delete",
                "required": True
            },
            "recursive": {
                "type": "boolean",
                "description": "Recursively delete directories",
                "required": False,
                "default": False
            }
        }
    
    async def execute(self, **kwargs) -> PrimitiveResult:
        """Execute path deletion."""
        path = kwargs.get("path")
        recursive = kwargs.get("recursive", False)
        
        try:
            target_path = Path(path).expanduser()
            
            if not target_path.exists():
                return PrimitiveResult(
                    success=False,
                    data=None,
                    message=f"Path not found: {path}",
                    error="PathNotFoundError"
                )
            
            if target_path.is_file():
                target_path.unlink()
            elif target_path.is_dir():
                if recursive:
                    shutil.rmtree(target_path)
                else:
                    target_path.rmdir()  # Only works if empty
            
            return PrimitiveResult(
                success=True,
                data={"deleted_path": str(target_path)},
                message=f"Deleted: {path}"
            )
            
        except Exception as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Failed to delete: {e}",
                error=str(e)
            )


# Register all primitives
def register_all():
    """Register all file operation primitives."""
    register_primitive(ReadFilePrimitive())
    register_primitive(WriteFilePrimitive())
    register_primitive(ListDirectoryPrimitive())
    register_primitive(CreateDirectoryPrimitive())
    register_primitive(DeletePathPrimitive())