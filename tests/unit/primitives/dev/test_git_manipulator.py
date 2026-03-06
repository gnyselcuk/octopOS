"""Unit tests for primitives/dev/git_manipulator.py module.

This module tests the Git operations primitive.
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.primitives.dev.git_manipulator import GitCommit, GitManipulator, GitOperation
from src.primitives.base_primitive import PrimitiveResult


class TestGitOperation:
    """Test GitOperation enum."""
    
    def test_operation_values(self):
        """Test that all expected operations exist."""
        expected_ops = {
            "status", "log", "diff", "branch_list", "branch_create",
            "branch_checkout", "commit", "push", "pull", "add", "reset",
            "stash", "remotes", "init", "clone"
        }
        actual_ops = {op.value for op in GitOperation}
        assert actual_ops == expected_ops


class TestGitCommit:
    """Test GitCommit dataclass."""
    
    def test_create_commit(self):
        """Test creating a commit object."""
        commit = GitCommit(
            hash="abc123def456",
            short_hash="abc123",
            message="Test commit",
            author="Test User",
            date="2024-01-01",
            files_changed=5
        )
        
        assert commit.hash == "abc123def456"
        assert commit.short_hash == "abc123"
        assert commit.message == "Test commit"
        assert commit.author == "Test User"
        assert commit.files_changed == 5


class TestGitManipulator:
    """Test GitManipulator primitive."""
    
    @pytest.fixture
    def manipulator(self):
        """Create Git manipulator instance."""
        return GitManipulator()
    
    @pytest.fixture
    def mock_repo(self):
        """Create mock Git repository."""
        repo = MagicMock()
        
        # Mock HEAD
        head = MagicMock()
        head.name = "main"
        repo.head = head
        head.reference = head
        
        # Mock active branch
        repo.active_branch.name = "feature-branch"
        
        # Mock remotes
        remote = MagicMock()
        remote.name = "origin"
        remote.url = "https://github.com/user/repo.git"
        repo.remotes = [remote]
        
        # Mock index
        repo.index.diff.return_value = []
        
        # Mock untracked files
        repo.untracked_files = ["new_file.py"]
        
        # Mock iter_commits
        commit = MagicMock()
        commit.hexsha = "abc123def456"
        commit.message = "Test commit"
        commit.author.name = "Test User"
        commit.committed_datetime.isoformat.return_value = "2024-01-01T00:00:00"
        commit.stats.total["insertions"] = 10
        commit.stats.total["deletions"] = 5
        repo.iter_commits.return_value = [commit]
        
        return repo
    
    def test_name(self, manipulator):
        """Test primitive name."""
        assert manipulator.name == "git"
    
    def test_description(self, manipulator):
        """Test primitive description."""
        assert "Git" in manipulator.description
        assert "version control" in manipulator.description.lower()
    
    def test_parameters(self, manipulator):
        """Test parameter definitions."""
        params = manipulator.parameters
        
        assert "operation" in params
        assert "repo_path" in params
        assert "message" in params
        assert "branch" in params
        
        # Check operation enum
        assert params["operation"]["required"] is True
    
    @pytest.mark.asyncio
    async def test_execute_invalid_operation(self, manipulator):
        """Test executing with invalid operation."""
        result = await manipulator.execute(
            operation="invalid_op",
            repo_path="/tmp"
        )
        
        assert result.success is False
        assert "Invalid operation" in result.message
    
    @pytest.mark.asyncio
    async def test_status_success(self, manipulator, mock_repo, tmp_path):
        """Test git status operation."""
        with patch.object(manipulator, '_get_repo', return_value=mock_repo):
            result = await manipulator.execute(
                operation="status",
                repo_path=str(tmp_path)
            )
            
            assert result.success is True
            assert result.data["branch"] == "feature-branch"
    
    @pytest.mark.asyncio
    async def test_status_no_repo(self, manipulator, tmp_path):
        """Test status when not in a git repo."""
        with patch.object(manipulator, '_get_repo', return_value=None):
            result = await manipulator.execute(
                operation="status",
                repo_path=str(tmp_path)
            )
            
            assert result.success is False
            assert "not a git repository" in result.message.lower()
    
    @pytest.mark.asyncio
    async def test_log_success(self, manipulator, mock_repo, tmp_path):
        """Test git log operation."""
        with patch.object(manipulator, '_get_repo', return_value=mock_repo):
            result = await manipulator.execute(
                operation="log",
                repo_path=str(tmp_path),
                limit=5
            )
            
            assert result.success is True
            mock_repo.iter_commits.assert_called_once_with(max_count=5)
    
    @pytest.mark.asyncio
    async def test_branch_list_success(self, manipulator, mock_repo, tmp_path):
        """Test branch list operation."""
        mock_branch = MagicMock()
        mock_branch.name = "main"
        mock_repo.branches = [mock_branch]
        
        with patch.object(manipulator, '_get_repo', return_value=mock_repo):
            result = await manipulator.execute(
                operation="branch_list",
                repo_path=str(tmp_path)
            )
            
            assert result.success is True
            assert "branches" in result.data
    
    @pytest.mark.asyncio
    async def test_branch_create_success(self, manipulator, mock_repo, tmp_path):
        """Test branch creation."""
        with patch.object(manipulator, '_get_repo', return_value=mock_repo):
            result = await manipulator.execute(
                operation="branch_create",
                repo_path=str(tmp_path),
                branch="new-feature"
            )
            
            assert result.success is True
            mock_repo.create_head.assert_called_once_with("new-feature")
    
    @pytest.mark.asyncio
    async def test_branch_checkout_success(self, manipulator, mock_repo, tmp_path):
        """Test branch checkout."""
        mock_branch = MagicMock()
        mock_repo.branches = [mock_branch]
        
        with patch.object(manipulator, '_get_repo', return_value=mock_repo):
            result = await manipulator.execute(
                operation="branch_checkout",
                repo_path=str(tmp_path),
                branch="develop"
            )
            
            assert result.success is True
    
    @pytest.mark.asyncio
    async def test_add_success(self, manipulator, mock_repo, tmp_path):
        """Test git add operation."""
        with patch.object(manipulator, '_get_repo', return_value=mock_repo):
            result = await manipulator.execute(
                operation="add",
                repo_path=str(tmp_path),
                files=["file1.py", "file2.py"]
            )
            
            assert result.success is True
            mock_repo.index.add.assert_called_once_with(["file1.py", "file2.py"])
    
    @pytest.mark.asyncio
    async def test_commit_success(self, manipulator, mock_repo, tmp_path):
        """Test git commit operation."""
        with patch.object(manipulator, '_get_repo', return_value=mock_repo):
            result = await manipulator.execute(
                operation="commit",
                repo_path=str(tmp_path),
                message="Test commit message"
            )
            
            assert result.success is True
            mock_repo.index.commit.assert_called_once_with("Test commit message")
    
    @pytest.mark.asyncio
    async def test_push_success(self, manipulator, mock_repo, tmp_path):
        """Test git push operation."""
        mock_remote = MagicMock()
        mock_repo.remotes = {"origin": mock_remote}
        
        with patch.object(manipulator, '_get_repo', return_value=mock_repo):
            result = await manipulator.execute(
                operation="push",
                repo_path=str(tmp_path),
                remote="origin"
            )
            
            assert result.success is True
            mock_remote.push.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_pull_success(self, manipulator, mock_repo, tmp_path):
        """Test git pull operation."""
        mock_remote = MagicMock()
        mock_repo.remotes = {"origin": mock_remote}
        
        with patch.object(manipulator, '_get_repo', return_value=mock_repo):
            result = await manipulator.execute(
                operation="pull",
                repo_path=str(tmp_path),
                remote="origin"
            )
            
            assert result.success is True
            mock_remote.pull.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_remotes_success(self, manipulator, mock_repo, tmp_path):
        """Test listing remotes."""
        with patch.object(manipulator, '_get_repo', return_value=mock_repo):
            result = await manipulator.execute(
                operation="remotes",
                repo_path=str(tmp_path)
            )
            
            assert result.success is True
            assert "remotes" in result.data
            assert result.data["remotes"][0]["name"] == "origin"
    
    @pytest.mark.asyncio
    async def test_init_success(self, manipulator, tmp_path):
        """Test git init operation."""
        with patch('src.primitives.dev.git_manipulator.Repo') as mock_repo_class:
            result = await manipulator.execute(
                operation="init",
                repo_path=str(tmp_path)
            )
            
            assert result.success is True
            mock_repo_class.init.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_clone_success(self, manipulator, tmp_path):
        """Test git clone operation."""
        with patch('src.primitives.dev.git_manipulator.Repo') as mock_repo_class:
            result = await manipulator.execute(
                operation="clone",
                repo_path=str(tmp_path),
                url="https://github.com/user/repo.git"
            )
            
            assert result.success is True
            mock_repo_class.clone_from.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_clone_missing_url(self, manipulator, tmp_path):
        """Test clone without URL."""
        result = await manipulator.execute(
            operation="clone",
            repo_path=str(tmp_path)
        )
        
        assert result.success is False
        assert "URL" in result.message
    
    def test_get_repo_success(self, manipulator, tmp_path):
        """Test getting repository at path."""
        with patch('src.primitives.dev.git_manipulator.Repo') as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo_class.return_value = mock_repo
            
            repo = manipulator._get_repo(str(tmp_path))
            
            assert repo is not None
    
    def test_get_repo_invalid(self, manipulator, tmp_path):
        """Test getting invalid repository."""
        with patch('src.primitives.dev.git_manipulator.Repo') as mock_repo_class:
            from git import InvalidGitRepositoryError
            mock_repo_class.side_effect = InvalidGitRepositoryError()
            
            repo = manipulator._get_repo(str(tmp_path))
            
            assert repo is None
