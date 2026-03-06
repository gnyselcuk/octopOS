"""Unit tests for primitives/cloud_aws/s3_manager.py module.

This module tests the Amazon S3 operations primitive.
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from botocore.exceptions import ClientError

from src.primitives.cloud_aws.s3_manager import S3Manager, S3Operation
from src.primitives.base_primitive import PrimitiveResult


class TestS3Operation:
    """Test S3Operation enum."""
    
    def test_operation_values(self):
        """Test that all expected operations exist."""
        expected_ops = {
            "upload", "download", "list", "delete",
            "exists", "presigned_url", "copy"
        }
        actual_ops = {op.value for op in S3Operation}
        assert actual_ops == expected_ops
    
    def test_operation_comparison(self):
        """Test operation enum comparison."""
        assert S3Operation.UPLOAD == "upload"
        assert S3Operation.UPLOAD != "download"


class TestS3Manager:
    """Test S3Manager primitive."""
    
    @pytest.fixture
    def manager(self):
        """Create S3 manager instance."""
        return S3Manager()
    
    @pytest.fixture
    def mock_auth_manager(self):
        """Create mock auth manager."""
        with patch('src.primitives.cloud_aws.s3_manager.get_auth_manager') as mock_get:
            auth = MagicMock()
            creds = MagicMock()
            creds.region = "us-east-1"
            creds.access_key_id = "AKIAIOSFODNN7EXAMPLE"
            creds.secret_access_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
            creds.session_token = None
            auth.get_credentials.return_value = creds
            mock_get.return_value = auth
            yield auth
    
    @pytest.fixture
    def mock_s3_client(self, mock_auth_manager):
        """Create mock S3 client."""
        with patch('boto3.client') as mock_client:
            s3 = MagicMock()
            mock_client.return_value = s3
            yield s3
    
    def test_name(self, manager):
        """Test primitive name."""
        assert manager.name == "s3_manage"
    
    def test_description(self, manager):
        """Test primitive description."""
        assert "S3" in manager.description
        assert "upload" in manager.description.lower()
    
    def test_parameters(self, manager):
        """Test parameter definitions."""
        params = manager.parameters
        
        assert "operation" in params
        assert "bucket" in params
        assert "key" in params
        assert "file_path" in params
        
        # Check operation enum
        assert params["operation"]["required"] is True
        assert "enum" in params["operation"]
    
    @pytest.mark.asyncio
    async def test_execute_invalid_operation(self, manager):
        """Test executing with invalid operation."""
        result = await manager.execute(operation="invalid_op", bucket="test")
        
        assert result.success is False
        assert "Invalid operation" in result.message
    
    @pytest.mark.asyncio
    async def test_upload_success(self, manager, mock_s3_client, tmp_path):
        """Test successful file upload."""
        # Create test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")
        
        result = await manager.execute(
            operation="upload",
            bucket="test-bucket",
            key="uploads/test.txt",
            file_path=str(test_file)
        )
        
        assert result.success is True
        assert result.data["bucket"] == "test-bucket"
        assert result.data["key"] == "uploads/test.txt"
        mock_s3_client.upload_file.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_upload_missing_parameters(self, manager):
        """Test upload with missing parameters."""
        result = await manager.execute(
            operation="upload",
            bucket="test-bucket"
            # Missing key and file_path
        )
        
        assert result.success is False
        assert "Missing" in result.message
    
    @pytest.mark.asyncio
    async def test_upload_file_not_found(self, manager):
        """Test upload with non-existent file."""
        result = await manager.execute(
            operation="upload",
            bucket="test-bucket",
            key="test.txt",
            file_path="/nonexistent/file.txt"
        )
        
        assert result.success is False
        assert "not found" in result.message.lower()
    
    @pytest.mark.asyncio
    async def test_download_success(self, manager, mock_s3_client, tmp_path):
        """Test successful file download."""
        download_path = tmp_path / "downloaded.txt"
        
        result = await manager.execute(
            operation="download",
            bucket="test-bucket",
            key="test.txt",
            file_path=str(download_path)
        )
        
        assert result.success is True
        assert result.data["bucket"] == "test-bucket"
        assert result.data["key"] == "test.txt"
        mock_s3_client.download_file.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_list_success(self, manager, mock_s3_client):
        """Test successful object listing."""
        mock_s3_client.list_objects_v2.return_value = {
            "Contents": [
                {
                    "Key": "file1.txt",
                    "Size": 100,
                    "LastModified": datetime.now(),
                    "ETag": '"abc123"'
                },
                {
                    "Key": "file2.txt",
                    "Size": 200,
                    "LastModified": datetime.now(),
                    "ETag": '"def456"'
                }
            ],
            "IsTruncated": False
        }
        
        result = await manager.execute(
            operation="list",
            bucket="test-bucket",
            prefix="files/"
        )
        
        assert result.success is True
        assert result.data["count"] == 2
        assert len(result.data["objects"]) == 2
        mock_s3_client.list_objects_v2.assert_called_once_with(
            Bucket="test-bucket",
            Prefix="files/",
            MaxKeys=1000
        )
    
    @pytest.mark.asyncio
    async def test_delete_success(self, manager, mock_s3_client):
        """Test successful object deletion."""
        result = await manager.execute(
            operation="delete",
            bucket="test-bucket",
            key="test.txt"
        )
        
        assert result.success is True
        assert result.data["deleted"] is True
        mock_s3_client.delete_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="test.txt"
        )
    
    @pytest.mark.asyncio
    async def test_exists_success(self, manager, mock_s3_client):
        """Test checking if object exists."""
        result = await manager.execute(
            operation="exists",
            bucket="test-bucket",
            key="test.txt"
        )
        
        assert result.success is True
        mock_s3_client.head_object.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_exists_not_found(self, manager, mock_s3_client):
        """Test checking non-existent object."""
        error_response = {
            "Error": {"Code": "404", "Message": "Not Found"}
        }
        mock_s3_client.head_object.side_effect = ClientError(
            error_response, "HeadObject"
        )
        
        result = await manager.execute(
            operation="exists",
            bucket="test-bucket",
            key="nonexistent.txt"
        )
        
        assert result.success is False
    
    @pytest.mark.asyncio
    async def test_presigned_url_success(self, manager, mock_s3_client):
        """Test generating presigned URL."""
        mock_s3_client.generate_presigned_url.return_value = "https://presigned-url.example.com"
        
        result = await manager.execute(
            operation="presigned_url",
            bucket="test-bucket",
            key="test.txt",
            expiration=7200
        )
        
        assert result.success is True
        assert "presigned-url" in result.data["url"]
        mock_s3_client.generate_presigned_url.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_copy_success(self, manager, mock_s3_client):
        """Test copying object between buckets."""
        result = await manager.execute(
            operation="copy",
            bucket="dest-bucket",
            key="dest-key.txt",
            source_bucket="source-bucket",
            source_key="source-key.txt"
        )
        
        assert result.success is True
        assert result.data["copied"] is True
        mock_s3_client.copy.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_client_error_handling(self, manager, mock_s3_client):
        """Test handling of AWS client errors."""
        error_response = {
            "Error": {"Code": "NoSuchBucket", "Message": "Bucket not found"}
        }
        mock_s3_client.list_objects_v2.side_effect = ClientError(
            error_response, "ListObjectsV2"
        )
        
        result = await manager.execute(
            operation="list",
            bucket="nonexistent-bucket"
        )
        
        assert result.success is False
        assert "NoSuchBucket" in result.error or "not found" in result.message.lower()
    
    @pytest.mark.asyncio
    async def test_generic_exception_handling(self, manager, mock_s3_client):
        """Test handling of generic exceptions."""
        mock_s3_client.list_objects_v2.side_effect = Exception("Unexpected error")
        
        result = await manager.execute(
            operation="list",
            bucket="test-bucket"
        )
        
        assert result.success is False
        assert "Unexpected error" in result.message
