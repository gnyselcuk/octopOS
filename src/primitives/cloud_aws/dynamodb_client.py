"""DynamoDB Client - Amazon DynamoDB operations primitive.

Provides DynamoDB operations including get, put, query, scan, and delete.

Example:
    >>> from src.primitives.cloud_aws.dynamodb_client import DynamoDBClient
    >>> db = DynamoDBClient()
    >>> result = await db.execute(
    ...     operation="get_item",
    ...     table_name="users",
    ...     key={"user_id": "123"}
    ... )
"""

from typing import Any, Dict, List, Optional
from enum import Enum
import json

import boto3
from botocore.exceptions import ClientError

from src.primitives.base_primitive import BasePrimitive, PrimitiveResult, register_primitive
from src.utils.aws_sts import get_auth_manager
from src.utils.logger import get_logger

logger = get_logger()


class DynamoDBOperation(str, Enum):
    """DynamoDB operation types."""
    GET_ITEM = "get_item"
    PUT_ITEM = "put_item"
    DELETE_ITEM = "delete_item"
    QUERY = "query"
    SCAN = "scan"
    UPDATE_ITEM = "update_item"
    BATCH_GET = "batch_get"
    BATCH_WRITE = "batch_write"


class DynamoDBClient(BasePrimitive):
    """Manage Amazon DynamoDB operations.
    
    Provides comprehensive DynamoDB functionality:
    - Item CRUD operations (get, put, update, delete)
    - Query and scan operations
    - Batch operations
    - JSON serialization/deserialization
    """
    
    def __init__(self) -> None:
        """Initialize DynamoDB Client."""
        super().__init__()
        self._resource = None
        self._client = None
    
    @property
    def name(self) -> str:
        return "dynamodb"
    
    @property
    def description(self) -> str:
        return (
            "Perform Amazon DynamoDB operations: get_item, put_item, delete_item, "
            "query, scan, update_item, batch_get, batch_write."
        )
    
    @property
    def parameters(self) -> Dict[str, Dict[str, Any]]:
        return {
            "operation": {
                "type": "string",
                "description": "DynamoDB operation type",
                "required": True,
                "enum": [op.value for op in DynamoDBOperation]
            },
            "table_name": {
                "type": "string",
                "description": "DynamoDB table name",
                "required": True
            },
            "key": {
                "type": "object",
                "description": "Primary key dict (e.g., {'id': '123'}) for get/delete",
                "required": False
            },
            "item": {
                "type": "object",
                "description": "Item data dict for put/update",
                "required": False
            },
            "key_condition": {
                "type": "string",
                "description": "Key condition expression for query",
                "required": False
            },
            "filter": {
                "type": "string",
                "description": "Filter expression",
                "required": False
            },
            "expression_values": {
                "type": "object",
                "description": "Expression attribute values",
                "required": False
            },
            "expression_names": {
                "type": "object",
                "description": "Expression attribute names",
                "required": False
            },
            "index_name": {
                "type": "string",
                "description": "Global secondary index name",
                "required": False
            },
            "limit": {
                "type": "integer",
                "description": "Maximum items to return",
                "required": False,
                "default": 100
            },
            "region": {
                "type": "string",
                "description": "AWS region",
                "required": False
            }
        }
    
    def _get_resource(self, region: Optional[str] = None):
        """Get or create DynamoDB resource (synchronous — called via run_in_executor)."""
        if self._resource is None:
            auth_manager = get_auth_manager()
            creds = auth_manager.get_credentials()
            self._resource = boto3.resource(
                'dynamodb',
                region_name=region or creds.region,
                aws_access_key_id=creds.access_key_id,
                aws_secret_access_key=creds.secret_access_key,
                aws_session_token=creds.session_token,
            )
        return self._resource

    def _get_client(self, region: Optional[str] = None):
        """Get or create DynamoDB low-level client (synchronous)."""
        if self._client is None:
            auth_manager = get_auth_manager()
            creds = auth_manager.get_credentials()
            self._client = boto3.client(
                'dynamodb',
                region_name=region or creds.region,
                aws_access_key_id=creds.access_key_id,
                aws_secret_access_key=creds.secret_access_key,
                aws_session_token=creds.session_token,
            )
        return self._client

    async def _run(self, fn, *args, **kwargs):
        """Run a blocking boto3 call in a thread pool to avoid blocking the event loop."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))


    async def execute(self, **kwargs) -> PrimitiveResult:
        """Execute DynamoDB operation.
        
        Args:
            operation: DynamoDBOperation type
            table_name: Table name
            key: Primary key dict
            item: Item data dict
            key_condition: Query key condition
            filter: Filter expression
            expression_values: Expression attribute values
            expression_names: Expression attribute names
            index_name: GSI name
            limit: Max results
            region: AWS region
            
        Returns:
            PrimitiveResult with operation results
        """
        operation_str = kwargs.get("operation", "")
        
        try:
            operation = DynamoDBOperation(operation_str)
        except ValueError:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Invalid operation: {operation_str}",
                error="InvalidOperation"
            )
        
        try:
            if operation == DynamoDBOperation.GET_ITEM:
                return await self._get_item(kwargs)
            elif operation == DynamoDBOperation.PUT_ITEM:
                return await self._put_item(kwargs)
            elif operation == DynamoDBOperation.DELETE_ITEM:
                return await self._delete_item(kwargs)
            elif operation == DynamoDBOperation.QUERY:
                return await self._query(kwargs)
            elif operation == DynamoDBOperation.SCAN:
                return await self._scan(kwargs)
            elif operation == DynamoDBOperation.UPDATE_ITEM:
                return await self._update_item(kwargs)
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
            logger.error(f"DynamoDB error ({error_code}): {error_msg}")
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"DynamoDB error: {error_msg}",
                error=error_code
            )
        except Exception as e:
            logger.error(f"DynamoDB operation error: {e}")
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Operation failed: {e}",
                error=str(e)
            )
    
    async def _get_item(self, kwargs: Dict) -> PrimitiveResult:
        """Get a single item."""
        table_name = kwargs.get("table_name")
        key = kwargs.get("key")
        region = kwargs.get("region")

        if not table_name or not key:
            return PrimitiveResult(
                success=False, data=None,
                message="Missing required parameters: table_name, key",
                error="MissingParameters"
            )

        resource = self._get_resource(region)
        table = resource.Table(table_name)
        response = await self._run(table.get_item, Key=key)
        item = response.get('Item')

        if item:
            return PrimitiveResult(
                success=True,
                data={"item": item, "table": table_name},
                message=f"Retrieved item from {table_name}"
            )
        return PrimitiveResult(
            success=True, data=None,
            message=f"Item not found in {table_name}",
            error="ItemNotFound"
        )
    
    async def _put_item(self, kwargs: Dict) -> PrimitiveResult:
        """Put an item."""
        table_name = kwargs.get("table_name")
        item = kwargs.get("item")
        region = kwargs.get("region")

        if not table_name or not item:
            return PrimitiveResult(
                success=False, data=None,
                message="Missing required parameters: table_name, item",
                error="MissingParameters"
            )

        resource = self._get_resource(region)
        table = resource.Table(table_name)
        await self._run(table.put_item, Item=item)

        return PrimitiveResult(
            success=True,
            data={"table": table_name, "item_keys": list(item.keys())},
            message=f"Put item into {table_name}"
        )
    
    async def _delete_item(self, kwargs: Dict) -> PrimitiveResult:
        """Delete an item."""
        table_name = kwargs.get("table_name")
        key = kwargs.get("key")
        region = kwargs.get("region")
        
        if not table_name or not key:
            return PrimitiveResult(
                success=False,
                data=None,
                message="Missing required parameters: table_name, key",
                error="MissingParameters"
            )
        
        resource = self._get_resource(region)
        table = resource.Table(table_name)
        table.delete_item(Key=key)
        
        return PrimitiveResult(
            success=True,
            data={
                "table": table_name,
                "deleted_key": key
            },
            message=f"Deleted item from {table_name}"
        )
    
    async def _query(self, kwargs: Dict) -> PrimitiveResult:
        """Query items."""
        table_name = kwargs.get("table_name")
        key_condition = kwargs.get("key_condition")
        region = kwargs.get("region")
        index_name = kwargs.get("index_name")
        limit = kwargs.get("limit", 100)
        filter_expr = kwargs.get("filter")
        expr_values = kwargs.get("expression_values", {})
        expr_names = kwargs.get("expression_names", {})
        
        if not table_name:
            return PrimitiveResult(
                success=False,
                data=None,
                message="Missing required parameter: table_name",
                error="MissingParameters"
            )
        
        resource = self._get_resource(region)
        table = resource.Table(table_name)
        
        query_kwargs = {'Limit': limit}
        
        if key_condition:
            query_kwargs['KeyConditionExpression'] = key_condition
        if filter_expr:
            query_kwargs['FilterExpression'] = filter_expr
        if expr_values:
            query_kwargs['ExpressionAttributeValues'] = expr_values
        if expr_names:
            query_kwargs['ExpressionAttributeNames'] = expr_names
        if index_name:
            query_kwargs['IndexName'] = index_name
        
        response = table.query(**query_kwargs)
        items = response.get('Items', [])
        
        return PrimitiveResult(
            success=True,
            data={
                "items": items,
                "count": len(items),
                "table": table_name,
                "scanned_count": response.get('ScannedCount', 0)
            },
            message=f"Query returned {len(items)} items from {table_name}"
        )
    
    async def _scan(self, kwargs: Dict) -> PrimitiveResult:
        """Scan table."""
        table_name = kwargs.get("table_name")
        region = kwargs.get("region")
        limit = kwargs.get("limit", 100)
        filter_expr = kwargs.get("filter")
        expr_values = kwargs.get("expression_values", {})
        expr_names = kwargs.get("expression_names", {})
        index_name = kwargs.get("index_name")
        
        if not table_name:
            return PrimitiveResult(
                success=False,
                data=None,
                message="Missing required parameter: table_name",
                error="MissingParameters"
            )
        
        resource = self._get_resource(region)
        table = resource.Table(table_name)
        
        scan_kwargs = {'Limit': limit}
        
        if filter_expr:
            scan_kwargs['FilterExpression'] = filter_expr
        if expr_values:
            scan_kwargs['ExpressionAttributeValues'] = expr_values
        if expr_names:
            scan_kwargs['ExpressionAttributeNames'] = expr_names
        if index_name:
            scan_kwargs['IndexName'] = index_name
        
        response = table.scan(**scan_kwargs)
        items = response.get('Items', [])
        
        return PrimitiveResult(
            success=True,
            data={
                "items": items,
                "count": len(items),
                "table": table_name,
                "scanned_count": response.get('ScannedCount', 0)
            },
            message=f"Scan returned {len(items)} items from {table_name}"
        )
    
    async def _update_item(self, kwargs: Dict) -> PrimitiveResult:
        """Update an item."""
        table_name = kwargs.get("table_name")
        key = kwargs.get("key")
        item = kwargs.get("item")
        region = kwargs.get("region")
        
        if not table_name or not key or not item:
            return PrimitiveResult(
                success=False,
                data=None,
                message="Missing required parameters: table_name, key, item",
                error="MissingParameters"
            )
        
        resource = self._get_resource(region)
        table = resource.Table(table_name)
        
        # Build update expression
        update_expr = "SET " + ", ".join([f"#{k}=:{k}" for k in item.keys() if k not in key])
        expr_names = {f"#{k}": k for k in item.keys() if k not in key}
        expr_values = {f":{k}": v for k, v in item.items() if k not in key}
        
        if not update_expr.replace("SET ", ""):
            return PrimitiveResult(
                success=False,
                data=None,
                message="No attributes to update (key attributes excluded)",
                error="NoUpdateAttributes"
            )
        
        table.update_item(
            Key=key,
            UpdateExpression=update_expr,
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values
        )
        
        return PrimitiveResult(
            success=True,
            data={
                "table": table_name,
                "updated_key": key,
                "updated_attributes": list(item.keys())
            },
            message=f"Updated item in {table_name}"
        )


def register_all() -> None:
    """Register DynamoDB primitives."""
    register_primitive(DynamoDBClient())
