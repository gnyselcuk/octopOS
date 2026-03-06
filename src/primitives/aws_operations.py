"""AWS Operations Primitives - AWS service operations.

This module provides primitives for common AWS operations like
S3, DynamoDB, and Bedrock interactions.
"""

import json
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

from src.primitives.base_primitive import BasePrimitive, PrimitiveResult, register_primitive
from src.utils.aws_sts import get_auth_manager


class S3UploadPrimitive(BasePrimitive):
    """Upload a file to S3."""
    
    @property
    def name(self) -> str:
        return "s3_upload"
    
    @property
    def description(self) -> str:
        return "Upload a file to Amazon S3"
    
    @property
    def parameters(self) -> Dict[str, Dict[str, Any]]:
        return {
            "bucket": {
                "type": "string",
                "description": "S3 bucket name",
                "required": True
            },
            "key": {
                "type": "string",
                "description": "S3 object key (path in bucket)",
                "required": True
            },
            "file_path": {
                "type": "string",
                "description": "Local file path to upload",
                "required": True
            },
            "region": {
                "type": "string",
                "description": "AWS region",
                "required": False,
                "default": None
            }
        }
    
    async def execute(self, **kwargs) -> PrimitiveResult:
        """Execute S3 upload."""
        bucket = kwargs.get("bucket")
        key = kwargs.get("key")
        file_path = kwargs.get("file_path")
        region = kwargs.get("region")
        
        try:
            auth_manager = get_auth_manager()
            creds = auth_manager.get_credentials()
            
            s3 = boto3.client(
                's3',
                region_name=region or creds.region,
                aws_access_key_id=creds.access_key_id,
                aws_secret_access_key=creds.secret_access_key,
                aws_session_token=creds.session_token
            )
            
            s3.upload_file(file_path, bucket, key)
            
            return PrimitiveResult(
                success=True,
                data={
                    "bucket": bucket,
                    "key": key,
                    "url": f"s3://{bucket}/{key}"
                },
                message=f"Successfully uploaded to s3://{bucket}/{key}"
            )
            
        except ClientError as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"S3 upload failed: {e}",
                error=str(e)
            )
        except Exception as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Upload failed: {e}",
                error=str(e)
            )


class S3DownloadPrimitive(BasePrimitive):
    """Download a file from S3."""
    
    @property
    def name(self) -> str:
        return "s3_download"
    
    @property
    def description(self) -> str:
        return "Download a file from Amazon S3"
    
    @property
    def parameters(self) -> Dict[str, Dict[str, Any]]:
        return {
            "bucket": {
                "type": "string",
                "description": "S3 bucket name",
                "required": True
            },
            "key": {
                "type": "string",
                "description": "S3 object key",
                "required": True
            },
            "file_path": {
                "type": "string",
                "description": "Local path to save file",
                "required": True
            },
            "region": {
                "type": "string",
                "description": "AWS region",
                "required": False,
                "default": None
            }
        }
    
    async def execute(self, **kwargs) -> PrimitiveResult:
        """Execute S3 download."""
        bucket = kwargs.get("bucket")
        key = kwargs.get("key")
        file_path = kwargs.get("file_path")
        region = kwargs.get("region")
        
        try:
            from pathlib import Path
            
            auth_manager = get_auth_manager()
            creds = auth_manager.get_credentials()
            
            s3 = boto3.client(
                's3',
                region_name=region or creds.region,
                aws_access_key_id=creds.access_key_id,
                aws_secret_access_key=creds.secret_access_key,
                aws_session_token=creds.session_token
            )
            
            # Ensure directory exists
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)
            
            s3.download_file(bucket, key, file_path)
            
            return PrimitiveResult(
                success=True,
                data={
                    "bucket": bucket,
                    "key": key,
                    "local_path": file_path
                },
                message=f"Successfully downloaded s3://{bucket}/{key} to {file_path}"
            )
            
        except ClientError as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"S3 download failed: {e}",
                error=str(e)
            )
        except Exception as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Download failed: {e}",
                error=str(e)
            )


class S3ListPrimitive(BasePrimitive):
    """List objects in S3 bucket."""
    
    @property
    def name(self) -> str:
        return "s3_list"
    
    @property
    def description(self) -> str:
        return "List objects in an S3 bucket"
    
    @property
    def parameters(self) -> Dict[str, Dict[str, Any]]:
        return {
            "bucket": {
                "type": "string",
                "description": "S3 bucket name",
                "required": True
            },
            "prefix": {
                "type": "string",
                "description": "Prefix filter (like folder path)",
                "required": False,
                "default": ""
            },
            "max_keys": {
                "type": "integer",
                "description": "Maximum number of keys to return",
                "required": False,
                "default": 1000
            },
            "region": {
                "type": "string",
                "description": "AWS region",
                "required": False,
                "default": None
            }
        }
    
    async def execute(self, **kwargs) -> PrimitiveResult:
        """Execute S3 list."""
        bucket = kwargs.get("bucket")
        prefix = kwargs.get("prefix", "")
        max_keys = kwargs.get("max_keys", 1000)
        region = kwargs.get("region")
        
        try:
            auth_manager = get_auth_manager()
            creds = auth_manager.get_credentials()
            
            s3 = boto3.client(
                's3',
                region_name=region or creds.region,
                aws_access_key_id=creds.access_key_id,
                aws_secret_access_key=creds.secret_access_key,
                aws_session_token=creds.session_token
            )
            
            response = s3.list_objects_v2(
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
                    "count": len(objects)
                },
                message=f"Listed {len(objects)} objects in s3://{bucket}/{prefix}"
            )
            
        except ClientError as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"S3 list failed: {e}",
                error=str(e)
            )
        except Exception as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"List failed: {e}",
                error=str(e)
            )


class BedrockInvokePrimitive(BasePrimitive):
    """Invoke an AWS Bedrock model."""
    
    @property
    def name(self) -> str:
        return "bedrock_invoke"
    
    @property
    def description(self) -> str:
        return "Invoke an AWS Bedrock foundation model"
    
    @property
    def parameters(self) -> Dict[str, Dict[str, Any]]:
        return {
            "prompt": {
                "type": "string",
                "description": "Input prompt text",
                "required": True
            },
            "model_id": {
                "type": "string",
                "description": "Bedrock model ID",
                "required": False,
                "default": "amazon.nova-lite-v1:0"
            },
            "max_tokens": {
                "type": "integer",
                "description": "Maximum tokens to generate",
                "required": False,
                "default": 500
            },
            "temperature": {
                "type": "number",
                "description": "Sampling temperature (0-1)",
                "required": False,
                "default": 0.7
            }
        }
    
    async def execute(self, **kwargs) -> PrimitiveResult:
        """Execute Bedrock invocation."""
        prompt = kwargs.get("prompt")
        model_id = kwargs.get("model_id", "amazon.nova-lite-v1:0")
        max_tokens = kwargs.get("max_tokens", 500)
        temperature = kwargs.get("temperature", 0.7)
        
        try:
            auth_manager = get_auth_manager()
            client = auth_manager.get_bedrock_client()
            
            response = client.converse(
                modelId=model_id,
                messages=[
                    {
                        "role": "user",
                        "content": [{"text": prompt}]
                    }
                ],
                inferenceConfig={
                    "maxTokens": max_tokens,
                    "temperature": temperature
                }
            )
            
            output_text = response['output']['message']['content'][0]['text']
            
            return PrimitiveResult(
                success=True,
                data={
                    "response": output_text,
                    "model": model_id,
                    "usage": response.get('usage', {})
                },
                message="Successfully invoked Bedrock model"
            )
            
        except ClientError as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Bedrock invocation failed: {e}",
                error=str(e)
            )
        except Exception as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Invocation failed: {e}",
                error=str(e)
            )


class DynamoDBGetItemPrimitive(BasePrimitive):
    """Get an item from DynamoDB."""
    
    @property
    def name(self) -> str:
        return "dynamodb_get_item"
    
    @property
    def description(self) -> str:
        return "Get a single item from a DynamoDB table"
    
    @property
    def parameters(self) -> Dict[str, Dict[str, Any]]:
        return {
            "table_name": {
                "type": "string",
                "description": "DynamoDB table name",
                "required": True
            },
            "key": {
                "type": "object",
                "description": "Primary key dict (e.g., {'id': '123'})",
                "required": True
            },
            "region": {
                "type": "string",
                "description": "AWS region",
                "required": False,
                "default": None
            }
        }
    
    async def execute(self, **kwargs) -> PrimitiveResult:
        """Execute DynamoDB get item."""
        table_name = kwargs.get("table_name")
        key = kwargs.get("key")
        region = kwargs.get("region")
        
        try:
            auth_manager = get_auth_manager()
            creds = auth_manager.get_credentials()
            
            dynamodb = boto3.resource(
                'dynamodb',
                region_name=region or creds.region,
                aws_access_key_id=creds.access_key_id,
                aws_secret_access_key=creds.secret_access_key,
                aws_session_token=creds.session_token
            )
            
            table = dynamodb.Table(table_name)
            response = table.get_item(Key=key)
            
            item = response.get('Item')
            
            if item:
                return PrimitiveResult(
                    success=True,
                    data={
                        "item": item,
                        "table": table_name
                    },
                    message=f"Retrieved item from {table_name}"
                )
            else:
                return PrimitiveResult(
                    success=True,
                    data=None,
                    message=f"Item not found in {table_name}",
                    error="ItemNotFound"
                )
            
        except ClientError as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"DynamoDB get failed: {e}",
                error=str(e)
            )
        except Exception as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Get item failed: {e}",
                error=str(e)
            )


# Register all primitives
def register_all():
    """Register all AWS operation primitives."""
    register_primitive(S3UploadPrimitive())
    register_primitive(S3DownloadPrimitive())
    register_primitive(S3ListPrimitive())
    register_primitive(BedrockInvokePrimitive())
    register_primitive(DynamoDBGetItemPrimitive())