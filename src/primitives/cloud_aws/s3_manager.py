"""S3 Manager - Amazon S3 operations primitive.

Provides S3 operations including upload, download, list, delete, and presigned URLs.

Example:
    >>> from src.primitives.cloud_aws.s3_manager import S3Manager
    >>> s3 = S3Manager()
    >>> result = await s3.execute(
    ...     operation="upload",
    ...     bucket="my-bucket",
    ...     key="data/file.txt",
    ...     file_path="/local/file.txt"
    ... )
"""

from typing import Any, Dict, List, Optional
from enum import Enum
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from src.primitives.base_primitive import BasePrimitive, PrimitiveResult, register_primitive
from src.utils.aws_sts import get_auth_manager
from src.utils.logger import get_logger

logger = get_logger()


class S3Operation(str, Enum):
    """S3 operation types."""
    UPLOAD = "upload"
    DOWNLOAD = "download"
    LIST = "list"
    DELETE = "delete"
    EXISTS = "exists"
    PRESIGNED_URL = "presigned_url"
    COPY = "copy"


class S3Manager(BasePrimitive):
    """Manage Amazon S3 operations.
    
    Provides comprehensive S3 functionality:
    - File upload/download
    - Bucket listing
    - Object deletion
    - Presigned URL generation
    - Cross-bucket copy
    """
    
    def __init__(self) -> None:
        """Initialize S3 Manager."""
        super().__init__()
        self._client = None
    
    @property
    def name(self) -> str:
        return "s3_manage"
    
    @property
    def description(self) -> str:
        return (
            "Perform Amazon S3 operations: upload, download, list objects, "
            "delete, generate presigned URLs, and copy between buckets."
        )
    
    @property
    def parameters(self) -> Dict[str, Dict[str, Any]]:
        return {
            "operation": {
                "type": "string",
                "description": "S3 operation: upload, download, list, delete, exists, presigned_url, copy",
                "required": True,
                "enum": [op.value for op in S3Operation]
            },
            "bucket": {
                "type": "string",
                "description": "S3 bucket name",
                "required": True
            },
            "key": {
                "type": "string",
                "description": "S3 object key (path in bucket)",
                "required": False
            },
            "file_path": {
                "type": "string",
                "description": "Local file path (for upload/download)",
                "required": False
            },
            "prefix": {
                "type": "string",
                "description": "Prefix filter for list operations",
                "required": False,
                "default": ""
            },
            "region": {
                "type": "string",
                "description": "AWS region (default: from config)",
                "required": False
            },
            "max_keys": {
                "type": "integer",
                "description": "Maximum keys to return (for list)",
                "required": False,
                "default": 1000
            },
            "expiration": {
                "type": "integer",
                "description": "Presigned URL expiration in seconds (default: 3600)",
                "required": False,
                "default": 3600
            },
            "source_bucket": {
                "type": "string",
                "description": "Source bucket (for copy)",
                "required": False
            },
            "source_key": {
                "type": "string",
                "description": "Source key (for copy)",
                "required": False
            }
        }
    
    def _get_client(self, region: Optional[str] = None):
        """Get or create S3 client."""
        if self._client is None:
            auth_manager = get_auth_manager()
            creds = auth_manager.get_credentials()
            
            self._client = boto3.client(
                's3',
                region_name=region or creds.region,
                aws_access_key_id=creds.access_key_id,
                aws_secret_access_key=creds.secret_access_key,
                aws_session_token=creds.session_token
            )
        return self._client
    
    async def execute(self, **kwargs) -> PrimitiveResult:
        """Execute S3 operation.
        
        Args:
            operation: S3Operation type
            bucket: Target bucket
            key: Object key
            file_path: Local file path
            prefix: List prefix filter
            region: AWS region
            max_keys: Max results for list
            expiration: Presigned URL expiration
            source_bucket: Copy source bucket
            source_key: Copy source key
            
        Returns:
            PrimitiveResult with operation results
        """
        operation_str = kwargs.get("operation", "")
        
        try:
            operation = S3Operation(operation_str)
        except ValueError:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Invalid operation: {operation_str}",
                error="InvalidOperation"
            )
        
        try:
            if operation == S3Operation.UPLOAD:
                return await self._upload(kwargs)
            elif operation == S3Operation.DOWNLOAD:
                return await self._download(kwargs)
            elif operation == S3Operation.LIST:
                return await self._list(kwargs)
            elif operation == S3Operation.DELETE:
                return await self._delete(kwargs)
            elif operation == S3Operation.EXISTS:
                return await self._exists(kwargs)
            elif operation == S3Operation.PRESIGNED_URL:
                return await self._presigned_url(kwargs)
            elif operation == S3Operation.COPY:
                return await self._copy(kwargs)
            else:
                return PrimitiveResult(
                    success=False,
                    data=None,
                    message=f"Operation not implemented: {operation}",
                    error="NotImplemented"
                )
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_msg = e.response['Error']['Message']
            logger.error(f"S3 error ({error_code}): {error_msg}")
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"S3 error: {error_msg}",
                error=error_code
            )
        except Exception as e:
            logger.error(f"S3 operation error: {e}")
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Operation failed: {e}",
                error=str(e)
            )
    
    async def _upload(self, kwargs: Dict) -> PrimitiveResult:
        """Upload file to S3."""
        bucket = kwargs.get("bucket")
        key = kwargs.get("key")
        file_path = kwargs.get("file_path")
        region = kwargs.get("region")
        
        if not all([bucket, key, file_path]):
            return PrimitiveResult(
                success=False,
                data=None,
                message="Missing required parameters: bucket, key, file_path",
                error="MissingParameters"
            )
        
        # Ensure file exists
        path = Path(file_path)
        if not path.exists():
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"File not found: {file_path}",
                error="FileNotFound"
            )
        
        client = self._get_client(region)
        client.upload_file(str(path), bucket, key)
        
        return PrimitiveResult(
            success=True,
            data={
                "bucket": bucket,
                "key": key,
                "local_path": str(path),
                "url": f"s3://{bucket}/{key}"
            },
            message=f"Uploaded to s3://{bucket}/{key}"
        )
    
    async def _download(self, kwargs: Dict) -> PrimitiveResult:
        """Download file from S3."""
        bucket = kwargs.get("bucket")
        key = kwargs.get("key")
        file_path = kwargs.get("file_path")
        region = kwargs.get("region")
        
        if not all([bucket, key, file_path]):
            return PrimitiveResult(
                success=False,
                data=None,
                message="Missing required parameters: bucket, key, file_path",
                error="MissingParameters"
            )
        
        # Ensure directory exists
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        client = self._get_client(region)
        client.download_file(bucket, key, str(path))
        
        return PrimitiveResult(
            success=True,
            data={
                "bucket": bucket,
                "key": key,
                "local_path": str(path)
            },
            message=f"Downloaded s3://{bucket}/{key} to {file_path}"
        )
    
    async def _list(self, kwargs: Dict) -> PrimitiveResult:
        """List objects in S3 bucket."""
        bucket = kwargs.get("bucket")
        prefix = kwargs.get("prefix", "")
        max_keys = kwargs.get("max_keys", 1000)
        region = kwargs.get("region")
        
        if not bucket:
            return PrimitiveResult(
                success=False,
                data=None,
                message="Missing required parameter: bucket",
                error="MissingParameters"
            )
        
        client = self._get_client(region)
        response = client.list_objects_v2(
            Bucket=bucket,
            Prefix=prefix,
            MaxKeys=max_keys
        )
        
        objects = []
        for obj in response.get('Contents', []):
            objects.append({
                "key": obj['Key'],
                "size": obj['Size'],
                "last_modified": obj['LastModified'].isoformat(),
                "etag": obj['ETag']
            })
        
        return PrimitiveResult(
            success=True,
            data={
                "bucket": bucket,
                "prefix": prefix,
                "objects": objects,
                "count": len(objects),
                "is_truncated": response.get('IsTruncated', False)
            },
            message=f"Listed {len(objects)} objects in s3://{bucket}/{prefix}"
        )
    
    async def _delete(self, kwargs: Dict) -> PrimitiveResult:
        """Delete object from S3."""
        bucket = kwargs.get("bucket")
        key = kwargs.get("key")
        region = kwargs.get("region")
        
        if not all([bucket, key]):
            return PrimitiveResult(
                success=False,
                data=None,
                message="Missing required parameters: bucket, key",
                error="MissingParameters"
            )
        
        client = self._get_client(region)
        client.delete_object(Bucket=bucket, Key=key)
        
        return PrimitiveResult(
            success=True,
            data={
                "bucket": bucket,
                "key": key,
                "deleted": True
            },
            message=f"Deleted s3://{bucket}/{key}"
        )
    
    async def _exists(self, kwargs: Dict) -> PrimitiveResult:
        """Check if object exists in S3."""
        bucket = kwargs.get("bucket")
        key = kwargs.get("key")
        region = kwargs.get("region")
        
        if not all([bucket, key]):
            return PrimitiveResult(
                success=False,
                data=None,
                message="Missing required parameters: bucket, key",
                error="MissingParameters"
            )
        
        client = self._get_client(region)
        
        try:
            client.head_object(Bucket=bucket, Key=key)
            exists = True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                exists = False
            else:
                raise
        
        return PrimitiveResult(
            success=True,
            data={
                "bucket": bucket,
                "key": key,
                "exists": exists
            },
            message=f"Object s3://{bucket}/{key} exists: {exists}"
        )
    
    async def _presigned_url(self, kwargs: Dict) -> PrimitiveResult:
        """Generate presigned URL for S3 object."""
        bucket = kwargs.get("bucket")
        key = kwargs.get("key")
        expiration = kwargs.get("expiration", 3600)
        region = kwargs.get("region")
        
        if not all([bucket, key]):
            return PrimitiveResult(
                success=False,
                data=None,
                message="Missing required parameters: bucket, key",
                error="MissingParameters"
            )
        
        client = self._get_client(region)
        url = client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': key},
            ExpiresIn=expiration
        )
        
        return PrimitiveResult(
            success=True,
            data={
                "bucket": bucket,
                "key": key,
                "url": url,
                "expiration_seconds": expiration
            },
            message=f"Generated presigned URL (expires in {expiration}s)"
        )
    
    async def _copy(self, kwargs: Dict) -> PrimitiveResult:
        """Copy object between S3 locations."""
        bucket = kwargs.get("bucket")
        key = kwargs.get("key")
        source_bucket = kwargs.get("source_bucket")
        source_key = kwargs.get("source_key")
        region = kwargs.get("region")
        
        if not all([bucket, key, source_key]):
            return PrimitiveResult(
                success=False,
                data=None,
                message="Missing required parameters: bucket, key, source_key",
                error="MissingParameters"
            )
        
        # Source bucket defaults to target bucket if not specified
        source_bucket = source_bucket or bucket
        copy_source = {'Bucket': source_bucket, 'Key': source_key}
        
        client = self._get_client(region)
        client.copy(copy_source, bucket, key)
        
        return PrimitiveResult(
            success=True,
            data={
                "source_bucket": source_bucket,
                "source_key": source_key,
                "destination_bucket": bucket,
                "destination_key": key
            },
            message=f"Copied from s3://{source_bucket}/{source_key} to s3://{bucket}/{key}"
        )


def register_all() -> None:
    """Register S3 primitives."""
    register_primitive(S3Manager())
