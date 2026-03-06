"""Unit tests for primitives/file_operations.py module.

This module tests the file operation primitives for reading, writing,
listing, and managing files and directories.
"""

import os
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.primitives.file_operations import (
    CreateDirectoryPrimitive,
    DeletePathPrimitive,
    ListDirectoryPrimitive,
    ReadFilePrimitive,
    WriteFilePrimitive,
)
from src.primitives.base_primitive import PrimitiveResult


class TestReadFilePrimitive:
    """Test ReadFilePrimitive class."""
    
    @pytest.fixture
    def primitive(self):
        """Create a ReadFilePrimitive instance."""
        return ReadFilePrimitive()
    
    @pytest.fixture
    def temp_file(self):
        """Create a temporary file for testing."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("Line 1\nLine 2\nLine 3\nLine 4\nLine 5")
            temp_path = f.name
        yield temp_path
        os.unlink(temp_path)
    
    def test_name(self, primitive):
        """Test primitive name."""
        assert primitive.name == "read_file"
    
    def test_description(self, primitive):
        """Test primitive description."""
        assert "contents" in primitive.description.lower()
    
    def test_parameters(self, primitive):
        """Test parameter schema."""
        params = primitive.parameters
        
        assert "path" in params
        assert params["path"]["required"] is True
        assert params["path"]["type"] == "string"
        
        assert "encoding" in params
        assert params["encoding"]["required"] is False
        assert params["encoding"]["default"] == "utf-8"
        
        assert "limit" in params
        assert params["limit"]["required"] is False
        assert params["limit"]["default"] == 0
    
    @pytest.mark.asyncio
    async def test_read_file_success(self, primitive, temp_file):
        """Test successful file read."""
        result = await primitive.execute(path=temp_file)
        
        assert result.success is True
        assert "Line 1" in result.data["content"]
        assert "Line 5" in result.data["content"]
        assert result.data["lines"] == 5
        assert result.data["size"] > 0
    
    @pytest.mark.asyncio
    async def test_read_file_with_limit(self, primitive, temp_file):
        """Test reading file with line limit."""
        result = await primitive.execute(path=temp_file, limit=2)
        
        assert result.success is True
        assert "Line 1" in result.data["content"]
        assert "Line 2" in result.data["content"]
        assert "Line 3" not in result.data["content"]
    
    @pytest.mark.asyncio
    async def test_read_file_not_found(self, primitive):
        """Test reading non-existent file."""
        result = await primitive.execute(path="/nonexistent/file.txt")
        
        assert result.success is False
        assert "not found" in result.message.lower()
        assert result.error == "FileNotFoundError"
    
    @pytest.mark.asyncio
    async def test_read_file_is_directory(self, primitive, tmp_path):
        """Test reading a directory as file."""
        result = await primitive.execute(path=str(tmp_path))
        
        assert result.success is False
        assert "not a file" in result.message.lower()
    
    @pytest.mark.asyncio
    async def test_read_file_with_encoding(self, primitive, tmp_path):
        """Test reading file with specific encoding."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello World", encoding='utf-8')
        
        result = await primitive.execute(path=str(test_file), encoding='utf-8')
        
        assert result.success is True
        assert result.data["content"] == "Hello World"
    
    @pytest.mark.asyncio
    async def test_read_file_expand_user(self, primitive, tmp_path, monkeypatch):
        """Test that ~ is expanded to home directory."""
        # Create a file in tmp_path
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")
        
        # Mock Path.home() to return tmp_path
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        
        result = await primitive.execute(path="~/test.txt")
        
        assert result.success is True
        assert result.data["content"] == "test content"


class TestWriteFilePrimitive:
    """Test WriteFilePrimitive class."""
    
    @pytest.fixture
    def primitive(self):
        """Create a WriteFilePrimitive instance."""
        return WriteFilePrimitive()
    
    def test_name(self, primitive):
        """Test primitive name."""
        assert primitive.name == "write_file"
    
    def test_parameters(self, primitive):
        """Test parameter schema."""
        params = primitive.parameters
        
        assert "path" in params
        assert "content" in params
        assert "encoding" in params
        assert "append" in params
        
        assert params["path"]["required"] is True
        assert params["content"]["required"] is True
        assert params["append"]["default"] is False
    
    @pytest.mark.asyncio
    async def test_write_file_success(self, primitive, tmp_path):
        """Test successful file write."""
        test_file = tmp_path / "output.txt"
        
        result = await primitive.execute(
            path=str(test_file),
            content="Hello, World!"
        )
        
        assert result.success is True
        assert test_file.exists()
        assert test_file.read_text() == "Hello, World!"
        assert result.data["bytes_written"] == len("Hello, World!".encode('utf-8'))
    
    @pytest.mark.asyncio
    async def test_write_file_creates_directory(self, primitive, tmp_path):
        """Test that write creates parent directories."""
        test_file = tmp_path / "subdir" / "nested" / "file.txt"
        
        result = await primitive.execute(
            path=str(test_file),
            content="test"
        )
        
        assert result.success is True
        assert test_file.exists()
    
    @pytest.mark.asyncio
    async def test_write_file_append(self, primitive, tmp_path):
        """Test appending to file."""
        test_file = tmp_path / "append.txt"
        test_file.write_text("First line\n")
        
        result = await primitive.execute(
            path=str(test_file),
            content="Second line",
            append=True
        )
        
        assert result.success is True
        content = test_file.read_text()
        assert "First line" in content
        assert "Second line" in content
    
    @pytest.mark.asyncio
    async def test_write_file_overwrite(self, primitive, tmp_path):
        """Test overwriting existing file."""
        test_file = tmp_path / "overwrite.txt"
        test_file.write_text("original content")
        
        result = await primitive.execute(
            path=str(test_file),
            content="new content",
            append=False
        )
        
        assert result.success is True
        assert test_file.read_text() == "new content"


class TestListDirectoryPrimitive:
    """Test ListDirectoryPrimitive class."""
    
    @pytest.fixture
    def primitive(self):
        """Create a ListDirectoryPrimitive instance."""
        return ListDirectoryPrimitive()
    
    @pytest.fixture
    def sample_directory(self, tmp_path):
        """Create a sample directory structure."""
        # Create files
        (tmp_path / "file1.txt").write_text("content1")
        (tmp_path / "file2.py").write_text("content2")
        
        # Create subdirectory
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "nested.txt").write_text("nested content")
        
        return tmp_path
    
    def test_name(self, primitive):
        """Test primitive name."""
        assert primitive.name == "list_directory"
    
    def test_parameters(self, primitive):
        """Test parameter schema."""
        params = primitive.parameters
        
        assert "path" in params
        assert "recursive" in params
        assert "pattern" in params
        
        assert params["recursive"]["default"] is False
        assert params["pattern"]["default"] == "*"
    
    @pytest.mark.asyncio
    async def test_list_directory_success(self, primitive, sample_directory):
        """Test successful directory listing."""
        result = await primitive.execute(path=str(sample_directory))
        
        assert result.success is True
        assert result.data["count"] == 3  # 2 files + 1 subdir
        
        names = [item["name"] for item in result.data["items"]]
        assert "file1.txt" in names
        assert "file2.py" in names
        assert "subdir" in names
    
    @pytest.mark.asyncio
    async def test_list_directory_recursive(self, primitive, sample_directory):
        """Test recursive directory listing."""
        result = await primitive.execute(
            path=str(sample_directory),
            recursive=True
        )
        
        assert result.success is True
        assert result.data["count"] == 4  # Including nested file
        
        names = [item["name"] for item in result.data["items"]]
        assert "nested.txt" in names
    
    @pytest.mark.asyncio
    async def test_list_directory_with_pattern(self, primitive, sample_directory):
        """Test directory listing with pattern filter."""
        result = await primitive.execute(
            path=str(sample_directory),
            pattern="*.txt"
        )
        
        assert result.success is True
        
        names = [item["name"] for item in result.data["items"]]
        assert "file1.txt" in names
        assert "file2.py" not in names
    
    @pytest.mark.asyncio
    async def test_list_directory_not_found(self, primitive):
        """Test listing non-existent directory."""
        result = await primitive.execute(path="/nonexistent/directory")
        
        assert result.success is False
        assert "not found" in result.message.lower()
    
    @pytest.mark.asyncio
    async def test_list_directory_not_a_directory(self, primitive, tmp_path):
        """Test listing a file as directory."""
        test_file = tmp_path / "file.txt"
        test_file.write_text("content")
        
        result = await primitive.execute(path=str(test_file))
        
        assert result.success is False
        assert "not a directory" in result.message.lower()
    
    @pytest.mark.asyncio
    async def test_list_directory_item_types(self, primitive, sample_directory):
        """Test that items have correct types."""
        result = await primitive.execute(path=str(sample_directory))
        
        assert result.success is True
        
        for item in result.data["items"]:
            if item["name"] == "subdir":
                assert item["type"] == "directory"
            else:
                assert item["type"] == "file"
    
    @pytest.mark.asyncio
    async def test_list_directory_file_sizes(self, primitive, sample_directory):
        """Test that files have size information."""
        result = await primitive.execute(path=str(sample_directory))
        
        assert result.success is True
        
        for item in result.data["items"]:
            if item["type"] == "file":
                assert item["size"] is not None
                assert isinstance(item["size"], int)
            else:
                assert item["size"] is None


class TestCreateDirectoryPrimitive:
    """Test CreateDirectoryPrimitive class."""
    
    @pytest.fixture
    def primitive(self):
        """Create a CreateDirectoryPrimitive instance."""
        return CreateDirectoryPrimitive()
    
    def test_name(self, primitive):
        """Test primitive name."""
        assert primitive.name == "create_directory"
    
    def test_parameters(self, primitive):
        """Test parameter schema."""
        params = primitive.parameters
        
        assert "path" in params
        assert "parents" in params
        
        assert params["path"]["required"] is True
        assert params["parents"]["default"] is True
    
    @pytest.mark.asyncio
    async def test_create_directory_success(self, primitive, tmp_path):
        """Test successful directory creation."""
        new_dir = tmp_path / "new_directory"
        
        result = await primitive.execute(path=str(new_dir))
        
        assert result.success is True
        assert new_dir.exists()
        assert new_dir.is_dir()
    
    @pytest.mark.asyncio
    async def test_create_directory_nested(self, primitive, tmp_path):
        """Test creating nested directories."""
        nested_dir = tmp_path / "a" / "b" / "c"
        
        result = await primitive.execute(path=str(nested_dir), parents=True)
        
        assert result.success is True
        assert nested_dir.exists()
    
    @pytest.mark.asyncio
    async def test_create_directory_already_exists(self, primitive, tmp_path):
        """Test creating directory that already exists."""
        existing_dir = tmp_path / "existing"
        existing_dir.mkdir()
        
        result = await primitive.execute(path=str(existing_dir))
        
        assert result.success is True  # exist_ok=True makes this succeed
    
    @pytest.mark.asyncio
    async def test_create_directory_expand_user(self, primitive, tmp_path, monkeypatch):
        """Test that ~ is expanded in path."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        
        result = await primitive.execute(path="~/test_dir")
        
        assert result.success is True
        assert (tmp_path / "test_dir").exists()


class TestDeletePathPrimitive:
    """Test DeletePathPrimitive class."""
    
    @pytest.fixture
    def primitive(self):
        """Create a DeletePathPrimitive instance."""
        return DeletePathPrimitive()
    
    def test_name(self, primitive):
        """Test primitive name."""
        assert primitive.name == "delete_path"
    
    def test_parameters(self, primitive):
        """Test parameter schema."""
        params = primitive.parameters
        
        assert "path" in params
        assert "recursive" in params
        
        assert params["path"]["required"] is True
        assert params["recursive"]["default"] is False
    
    @pytest.mark.asyncio
    async def test_delete_file_success(self, primitive, tmp_path):
        """Test successful file deletion."""
        test_file = tmp_path / "to_delete.txt"
        test_file.write_text("content")
        
        result = await primitive.execute(path=str(test_file))
        
        assert result.success is True
        assert not test_file.exists()
    
    @pytest.mark.asyncio
    async def test_delete_empty_directory(self, primitive, tmp_path):
        """Test deleting empty directory."""
        empty_dir = tmp_path / "empty_dir"
        empty_dir.mkdir()
        
        result = await primitive.execute(path=str(empty_dir))
        
        assert result.success is True
        assert not empty_dir.exists()
    
    @pytest.mark.asyncio
    async def test_delete_directory_recursive(self, primitive, tmp_path):
        """Test recursive directory deletion."""
        parent_dir = tmp_path / "parent"
        parent_dir.mkdir()
        (parent_dir / "child.txt").write_text("content")
        (parent_dir / "subdir").mkdir()
        
        result = await primitive.execute(
            path=str(parent_dir),
            recursive=True
        )
        
        assert result.success is True
        assert not parent_dir.exists()
    
    @pytest.mark.asyncio
    async def test_delete_non_empty_directory_no_recursive(self, primitive, tmp_path):
        """Test deleting non-empty directory without recursive flag."""
        parent_dir = tmp_path / "parent"
        parent_dir.mkdir()
        (parent_dir / "child.txt").write_text("content")
        
        result = await primitive.execute(
            path=str(parent_dir),
            recursive=False
        )
        
        # Should fail because directory is not empty
        assert result.success is False
    
    @pytest.mark.asyncio
    async def test_delete_nonexistent_path(self, primitive):
        """Test deleting non-existent path."""
        result = await primitive.execute(path="/nonexistent/path")
        
        assert result.success is False
        assert "not found" in result.message.lower()


class TestFileOperationsIntegration:
    """Integration tests for file operations."""
    
    @pytest.mark.asyncio
    async def test_write_read_delete_workflow(self, tmp_path):
        """Test complete file operation workflow."""
        test_file = tmp_path / "workflow.txt"
        
        # Write
        writer = WriteFilePrimitive()
        write_result = await writer.execute(
            path=str(test_file),
            content="Integration test content"
        )
        assert write_result.success is True
        
        # Read
        reader = ReadFilePrimitive()
        read_result = await reader.execute(path=str(test_file))
        assert read_result.success is True
        assert read_result.data["content"] == "Integration test content"
        
        # Delete
        deleter = DeletePathPrimitive()
        delete_result = await deleter.execute(path=str(test_file))
        assert delete_result.success is True
        assert not test_file.exists()
    
    @pytest.mark.asyncio
    async def test_directory_workflow(self, tmp_path):
        """Test directory creation and listing workflow."""
        # Create directory
        creator = CreateDirectoryPrimitive()
        new_dir = tmp_path / "workflow_dir"
        create_result = await creator.execute(path=str(new_dir))
        assert create_result.success is True
        
        # Create some files
        (new_dir / "file1.txt").write_text("content1")
        (new_dir / "file2.txt").write_text("content2")
        
        # List
        lister = ListDirectoryPrimitive()
        list_result = await lister.execute(path=str(new_dir))
        assert list_result.success is True
        assert list_result.data["count"] == 2
        
        # Delete recursive
        deleter = DeletePathPrimitive()
        delete_result = await deleter.execute(path=str(new_dir), recursive=True)
        assert delete_result.success is True
        assert not new_dir.exists()
