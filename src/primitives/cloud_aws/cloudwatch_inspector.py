"""CloudWatch Inspector - AWS CloudWatch log and metric analysis primitive.

Provides CloudWatch operations for log analysis, anomaly detection, and monitoring.

Example:
    >>> from src.primitives.cloud_aws.cloudwatch_inspector import CloudWatchInspector
    >>> inspector = CloudWatchInspector()
    >>> result = await inspector.execute(
    ...     operation="search_logs",
    ...     log_group="/aws/lambda/my-function",
    ...     pattern="ERROR",
    ...     hours=24
    ... )
"""

import re
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

from src.primitives.base_primitive import BasePrimitive, PrimitiveResult, register_primitive
from src.utils.aws_sts import get_auth_manager
from src.utils.logger import get_logger

logger = get_logger()


class CloudWatchOperation(str, Enum):
    """CloudWatch operation types."""
    SEARCH_LOGS = "search_logs"
    GET_METRIC = "get_metric"
    LIST_LOG_GROUPS = "list_log_groups"
    DESCRIBE_ALARMS = "describe_alarms"
    FILTER_LOGS = "filter_logs"
    ANALYZE_PATTERNS = "analyze_patterns"


class CloudWatchInspector(BasePrimitive):
    """Inspect and analyze CloudWatch logs and metrics.
    
    Provides CloudWatch monitoring capabilities:
    - Log group searching and filtering
    - Metric retrieval and analysis
    - Pattern matching for anomaly detection
    - Alarm status checking
    - Integration with Self-Healing Agent
    """
    
    def __init__(self) -> None:
        """Initialize CloudWatch Inspector."""
        super().__init__()
        self._logs_client = None
        self._monitoring_client = None
    
    @property
    def name(self) -> str:
        return "cloudwatch_inspect"
    
    @property
    def description(self) -> str:
        return (
            "Analyze AWS CloudWatch logs and metrics. "
            "Search logs, filter by patterns, retrieve metrics, "
            "and detect anomalies for system monitoring."
        )
    
    @property
    def parameters(self) -> Dict[str, Dict[str, Any]]:
        return {
            "operation": {
                "type": "string",
                "description": "CloudWatch operation type",
                "required": True,
                "enum": [op.value for op in CloudWatchOperation]
            },
            "log_group": {
                "type": "string",
                "description": "CloudWatch log group name",
                "required": False
            },
            "pattern": {
                "type": "string",
                "description": "Search pattern or filter pattern",
                "required": False
            },
            "hours": {
                "type": "integer",
                "description": "Hours back to search (default: 24)",
                "required": False,
                "default": 24
            },
            "limit": {
                "type": "integer",
                "description": "Maximum results to return",
                "required": False,
                "default": 100
            },
            "namespace": {
                "type": "string",
                "description": "Metric namespace",
                "required": False
            },
            "metric_name": {
                "type": "string",
                "description": "Metric name",
                "required": False
            },
            "dimensions": {
                "type": "object",
                "description": "Metric dimensions",
                "required": False
            },
            "region": {
                "type": "string",
                "description": "AWS region",
                "required": False
            },
            "statistic": {
                "type": "string",
                "description": "Statistic type (Average, Sum, Min, Max)",
                "required": False,
                "default": "Average"
            }
        }
    
    def _get_logs_client(self, region: Optional[str] = None):
        """Get or create CloudWatch Logs client."""
        if self._logs_client is None:
            auth_manager = get_auth_manager()
            creds = auth_manager.get_credentials()
            
            self._logs_client = boto3.client(
                'logs',
                region_name=region or creds.region,
                aws_access_key_id=creds.access_key_id,
                aws_secret_access_key=creds.secret_access_key,
                aws_session_token=creds.session_token
            )
        return self._logs_client
    
    def _get_monitoring_client(self, region: Optional[str] = None):
        """Get or create CloudWatch Monitoring client."""
        if self._monitoring_client is None:
            auth_manager = get_auth_manager()
            creds = auth_manager.get_credentials()
            
            self._monitoring_client = boto3.client(
                'cloudwatch',
                region_name=region or creds.region,
                aws_access_key_id=creds.access_key_id,
                aws_secret_access_key=creds.secret_access_key,
                aws_session_token=creds.session_token
            )
        return self._monitoring_client
    
    async def execute(self, **kwargs) -> PrimitiveResult:
        """Execute CloudWatch operation.
        
        Args:
            operation: CloudWatchOperation type
            log_group: Log group name
            pattern: Search/filter pattern
            hours: Hours to look back
            limit: Max results
            namespace: Metric namespace
            metric_name: Metric name
            dimensions: Metric dimensions
            region: AWS region
            statistic: Metric statistic
            
        Returns:
            PrimitiveResult with operation results
        """
        operation_str = kwargs.get("operation", "")
        
        try:
            operation = CloudWatchOperation(operation_str)
        except ValueError:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Invalid operation: {operation_str}",
                error="InvalidOperation"
            )
        
        try:
            if operation == CloudWatchOperation.SEARCH_LOGS:
                return await self._search_logs(kwargs)
            elif operation == CloudWatchOperation.FILTER_LOGS:
                return await self._filter_logs(kwargs)
            elif operation == CloudWatchOperation.GET_METRIC:
                return await self._get_metric(kwargs)
            elif operation == CloudWatchOperation.LIST_LOG_GROUPS:
                return await self._list_log_groups(kwargs)
            elif operation == CloudWatchOperation.DESCRIBE_ALARMS:
                return await self._describe_alarms(kwargs)
            elif operation == CloudWatchOperation.ANALYZE_PATTERNS:
                return await self._analyze_patterns(kwargs)
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
            logger.error(f"CloudWatch error ({error_code}): {error_msg}")
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"CloudWatch error: {error_msg}",
                error=error_code
            )
        except Exception as e:
            logger.error(f"CloudWatch operation error: {e}")
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Operation failed: {e}",
                error=str(e)
            )
    
    async def _search_logs(self, kwargs: Dict) -> PrimitiveResult:
        """Simple text search in logs (simplified filter)."""
        log_group = kwargs.get("log_group")
        pattern = kwargs.get("pattern", "")
        hours = kwargs.get("hours", 24)
        limit = kwargs.get("limit", 100)
        region = kwargs.get("region")
        
        if not log_group:
            return PrimitiveResult(
                success=False,
                data=None,
                message="Missing required parameter: log_group",
                error="MissingParameters"
            )
        
        client = self._get_logs_client(region)
        
        # Calculate time range
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)
        
        # Convert to milliseconds
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)
        
        # Build filter pattern (simple text match)
        filter_pattern = f'"{pattern}"' if pattern else None
        
        matches = []
        next_token = None
        
        while len(matches) < limit:
            query_kwargs = {
                'logGroupName': log_group,
                'startTime': start_ms,
                'endTime': end_ms,
                'limit': min(limit - len(matches), 100)  # Max 100 per request
            }
            
            if filter_pattern:
                query_kwargs['filterPattern'] = filter_pattern
            if next_token:
                query_kwargs['nextToken'] = next_token
            
            response = client.filter_log_events(**query_kwargs)
            
            for event in response.get('events', []):
                matches.append({
                    "timestamp": datetime.fromtimestamp(event['timestamp'] / 1000).isoformat(),
                    "message": event['message'],
                    "log_stream": event['logStreamName'],
                    "event_id": event.get('eventId', '')
                })
                
                if len(matches) >= limit:
                    break
            
            next_token = response.get('nextToken')
            if not next_token:
                break
        
        return PrimitiveResult(
            success=True,
            data={
                "log_group": log_group,
                "pattern": pattern,
                "hours": hours,
                "matches": matches,
                "count": len(matches)
            },
            message=f"Found {len(matches)} log entries matching '{pattern}' in {log_group}"
        )
    
    async def _filter_logs(self, kwargs: Dict) -> PrimitiveResult:
        """Filter logs using CloudWatch filter patterns."""
        log_group = kwargs.get("log_group")
        pattern = kwargs.get("pattern")
        hours = kwargs.get("hours", 24)
        limit = kwargs.get("limit", 100)
        region = kwargs.get("region")
        
        if not log_group:
            return PrimitiveResult(
                success=False,
                data=None,
                message="Missing required parameter: log_group",
                error="MissingParameters"
            )
        
        client = self._get_logs_client(region)
        
        # Calculate time range
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)
        
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)
        
        matches = []
        next_token = None
        
        while len(matches) < limit:
            query_kwargs = {
                'logGroupName': log_group,
                'startTime': start_ms,
                'endTime': end_ms,
                'limit': min(limit - len(matches), 100)
            }
            
            if pattern:
                query_kwargs['filterPattern'] = pattern
            if next_token:
                query_kwargs['nextToken'] = next_token
            
            response = client.filter_log_events(**query_kwargs)
            
            for event in response.get('events', []):
                matches.append({
                    "timestamp": datetime.fromtimestamp(event['timestamp'] / 1000).isoformat(),
                    "message": event['message'],
                    "log_stream": event['logStreamName'],
                    "ingestion_time": datetime.fromtimestamp(event['ingestionTime'] / 1000).isoformat() if 'ingestionTime' in event else None
                })
                
                if len(matches) >= limit:
                    break
            
            next_token = response.get('nextToken')
            if not next_token:
                break
        
        return PrimitiveResult(
            success=True,
            data={
                "log_group": log_group,
                "filter_pattern": pattern,
                "hours": hours,
                "matches": matches,
                "count": len(matches)
            },
            message=f"Filtered {len(matches)} log entries from {log_group}"
        )
    
    async def _get_metric(self, kwargs: Dict) -> PrimitiveResult:
        """Retrieve CloudWatch metric data."""
        namespace = kwargs.get("namespace")
        metric_name = kwargs.get("metric_name")
        dimensions = kwargs.get("dimensions", {})
        hours = kwargs.get("hours", 24)
        statistic = kwargs.get("statistic", "Average")
        region = kwargs.get("region")
        
        if not namespace or not metric_name:
            return PrimitiveResult(
                success=False,
                data=None,
                message="Missing required parameters: namespace, metric_name",
                error="MissingParameters"
            )
        
        client = self._get_monitoring_client(region)
        
        # Calculate time range
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)
        
        # Build dimensions
        metric_dimensions = [
            {'Name': k, 'Value': v}
            for k, v in dimensions.items()
        ]
        
        response = client.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric_name,
            Dimensions=metric_dimensions,
            StartTime=start_time,
            EndTime=end_time,
            Period=300,  # 5 minute periods
            Statistics=[statistic]
        )
        
        datapoints = response.get('Datapoints', [])
        
        # Sort by timestamp
        datapoints.sort(key=lambda x: x['Timestamp'])
        
        return PrimitiveResult(
            success=True,
            data={
                "namespace": namespace,
                "metric_name": metric_name,
                "dimensions": dimensions,
                "statistic": statistic,
                "hours": hours,
                "datapoints": [
                    {
                        "timestamp": dp['Timestamp'].isoformat(),
                        "value": dp.get(statistic, 0),
                        "unit": dp.get('Unit', 'None')
                    }
                    for dp in datapoints
                ],
                "count": len(datapoints)
            },
            message=f"Retrieved {len(datapoints)} datapoints for {metric_name}"
        )
    
    async def _list_log_groups(self, kwargs: Dict) -> PrimitiveResult:
        """List CloudWatch log groups."""
        limit = kwargs.get("limit", 100)
        region = kwargs.get("region")
        pattern = kwargs.get("pattern")
        
        client = self._get_logs_client(region)
        
        log_groups = []
        next_token = None
        
        while len(log_groups) < limit:
            query_kwargs = {'limit': min(limit - len(log_groups), 50)}
            if next_token:
                query_kwargs['nextToken'] = next_token
            
            response = client.describe_log_groups(**query_kwargs)
            
            for group in response.get('logGroups', []):
                name = group['logGroupName']
                
                # Filter by pattern if provided
                if pattern and pattern not in name:
                    continue
                
                log_groups.append({
                    "name": name,
                    "stored_bytes": group.get('storedBytes', 0),
                    "creation_time": datetime.fromtimestamp(group['creationTime'] / 1000).isoformat() if 'creationTime' in group else None,
                    "retention_days": group.get('retentionInDays')
                })
                
                if len(log_groups) >= limit:
                    break
            
            next_token = response.get('nextToken')
            if not next_token:
                break
        
        return PrimitiveResult(
            success=True,
            data={
                "log_groups": log_groups,
                "count": len(log_groups)
            },
            message=f"Listed {len(log_groups)} log groups"
        )
    
    async def _describe_alarms(self, kwargs: Dict) -> PrimitiveResult:
        """Describe CloudWatch alarms."""
        limit = kwargs.get("limit", 100)
        region = kwargs.get("region")
        
        client = self._get_monitoring_client(region)
        
        response = client.describe_alarms(MaxRecords=limit)
        
        alarms = []
        for alarm in response.get('MetricAlarms', []):
            alarms.append({
                "name": alarm['AlarmName'],
                "state": alarm['StateValue'],
                "metric": alarm.get('MetricName'),
                "namespace": alarm.get('Namespace'),
                "threshold": alarm.get('Threshold'),
                "comparison": alarm.get('ComparisonOperator')
            })
        
        return PrimitiveResult(
            success=True,
            data={
                "alarms": alarms,
                "count": len(alarms)
            },
            message=f"Described {len(alarms)} alarms"
        )
    
    async def _analyze_patterns(self, kwargs: Dict) -> PrimitiveResult:
        """Analyze log patterns for anomalies."""
        log_group = kwargs.get("log_group")
        hours = kwargs.get("hours", 24)
        region = kwargs.get("region")
        
        if not log_group:
            return PrimitiveResult(
                success=False,
                data=None,
                message="Missing required parameter: log_group",
                error="MissingParameters"
            )
        
        client = self._get_logs_client(region)
        
        # Get insights query results
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)
        
        # Common error patterns to search for
        error_patterns = [
            ('ERROR', 'Error messages'),
            ('Exception', 'Exceptions'),
            ('Traceback', 'Python tracebacks'),
            ('FAIL', 'Failure messages'),
            ('timeout', 'Timeouts'),
            ('Connection refused', 'Connection errors'),
        ]
        
        analysis = {
            "log_group": log_group,
            "time_range_hours": hours,
            "patterns_found": {}
        }
        
        for pattern, description in error_patterns:
            try:
                result = await self._search_logs({
                    "log_group": log_group,
                    "pattern": pattern,
                    "hours": hours,
                    "limit": 100,
                    "region": region
                })
                
                if result.success:
                    count = len(result.data.get("matches", []))
                    if count > 0:
                        analysis["patterns_found"][description] = count
                        
            except Exception as e:
                logger.debug(f"Pattern search failed for {pattern}: {e}")
        
        total_errors = sum(analysis["patterns_found"].values())
        analysis["total_issues_found"] = total_errors
        
        return PrimitiveResult(
            success=True,
            data=analysis,
            message=f"Analysis complete. Found {total_errors} potential issues in {log_group}"
        )


def register_all() -> None:
    """Register CloudWatch primitives."""
    register_primitive(CloudWatchInspector())
