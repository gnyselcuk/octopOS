"""File Search - Regex and glob-based file search primitive.

This module provides advanced file search capabilities including:
- Glob pattern matching (e.g., "*.py", "**/*.txt")
- Regex-based content search within files
- File metadata extraction
- Recursive directory traversal

Example:
    >>> from src.primitives.native.file_search import FileSearch
    >>> searcher = FileSearch()
    >>> result = await searcher.execute(
    ...     pattern="*.py",
    ...     path="/workspace",
    ...     regex="def.*main"
    ... )
"""

import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Iterator
import os

from src.primitives.base_primitive import BasePrimitive, PrimitiveResult, register_primitive
from src.utils.logger import get_logger

logger = get_logger()


@dataclass
class FileMatch:
    """A file that matched the search criteria."""
    path: str
    name: str
    type: str  # 'file' or 'directory'
    size: int
    modified_time: float
    content_matches: Optional[List[Dict[str, Any]]] = None


@dataclass
class ContentMatch:
    """A content match within a file."""
    line_number: int
    line_content: str
    match_start: int
    match_end: int
    groups: Optional[List[str]] = None


class FileSearch(BasePrimitive):
    """Search for files using glob patterns and regex content matching.
    
    This primitive provides grep-like functionality with additional features:
    - Glob pattern matching for filenames
    - Regex-based content search
    - Match context (lines before/after)
    - File metadata inclusion
    
    Attributes:
        max_file_size: Maximum file size to search within (for content search)
        max_results: Maximum number of results to return
    """
    
    def __init__(
        self,
        max_file_size: int = 10 * 1024 * 1024,  # 10MB
        max_results: int = 1000
    ) -> None:
        """Initialize File Search.
        
        Args:
            max_file_size: Maximum file size for content search (bytes)
            max_results: Maximum number of file results to return
        """
        super().__init__()
        self.max_file_size = max_file_size
        self.max_results = max_results
    
    @property
    def name(self) -> str:
        return "file_search"
    
    @property
    def description(self) -> str:
        return (
            "Search for files and content using patterns. "
            "Supports glob patterns (e.g., '*.py') for filenames "
            "and regex for content matching. "
            "Returns file paths and optionally matching content lines."
        )
    
    @property
    def parameters(self) -> Dict[str, Dict[str, Any]]:
        return {
            "pattern": {
                "type": "string",
                "description": "Glob pattern for file matching (e.g., '*.py', '**/*.txt')",
                "required": True
            },
            "path": {
                "type": "string",
                "description": "Directory to search in (default: current directory)",
                "required": False,
                "default": "."
            },
            "regex": {
                "type": "string",
                "description": "Regex pattern to search within file contents",
                "required": False,
                "default": None
            },
            "recursive": {
                "type": "boolean",
                "description": "Search recursively in subdirectories",
                "required": False,
                "default": True
            },
            "case_sensitive": {
                "type": "boolean",
                "description": "Case-sensitive regex matching",
                "required": False,
                "default": False
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results (default: 1000)",
                "required": False,
                "default": 1000
            },
            "context_lines": {
                "type": "integer",
                "description": "Lines of context around content matches",
                "required": False,
                "default": 0
            },
            "exclude_pattern": {
                "type": "string",
                "description": "Glob pattern for files to exclude",
                "required": False,
                "default": None
            }
        }
    
    async def execute(self, **kwargs) -> PrimitiveResult:
        """Execute file search.
        
        Args:
            pattern: Glob pattern for file matching
            path: Directory to search (default: current directory)
            regex: Regex pattern for content search (optional)
            recursive: Whether to search recursively (default: True)
            case_sensitive: Case-sensitive regex (default: False)
            max_results: Maximum results to return
            context_lines: Lines of context for content matches
            exclude_pattern: Glob pattern for excluded files
            
        Returns:
            PrimitiveResult with search results
        """
        pattern = kwargs.get("pattern", "*")
        search_path = kwargs.get("path", ".")
        regex = kwargs.get("regex")
        recursive = kwargs.get("recursive", True)
        case_sensitive = kwargs.get("case_sensitive", False)
        max_results = kwargs.get("max_results", self.max_results)
        context_lines = kwargs.get("context_lines", 0)
        exclude_pattern = kwargs.get("exclude_pattern")
        
        try:
            # Resolve path
            base_path = Path(search_path).expanduser().resolve()
            
            if not base_path.exists():
                return PrimitiveResult(
                    success=False,
                    data=None,
                    message=f"Path not found: {search_path}",
                    error="PathNotFound"
                )
            
            if not base_path.is_dir():
                return PrimitiveResult(
                    success=False,
                    data=None,
                    message=f"Path is not a directory: {search_path}",
                    error="NotADirectory"
                )
            
            # Find files matching pattern
            file_matches = self._find_files(
                base_path, pattern, recursive, exclude_pattern, max_results
            )
            
            # If regex specified, search content
            if regex and file_matches:
                compiled_regex = re.compile(
                    regex,
                    0 if case_sensitive else re.IGNORECASE
                )
                
                file_matches = self._search_content(
                    file_matches,
                    compiled_regex,
                    context_lines,
                    max_results
                )
            
            # Convert to result format
            results = []
            for match in file_matches[:max_results]:
                result = {
                    "path": match.path,
                    "name": match.name,
                    "type": match.type,
                    "size": match.size,
                    "modified_time": match.modified_time
                }
                
                if match.content_matches:
                    result["content_matches"] = match.content_matches
                
                results.append(result)
            
            # Build summary message
            if regex:
                files_with_matches = sum(1 for m in file_matches if m.content_matches)
                total_matches = sum(
                    len(m.content_matches or []) for m in file_matches
                )
                message = (
                    f"Found {len(results)} files, "
                    f"{files_with_matches} with {total_matches} content matches"
                )
            else:
                message = f"Found {len(results)} files matching pattern"
            
            return PrimitiveResult(
                success=True,
                data={
                    "files": results,
                    "count": len(results),
                    "pattern": pattern,
                    "path": str(base_path),
                    "regex": regex
                },
                message=message,
                metadata={
                    "truncated": len(file_matches) > max_results
                }
            )
            
        except re.error as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Invalid regex pattern: {e}",
                error="InvalidRegex"
            )
        except Exception as e:
            logger.error(f"File search error: {e}")
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Search failed: {e}",
                error=str(e)
            )
    
    def _find_files(
        self,
        base_path: Path,
        pattern: str,
        recursive: bool,
        exclude_pattern: Optional[str],
        max_results: int
    ) -> List[FileMatch]:
        """Find files matching the glob pattern.
        
        Args:
            base_path: Directory to search
            pattern: Glob pattern
            recursive: Whether to search recursively
            exclude_pattern: Pattern for excluded files
            max_results: Maximum results
            
        Returns:
            List of FileMatch objects
        """
        matches = []
        
        # Determine iterator based on recursive flag
        if recursive:
            iterator = base_path.rglob(pattern)
        else:
            iterator = base_path.glob(pattern)
        
        for path in iterator:
            # Check exclude pattern
            if exclude_pattern and fnmatch.fnmatch(path.name, exclude_pattern):
                continue
            
            try:
                stat = path.stat()
                is_dir = path.is_dir()
                
                matches.append(FileMatch(
                    path=str(path),
                    name=path.name,
                    type="directory" if is_dir else "file",
                    size=stat.st_size if not is_dir else 0,
                    modified_time=stat.st_mtime,
                    content_matches=None
                ))
                
                if len(matches) >= max_results:
                    break
                    
            except (OSError, PermissionError) as e:
                logger.debug(f"Cannot access {path}: {e}")
                continue
        
        return matches
    
    def _search_content(
        self,
        file_matches: List[FileMatch],
        regex: re.Pattern,
        context_lines: int,
        max_results: int
    ) -> List[FileMatch]:
        """Search file contents with regex.
        
        Args:
            file_matches: Files to search
            regex: Compiled regex pattern
            context_lines: Lines of context around matches
            max_results: Maximum file results
            
        Returns:
            Filtered list with content matches
        """
        results = []
        
        for file_match in file_matches:
            # Skip directories
            if file_match.type == "directory":
                continue
            
            # Skip large files
            if file_match.size > self.max_file_size:
                logger.debug(f"Skipping large file: {file_match.path}")
                continue
            
            content_matches = self._search_file_content(
                file_match.path, regex, context_lines
            )
            
            if content_matches:
                file_match.content_matches = content_matches
                results.append(file_match)
                
                if len(results) >= max_results:
                    break
        
        return results
    
    def _search_file_content(
        self,
        file_path: str,
        regex: re.Pattern,
        context_lines: int
    ) -> Optional[List[Dict[str, Any]]]:
        """Search content within a single file.
        
        Args:
            file_path: Path to file
            regex: Compiled regex pattern
            context_lines: Lines of context
            
        Returns:
            List of content matches or None
        """
        matches = []
        
        try:
            # Read file with encoding detection
            encodings = ['utf-8', 'latin-1', 'cp1252']
            lines = None
            
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        lines = f.readlines()
                    break
                except UnicodeDecodeError:
                    continue
            
            if lines is None:
                return None  # Binary or unreadable file
            
            # Strip newline characters for cleaner output
            lines = [line.rstrip('\n\r') for line in lines]
            
            for line_num, line in enumerate(lines, 1):
                for match in regex.finditer(line):
                    content_match = {
                        "line_number": line_num,
                        "line_content": line,
                        "match_start": match.start(),
                        "match_end": match.end(),
                        "match_text": match.group(0)
                    }
                    
                    # Add capture groups if present
                    if match.groups():
                        content_match["groups"] = list(match.groups())
                    
                    # Add context lines
                    if context_lines > 0:
                        start_line = max(1, line_num - context_lines)
                        end_line = min(len(lines), line_num + context_lines)
                        
                        content_match["context_before"] = [
                            {"line": i, "content": lines[i-1]}
                            for i in range(start_line, line_num)
                        ]
                        content_match["context_after"] = [
                            {"line": i, "content": lines[i-1]}
                            for i in range(line_num + 1, end_line + 1)
                        ]
                    
                    matches.append(content_match)
            
            return matches if matches else None
            
        except (OSError, PermissionError) as e:
            logger.debug(f"Cannot read {file_path}: {e}")
            return None
        except Exception as e:
            logger.debug(f"Error searching {file_path}: {e}")
            return None


def register_all() -> None:
    """Register all file search primitives."""
    register_primitive(FileSearch())
