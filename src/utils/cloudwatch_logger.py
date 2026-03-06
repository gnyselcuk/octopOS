"""CloudWatch Integration - AWS CloudWatch monitoring and logging."""

from typing import Any, Dict, List, Optional
from datetime import datetime
import boto3
from botocore.exceptions import ClientError

from src.utils.config import get_config
from src.utils.logger import get_logger

logger = get_logger()


class CloudWatchLogger:
    """AWS CloudWatch logging and metrics integration.
    
    Provides CloudWatch Logs integration, custom metrics, and anomaly detection.
    """
    
    def __init__(self, log_group: str = "octopos", region: Optional[str] = None):
        """Initialize CloudWatch logger.
        
        Args:
            log_group: CloudWatch log group name
            region: AWS region
        """
        self._config = get_config()
        self._region = region or self._config.aws.region
        self._log_group = log_group
        self._log_stream = f"agents-{datetime.now().astimezone().strftime('%Y-%m-%d')}"
        
        self._logs_client = None
        self._cloudwatch_client = None
        
        try:
            self._logs_client = boto3.client('logs', region_name=self._region)
            self._cloudwatch_client = boto3.client('cloudwatch', region_name=self._region)
            self._ensure_log_group()
            logger.info(f"CloudWatch logger initialized: {log_group}")
        except Exception as e:
            logger.warning(f"Failed to initialize CloudWatch: {e}")
    
    def _ensure_log_group(self):
        """Ensure log group exists."""
        if not self._logs_client:
            return
        try:
            self._logs_client.create_log_group(logGroupName=self._log_group)
        except ClientError as e:
            if e.response['Error']['Code'] != 'ResourceAlreadyExistsException':
                raise
    
    def log_message(self, message: str, level: str = "INFO", **kwargs) -> bool:
        """Log a message to CloudWatch.
        
        Args:
            message: Log message
            level: Log level
            **kwargs: Additional fields
            
        Returns:
            True if logged successfully
        """
        if not self._logs_client:
            return False
        
        try:
            from datetime import timezone
            timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
            log_event = {
                'timestamp': timestamp,
                'message': f"[{level}] {message} | {kwargs}"
            }
            
            self._logs_client.put_log_events(
                logGroupName=self._log_group,
                logStreamName=self._log_stream,
                logEvents=[log_event]
            )
            return True
        except Exception as e:
            logger.error(f"Failed to log to CloudWatch: {e}")
            return False
    
    def put_metric(
        self,
        metric_name: str,
        value: float,
        unit: str = "Count",
        dimensions: Optional[Dict[str, str]] = None
    ) -> bool:
        """Put a custom metric to CloudWatch.
        
        Args:
            metric_name: Metric name
            value: Metric value
            unit: Metric unit
            dimensions: Metric dimensions
            
        Returns:
            True if successful
        """
        if not self._cloudwatch_client:
            return False
        
        try:
            metric_data = {
                'MetricName': metric_name,
                'Value': value,
                'Unit': unit,
                'Timestamp': datetime.now(timezone.utc)
            }
            
            if dimensions:
                metric_data['Dimensions'] = [
                    {'Name': k, 'Value': v}
                    for k, v in dimensions.items()
                ]
            
            self._cloudwatch_client.put_metric_data(
                Namespace='octopos',
                MetricData=[metric_data]
            )
            return True
        except Exception as e:
            logger.error(f"Failed to put metric: {e}")
            return False
    
    def log_agent_metric(
        self,
        agent_name: str,
        metric_name: str,
        value: float
    ) -> bool:
        """Log an agent-specific metric.
        
        Args:
            agent_name: Agent name
            metric_name: Metric name
            value: Metric value
            
        Returns:
            True if successful
        """
        return self.put_metric(
            metric_name=f"{agent_name}_{metric_name}",
            value=value,
            dimensions={'Agent': agent_name}
        )
