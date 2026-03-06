"""Logging configuration for octopOS.

Provides structured logging with support for multiple destinations:
- stdout (default)
- file (with rotation)
- AWS CloudWatch

Features:
- JSON/text formatting
- Correlation ID tracking for distributed tracing
- Agent-specific context logging
- Automatic log rotation
- Sensitive data masking for security
"""

import json
import logging
import logging.handlers
import re
import sys
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Pattern

from pythonjsonlogger import jsonlogger

from src.utils.config import get_config, LogDestination


class SensitiveDataMasker:
    """Masks sensitive data in log messages using regex patterns.
    
    Efficiently masks sensitive patterns like API keys, passwords, tokens,
    AWS credentials, credit card numbers, and email addresses.
    
    The masker compiles regex patterns once and reuses them for performance.
    """
    
    # Default patterns for common sensitive data
    DEFAULT_PATTERNS: Dict[str, str] = {
        # OpenAI API keys (sk-...)
        'openai_api_key': r'sk-[a-zA-Z0-9]{20,}',
        # AWS Access Key IDs (AKIA...)
        'aws_access_key_id': r'AKIA[0-9A-Z]{16}',
        # AWS Secret Access Keys
        'aws_secret_key': r'aws_secret_access_key[\s]*[=:]+[\s]*["\']?[a-zA-Z0-9/+=]{40}["\']?',
        # Generic API keys
        'generic_api_key': r'(?:api[_-]?key|apikey)[\s]*[=:]+[\s]*["\']?[a-zA-Z0-9_-]{16,}["\']?',
        # Passwords
        'password': r'(?:password|passwd|pwd)[\s]*[=:]+[\s]*["\']?[^"\'\s]{8,}["\']?',
        # Bearer tokens
        'bearer_token': r'Bearer\s+[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+',
        # JWT tokens
        'jwt_token': r'eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*',
        # Credit card numbers (major card types)
        'credit_card': r'\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|3(?:0[0-5]|[68][0-9])[0-9]{11}|6(?:011|5[0-9]{2})[0-9]{12}|(?:2131|1800|35\d{3})\d{11})\b',
        # Email addresses (optional masking)
        'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        # Private keys
        'private_key': r'-----BEGIN (?:RSA |DSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |DSA |EC |OPENSSH )?PRIVATE KEY-----',
        # Database connection strings with passwords
        'db_connection': r'(?:mongodb|mysql|postgresql|postgres)://[^:\s]+:([^@\s]+)@[^/\s]+',
        # Slack tokens
        'slack_token': r'xox[baprs]-[0-9]{10,13}-[0-9]{10,13}[a-zA-Z0-9-]*',
        # GitHub tokens
        'github_token': r'gh[pousr]_[A-Za-z0-9_]{36,}',
    }
    
    def __init__(
        self,
        mask_character: str = '*',
        custom_patterns: Optional[List[str]] = None,
        enabled: bool = True
    ):
        """Initialize the sensitive data masker.
        
        Args:
            mask_character: Character to use for masking (default: '*')
            custom_patterns: Additional regex patterns to mask
            enabled: Whether masking is enabled
        """
        self.mask_character = mask_character
        self.enabled = enabled
        self._patterns: Dict[str, Pattern] = {}
        self._custom_patterns: List[str] = custom_patterns or []
        
        if self.enabled:
            self._compile_patterns()
    
    def _compile_patterns(self) -> None:
        """Compile all regex patterns for efficient reuse."""
        # Compile default patterns
        for name, pattern in self.DEFAULT_PATTERNS.items():
            try:
                self._patterns[name] = re.compile(pattern, re.IGNORECASE)
            except re.error as e:
                # Log pattern compilation errors but don't crash
                sys.stderr.write(f"Warning: Failed to compile pattern '{name}': {e}\n")
        
        # Compile custom patterns
        for i, pattern in enumerate(self._custom_patterns):
            try:
                self._patterns[f'custom_{i}'] = re.compile(pattern, re.IGNORECASE)
            except re.error as e:
                sys.stderr.write(f"Warning: Failed to compile custom pattern {i}: {e}\n")
    
    def mask(self, text: str) -> str:
        """Mask sensitive data in the given text.
        
        Args:
            text: Input text that may contain sensitive data
            
        Returns:
            Text with sensitive data masked
        """
        if not self.enabled or not text:
            return text
        
        result = text
        for name, pattern in self._patterns.items():
            try:
                if name == 'db_connection':
                    # Special handling for DB connection strings to preserve structure
                    result = pattern.sub(self._mask_db_password, result)
                elif name == 'email':
                    # Partial mask for emails: show first 2 chars and domain
                    result = pattern.sub(self._mask_email, result)
                else:
                    # Standard masking: replace with mask character
                    result = pattern.sub(self._mask_full, result)
            except Exception:
                # If a pattern fails, skip it and continue
                continue
        
        return result
    
    def _mask_full(self, match: re.Match) -> str:
        """Replace matched text entirely with mask characters.
        
        Preserves the length of the original text for debugging purposes.
        """
        matched_text = match.group(0)
        # Keep first 4 chars visible for identification, mask the rest
        if len(matched_text) > 8:
            return matched_text[:4] + self.mask_character * (len(matched_text) - 4)
        return self.mask_character * len(matched_text)
    
    def _mask_db_password(self, match: re.Match) -> str:
        """Mask only the password part of a database connection string."""
        full_match = match.group(0)
        password = match.group(1)
        masked_password = self.mask_character * min(len(password), 8)
        return full_match.replace(password, masked_password, 1)
    
    def _mask_email(self, match: re.Match) -> str:
        """Partially mask email addresses.
        
        Shows first 2 chars of local part and the domain.
        Example: john.doe@example.com -> jo***@example.com
        """
        email = match.group(0)
        local, domain = email.rsplit('@', 1)
        if len(local) <= 2:
            masked_local = local[0] + self.mask_character * (len(local) - 1) if len(local) > 1 else local
        else:
            masked_local = local[:2] + self.mask_character * (len(local) - 2)
        return f"{masked_local}@{domain}"
    
    def add_pattern(self, name: str, pattern: str) -> None:
        """Add a new pattern at runtime.
        
        Args:
            name: Name for the pattern
            pattern: Regex pattern string
        """
        try:
            self._patterns[name] = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern '{name}': {e}")
    
    def remove_pattern(self, name: str) -> bool:
        """Remove a pattern by name.
        
        Args:
            name: Name of the pattern to remove
            
        Returns:
            True if pattern was removed, False if not found
        """
        if name in self._patterns:
            del self._patterns[name]
            return True
        return False


# Global masker instance (lazy initialization)
_masker: Optional[SensitiveDataMasker] = None
_masker_lock = threading.Lock()


def get_masker() -> SensitiveDataMasker:
    """Get the global sensitive data masker instance.
    
    Returns:
        Configured SensitiveDataMasker instance
    """
    global _masker
    if _masker is None:
        with _masker_lock:
            if _masker is None:
                config = get_config()
                _masker = SensitiveDataMasker(
                    mask_character=config.logging.mask_character,
                    custom_patterns=config.logging.mask_custom_patterns,
                    enabled=config.logging.mask_sensitive_data
                )
    return _masker


def mask_sensitive_data(text: str) -> str:
    """Convenience function to mask sensitive data in text.
    
    Args:
        text: Input text that may contain sensitive data
        
    Returns:
        Text with sensitive data masked
    """
    return get_masker().mask(text)

# Thread-local storage for correlation ID
_local = threading.local()


def get_correlation_id() -> str:
    """Get the current correlation ID for distributed tracing.
    
    Returns:
        Current correlation ID or generates a new one if not set.
    """
    if not hasattr(_local, 'correlation_id'):
        _local.correlation_id = str(uuid.uuid4())
    return _local.correlation_id


def set_correlation_id(correlation_id: str) -> None:
    """Set the correlation ID for the current thread.
    
    Args:
        correlation_id: Unique identifier for tracing requests across agents.
    """
    _local.correlation_id = correlation_id


def clear_correlation_id() -> None:
    """Clear the correlation ID for the current thread."""
    if hasattr(_local, 'correlation_id'):
        delattr(_local, 'correlation_id')


class OctoLogFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter for octopOS logs.
    
    Automatically masks sensitive data in log messages.
    """
    
    def __init__(self, fmt: Optional[str] = None, *args, **kwargs):
        """Initialize the formatter with optional format string.
        
        Args:
            fmt: Format string for log records
            *args: Additional arguments passed to parent
            **kwargs: Additional keyword arguments passed to parent
        """
        super().__init__(fmt, *args, **kwargs)
        self._masker: Optional[SensitiveDataMasker] = None
    
    def _get_masker(self) -> SensitiveDataMasker:
        """Get or create the masker instance (lazy initialization)."""
        if self._masker is None:
            self._masker = get_masker()
        return self._masker
    
    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with sensitive data masking.
        
        Args:
            record: The log record to format
            
        Returns:
            Formatted log string with sensitive data masked
        """
        # Create a copy of the record to avoid modifying the original
        # This is important for handlers that might reuse the record
        masked_record = logging.makeLogRecord(record.__dict__.copy())
        
        # Mask the message
        masker = self._get_masker()
        if hasattr(masked_record, 'msg'):
            masked_record.msg = masker.mask(str(masked_record.msg))
        
        # Mask args if they exist (for formatted messages)
        if masked_record.args:
            if isinstance(masked_record.args, (list, tuple)):
                masked_record.args = tuple(
                    masker.mask(str(arg)) for arg in masked_record.args
                )
            elif isinstance(masked_record.args, dict):
                masked_record.args = {
                    k: masker.mask(str(v)) for k, v in masked_record.args.items()
                }
        
        # Call parent formatter
        return super().format(masked_record)
    
    def add_fields(
        self,
        log_record: Dict[str, Any],
        record: logging.LogRecord,
        message_dict: Dict[str, Any]
    ) -> None:
        """Add custom fields to log record."""
        super().add_fields(log_record, record, message_dict)
        
        # Add timestamp in ISO format
        log_record['timestamp'] = datetime.now().astimezone().isoformat()
        log_record['level'] = record.levelname
        log_record['logger'] = record.name
        log_record['agent'] = 'octopos'
        
        # Add correlation ID for distributed tracing
        config = get_config()
        if config.logging.enable_correlation_id:
            log_record['correlation_id'] = get_correlation_id()
        
        # Add agent name from config if available
        try:
            log_record['agent_name'] = config.agent.name
        except Exception:
            pass
        
        # Mask any additional fields that might contain sensitive data
        masker = self._get_masker()
        for key in ['message', 'msg']:
            if key in log_record and log_record[key]:
                log_record[key] = masker.mask(str(log_record[key]))


class CloudWatchLogHandler(logging.Handler):
    """Custom logging handler that sends logs to AWS CloudWatch.
    
    Integrates with the CloudWatchLogger class to provide seamless
    CloudWatch integration within the standard logging chain.
    """
    
    def __init__(self, log_group: str, log_stream: Optional[str] = None):
        """Initialize CloudWatch handler.
        
        Args:
            log_group: CloudWatch log group name
            log_stream: CloudWatch log stream name (defaults to date-based)
        """
        super().__init__()
        self.log_group = log_group
        self.log_stream = log_stream or f"octopos-{datetime.now().astimezone().strftime('%Y-%m-%d')}"
        self._cw_logger = None
        self._initialized = False
        
    def _get_cw_logger(self):
        """Lazy initialization of CloudWatch logger."""
        if not self._initialized:
            try:
                from src.utils.cloudwatch_logger import CloudWatchLogger
                self._cw_logger = CloudWatchLogger(
                    log_group=self.log_group,
                    region=None  # Use config default
                )
                self._initialized = True
            except Exception as e:
                # Fallback: log error but don't crash
                sys.stderr.write(f"Failed to initialize CloudWatch handler: {e}\n")
                self._initialized = True  # Prevent repeated attempts
        return self._cw_logger
    
    def emit(self, record: logging.LogRecord) -> None:
        """Send log record to CloudWatch.
        
        Args:
            record: The log record to send.
        """
        try:
            cw_logger = self._get_cw_logger()
            if cw_logger and cw_logger._logs_client:
                msg = self.format(record)
                level = record.levelname
                cw_logger.log_message(msg, level=level)
        except Exception:
            # Silently fail to avoid infinite loops
            self.handleError(record)


def setup_logging(
    level: Optional[str] = None,
    destination: Optional[str] = None,
    format_type: Optional[str] = None
) -> logging.Logger:
    """Set up logging for octopOS.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        destination: Where to send logs (stdout, file, cloudwatch)
        format_type: Log format (json, text)
        
    Returns:
        Configured logger instance
    """
    config = get_config()
    
    # Use config values if not provided
    if level is None:
        level = config.logging.level
        if hasattr(level, "value"):
            level = level.value
            
    if destination is None:
        destination = config.logging.destination
        if hasattr(destination, "value"):
            destination = destination.value
            
    format_type = format_type or config.logging.format
    
    # Create logger
    logger = logging.getLogger('octopos')
    logger.setLevel(getattr(logging, level))
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Create handler based on destination
    if destination == 'stdout':
        handler = logging.StreamHandler(sys.stdout)
    elif destination == 'file':
        # Create log directory if needed
        import os
        log_dir = os.path.dirname(config.logging.file_path)
        os.makedirs(log_dir, exist_ok=True)
        
        # Use rotating file handler for log rotation
        handler = logging.handlers.RotatingFileHandler(
            filename=config.logging.file_path,
            maxBytes=config.logging.file_max_bytes,
            backupCount=config.logging.file_backup_count
        )
    elif destination == 'cloudwatch':
        # Use CloudWatch handler
        handler = CloudWatchLogHandler(
            log_group=config.logging.cloudwatch_log_group,
            log_stream=config.logging.cloudwatch_log_stream
        )
    else:
        handler = logging.StreamHandler(sys.stdout)
    
    # Create formatter
    if format_type == 'json':
        formatter = OctoLogFormatter(
            '%(timestamp)s %(level)s %(name)s %(message)s'
        )
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    return logger


# Global logger instance
_logger: Optional[logging.Logger] = None


def get_logger() -> logging.Logger:
    """Get the global logger instance.
    
    Returns:
        Configured logger instance
    """
    global _logger
    if _logger is None:
        _logger = setup_logging()
    return _logger


class AgentLogger:
    """Logger wrapper for agent-specific logging.
    
    Adds agent context and correlation ID to all log messages.
    """
    
    def __init__(self, agent_name: str) -> None:
        """Initialize agent logger.
        
        Args:
            agent_name: Name of the agent
        """
        self.agent_name = agent_name
        self._logger = get_logger()
    
    def _log(
        self,
        level: int,
        message: str,
        extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """Internal log method with agent context."""
        extra = extra or {}
        extra['agent_name'] = self.agent_name
        
        # Add correlation ID for distributed tracing
        config = get_config()
        if config.logging.enable_correlation_id:
            extra['correlation_id'] = get_correlation_id()
        
        self._logger.log(level, message, extra=extra)
    
    def debug(self, message: str, **kwargs: Any) -> None:
        """Log debug message."""
        self._log(logging.DEBUG, message, kwargs)
    
    def info(self, message: str, **kwargs: Any) -> None:
        """Log info message."""
        self._log(logging.INFO, message, kwargs)
    
    def warning(self, message: str, **kwargs: Any) -> None:
        """Log warning message."""
        self._log(logging.WARNING, message, kwargs)
    
    def error(self, message: str, **kwargs: Any) -> None:
        """Log error message."""
        self._log(logging.ERROR, message, kwargs)
    
    def critical(self, message: str, **kwargs: Any) -> None:
        """Log critical message."""
        self._log(logging.CRITICAL, message, kwargs)


class CorrelationContext:
    """Context manager for correlation ID tracking.
    
    Usage:
        with CorrelationContext() as cid:
            logger.info("Processing request")
            # All logs within this block will have the same correlation_id
    """
    
    def __init__(self, correlation_id: Optional[str] = None):
        """Initialize correlation context.
        
        Args:
            correlation_id: Optional explicit correlation ID (generates new if None)
        """
        self.correlation_id = correlation_id or str(uuid.uuid4())
        self._previous_id: Optional[str] = None
    
    def __enter__(self) -> str:
        """Enter context and set correlation ID.
        
        Returns:
            The correlation ID being used
        """
        self._previous_id = get_correlation_id() if hasattr(_local, 'correlation_id') else None
        set_correlation_id(self.correlation_id)
        return self.correlation_id
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context and restore previous correlation ID."""
        if self._previous_id:
            set_correlation_id(self._previous_id)
        else:
            clear_correlation_id()
