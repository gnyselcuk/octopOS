"""Git Manipulator - Git operations for version control.

Provides comprehensive Git functionality for agents:
- Repository status and information
- Branch operations
- Commit, push, pull
- Diff viewing
- Change tracking

Example:
    >>> from src.primitives.dev.git_manipulator import GitManipulator
    >>> git = GitManipulator()
    >>> result = await git.execute(
    ...     operation="status",
    ...     repo_path="/workspace/my-project"
    ... )
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
import asyncio

try:
    import git
    from git import Repo, InvalidGitRepositoryError
    HAS_GIT = True
except ImportError:
    HAS_GIT = False

from src.primitives.base_primitive import BasePrimitive, PrimitiveResult, register_primitive
from src.utils.logger import get_logger

logger = get_logger()


class GitOperation(str, Enum):
    """Git operations."""
    STATUS = "status"
    LOG = "log"
    DIFF = "diff"
    BRANCH_LIST = "branch_list"
    BRANCH_CREATE = "branch_create"
    BRANCH_CHECKOUT = "branch_checkout"
    COMMIT = "commit"
    PUSH = "push"
    PULL = "pull"
    ADD = "add"
    RESET = "reset"
    STASH = "stash"
    REMOTES = "remotes"
    INIT = "init"
    CLONE = "clone"


@dataclass
class GitCommit:
    """Git commit information."""
    hash: str
    short_hash: str
    message: str
    author: str
    date: str
    files_changed: int = 0


class GitManipulator(BasePrimitive):
    """Execute Git operations on repositories.
    
    This primitive provides agents with version control capabilities:
    - Check repository status
    - View commit history
    - Create branches and switch between them
    - Stage, commit, and push changes
    - Pull updates from remote
    - View diffs
    
    All operations are performed safely with proper error handling.
    """
    
    def __init__(self) -> None:
        """Initialize Git Manipulator."""
        super().__init__()
    
    def _get_repo(self, repo_path: str) -> Optional[Any]:
        """Get Git repository at path."""
        if not HAS_GIT:
            return None
        
        try:
            return Repo(repo_path, search_parent_directories=True)
        except InvalidGitRepositoryError:
            return None
    
    @property
    def name(self) -> str:
        return "git"
    
    @property
    def description(self) -> str:
        return (
            "Execute Git version control operations. "
            "Status, commit, push, pull, branch, diff, log. "
            "Manage code changes and collaborate."
        )
    
    @property
    def parameters(self) -> Dict[str, Dict[str, Any]]:
        return {
            "operation": {
                "type": "string",
                "description": "Git operation to perform",
                "required": True,
                "enum": [op.value for op in GitOperation]
            },
            "repo_path": {
                "type": "string",
                "description": "Path to git repository (default: current directory)",
                "required": False,
                "default": "."
            },
            "message": {
                "type": "string",
                "description": "Commit message (for commit operation)",
                "required": False
            },
            "branch": {
                "type": "string",
                "description": "Branch name (for branch operations)",
                "required": False
            },
            "files": {
                "type": "array",
                "description": "Files to add/stage (for add operation)",
                "required": False
            },
            "remote": {
                "type": "string",
                "description": "Remote name (default: origin)",
                "required": False,
                "default": "origin"
            },
            "limit": {
                "type": "integer",
                "description": "Number of commits to show (for log)",
                "required": False,
                "default": 10
            },
            "url": {
                "type": "string",
                "description": "Repository URL (for clone)",
                "required": False
            }
        }
    
    async def execute(self, **kwargs) -> PrimitiveResult:
        """Execute Git operation.
        
        Args:
            operation: GitOperation type
            repo_path: Repository path
            message: Commit message
            branch: Branch name
            files: Files to stage
            remote: Remote name
            limit: Log entry limit
            url: Clone URL
            
        Returns:
            PrimitiveResult with operation results
        """
        operation_str = kwargs.get("operation", "")
        repo_path = kwargs.get("repo_path", ".")
        
        if not HAS_GIT:
            return PrimitiveResult(
                success=False,
                data=None,
                message="GitPython is required. Install with: pip install gitpython",
                error="MissingDependency"
            )
        
        try:
            operation = GitOperation(operation_str)
        except ValueError:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Invalid operation: {operation_str}",
                error="InvalidOperation"
            )
        
        try:
            # Resolve path
            path = Path(repo_path).expanduser().resolve()
            
            # Handle init and clone specially (don't need existing repo)
            if operation == GitOperation.INIT:
                return await self._init_repo(path)
            elif operation == GitOperation.CLONE:
                return await self._clone_repo(kwargs, path)
            
            # Get repository
            repo = self._get_repo(str(path))
            if not repo:
                return PrimitiveResult(
                    success=False,
                    data=None,
                    message=f"Not a git repository: {repo_path}",
                    error="NotARepository"
                )
            
            # Execute operation
            if operation == GitOperation.STATUS:
                return await self._status(repo)
            elif operation == GitOperation.LOG:
                return await self._log(repo, kwargs)
            elif operation == GitOperation.DIFF:
                return await self._diff(repo, kwargs)
            elif operation == GitOperation.BRANCH_LIST:
                return await self._branch_list(repo)
            elif operation == GitOperation.BRANCH_CREATE:
                return await self._branch_create(repo, kwargs)
            elif operation == GitOperation.BRANCH_CHECKOUT:
                return await self._branch_checkout(repo, kwargs)
            elif operation == GitOperation.ADD:
                return await self._add(repo, kwargs)
            elif operation == GitOperation.COMMIT:
                return await self._commit(repo, kwargs)
            elif operation == GitOperation.PUSH:
                return await self._push(repo, kwargs)
            elif operation == GitOperation.PULL:
                return await self._pull(repo, kwargs)
            elif operation == GitOperation.RESET:
                return await self._reset(repo, kwargs)
            elif operation == GitOperation.STASH:
                return await self._stash(repo, kwargs)
            elif operation == GitOperation.REMOTES:
                return await self._remotes(repo)
            else:
                return PrimitiveResult(
                    success=False,
                    data=None,
                    message=f"Operation not implemented: {operation}",
                    error="NotImplemented"
                )
                
        except Exception as e:
            logger.error(f"Git operation error: {e}")
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Git operation failed: {e}",
                error=str(e)
            )
    
    # ==================== Operations ====================
    
    async def _init_repo(self, path: Path) -> PrimitiveResult:
        """Initialize a new repository."""
        try:
            repo = Repo.init(str(path))
            return PrimitiveResult(
                success=True,
                data={"path": str(path)},
                message=f"Initialized empty git repository in {path}"
            )
        except Exception as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Failed to initialize repository: {e}",
                error=str(e)
            )
    
    async def _clone_repo(self, kwargs: Dict, path: Path) -> PrimitiveResult:
        """Clone a repository."""
        url = kwargs.get("url")
        if not url:
            return PrimitiveResult(
                success=False,
                data=None,
                message="URL is required for clone operation",
                error="MissingURL"
            )
        
        try:
            # Run in thread since clone can be slow
            loop = asyncio.get_event_loop()
            repo = await loop.run_in_executor(None, lambda: Repo.clone_from(url, str(path)))
            
            return PrimitiveResult(
                success=True,
                data={
                    "url": url,
                    "path": str(path)
                },
                message=f"Cloned repository from {url}"
            )
        except Exception as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Failed to clone: {e}",
                error=str(e)
            )
    
    async def _status(self, repo: Any) -> PrimitiveResult:
        """Get repository status."""
        try:
            # Get current branch
            try:
                current_branch = repo.active_branch.name
            except:
                current_branch = "HEAD (detached)"
            
            # Get status
            modified = [item.a_path for item in repo.index.diff(None)]
            staged = [item.a_path for item in repo.index.diff('HEAD')]
            untracked = repo.untracked_files
            
            # Check for unpushed commits
            try:
                unpushed = list(repo.iter_commits(f'{repo.active_branch}@{{u}}..'))
            except:
                unpushed = []
            
            return PrimitiveResult(
                success=True,
                data={
                    "branch": current_branch,
                    "is_dirty": repo.is_dirty(),
                    "modified": modified,
                    "staged": staged,
                    "untracked": untracked,
                    "unpushed_commits": len(unpushed)
                },
                message=f"On branch {current_branch}: {len(modified)} modified, {len(staged)} staged, {len(untracked)} untracked"
            )
        except Exception as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Status failed: {e}",
                error=str(e)
            )
    
    async def _log(self, repo: Any, kwargs: Dict) -> PrimitiveResult:
        """Get commit history."""
        try:
            limit = kwargs.get("limit", 10)
            commits = []
            
            for commit in repo.iter_commits(max_count=limit):
                commits.append({
                    "hash": commit.hexsha,
                    "short_hash": commit.hexsha[:7],
                    "message": commit.message.strip(),
                    "author": str(commit.author),
                    "date": commit.committed_datetime.isoformat(),
                    "files_changed": len(commit.stats.files)
                })
            
            return PrimitiveResult(
                success=True,
                data={
                    "commits": commits,
                    "count": len(commits)
                },
                message=f"Showing last {len(commits)} commits"
            )
        except Exception as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Log failed: {e}",
                error=str(e)
            )
    
    async def _diff(self, repo: Any, kwargs: Dict) -> PrimitiveResult:
        """Get diff of changes."""
        try:
            # Get diff
            diffs = []
            for diff in repo.index.diff(None):
                diffs.append({
                    "file": diff.a_path,
                    "change_type": diff.change_type,
                    "additions": diff.line_stats[0] if hasattr(diff, 'line_stats') else 0,
                    "deletions": diff.line_stats[1] if hasattr(diff, 'line_stats') else 0
                })
            
            # Get actual diff text for modified files
            diff_text = repo.git.diff() if diffs else ""
            
            return PrimitiveResult(
                success=True,
                data={
                    "files": diffs,
                    "diff_preview": diff_text[:2000] if diff_text else "",
                    "total_additions": sum(d.get("additions", 0) for d in diffs),
                    "total_deletions": sum(d.get("deletions", 0) for d in diffs)
                },
                message=f"Diff: {len(diffs)} files changed"
            )
        except Exception as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Diff failed: {e}",
                error=str(e)
            )
    
    async def _branch_list(self, repo: Any) -> PrimitiveResult:
        """List branches."""
        try:
            branches = []
            for branch in repo.branches:
                branches.append({
                    "name": branch.name,
                    "is_remote": branch.is_remote,
                    "is_active": branch.name == repo.active_branch.name
                })
            
            return PrimitiveResult(
                success=True,
                data={
                    "branches": branches,
                    "current": repo.active_branch.name,
                    "count": len(branches)
                },
                message=f"{len(branches)} branches, currently on {repo.active_branch.name}"
            )
        except Exception as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Branch list failed: {e}",
                error=str(e)
            )
    
    async def _branch_create(self, repo: Any, kwargs: Dict) -> PrimitiveResult:
        """Create a new branch."""
        branch_name = kwargs.get("branch")
        if not branch_name:
            return PrimitiveResult(
                success=False,
                data=None,
                message="Branch name is required",
                error="MissingBranchName"
            )
        
        try:
            new_branch = repo.create_head(branch_name)
            return PrimitiveResult(
                success=True,
                data={"branch": branch_name},
                message=f"Created branch '{branch_name}'"
            )
        except Exception as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Branch creation failed: {e}",
                error=str(e)
            )
    
    async def _branch_checkout(self, repo: Any, kwargs: Dict) -> PrimitiveResult:
        """Checkout a branch."""
        branch_name = kwargs.get("branch")
        if not branch_name:
            return PrimitiveResult(
                success=False,
                data=None,
                message="Branch name is required",
                error="MissingBranchName"
            )
        
        try:
            repo.git.checkout(branch_name)
            return PrimitiveResult(
                success=True,
                data={"branch": branch_name},
                message=f"Switched to branch '{branch_name}'"
            )
        except Exception as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Checkout failed: {e}",
                error=str(e)
            )
    
    async def _add(self, repo: Any, kwargs: Dict) -> PrimitiveResult:
        """Stage files."""
        files = kwargs.get("files", ["."])
        
        try:
            repo.git.add(files)
            
            # Get staged files
            staged = [item.a_path for item in repo.index.diff('HEAD')]
            
            return PrimitiveResult(
                success=True,
                data={"staged_files": staged},
                message=f"Staged {len(staged)} files"
            )
        except Exception as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Add failed: {e}",
                error=str(e)
            )
    
    async def _commit(self, repo: Any, kwargs: Dict) -> PrimitiveResult:
        """Create a commit."""
        message = kwargs.get("message", "Agent commit")
        
        try:
            # Check if there are staged changes
            if not repo.index.diff('HEAD'):
                return PrimitiveResult(
                    success=False,
                    data=None,
                    message="No changes to commit",
                    error="NothingToCommit"
                )
            
            commit = repo.index.commit(message)
            
            return PrimitiveResult(
                success=True,
                data={
                    "commit_hash": commit.hexsha,
                    "short_hash": commit.hexsha[:7],
                    "message": message
                },
                message=f"Created commit {commit.hexsha[:7]}: {message}"
            )
        except Exception as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Commit failed: {e}",
                error=str(e)
            )
    
    async def _push(self, repo: Any, kwargs: Dict) -> PrimitiveResult:
        """Push to remote."""
        remote_name = kwargs.get("remote", "origin")
        
        try:
            origin = repo.remote(remote_name)
            result = origin.push()
            
            return PrimitiveResult(
                success=True,
                data={
                    "remote": remote_name,
                    "summary": [str(r) for r in result]
                },
                message=f"Pushed to {remote_name}"
            )
        except Exception as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Push failed: {e}",
                error=str(e)
            )
    
    async def _pull(self, repo: Any, kwargs: Dict) -> PrimitiveResult:
        """Pull from remote."""
        remote_name = kwargs.get("remote", "origin")
        
        try:
            origin = repo.remote(remote_name)
            result = origin.pull()
            
            return PrimitiveResult(
                success=True,
                data={
                    "remote": remote_name,
                    "commits_pulled": len(result)
                },
                message=f"Pulled {len(result)} commits from {remote_name}"
            )
        except Exception as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Pull failed: {e}",
                error=str(e)
            )
    
    async def _reset(self, repo: Any, kwargs: Dict) -> PrimitiveResult:
        """Reset changes."""
        try:
            repo.git.reset('HEAD')
            repo.git.checkout('--', '.')
            
            return PrimitiveResult(
                success=True,
                data={},
                message="Reset all changes"
            )
        except Exception as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Reset failed: {e}",
                error=str(e)
            )
    
    async def _stash(self, repo: Any, kwargs: Dict) -> PrimitiveResult:
        """Stash changes."""
        message = kwargs.get("message", "Agent stash")
        
        try:
            repo.git.stash('save', message)
            
            return PrimitiveResult(
                success=True,
                data={"message": message},
                message=f"Stashed changes: {message}"
            )
        except Exception as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Stash failed: {e}",
                error=str(e)
            )
    
    async def _remotes(self, repo: Any) -> PrimitiveResult:
        """List remotes."""
        try:
            remotes = []
            for remote in repo.remotes:
                remotes.append({
                    "name": remote.name,
                    "url": remote.url
                })
            
            return PrimitiveResult(
                success=True,
                data={
                    "remotes": remotes,
                    "count": len(remotes)
                },
                message=f"{len(remotes)} remotes configured"
            )
        except Exception as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Remotes failed: {e}",
                error=str(e)
            )


def register_all() -> None:
    """Register Git manipulator primitive."""
    register_primitive(GitManipulator())
