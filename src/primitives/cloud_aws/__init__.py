"""Cloud AWS Primitives - AWS service operations."""

from src.primitives.cloud_aws.s3_manager import S3Manager
from src.primitives.cloud_aws.dynamodb_client import DynamoDBClient
from src.primitives.cloud_aws.bedrock_invoker import BedrockInvoker
from src.primitives.cloud_aws.cloudwatch_inspector import CloudWatchInspector

__all__ = [
    "S3Manager",
    "DynamoDBClient",
    "BedrockInvoker",
    "CloudWatchInspector",
]


def register_all() -> None:
    """Register all cloud AWS primitives with the tool registry."""
    from src.primitives.tool_registry import register_primitive
    
    register_primitive(S3Manager(), category='cloud_aws', tags=['aws', 's3', 'storage'])
    register_primitive(DynamoDBClient(), category='cloud_aws', tags=['aws', 'dynamodb', 'database'])
    register_primitive(BedrockInvoker(), category='cloud_aws', tags=['aws', 'bedrock', 'ai'])
    register_primitive(CloudWatchInspector(), category='cloud_aws', tags=['aws', 'cloudwatch', 'monitoring'])
