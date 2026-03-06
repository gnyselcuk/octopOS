"""AWS EventBridge Integration - Serverless cron for cloud deployments."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
import json

import boto3
from botocore.exceptions import ClientError

from src.utils.config import get_config
from src.utils.logger import get_logger

logger = get_logger()


@dataclass
class ScheduledRule:
    """An EventBridge scheduled rule."""
    
    name: str
    schedule_expression: str
    target_arn: str
    target_input: Optional[Dict[str, Any]] = None
    state: str = "ENABLED"
    description: Optional[str] = None


class EventBridgeScheduler:
    """AWS EventBridge scheduler for serverless cron jobs.
    
    Manages scheduled tasks using AWS EventBridge rules.
    Supports both cloud (EventBridge) and local (APScheduler) modes.
    """
    
    def __init__(self, use_eventbridge: bool = True, region: Optional[str] = None):
        """Initialize EventBridge scheduler.
        
        Args:
            use_eventbridge: True for EventBridge, False for local scheduler
            region: AWS region
        """
        self._use_eventbridge = use_eventbridge
        self._config = get_config()
        self._region = region or self._config.aws.region
        
        self._client = None
        if use_eventbridge:
            try:
                self._client = boto3.client('events', region_name=self._region)
                logger.info(f"EventBridge scheduler initialized for {self._region}")
            except Exception as e:
                logger.warning(f"Failed to initialize EventBridge: {e}. Using local mode.")
                self._use_eventbridge = False
        
        self._rules: Dict[str, ScheduledRule] = {}
    
    async def create_scheduled_rule(
        self,
        name: str,
        schedule_expression: str,  # e.g., "rate(5 minutes)" or "cron(0 12 * * ? *)"
        target_lambda_arn: str,
        target_input: Optional[Dict[str, Any]] = None,
        description: Optional[str] = None
    ) -> bool:
        """Create a scheduled rule.
        
        Args:
            name: Rule name
            schedule_expression: EventBridge schedule expression
            target_lambda_arn: Lambda function ARN to invoke
            target_input: Input payload for Lambda
            description: Rule description
            
        Returns:
            True if created successfully
        """
        if not self._use_eventbridge or not self._client:
            logger.info(f"[Local Mode] Would create rule: {name} - {schedule_expression}")
            self._rules[name] = ScheduledRule(
                name=name,
                schedule_expression=schedule_expression,
                target_arn=target_lambda_arn,
                target_input=target_input,
                description=description
            )
            return True
        
        try:
            # Create rule
            rule_response = self._client.put_rule(
                Name=name,
                ScheduleExpression=schedule_expression,
                State='ENABLED',
                Description=description or f"Scheduled rule for {name}"
            )
            
            # Add target
            target = {
                'Id': '1',
                'Arn': target_lambda_arn
            }
            
            if target_input:
                target['Input'] = json.dumps(target_input)
            
            self._client.put_targets(
                Rule=name,
                Targets=[target]
            )
            
            # Add permission for EventBridge to invoke Lambda
            try:
                lambda_client = boto3.client('lambda', region_name=self._region)
                lambda_client.add_permission(
                    FunctionName=target_lambda_arn,
                    StatementId=f'EventBridge-{name}',
                    Action='lambda:InvokeFunction',
                    Principal='events.amazonaws.com',
                    SourceArn=rule_response['RuleArn']
                )
            except ClientError as e:
                if e.response['Error']['Code'] != 'ResourceConflictException':
                    raise
            
            self._rules[name] = ScheduledRule(
                name=name,
                schedule_expression=schedule_expression,
                target_arn=target_lambda_arn,
                target_input=target_input,
                description=description
            )
            
            logger.info(f"Created EventBridge rule: {name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create rule {name}: {e}")
            return False
    
    async def delete_rule(self, name: str) -> bool:
        """Delete a scheduled rule.
        
        Args:
            name: Rule name to delete
            
        Returns:
            True if deleted successfully
        """
        if not self._use_eventbridge or not self._client:
            self._rules.pop(name, None)
            logger.info(f"[Local Mode] Deleted rule: {name}")
            return True
        
        try:
            # Remove targets first
            self._client.remove_targets(
                Rule=name,
                Ids=['1']
            )
            
            # Delete rule
            self._client.delete_rule(Name=name)
            
            self._rules.pop(name, None)
            
            logger.info(f"Deleted EventBridge rule: {name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete rule {name}: {e}")
            return False
    
    def list_rules(self) -> List[Dict[str, Any]]:
        """List all scheduled rules.
        
        Returns:
            List of rule dictionaries
        """
        if not self._use_eventbridge or not self._client:
            return [
                {
                    "Name": rule.name,
                    "ScheduleExpression": rule.schedule_expression,
                    "State": rule.state
                }
                for rule in self._rules.values()
            ]
        
        try:
            response = self._client.list_rules()
            return response.get('Rules', [])
        except Exception as e:
            logger.error(f"Failed to list rules: {e}")
            return []
    
    def enable_rule(self, name: str) -> bool:
        """Enable a rule.
        
        Args:
            name: Rule name
            
        Returns:
            True if enabled
        """
        if not self._use_eventbridge or not self._client:
            if name in self._rules:
                self._rules[name].state = "ENABLED"
            return True
        
        try:
            self._client.enable_rule(Name=name)
            return True
        except Exception as e:
            logger.error(f"Failed to enable rule {name}: {e}")
            return False
    
    def disable_rule(self, name: str) -> bool:
        """Disable a rule.
        
        Args:
            name: Rule name
            
        Returns:
            True if disabled
        """
        if not self._use_eventbridge or not self._client:
            if name in self._rules:
                self._rules[name].state = "DISABLED"
            return True
        
        try:
            self._client.disable_rule(Name=name)
            return True
        except Exception as e:
            logger.error(f"Failed to disable rule {name}: {e}")
            return False
