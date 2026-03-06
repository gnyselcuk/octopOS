"""Mock AWS services for testing.

This module provides mock implementations of AWS services
used throughout the octopOS system.
"""

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock


class MockBedrockRuntime:
    """Mock AWS Bedrock runtime client."""
    
    def __init__(self, responses: Optional[List[Dict]] = None):
        """Initialize with optional predefined responses.
        
        Args:
            responses: List of response dicts to return sequentially
        """
        self.responses = responses or []
        self.call_count = 0
        self.invoked_models: List[Dict] = []
    
    def invoke_model(
        self,
        modelId: str,
        body: bytes,
        **kwargs
    ) -> Dict[str, Any]:
        """Mock invoke_model method."""
        self.invoked_models.append({
            "modelId": modelId,
            "body": body,
            "kwargs": kwargs
        })
        
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
        else:
            response = {
                "content": [{"text": "Mock response"}],
                "usage": {"inputTokens": 10, "outputTokens": 20}
            }
        
        self.call_count += 1
        
        # Return mock response body
        mock_body = MagicMock()
        import json
        mock_body.read.return_value = json.dumps(response).encode()
        
        return {"body": mock_body}
    
    def converse(self, **kwargs) -> Dict[str, Any]:
        """Mock converse method for Bedrock Converse API."""
        return {
            "output": {
                "message": {
                    "content": [{"text": "Mock converse response"}]
                }
            },
            "usage": {"inputTokens": 10, "outputTokens": 20}
        }


class MockCloudWatch:
    """Mock CloudWatch client."""
    
    def __init__(self):
        """Initialize mock CloudWatch client."""
        self.log_groups: Dict[str, List[Dict]] = {}
        self.metrics: List[Dict] = []
        self.alarms: List[Dict] = []
    
    def put_log_events(
        self,
        logGroupName: str,
        logStreamName: str,
        logEvents: List[Dict]
    ) -> Dict[str, Any]:
        """Mock put_log_events method."""
        if logGroupName not in self.log_groups:
            self.log_groups[logGroupName] = []
        
        self.log_groups[logGroupName].extend(logEvents)
        
        return {
            "nextSequenceToken": "mock_token",
            "rejectedLogEventsInfo": {}
        }
    
    def create_log_group(self, logGroupName: str, **kwargs) -> Dict[str, Any]:
        """Mock create_log_group method."""
        if logGroupName not in self.log_groups:
            self.log_groups[logGroupName] = []
        return {}
    
    def put_metric_data(
        self,
        Namespace: str,
        MetricData: List[Dict]
    ) -> Dict[str, Any]:
        """Mock put_metric_data method."""
        for metric in MetricData:
            self.metrics.append({
                "namespace": Namespace,
                **metric
            })
        return {}
    
    def put_metric_alarm(self, **kwargs) -> Dict[str, Any]:
        """Mock put_metric_alarm method."""
        self.alarms.append(kwargs)
        return {}


class MockDynamoDB:
    """Mock DynamoDB table."""
    
    def __init__(self, table_name: str = "mock_table"):
        """Initialize mock DynamoDB table.
        
        Args:
            table_name: Name of the mock table
        """
        self.table_name = table_name
        self.items: Dict[str, Dict] = {}
        self.scan_results: List[Dict] = []
    
    def put_item(self, Item: Dict[str, Any]) -> Dict[str, Any]:
        """Mock put_item method."""
        key = self._get_key(Item)
        self.items[key] = Item
        return {}
    
    def get_item(self, Key: Dict[str, Any]) -> Dict[str, Any]:
        """Mock get_item method."""
        key = self._get_key(Key)
        item = self.items.get(key)
        return {"Item": item} if item else {}
    
    def query(
        self,
        KeyConditionExpression: Any,
        **kwargs
    ) -> Dict[str, Any]:
        """Mock query method."""
        return {"Items": list(self.items.values()), "Count": len(self.items)}
    
    def scan(self, **kwargs) -> Dict[str, Any]:
        """Mock scan method."""
        return {"Items": self.scan_results or list(self.items.values()), "Count": 0}
    
    def delete_item(self, Key: Dict[str, Any]) -> Dict[str, Any]:
        """Mock delete_item method."""
        key = self._get_key(Key)
        if key in self.items:
            del self.items[key]
        return {}
    
    def update_item(
        self,
        Key: Dict[str, Any],
        UpdateExpression: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Mock update_item method."""
        key = self._get_key(Key)
        if key in self.items:
            # Simple mock - just return success
            pass
        return {}
    
    def _get_key(self, item: Dict) -> str:
        """Generate key string from item."""
        # Simple key generation for mocking
        return str(sorted(item.items()))


class MockS3:
    """Mock S3 bucket."""
    
    def __init__(self, bucket_name: str = "mock_bucket"):
        """Initialize mock S3 bucket.
        
        Args:
            bucket_name: Name of the mock bucket
        """
        self.bucket_name = bucket_name
        self.objects: Dict[str, bytes] = {}
    
    def put_object(
        self,
        Bucket: str,
        Key: str,
        Body: bytes,
        **kwargs
    ) -> Dict[str, Any]:
        """Mock put_object method."""
        if isinstance(Body, str):
            Body = Body.encode()
        self.objects[Key] = Body
        return {"ETag": '"mock_etag"'}
    
    def get_object(self, Bucket: str, Key: str) -> Dict[str, Any]:
        """Mock get_object method."""
        if Key not in self.objects:
            raise Exception("NoSuchKey")
        
        import io
        return {
            "Body": io.BytesIO(self.objects[Key]),
            "ContentLength": len(self.objects[Key]),
            "ETag": '"mock_etag"'
        }
    
    def delete_object(self, Bucket: str, Key: str) -> Dict[str, Any]:
        """Mock delete_object method."""
        if Key in self.objects:
            del self.objects[Key]
        return {}
    
    def list_objects_v2(self, Bucket: str, **kwargs) -> Dict[str, Any]:
        """Mock list_objects_v2 method."""
        prefix = kwargs.get("Prefix", "")
        contents = [
            {"Key": key, "Size": len(data)}
            for key, data in self.objects.items()
            if key.startswith(prefix)
        ]
        return {"Contents": contents, "KeyCount": len(contents)}
