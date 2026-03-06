"""AWS STS credential management for octopOS.

Handles AWS authentication including:
- Profile-based credentials (local development)
- Direct credentials (access key/secret)
- STS assume role
- IAM role detection (EC2, ECS, Lambda)
"""

import os
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional
from urllib.request import urlopen, Request
from urllib.error import URLError

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError, NoCredentialsError

from src.utils.config import get_config
from src.utils.logger import get_logger

logger = get_logger()


class EnvironmentType(str, Enum):
    """Types of execution environments."""
    LOCAL = "local"
    EC2 = "ec2"
    ECS = "ecs"
    LAMBDA = "lambda"
    CLOUD9 = "cloud9"
    UNKNOWN = "unknown"


@dataclass
class AWSCredentials:
    """AWS credentials container."""
    access_key_id: str
    secret_access_key: str
    session_token: Optional[str] = None
    region: str = "us-east-1"
    expiration: Optional[str] = None


class AWSAuthManager:
    """Manages AWS authentication and credential handling.
    
    Automatically detects execution environment and uses appropriate
    credential source. Supports local development, EC2, ECS, and Lambda.
    """
    
    def __init__(self) -> None:
        """Initialize AWS auth manager."""
        self.config = get_config()
        self._credentials: Optional[AWSCredentials] = None
        self._bedrock_client: Optional[boto3.client] = None
        self._environment: Optional[EnvironmentType] = None
    
    def detect_environment(self) -> EnvironmentType:
        """Detect the current execution environment.
        
        Checks for:
        1. Lambda (AWS_EXECUTION_ENV, AWS_LAMBDA_FUNCTION_NAME)
        2. ECS (AWS_CONTAINER_CREDENTIALS_RELATIVE_URI)
        3. EC2 (IMDS available)
        4. Cloud9 (C9_PROJECT, C9_PID)
        
        Returns:
            Detected environment type
        """
        if self._environment:
            return self._environment
        
        # Check Lambda
        if os.getenv('AWS_LAMBDA_FUNCTION_NAME') or \
           (os.getenv('AWS_EXECUTION_ENV') and 'Lambda' in os.getenv('AWS_EXECUTION_ENV', '')):
            self._environment = EnvironmentType.LAMBDA
            logger.info("Detected Lambda environment")
            return self._environment
        
        # Check ECS
        if os.getenv('AWS_CONTAINER_CREDENTIALS_RELATIVE_URI'):
            self._environment = EnvironmentType.ECS
            logger.info("Detected ECS environment")
            return self._environment
        
        # Check Cloud9
        if os.getenv('C9_PROJECT') or os.getenv('C9_PID'):
            self._environment = EnvironmentType.CLOUD9
            logger.info("Detected Cloud9 environment")
            return self._environment
        
        # Check EC2 via IMDS
        try:
            # IMDSv2 - need to get token first
            token_req = Request(
                'http://169.254.169.254/latest/api/token',
                method='PUT',
                headers={'X-aws-ec2-metadata-token-ttl-seconds': '60'}
            )
            with urlopen(token_req, timeout=2) as response:
                token = response.read().decode('utf-8')
            
            # Use token to check instance metadata
            metadata_req = Request(
                'http://169.254.169.254/latest/meta-data/instance-id',
                headers={'X-aws-ec2-metadata-token': token}
            )
            with urlopen(metadata_req, timeout=2) as response:
                response.read()
            
            self._environment = EnvironmentType.EC2
            logger.info("Detected EC2 environment")
            return self._environment
        except (URLError, TimeoutError):
            pass
        
        self._environment = EnvironmentType.LOCAL
        logger.info("Detected local environment")
        return self._environment
    
    def _is_credentials_expiring(self) -> bool:
        """Check if current credentials are about to expire.
        
        Returns:
            True if credentials are expiring within 5 minutes
        """
        if not self._credentials:
            return True
        
        # Check if using temporary credentials with expiration
        if not self._credentials.expiration:
            return False  # Long-term credentials don't expire
        
        # Refresh if expiring within 5 minutes
        from datetime import datetime, timezone as tz
        try:
            exp_time = datetime.fromisoformat(self._credentials.expiration)
            now = datetime.now(tz.utc)
            # Convert exp_time to timezone-aware if needed
            if exp_time.tzinfo is None:
                exp_time = exp_time.replace(tzinfo=tz.utc)
            return (exp_time - now).total_seconds() < 300
        except (ValueError, TypeError):
            return True  # If we can't parse, assume expiring
    
    def get_credentials(self) -> AWSCredentials:
        """Get AWS credentials using appropriate method for environment.
        
        Priority:
        1. STS assume role (if role_arn configured)
        2. Profile credentials (if profile configured)
        3. Direct credentials (if access keys configured)
        4. Environment-specific (IMDS for EC2, container creds for ECS, etc.)
        
        Returns:
            AWSCredentials object
            
        Raises:
            NoCredentialsError: If no valid credentials found
        """
        # Check if we need to refresh expired credentials
        if self._credentials and self._is_credentials_expiring():
            logger.info("Credentials expiring or expired, refreshing...")
            self.refresh_credentials()
        
        if self._credentials:
            return self._credentials
        
        env = self.detect_environment()
        
        # Try STS assume role first
        if self.config.aws.role_arn:
            self._credentials = self._assume_role()
            if self._credentials:
                logger.info("Using STS assumed role credentials")
                return self._credentials
        
        # Try profile credentials (local development)
        if self.config.aws.profile and env == EnvironmentType.LOCAL:
            self._credentials = self._get_profile_credentials()
            if self._credentials:
                logger.info(f"Using profile credentials: {self.config.aws.profile}")
                return self._credentials
        
        # Try direct credentials
        if self.config.aws.access_key_id and self.config.aws.secret_access_key:
            self._credentials = AWSCredentials(
                access_key_id=self.config.aws.access_key_id,
                secret_access_key=self.config.aws.secret_access_key,
                session_token=self.config.aws.session_token,
                region=self.config.aws.region
            )
            logger.info("Using direct credentials")
            return self._credentials
        
        # Try default boto3 credential chain
        try:
            session = boto3.Session(region_name=self.config.aws.region)
            creds = session.get_credentials()
            if creds:
                frozen_creds = creds.get_frozen_credentials()
                self._credentials = AWSCredentials(
                    access_key_id=frozen_creds.access_key,
                    secret_access_key=frozen_creds.secret_key,
                    session_token=frozen_creds.token,
                    region=self.config.aws.region
                )
                logger.info("Using default boto3 credential chain")
                return self._credentials
        except Exception as e:
            logger.error(f"Failed to get credentials from boto3: {e}")
        
        raise NoCredentialsError(
            "No valid AWS credentials found. "
            "Please configure via environment variables, profile, or IAM role."
        )
    
    def _assume_role(self) -> Optional[AWSCredentials]:
        """Assume an IAM role using STS.
        
        Returns:
            AWSCredentials if successful, None otherwise
        """
        try:
            sts = boto3.client('sts')
            response = sts.assume_role(
                RoleArn=self.config.aws.role_arn,
                RoleSessionName=self.config.aws.role_session_name,
                DurationSeconds=3600
            )
            
            creds = response['Credentials']
            return AWSCredentials(
                access_key_id=creds['AccessKeyId'],
                secret_access_key=creds['SecretAccessKey'],
                session_token=creds['SessionToken'],
                region=self.config.aws.region,
                expiration=creds['Expiration'].isoformat()
            )
        except ClientError as e:
            logger.error(f"Failed to assume role: {e}")
            return None
    
    def _get_profile_credentials(self) -> Optional[AWSCredentials]:
        """Get credentials from AWS profile.
        
        Returns:
            AWSCredentials if successful, None otherwise
        """
        try:
            session = boto3.Session(
                profile_name=self.config.aws.profile,
                region_name=self.config.aws.region
            )
            creds = session.get_credentials()
            if creds:
                frozen_creds = creds.get_frozen_credentials()
                return AWSCredentials(
                    access_key_id=frozen_creds.access_key,
                    secret_access_key=frozen_creds.secret_key,
                    session_token=frozen_creds.token,
                    region=self.config.aws.region
                )
        except Exception as e:
            logger.error(f"Failed to get profile credentials: {e}")
        return None
    
    def get_bedrock_client(self) -> boto3.client:
        """Get or create Bedrock client with proper credentials.
        
        Returns:
            Configured boto3 Bedrock client
        """
        if self._bedrock_client:
            return self._bedrock_client
        
        # Get credentials
        creds = self.get_credentials()
        
        # Create boto3 config with retries
        boto_config = BotoConfig(
            retries={'max_attempts': 3, 'mode': 'adaptive'},
            connect_timeout=10,
            read_timeout=30
        )
        
        # Create client
        self._bedrock_client = boto3.client(
            'bedrock-runtime',
            region_name=creds.region,
            aws_access_key_id=creds.access_key_id,
            aws_secret_access_key=creds.secret_access_key,
            aws_session_token=creds.session_token,
            config=boto_config
        )
        
        logger.info(f"Created Bedrock client for region: {creds.region}")
        return self._bedrock_client
    
    def get_bedrock_agent_client(self) -> boto3.client:
        """Get or create Bedrock Agent client.
        
        Returns:
            Configured boto3 Bedrock Agent client
        """
        creds = self.get_credentials()
        
        return boto3.client(
            'bedrock-agent-runtime',
            region_name=creds.region,
            aws_access_key_id=creds.access_key_id,
            aws_secret_access_key=creds.secret_access_key,
            aws_session_token=creds.session_token
        )
    
    def refresh_credentials(self) -> None:
        """Force refresh of credentials."""
        self._credentials = None
        self._bedrock_client = None
        logger.info("Credentials refreshed")
    
    def validate_credentials(self) -> bool:
        """Validate that current credentials are valid.
        
        Returns:
            True if credentials are valid, False otherwise
        """
        try:
            creds = self.get_credentials()
            # Try to use STS GetCallerIdentity to validate
            sts = boto3.client(
                'sts',
                region_name=creds.region,
                aws_access_key_id=creds.access_key_id,
                aws_secret_access_key=creds.secret_access_key,
                aws_session_token=creds.session_token
            )
            sts.get_caller_identity()
            return True
        except Exception as e:
            logger.error(f"Credential validation failed: {e}")
            return False


# Global auth manager instance
_auth_manager: Optional[AWSAuthManager] = None


def get_auth_manager() -> AWSAuthManager:
    """Get the global AWS auth manager instance.
    
    Returns:
        Singleton AWSAuthManager instance
    """
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = AWSAuthManager()
    return _auth_manager


def get_bedrock_client() -> boto3.client:
    """Convenience function to get Bedrock client.
    
    Returns:
        Configured Bedrock client
    """
    return get_auth_manager().get_bedrock_client()


def detect_aws_environment() -> EnvironmentType:
    """Convenience function to detect environment.
    
    Returns:
        Detected environment type
    """
    return get_auth_manager().detect_environment()
