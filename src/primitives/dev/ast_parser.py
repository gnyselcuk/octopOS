"""AST Parser - Abstract Syntax Tree parsing for code understanding.

Parses Python code to extract semantic information:
- Class definitions and inheritance
- Function signatures
- Import statements
- Variable assignments

Helps agents understand large codebases without loading all code into LLM context.

Example:
    >>> from src.primitives.dev.ast_parser import ASTParser
    >>> parser = ASTParser()
    >>> result = await parser.execute(
    ...     operation="analyze_file",
    ...     path="/workspace/my_module.py"
    ... )
"""

import ast
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum

from src.primitives.base_primitive import BasePrimitive, PrimitiveResult, register_primitive
from src.utils.logger import get_logger

logger = get_logger()


class ASTOperation(str, Enum):
    """AST parsing operations."""
    ANALYZE_FILE = "analyze_file"
    ANALYZE_DIRECTORY = "analyze_directory"
    FIND_CLASS = "find_class"
    FIND_FUNCTION = "find_function"
    GET_INHERITANCE = "get_inheritance"
    GET_IMPORTS = "get_imports"
    QUERY_CODE = "query_code"


@dataclass
class ClassInfo:
    """Information about a class."""
    name: str
    line: int
    docstring: Optional[str]
    bases: List[str] = field(default_factory=list)
    methods: List[Dict] = field(default_factory=list)
    attributes: List[str] = field(default_factory=list)


@dataclass
class FunctionInfo:
    """Information about a function."""
    name: str
    line: int
    docstring: Optional[str]
    args: List[Dict] = field(default_factory=list)
    returns: Optional[str] = None
    decorators: List[str] = field(default_factory=list)
    is_method: bool = False
    is_async: bool = False


@dataclass
class ModuleInfo:
    """Information about a module."""
    file_path: str
    classes: List[ClassInfo] = field(default_factory=list)
    functions: List[FunctionInfo] = field(default_factory=list)
    imports: List[Dict] = field(default_factory=list)
    docstring: Optional[str] = None


class ASTParser(BasePrimitive):
    """Parse Python code using Abstract Syntax Trees.
    
    This primitive helps agents understand code structure without loading
    entire files into the LLM context. It can:
    
    - Extract class hierarchies and inheritance
    - Get function signatures and docstrings
    - Find all imports
    - Query code for specific patterns
    - Analyze entire directories
    
    Benefits:
    - Works on large codebases efficiently
    - Provides structured, semantic information
    - Reduces token usage vs loading raw code
    """
    
    def __init__(self, max_file_size: int = 5 * 1024 * 1024) -> None:
        """Initialize AST Parser.
        
        Args:
            max_file_size: Maximum file size to parse (bytes)
        """
        super().__init__()
        self.max_file_size = max_file_size
    
    @property
    def name(self) -> str:
        return "code_analyze"
    
    @property
    def description(self) -> str:
        return (
            "Analyze Python code structure using AST parsing. "
            "Extract classes, functions, inheritance, imports without "
            "loading full code into context. Query code semantics."
        )
    
    @property
    def parameters(self) -> Dict[str, Dict[str, Any]]:
        return {
            "operation": {
                "type": "string",
                "description": "Analysis operation",
                "required": True,
                "enum": [op.value for op in ASTOperation]
            },
            "path": {
                "type": "string",
                "description": "File or directory path to analyze",
                "required": True
            },
            "name": {
                "type": "string",
                "description": "Class or function name to find",
                "required": False
            },
            "query": {
                "type": "string",
                "description": "Natural language query about the code",
                "required": False
            },
            "include_private": {
                "type": "boolean",
                "description": "Include private members (_name, __name)",
                "required": False,
                "default": False
            },
            "recursive": {
                "type": "boolean",
                "description": "Analyze subdirectories",
                "required": False,
                "default": True
            }
        }
    
    async def execute(self, **kwargs) -> PrimitiveResult:
        """Execute AST analysis.
        
        Args:
            operation: ASTOperation type
            path: File or directory path
            name: Target name (for find operations)
            query: Natural language query
            include_private: Include private members
            recursive: Recurse into subdirectories
            
        Returns:
            PrimitiveResult with analysis results
        """
        operation_str = kwargs.get("operation", "")
        path = kwargs.get("path", "")
        
        try:
            operation = ASTOperation(operation_str)
        except ValueError:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Invalid operation: {operation_str}",
                error="InvalidOperation"
            )
        
        try:
            file_path = Path(path).expanduser().resolve()
            
            if not file_path.exists():
                return PrimitiveResult(
                    success=False,
                    data=None,
                    message=f"Path not found: {path}",
                    error="PathNotFound"
                )
            
            if operation == ASTOperation.ANALYZE_FILE:
                return await self._analyze_file(file_path, kwargs)
            elif operation == ASTOperation.ANALYZE_DIRECTORY:
                return await self._analyze_directory(file_path, kwargs)
            elif operation == ASTOperation.FIND_CLASS:
                return await self._find_class(file_path, kwargs)
            elif operation == ASTOperation.FIND_FUNCTION:
                return await self._find_function(file_path, kwargs)
            elif operation == ASTOperation.GET_INHERITANCE:
                return await self._get_inheritance(file_path, kwargs)
            elif operation == ASTOperation.GET_IMPORTS:
                return await self._get_imports(file_path, kwargs)
            elif operation == ASTOperation.QUERY_CODE:
                return await self._query_code(file_path, kwargs)
            else:
                return PrimitiveResult(
                    success=False,
                    data=None,
                    message=f"Operation not implemented: {operation}",
                    error="NotImplemented"
                )
                
        except SyntaxError as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Syntax error in Python file: {e}",
                error="SyntaxError"
            )
        except Exception as e:
            logger.error(f"AST analysis error: {e}")
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Analysis failed: {e}",
                error=str(e)
            )
    
    def _parse_file(self, file_path: Path) -> Optional[ast.AST]:
        """Parse a Python file into AST."""
        if not file_path.suffix == ".py":
            return None
        
        # Check file size
        if file_path.stat().st_size > self.max_file_size:
            logger.warning(f"File too large: {file_path}")
            return None
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            return ast.parse(content)
        except UnicodeDecodeError:
            logger.warning(f"Cannot decode file: {file_path}")
            return None
    
    def _extract_module_info(self, tree: ast.AST, file_path: str) -> ModuleInfo:
        """Extract information from AST."""
        info = ModuleInfo(file_path=str(file_path))
        
        # Get module docstring
        info.docstring = ast.get_docstring(tree)
        
        for node in ast.iter_child_nodes(tree):
            # Classes
            if isinstance(node, ast.ClassDef):
                class_info = self._extract_class_info(node)
                info.classes.append(class_info)
            
            # Functions
            elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                func_info = self._extract_function_info(node)
                info.functions.append(func_info)
            
            # Imports
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                import_info = self._extract_import_info(node)
                info.imports.append(import_info)
        
        return info
    
    def _extract_class_info(self, node: ast.ClassDef) -> ClassInfo:
        """Extract class information."""
        info = ClassInfo(
            name=node.name,
            line=node.lineno,
            docstring=ast.get_docstring(node),
            bases=[self._get_name(base) for base in node.bases],
        )
        
        for item in node.body:
            # Methods
            if isinstance(item, ast.FunctionDef) or isinstance(item, ast.AsyncFunctionDef):
                method_info = self._extract_function_info(item, is_method=True)
                info.methods.append({
                    "name": method_info.name,
                    "line": method_info.line,
                    "args": [a["name"] for a in method_info.args],
                    "is_async": method_info.is_async,
                    "docstring": method_info.docstring
                })
            
            # Class attributes
            elif isinstance(item, ast.AnnAssign) or isinstance(item, ast.Assign):
                for target in getattr(item, 'targets', [item.target] if hasattr(item, 'target') else []):
                    if isinstance(target, ast.Name):
                        info.attributes.append(target.id)
        
        return info
    
    def _extract_function_info(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        is_method: bool = False
    ) -> FunctionInfo:
        """Extract function information."""
        args = []
        
        # Parse arguments
        for arg in node.args.args:
            arg_info = {
                "name": arg.arg,
                "annotation": self._get_name(arg.annotation) if arg.annotation else None
            }
            args.append(arg_info)
        
        # Parse defaults (paired with last N args)
        defaults = [None] * (len(node.args.args) - len(node.args.defaults)) + [
            ast.dump(d) for d in node.args.defaults
        ]
        for i, default in enumerate(defaults):
            if default and i < len(args):
                args[i]["default"] = default
        
        # Get return annotation
        returns = self._get_name(node.returns) if node.returns else None
        
        # Get decorators
        decorators = [self._get_name(d) for d in node.decorator_list]
        
        return FunctionInfo(
            name=node.name,
            line=node.lineno,
            docstring=ast.get_docstring(node),
            args=args,
            returns=returns,
            decorators=decorators,
            is_method=is_method,
            is_async=isinstance(node, ast.AsyncFunctionDef)
        )
    
    def _extract_import_info(self, node: ast.Import | ast.ImportFrom) -> Dict:
        """Extract import information."""
        if isinstance(node, ast.Import):
            return {
                "type": "import",
                "names": [{"name": alias.name, "asname": alias.asname} for alias in node.names],
                "line": node.lineno
            }
        else:  # ImportFrom
            return {
                "type": "from",
                "module": node.module,
                "names": [{"name": alias.name, "asname": alias.asname} for alias in node.names],
                "line": node.lineno
            }
    
    def _get_name(self, node: Optional[ast.AST]) -> str:
        """Extract name from AST node."""
        if node is None:
            return ""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_name(node.value)}.{node.attr}"
        elif isinstance(node, ast.Constant):
            return str(node.value)
        elif isinstance(node, ast.Subscript):
            return f"{self._get_name(node.value)}[...]"
        elif isinstance(node, ast.List):
            return "list"
        elif isinstance(node, ast.Dict):
            return "dict"
        elif isinstance(node, ast.Tuple):
            return "tuple"
        else:
            return ast.dump(node)[:50]
    
    # ==================== Operations ====================
    
    async def _analyze_file(self, file_path: Path, kwargs: Dict) -> PrimitiveResult:
        """Analyze a single file."""
        tree = self._parse_file(file_path)
        if not tree:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Could not parse file: {file_path}",
                error="ParseError"
            )
        
        info = self._extract_module_info(tree, str(file_path))
        
        # Filter private members if needed
        if not kwargs.get("include_private", False):
            info.classes = [c for c in info.classes if not c.name.startswith("_")]
            info.functions = [f for f in info.functions if not f.name.startswith("_")]
            info.methods = [m for m in info.methods if not m["name"].startswith("_")]
        
        return PrimitiveResult(
            success=True,
            data={
                "file": info.file_path,
                "docstring": info.docstring,
                "classes": [self._class_to_dict(c) for c in info.classes],
                "functions": [self._function_to_dict(f) for f in info.functions],
                "imports": info.imports,
                "summary": {
                    "class_count": len(info.classes),
                    "function_count": len(info.functions),
                    "import_count": len(info.imports)
                }
            },
            message=f"Analyzed {file_path.name}: {len(info.classes)} classes, {len(info.functions)} functions"
        )
    
    async def _analyze_directory(self, dir_path: Path, kwargs: Dict) -> PrimitiveResult:
        """Analyze all Python files in a directory."""
        recursive = kwargs.get("recursive", True)
        files_analyzed = 0
        all_classes = []
        all_functions = []
        all_imports = []
        
        pattern = "**/*.py" if recursive else "*.py"
        
        for py_file in dir_path.glob(pattern):
            tree = self._parse_file(py_file)
            if tree:
                info = self._extract_module_info(tree, str(py_file))
                
                # Filter private if needed
                if not kwargs.get("include_private", False):
                    info.classes = [c for c in info.classes if not c.name.startswith("_")]
                    info.functions = [f for f in info.functions if not f.name.startswith("_")]
                
                # Add file info
                for c in info.classes:
                    all_classes.append({"file": str(py_file), **self._class_to_dict(c)})
                for f in info.functions:
                    all_functions.append({"file": str(py_file), **self._function_to_dict(f)})
                for imp in info.imports:
                    all_imports.append({"file": str(py_file), **imp})
                
                files_analyzed += 1
        
        return PrimitiveResult(
            success=True,
            data={
                "directory": str(dir_path),
                "files_analyzed": files_analyzed,
                "classes": all_classes,
                "functions": all_functions,
                "imports": all_imports[:100],  # Limit imports
                "summary": {
                    "total_classes": len(all_classes),
                    "total_functions": len(all_functions),
                    "total_imports": len(all_imports)
                }
            },
            message=f"Analyzed {files_analyzed} files: {len(all_classes)} classes, {len(all_functions)} functions"
        )
    
    async def _find_class(self, file_path: Path, kwargs: Dict) -> PrimitiveResult:
        """Find a specific class."""
        name = kwargs.get("name")
        if not name:
            return PrimitiveResult(
                success=False,
                data=None,
                message="Class name is required",
                error="MissingName"
            )
        
        # Search in file or directory
        if file_path.is_file():
            files = [file_path]
        else:
            files = list(file_path.rglob("*.py"))
        
        matches = []
        for py_file in files:
            tree = self._parse_file(py_file)
            if tree:
                info = self._extract_module_info(tree, str(py_file))
                for cls in info.classes:
                    if cls.name == name or name.lower() in cls.name.lower():
                        matches.append({
                            "file": str(py_file),
                            **self._class_to_dict(cls)
                        })
        
        return PrimitiveResult(
            success=True,
            data={
                "query": name,
                "matches": matches,
                "count": len(matches)
            },
            message=f"Found {len(matches)} classes matching '{name}'"
        )
    
    async def _find_function(self, file_path: Path, kwargs: Dict) -> PrimitiveResult:
        """Find a specific function."""
        name = kwargs.get("name")
        if not name:
            return PrimitiveResult(
                success=False,
                data=None,
                message="Function name is required",
                error="MissingName"
            )
        
        # Search in file or directory
        if file_path.is_file():
            files = [file_path]
        else:
            files = list(file_path.rglob("*.py"))
        
        matches = []
        for py_file in files:
            tree = self._parse_file(py_file)
            if tree:
                info = self._extract_module_info(tree, str(py_file))
                for func in info.functions:
                    if func.name == name or name.lower() in func.name.lower():
                        matches.append({
                            "file": str(py_file),
                            **self._function_to_dict(func)
                        })
        
        return PrimitiveResult(
            success=True,
            data={
                "query": name,
                "matches": matches,
                "count": len(matches)
            },
            message=f"Found {len(matches)} functions matching '{name}'"
        )
    
    async def _get_inheritance(self, file_path: Path, kwargs: Dict) -> PrimitiveResult:
        """Get class inheritance hierarchy."""
        if file_path.is_file():
            files = [file_path]
        else:
            files = list(file_path.rglob("*.py"))
        
        inheritance = []
        for py_file in files:
            tree = self._parse_file(py_file)
            if tree:
                info = self._extract_module_info(tree, str(py_file))
                for cls in info.classes:
                    if cls.bases:
                        inheritance.append({
                            "class": cls.name,
                            "file": str(py_file),
                            "inherits_from": cls.bases,
                            "line": cls.line
                        })
        
        return PrimitiveResult(
            success=True,
            data={
                "inheritance_chains": inheritance,
                "count": len(inheritance)
            },
            message=f"Found {len(inheritance)} inheritance relationships"
        )
    
    async def _get_imports(self, file_path: Path, kwargs: Dict) -> PrimitiveResult:
        """Get all imports."""
        if file_path.is_file():
            files = [file_path]
        else:
            files = list(file_path.rglob("*.py"))
        
        all_imports = []
        for py_file in files:
            tree = self._parse_file(py_file)
            if tree:
                info = self._extract_module_info(tree, str(py_file))
                for imp in info.imports:
                    all_imports.append({
                        "file": str(py_file),
                        **imp
                    })
        
        return PrimitiveResult(
            success=True,
            data={
                "imports": all_imports[:200],  # Limit results
                "count": len(all_imports)
            },
            message=f"Found {len(all_imports)} import statements"
        )
    
    async def _query_code(self, file_path: Path, kwargs: Dict) -> PrimitiveResult:
        """Answer a natural language query about the code."""
        query = kwargs.get("query", "").lower()
        
        if "inherit" in query or "extends" in query or "subclass" in query:
            return await self._get_inheritance(file_path, kwargs)
        elif "import" in query:
            return await self._get_imports(file_path, kwargs)
        elif "class" in query:
            # Try to extract class name from query
            return await self._analyze_directory(file_path, kwargs)
        elif "function" in query or "method" in query:
            return await self._analyze_directory(file_path, kwargs)
        else:
            # Default to full analysis
            return await self._analyze_directory(file_path, kwargs)
    
    def _class_to_dict(self, cls: ClassInfo) -> Dict:
        """Convert ClassInfo to dictionary."""
        return {
            "name": cls.name,
            "line": cls.line,
            "docstring": cls.docstring,
            "bases": cls.bases,
            "methods": cls.methods,
            "attributes": cls.attributes
        }
    
    def _function_to_dict(self, func: FunctionInfo) -> Dict:
        """Convert FunctionInfo to dictionary."""
        return {
            "name": func.name,
            "line": func.line,
            "docstring": func.docstring,
            "args": func.args,
            "returns": func.returns,
            "decorators": func.decorators,
            "is_async": func.is_async
        }


def register_all() -> None:
    """Register AST parser primitive."""
    register_primitive(ASTParser())
