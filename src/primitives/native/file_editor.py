"""File Editor - Precise file modification with diff/patch logic.

This module provides surgical file editing capabilities:
- Line-by-line modifications (insert, delete, replace)
- Diff/patch logic for precise changes
- Automatic backup creation
- Validation before applying changes
- Never uses sed/cat hacks - pure Python file I/O

Example:
    >>> from src.primitives.native.file_editor import FileEditor
    >>> editor = FileEditor()
    >>> result = await editor.execute(
    ...     path="/workspace/example.py",
    ...     operation="replace_lines",
    ...     start_line=10,
    ...     end_line=15,
    ...     content="new code here"
    ... )
"""

import difflib
import hashlib
import shutil
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from src.primitives.base_primitive import BasePrimitive, PrimitiveResult, register_primitive
from src.utils.logger import get_logger

logger = get_logger()


class EditOperation(str, Enum):
    """Types of edit operations."""
    REPLACE_LINES = "replace_lines"  # Replace range of lines
    INSERT_LINES = "insert_lines"    # Insert at line number
    DELETE_LINES = "delete_lines"    # Delete range of lines
    REPLACE_ALL = "replace_all"      # Replace entire file
    APPEND = "append"                # Append to end
    INSERT_AT_STRING = "insert_at_string"  # Insert after matching string
    REPLACE_STRING = "replace_string"  # Replace matching string


@dataclass
class EditChange:
    """Represents a single change."""
    operation: EditOperation
    start_line: Optional[int] = None  # 1-indexed
    end_line: Optional[int] = None    # 1-indexed, inclusive
    old_content: Optional[str] = None
    new_content: Optional[str] = None
    search_string: Optional[str] = None


@dataclass
class DiffResult:
    """Result of computing a diff."""
    old_hash: str
    new_hash: str
    unified_diff: str
    lines_added: int
    lines_removed: int
    lines_modified: int


class FileEditor(BasePrimitive):
    """Precise file editor with diff/patch capabilities.
    
    This primitive provides surgical file modifications:
    - Line-by-line operations (insert, delete, replace)
    - String-based operations (find and replace)
    - Automatic backup creation before changes
    - Diff generation for review
    - Validation to prevent corruption
    
    Never uses shell commands like sed or cat - uses pure Python file I/O.
    """
    
    def __init__(
        self,
        backup_enabled: bool = True,
        backup_dir: str = ".backups",
        max_file_size: int = 50 * 1024 * 1024  # 50MB
    ) -> None:
        """Initialize File Editor.
        
        Args:
            backup_enabled: Whether to create backups before editing
            backup_dir: Directory for backup files (relative to file)
            max_file_size: Maximum file size to edit (bytes)
        """
        super().__init__()
        self.backup_enabled = backup_enabled
        self.backup_dir = backup_dir
        self.max_file_size = max_file_size
    
    @property
    def name(self) -> str:
        return "file_edit"
    
    @property
    def description(self) -> str:
        return (
            "Precisely edit files using line operations or string replacement. "
            "Supports inserting, deleting, replacing lines, or finding/replacing strings. "
            "Always creates backups before modifying. Uses pure Python file I/O, never shell commands."
        )
    
    @property
    def parameters(self) -> Dict[str, Dict[str, Any]]:
        return {
            "path": {
                "type": "string",
                "description": "Path to the file to edit",
                "required": True
            },
            "operation": {
                "type": "string",
                "description": "Edit operation: replace_lines, insert_lines, delete_lines, replace_all, append, insert_at_string, replace_string",
                "required": True,
                "enum": [op.value for op in EditOperation]
            },
            "content": {
                "type": "string",
                "description": "New content to insert or replace with",
                "required": False,
                "default": None
            },
            "start_line": {
                "type": "integer",
                "description": "Starting line number (1-indexed) for line-based operations",
                "required": False,
                "default": None
            },
            "end_line": {
                "type": "integer",
                "description": "Ending line number (1-indexed, inclusive) for line-based operations",
                "required": False,
                "default": None
            },
            "search_string": {
                "type": "string",
                "description": "String to search for (for insert_at_string or replace_string)",
                "required": False,
                "default": None
            },
            "create_if_missing": {
                "type": "boolean",
                "description": "Create file if it doesn't exist",
                "required": False,
                "default": False
            },
            "dry_run": {
                "type": "boolean",
                "description": "Show diff without applying changes",
                "required": False,
                "default": False
            }
        }
    
    async def execute(self, **kwargs) -> PrimitiveResult:
        """Execute file edit operation.
        
        Args:
            path: File path to edit
            operation: EditOperation type
            content: New content (for insert/replace operations)
            start_line: Starting line (1-indexed, for line operations)
            end_line: Ending line (1-indexed, for line operations)
            search_string: String to search for
            create_if_missing: Create file if not exists
            dry_run: Preview changes without applying
            
        Returns:
            PrimitiveResult with edit results
        """
        path = kwargs.get("path", "")
        operation_str = kwargs.get("operation", "")
        content = kwargs.get("content", "")
        start_line = kwargs.get("start_line")
        end_line = kwargs.get("end_line")
        search_string = kwargs.get("search_string")
        create_if_missing = kwargs.get("create_if_missing", False)
        dry_run = kwargs.get("dry_run", False)
        
        try:
            # Validate operation
            try:
                operation = EditOperation(operation_str)
            except ValueError:
                return PrimitiveResult(
                    success=False,
                    data=None,
                    message=f"Invalid operation: {operation_str}",
                    error="InvalidOperation"
                )
            
            # Resolve path
            file_path = Path(path).expanduser().resolve()
            
            # Check if file exists
            file_exists = file_path.exists()
            
            if not file_exists:
                if create_if_missing:
                    # Create new file
                    if not dry_run:
                        file_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(content)
                    
                    return PrimitiveResult(
                        success=True,
                        data={
                            "path": str(file_path),
                            "operation": "create",
                            "lines_affected": content.count('\n') + 1
                        },
                        message=f"Created new file: {path}"
                    )
                else:
                    return PrimitiveResult(
                        success=False,
                        data=None,
                        message=f"File not found: {path}",
                        error="FileNotFound"
                    )
            
            # Check file size
            file_size = file_path.stat().st_size
            if file_size > self.max_file_size:
                return PrimitiveResult(
                    success=False,
                    data=None,
                    message=f"File too large ({file_size} bytes > {self.max_file_size} limit)",
                    error="FileTooLarge"
                )
            
            # Read original content
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    original_lines = f.readlines()
                original_content = ''.join(original_lines)
            except UnicodeDecodeError:
                return PrimitiveResult(
                    success=False,
                    data=None,
                    message="File appears to be binary, cannot edit as text",
                    error="BinaryFile"
                )
            
            # Parse original lines (preserve line endings)
            original_lines = original_content.split('\n')
            # Add back newlines except for last line if empty
            original_lines = [line + '\n' for line in original_lines[:-1]] + [original_lines[-1]]
            
            # Apply operation
            new_lines = self._apply_operation(
                original_lines,
                operation,
                content,
                start_line,
                end_line,
                search_string
            )
            
            if new_lines is None:
                return PrimitiveResult(
                    success=False,
                    data=None,
                    message="Edit operation failed - invalid parameters",
                    error="InvalidEditParameters"
                )
            
            # Compute diff
            diff_result = self._compute_diff(original_lines, new_lines, str(file_path))
            
            # Check if there are any changes
            if diff_result.lines_added == 0 and diff_result.lines_removed == 0:
                return PrimitiveResult(
                    success=True,
                    data={
                        "path": str(file_path),
                        "changes": False
                    },
                    message="No changes needed - content already matches"
                )
            
            # If dry run, return diff without applying
            if dry_run:
                return PrimitiveResult(
                    success=True,
                    data={
                        "path": str(file_path),
                        "dry_run": True,
                        "diff": diff_result.unified_diff,
                        "lines_added": diff_result.lines_added,
                        "lines_removed": diff_result.lines_removed
                    },
                    message=f"Dry run - would add {diff_result.lines_added}, remove {diff_result.lines_removed} lines"
                )
            
            # Create backup if enabled
            backup_path = None
            if self.backup_enabled:
                backup_path = self._create_backup(file_path)
            
            # Write new content
            new_content = ''.join(new_lines)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            return PrimitiveResult(
                success=True,
                data={
                    "path": str(file_path),
                    "operation": operation.value,
                    "backup_path": str(backup_path) if backup_path else None,
                    "lines_added": diff_result.lines_added,
                    "lines_removed": diff_result.lines_removed,
                    "old_hash": diff_result.old_hash,
                    "new_hash": diff_result.new_hash,
                    "diff_preview": '\n'.join(diff_result.unified_diff.split('\n')[:20])  # First 20 lines
                },
                message=(
                    f"File edited successfully: +{diff_result.lines_added}/-{diff_result.lines_removed} lines. "
                    f"Backup: {backup_path or 'disabled'}"
                )
            )
            
        except Exception as e:
            logger.error(f"File edit error: {e}")
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Edit failed: {e}",
                error=str(e)
            )
    
    def _apply_operation(
        self,
        lines: List[str],
        operation: EditOperation,
        content: str,
        start_line: Optional[int],
        end_line: Optional[int],
        search_string: Optional[str]
    ) -> Optional[List[str]]:
        """Apply the edit operation to lines.
        
        Args:
            lines: Original lines (1-indexed in user terms)
            operation: Type of edit
            content: New content
            start_line: Start line (1-indexed)
            end_line: End line (1-indexed, inclusive)
            search_string: String to search for
            
        Returns:
            New list of lines or None if invalid
        """
        new_content_lines = content.split('\n') if content else []
        # Ensure proper line endings
        new_content_lines = [line + '\n' for line in new_content_lines[:-1]] + [new_content_lines[-1]] if new_content_lines else []
        
        if operation == EditOperation.REPLACE_ALL:
            return new_content_lines
        
        elif operation == EditOperation.APPEND:
            return lines + new_content_lines
        
        elif operation in (EditOperation.REPLACE_LINES, EditOperation.DELETE_LINES):
            if start_line is None:
                return None
            
            # Convert to 0-indexed
            start_idx = start_line - 1
            end_idx = (end_line or start_line) - 1
            
            # Validate indices
            if start_idx < 0 or start_idx >= len(lines):
                return None
            if end_idx < start_idx or end_idx >= len(lines):
                return None
            
            if operation == EditOperation.DELETE_LINES:
                return lines[:start_idx] + lines[end_idx + 1:]
            else:  # REPLACE_LINES
                return lines[:start_idx] + new_content_lines + lines[end_idx + 1:]
        
        elif operation == EditOperation.INSERT_LINES:
            if start_line is None:
                return None
            
            # Insert BEFORE the specified line (1-indexed)
            idx = start_line - 1
            if idx < 0:
                idx = 0
            if idx > len(lines):
                idx = len(lines)
            
            return lines[:idx] + new_content_lines + lines[idx:]
        
        elif operation == EditOperation.INSERT_AT_STRING:
            if not search_string:
                return None
            
            for i, line in enumerate(lines):
                if search_string in line:
                    # Insert after this line
                    return lines[:i+1] + new_content_lines + lines[i+1:]
            
            # String not found
            return None
        
        elif operation == EditOperation.REPLACE_STRING:
            if not search_string:
                return None
            
            result = []
            found = False
            for line in lines:
                if search_string in line and not found:
                    # Replace first occurrence only
                    new_line = line.replace(search_string, content, 1)
                    result.append(new_line)
                    found = True
                else:
                    result.append(line)
            
            if not found:
                return None
            
            return result
        
        return None
    
    def _compute_diff(
        self,
        old_lines: List[str],
        new_lines: List[str],
        file_path: str
    ) -> DiffResult:
        """Compute unified diff between old and new lines.
        
        Args:
            old_lines: Original lines
            new_lines: New lines
            file_path: Path for diff header
            
        Returns:
            DiffResult with statistics
        """
        old_content = ''.join(old_lines)
        new_content = ''.join(new_lines)
        
        # Compute hashes
        old_hash = hashlib.md5(old_content.encode()).hexdigest()[:8]
        new_hash = hashlib.md5(new_content.encode()).hexdigest()[:8]
        
        # Generate unified diff
        diff = list(difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"{file_path} (old {old_hash})",
            tofile=f"{file_path} (new {new_hash})",
            lineterm=''
        ))
        
        unified_diff = '\n'.join(diff)
        
        # Count changes
        lines_added = 0
        lines_removed = 0
        
        for line in diff:
            if line.startswith('+') and not line.startswith('+++'):
                lines_added += 1
            elif line.startswith('-') and not line.startswith('---'):
                lines_removed += 1
        
        return DiffResult(
            old_hash=old_hash,
            new_hash=new_hash,
            unified_diff=unified_diff,
            lines_added=lines_added,
            lines_removed=lines_removed,
            lines_modified=0  # Could compute this more precisely
        )
    
    def _create_backup(self, file_path: Path) -> Path:
        """Create a backup of the file.
        
        Args:
            file_path: Path to file
            
        Returns:
            Path to backup file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{file_path.name}.{timestamp}.bak"
        
        # Create backup directory
        backup_dir = file_path.parent / self.backup_dir
        backup_dir.mkdir(exist_ok=True)
        
        backup_path = backup_dir / backup_name
        
        shutil.copy2(file_path, backup_path)
        logger.debug(f"Created backup: {backup_path}")
        
        return backup_path


def register_all() -> None:
    """Register all file editor primitives."""
    register_primitive(FileEditor())
