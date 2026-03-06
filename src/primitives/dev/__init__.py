"""Developer Tools Primitives - Code analysis and version control."""

from src.primitives.dev.ast_parser import ASTParser
from src.primitives.dev.git_manipulator import GitManipulator

__all__ = [
    "ASTParser",
    "GitManipulator",
]


def register_all() -> None:
    """Register all developer tools primitives with the tool registry."""
    from src.primitives.tool_registry import register_primitive
    
    register_primitive(ASTParser(), category='dev', tags=['code', 'analysis', 'ast'])
    register_primitive(GitManipulator(), category='dev', tags=['git', 'vcs', 'version-control'])
