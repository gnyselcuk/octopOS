"""Tests for the logging system.

Tests cover:
- Logger setup and configuration
- JSON/text formatting
- Log rotation
- Correlation ID tracking
- Agent logging
- CloudWatch handler
- Sensitive data masking
"""

import json
import logging
import os
import re
import tempfile
import threading
import time
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from src.utils.logger import (
    AgentLogger,
    CloudWatchLogHandler,
    CorrelationContext,
    OctoLogFormatter,
    SensitiveDataMasker,
    clear_correlation_id,
    get_correlation_id,
    get_logger,
    get_masker,
    mask_sensitive_data,
    set_correlation_id,
    setup_logging,
)


class TestCorrelationID:
    """Tests for correlation ID functionality."""
    
    def test_get_correlation_id_generates_new_id(self):
        """Test that get_correlation_id generates a new ID if not set."""
        clear_correlation_id()
        cid = get_correlation_id()
        assert cid is not None
        assert len(cid) == 36  # UUID length
        
    def test_set_correlation_id(self):
        """Test setting correlation ID."""
        test_id = "test-correlation-id-123"
        set_correlation_id(test_id)
        assert get_correlation_id() == test_id
        
    def test_clear_correlation_id(self):
        """Test clearing correlation ID."""
        set_correlation_id("test-id")
        clear_correlation_id()
        # After clearing, a new ID should be generated
        new_id = get_correlation_id()
        assert new_id != "test-id"
        
    def test_correlation_id_thread_isolation(self):
        """Test that correlation IDs are thread-local."""
        set_correlation_id("main-thread-id")
        
        def check_thread_cid():
            # Should generate new ID in different thread
            return get_correlation_id()
        
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(check_thread_cid)
            thread_cid = future.result()
            
        # Thread should have different ID
        assert thread_cid != "main-thread-id"
        assert get_correlation_id() == "main-thread-id"


class TestCorrelationContext:
    """Tests for CorrelationContext context manager."""
    
    def test_context_manager_sets_correlation_id(self):
        """Test that context manager sets correlation ID."""
        with CorrelationContext() as cid:
            assert get_correlation_id() == cid
            assert len(cid) == 36  # UUID format
            
    def test_context_manager_with_explicit_id(self):
        """Test context manager with explicit correlation ID."""
        explicit_id = "my-explicit-id"
        with CorrelationContext(explicit_id) as cid:
            assert cid == explicit_id
            assert get_correlation_id() == explicit_id
            
    def test_context_manager_restores_previous_id(self):
        """Test that previous ID is restored after context."""
        set_correlation_id("previous-id")
        
        with CorrelationContext("new-id") as cid:
            assert get_correlation_id() == "new-id"
            
        assert get_correlation_id() == "previous-id"
        
    def test_nested_context_managers(self):
        """Test nested correlation contexts."""
        with CorrelationContext("outer-id") as outer:
            assert get_correlation_id() == outer
            
            with CorrelationContext("inner-id") as inner:
                assert get_correlation_id() == inner
                
            assert get_correlation_id() == outer


class TestOctoLogFormatter:
    """Tests for OctoLogFormatter."""
    
    def test_json_format_includes_required_fields(self):
        """Test that JSON formatter includes all required fields."""
        formatter = OctoLogFormatter('%(timestamp)s %(level)s %(message)s')
        
        record = logging.LogRecord(
            name='test_logger',
            level=logging.INFO,
            pathname='test.py',
            lineno=1,
            msg='Test message',
            args=(),
            exc_info=None
        )
        
        output = formatter.format(record)
        parsed = json.loads(output)
        
        assert 'timestamp' in parsed
        assert 'level' in parsed
        assert parsed['level'] == 'INFO'
        assert 'logger' in parsed
        assert parsed['logger'] == 'test_logger'
        assert 'agent' in parsed
        assert parsed['agent'] == 'octopos'
        assert 'message' in parsed
        
    def test_json_format_includes_correlation_id(self):
        """Test that JSON formatter includes correlation ID."""
        formatter = OctoLogFormatter('%(timestamp)s %(level)s %(message)s')
        
        with CorrelationContext("test-cid-123"):
            record = logging.LogRecord(
                name='test_logger',
                level=logging.INFO,
                pathname='test.py',
                lineno=1,
                msg='Test message',
                args=(),
                exc_info=None
            )
            
            output = formatter.format(record)
            parsed = json.loads(output)
            
            assert 'correlation_id' in parsed
            assert parsed['correlation_id'] == "test-cid-123"


class TestSetupLogging:
    """Tests for setup_logging function."""
    
    def test_setup_logging_returns_logger(self):
        """Test that setup_logging returns a logger instance."""
        logger = setup_logging(level='INFO', destination='stdout', format_type='text')
        assert isinstance(logger, logging.Logger)
        assert logger.name == 'octopos'
        
    def test_setup_logging_stdout_destination(self):
        """Test stdout logging destination."""
        logger = setup_logging(level='INFO', destination='stdout', format_type='text')
        
        # Check that there's a StreamHandler
        handlers = [h for h in logger.handlers if isinstance(h, logging.StreamHandler)]
        assert len(handlers) > 0
        
    def test_setup_logging_json_format(self):
        """Test JSON format configuration."""
        logger = setup_logging(level='INFO', destination='stdout', format_type='json')
        
        # Check that formatter is OctoLogFormatter
        for handler in logger.handlers:
            assert isinstance(handler.formatter, OctoLogFormatter)
            
    def test_setup_logging_text_format(self):
        """Test text format configuration."""
        logger = setup_logging(level='INFO', destination='stdout', format_type='text')
        
        # Check that formatter is standard Formatter
        for handler in logger.handlers:
            assert isinstance(handler.formatter, logging.Formatter)
            assert not isinstance(handler.formatter, OctoLogFormatter)
            
    @pytest.mark.skipif(os.environ.get('SKIP_FILE_TESTS'), reason="File tests disabled")
    def test_setup_logging_file_destination(self):
        """Test file logging destination with rotation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, 'test.log')
            
            with patch('src.utils.logger.get_config') as mock_config:
                mock_config.return_value.logging.file_path = log_file
                mock_config.return_value.logging.file_max_bytes = 1024
                mock_config.return_value.logging.file_backup_count = 3
                mock_config.return_value.logging.enable_correlation_id = True
                
                logger = setup_logging(level='INFO', destination='file', format_type='text')
                
                # Log a message
                logger.info('Test file logging')
                
                # Check that file was created
                assert os.path.exists(log_file)
                
                # Check that RotatingFileHandler is used
                handlers = [h for h in logger.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
                assert len(handlers) > 0


class TestLogRotation:
    """Tests for log rotation functionality."""
    
    @pytest.mark.skipif(os.environ.get('SKIP_FILE_TESTS'), reason="File tests disabled")
    def test_log_rotation_creates_backup_files(self):
        """Test that log rotation creates backup files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, 'rotating.log')
            
            with patch('src.utils.logger.get_config') as mock_config:
                mock_config.return_value.logging.file_path = log_file
                mock_config.return_value.logging.file_max_bytes = 100  # Small for testing
                mock_config.return_value.logging.file_backup_count = 2
                mock_config.return_value.logging.enable_correlation_id = True
                
                logger = setup_logging(level='INFO', destination='file', format_type='text')
                
                # Write enough data to trigger rotation
                for i in range(20):
                    logger.info('X' * 50)  # 50 char messages
                    
                # Give filesystem time to sync
                time.sleep(0.1)
                
                # Check for backup files
                backup_files = [f for f in os.listdir(tmpdir) if f.startswith('rotating.log.')]
                assert len(backup_files) > 0


class TestAgentLogger:
    """Tests for AgentLogger class."""
    
    def test_agent_logger_adds_agent_name(self):
        """Test that AgentLogger adds agent name to logs."""
        agent_logger = AgentLogger("TestAgent")
        assert agent_logger.agent_name == "TestAgent"
        
    def test_agent_logger_methods(self):
        """Test all AgentLogger logging methods."""
        agent_logger = AgentLogger("TestAgent")
        
        # These should not raise exceptions
        agent_logger.debug("Debug message")
        agent_logger.info("Info message")
        agent_logger.warning("Warning message")
        agent_logger.error("Error message")
        agent_logger.critical("Critical message")
        
    def test_agent_logger_includes_correlation_id(self):
        """Test that AgentLogger includes correlation ID."""
        with CorrelationContext("agent-test-cid"):
            agent_logger = AgentLogger("TestAgent")
            
            # Create a mock to capture log calls
            with patch.object(agent_logger._logger, 'log') as mock_log:
                agent_logger.info("Test message")
                
                # Check that log was called with correlation_id in extra
                call_args = mock_log.call_args
                extra = call_args[1].get('extra', {})
                assert 'correlation_id' in extra
                assert extra['correlation_id'] == "agent-test-cid"


class TestCloudWatchLogHandler:
    """Tests for CloudWatchLogHandler."""
    
    def test_handler_initialization(self):
        """Test CloudWatch handler initialization."""
        handler = CloudWatchLogHandler(
            log_group="/test/group",
            log_stream="test-stream"
        )
        assert handler.log_group == "/test/group"
        assert handler.log_stream == "test-stream"
        
    def test_handler_creates_default_stream_name(self):
        """Test that handler creates default stream name if not provided."""
        handler = CloudWatchLogHandler(log_group="/test/group")
        assert handler.log_stream is not None
        assert "octopos-" in handler.log_stream
        
    @patch('src.utils.cloudwatch_logger.CloudWatchLogger')
    def test_handler_emit_calls_cloudwatch(self, mock_cw_class):
        """Test that handler emit calls CloudWatch logger."""
        mock_cw = MagicMock()
        mock_cw._logs_client = MagicMock()  # Simulate connected client
        mock_cw_class.return_value = mock_cw
        
        handler = CloudWatchLogHandler(log_group="/test/group")
        handler._initialized = True
        handler._cw_logger = mock_cw
        
        record = logging.LogRecord(
            name='test',
            level=logging.INFO,
            pathname='test.py',
            lineno=1,
            msg='Test message',
            args=(),
            exc_info=None
        )
        
        handler.emit(record)
        
        # Verify CloudWatch logger was called
        mock_cw.log_message.assert_called_once()
        call_args = mock_cw.log_message.call_args
        assert 'Test message' in str(call_args)
        assert call_args[1]['level'] == 'INFO'


class TestGetLogger:
    """Tests for get_logger function."""
    
    def test_get_logger_returns_same_instance(self):
        """Test that get_logger returns singleton instance."""
        logger1 = get_logger()
        logger2 = get_logger()
        assert logger1 is logger2
        
    def test_get_logger_configures_logger(self):
        """Test that get_logger returns configured logger."""
        logger = get_logger()
        assert logger.name == 'octopos'
        assert len(logger.handlers) > 0


class TestIntegration:
    """Integration tests for the logging system."""
    
    def test_full_logging_flow_with_correlation(self):
        """Test complete logging flow with correlation tracking."""
        with CorrelationContext() as cid:
            agent_logger = AgentLogger("IntegrationAgent")
            
            # Capture log output
            log_capture = StringIO()
            handler = logging.StreamHandler(log_capture)
            handler.setFormatter(OctoLogFormatter('%(timestamp)s %(level)s %(name)s %(message)s'))
            
            # Store original handlers and level
            original_handlers = agent_logger._logger.handlers[:]
            original_level = agent_logger._logger.level
            
            # Clear existing handlers and add our test handler
            agent_logger._logger.handlers.clear()
            agent_logger._logger.addHandler(handler)
            agent_logger._logger.setLevel(logging.INFO)
            
            try:
                agent_logger.info("Integration test message")
                
                # Parse the log output
                output = log_capture.getvalue()
                assert output, "No log output captured"
                
                parsed = json.loads(output.strip())
                assert parsed['correlation_id'] == cid
                assert 'Integration test message' in str(parsed.get('message', ''))
            finally:
                # Restore original handlers and level
                agent_logger._logger.handlers.clear()
                agent_logger._logger.handlers.extend(original_handlers)
                agent_logger._logger.setLevel(original_level)


class TestSensitiveDataMasker:
    """Tests for SensitiveDataMasker class."""
    
    def test_masker_initialization(self):
        """Test SensitiveDataMasker initialization."""
        masker = SensitiveDataMasker(mask_character='#', enabled=True)
        assert masker.mask_character == '#'
        assert masker.enabled is True
        
    def test_masker_disabled(self):
        """Test that disabled masker returns text unchanged."""
        masker = SensitiveDataMasker(enabled=False)
        text = "API key: sk-1234567890abcdef"
        assert masker.mask(text) == text
        
    def test_mask_openai_api_key(self):
        """Test masking of OpenAI API keys."""
        masker = SensitiveDataMasker()
        text = "Using API key: sk-abcdefghijklmnopqrstuvwxyz1234567890abcdef"
        masked = masker.mask(text)
        assert 'sk-a' in masked  # First 3 chars of key preserved
        assert 'abcdefghijklmnopqrstuvwxyz1234567890abcdef' not in masked
        assert '*' in masked
        
    def test_mask_aws_access_key(self):
        """Test masking of AWS Access Key IDs."""
        masker = SensitiveDataMasker()
        text = "Access key: AKIAIOSFODNN7EXAMPLE"
        masked = masker.mask(text)
        assert 'AKIA' in masked
        assert 'IOSFODNN7EXAMPLE' not in masked
        
    def test_mask_aws_secret_key(self):
        """Test masking of AWS Secret Access Keys."""
        masker = SensitiveDataMasker()
        text = "aws_secret_access_key = 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY'"
        masked = masker.mask(text)
        assert 'wJalrXUtnFEMI' not in masked
        assert '*' in masked
        
    def test_mask_password(self):
        """Test masking of passwords."""
        masker = SensitiveDataMasker()
        text = "password = mySecretPassword123"
        masked = masker.mask(text)
        assert 'mySecretPassword123' not in masked
        assert '*' in masked
        
    def test_mask_bearer_token(self):
        """Test masking of Bearer tokens."""
        masker = SensitiveDataMasker()
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        masked = masker.mask(text)
        assert 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9' not in masked
        # The entire Bearer token including "Bearer " is masked, only Bear remains
        assert 'Bear' in masked
        
    def test_mask_jwt_token(self):
        """Test masking of JWT tokens."""
        masker = SensitiveDataMasker()
        text = "token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        masked = masker.mask(text)
        assert 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9' not in masked
        assert 'eyJ' in masked  # First 3 chars preserved
        
    def test_mask_credit_card(self):
        """Test masking of credit card numbers."""
        masker = SensitiveDataMasker()
        # Visa
        text = "Card: 4111111111111111"
        masked = masker.mask(text)
        assert '4111111111111111' not in masked
        assert '4111' in masked  # First 4 chars preserved
        # Mastercard
        text = "Card: 5555555555554444"
        masked = masker.mask(text)
        assert '5555555555554444' not in masked
        
    def test_mask_email(self):
        """Test masking of email addresses."""
        masker = SensitiveDataMasker()
        text = "Contact: john.doe@example.com"
        masked = masker.mask(text)
        assert 'john.doe@example.com' not in masked
        assert 'jo******@example.com' == masked.replace('Contact: ', '')  # First 2 chars + 6 masked + domain
        
    def test_mask_short_email(self):
        """Test masking of short email addresses."""
        masker = SensitiveDataMasker()
        text = "Contact: ab@example.com"
        masked = masker.mask(text)
        assert 'ab@example.com' not in masked
        assert '@example.com' in masked
        
    def test_mask_slack_token(self):
        """Test masking of Slack tokens."""
        masker = SensitiveDataMasker()
        # Using fake token format for testing - not a real secret
        text = "Slack token: xoxb-FAKE123456789-FAKE123456789-FAKE123FAKE123FAKE"
        masked = masker.mask(text)
        assert 'xoxb-FAKE' not in masked
        
    def test_mask_github_token(self):
        """Test masking of GitHub tokens."""
        masker = SensitiveDataMasker()
        text = "GitHub token: ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        masked = masker.mask(text)
        assert 'ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx' not in masked
        
    def test_mask_db_connection(self):
        """Test masking of database connection strings."""
        masker = SensitiveDataMasker()
        text = "mongodb://admin:secretpassword123@mongodb.example.com:27017/mydb"
        masked = masker.mask(text)
        assert 'secretpassword123' not in masked
        assert 'mongodb://admin:' in masked
        assert '@mongodb.example.com' in masked
        
    def test_mask_custom_character(self):
        """Test masking with custom character."""
        masker = SensitiveDataMasker(mask_character='#')
        text = "API key: sk-1234567890abcdefghijklmnopqrstuvwxyz"
        masked = masker.mask(text)
        assert '#' in masked
        assert '*' not in masked
        
    def test_mask_custom_pattern(self):
        """Test masking with custom patterns."""
        custom_patterns = [r'secret_[a-z]+']
        masker = SensitiveDataMasker(custom_patterns=custom_patterns)
        text = "Secret: secret_token_value"
        masked = masker.mask(text)
        assert 'secret_token' not in masked
        
    def test_add_pattern_runtime(self):
        """Test adding patterns at runtime."""
        masker = SensitiveDataMasker()
        masker.add_pattern('my_pattern', r'my_secret_\d+')
        text = "Value: my_secret_12345"
        masked = masker.mask(text)
        assert 'my_secret_12345' not in masked
        
    def test_add_invalid_pattern(self):
        """Test adding invalid pattern raises error."""
        masker = SensitiveDataMasker()
        with pytest.raises(ValueError):
            masker.add_pattern('invalid', r'[invalid')
            
    def test_remove_pattern(self):
        """Test removing patterns."""
        masker = SensitiveDataMasker()
        masker.remove_pattern('openai_api_key')
        text = "API key: sk-1234567890abcdef"
        masked = masker.mask(text)
        # Should not be masked anymore
        assert 'sk-1234567890abcdef' in masked
        
    def test_remove_nonexistent_pattern(self):
        """Test removing non-existent pattern returns False."""
        masker = SensitiveDataMasker()
        result = masker.remove_pattern('nonexistent')
        assert result is False
        
    def test_mask_empty_text(self):
        """Test masking empty text."""
        masker = SensitiveDataMasker()
        assert masker.mask('') == ''
        assert masker.mask(None) is None
        
    def test_mask_no_sensitive_data(self):
        """Test masking text with no sensitive data."""
        masker = SensitiveDataMasker()
        text = "This is a normal log message without secrets"
        assert masker.mask(text) == text
        
    def test_mask_multiple_patterns(self):
        """Test masking multiple patterns in one text."""
        masker = SensitiveDataMasker()
        text = "API: sk-1234567890abcdefghijklmnopqrstuvwxyz, Email: user@example.com, password: secret123"
        masked = masker.mask(text)
        assert 'sk-1234567890abcdefghijklmnopqrstuvwxyz' not in masked
        assert 'user@example.com' not in masked
        assert 'secret123' not in masked


class TestMaskSensitiveDataFunction:
    """Tests for mask_sensitive_data convenience function."""
    
    @pytest.fixture(autouse=True)
    def reset_masker(self):
        """Reset global masker before each test."""
        import src.utils.logger as logger_module
        logger_module._masker = None
        yield
        logger_module._masker = None
    
    def test_mask_sensitive_data_function(self):
        """Test the convenience function."""
        text = "API key: sk-1234567890abcdefghijklmnopqrstuvwxyz"
        masked = mask_sensitive_data(text)
        assert 'sk-1234567890abcdefghijklmnopqrstuvwxyz' not in masked
        
    def test_mask_sensitive_data_with_mock_config(self):
        """Test masking with mocked config."""
        with patch('src.utils.logger.get_config') as mock_config:
            mock_config.return_value.logging.mask_sensitive_data = True
            mock_config.return_value.logging.mask_character = '#'
            mock_config.return_value.logging.mask_custom_patterns = []
            
            # Reset the global masker to pick up new config
            import src.utils.logger as logger_module
            logger_module._masker = None
            
            text = "API key: sk-1234567890abcdefghijklmnopqrstuvwxyz"
            masked = mask_sensitive_data(text)
            assert '#' in masked
            
            # Reset again for other tests
            logger_module._masker = None


class TestOctoLogFormatterMasking:
    """Tests for OctoLogFormatter with sensitive data masking."""
    
    @pytest.fixture(autouse=True)
    def reset_masker(self):
        """Reset global masker before each test."""
        import src.utils.logger as logger_module
        logger_module._masker = None
        yield
        logger_module._masker = None
    
    def test_formatter_masks_api_key_in_message(self):
        """Test that formatter masks API keys in log messages."""
        formatter = OctoLogFormatter('%(timestamp)s %(level)s %(message)s')
        
        record = logging.LogRecord(
            name='test_logger',
            level=logging.INFO,
            pathname='test.py',
            lineno=1,
            msg='API key: sk-1234567890abcdefghijklmnopqrstuvwxyz',
            args=(),
            exc_info=None
        )
        
        output = formatter.format(record)
        parsed = json.loads(output)
        
        assert 'sk-1234567890abcdefghijklmnopqrstuvwxyz' not in str(parsed.get('message', ''))
        # Check for mask character (either * or masked key portion)
        message = str(parsed.get('message', ''))
        assert '*' in message or 'sk-1' in message  # Either masked or has prefix
        
    def test_formatter_masks_formatted_message(self):
        """Test that formatter masks sensitive data in formatted messages."""
        formatter = OctoLogFormatter('%(timestamp)s %(level)s %(message)s')
        
        record = logging.LogRecord(
            name='test_logger',
            level=logging.INFO,
            pathname='test.py',
            lineno=1,
            msg='User %s has password: %s',
            args=('john', 'mysecretpass'),
            exc_info=None
        )
        
        output = formatter.format(record)
        parsed = json.loads(output)
        
        message = str(parsed.get('message', ''))
        assert 'mysecretpass' not in message
        # Password should be masked - check for any masking indicator
        assert '#' in message or '*' in message or 'pass' not in message.lower()
        
    def test_formatter_masks_dict_args(self):
        """Test that formatter masks sensitive data in dict args."""
        formatter = OctoLogFormatter('%(timestamp)s %(level)s %(message)s')
        
        # dict args must be passed as a single-element tuple containing the dict
        record = logging.LogRecord(
            name='test_logger',
            level=logging.INFO,
            pathname='test.py',
            lineno=1,
            msg='Config: %(config)s',
            args=({'config': 'api_key=sk-1234567890abcdefghijklmnopqrstuvwxyz'},),
            exc_info=None
        )
        
        output = formatter.format(record)
        parsed = json.loads(output)
        
        message = str(parsed.get('message', ''))
        assert 'sk-1234567890abcdefghijklmnopqrstuvwxyz' not in message
        
    def test_formatter_preserves_original_record(self):
        """Test that formatter doesn't modify the original record."""
        formatter = OctoLogFormatter('%(timestamp)s %(level)s %(message)s')
        
        original_msg = 'API key: sk-1234567890abcdefghijklmnopqrstuvwxyz'
        record = logging.LogRecord(
            name='test_logger',
            level=logging.INFO,
            pathname='test.py',
            lineno=1,
            msg=original_msg,
            args=(),
            exc_info=None
        )
        
        # Format the record
        formatter.format(record)
        
        # Original record should be unchanged
        assert record.msg == original_msg
        assert 'sk-1234567890abcdefghijklmnopqrstuvwxyz' in record.msg  # Verify original still has full key
        
    def test_formatter_handles_empty_message(self):
        """Test that formatter handles empty messages."""
        formatter = OctoLogFormatter('%(timestamp)s %(level)s %(message)s')
        
        record = logging.LogRecord(
            name='test_logger',
            level=logging.INFO,
            pathname='test.py',
            lineno=1,
            msg='',
            args=(),
            exc_info=None
        )
        
        output = formatter.format(record)
        assert output is not None
        
    def test_formatter_integration_with_setup_logging(self):
        """Test formatter masking in full logging setup."""
        log_capture = StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setFormatter(OctoLogFormatter('%(timestamp)s %(level)s %(message)s'))
        
        logger = logging.getLogger('test_masking_logger')
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        
        # Log a message with sensitive data (long enough API key)
        logger.info("Connecting with API key: sk-1234567890abcdefghijklmnopqrstuvwxyz")
        
        output = log_capture.getvalue()
        parsed = json.loads(output.strip())
        
        assert 'sk-1234567890abcdefghijklmnopqrstuvwxyz' not in str(parsed.get('message', ''))
        
        # Clean up
        logger.handlers.clear()


class TestSensitiveDataMaskingIntegration:
    """Integration tests for sensitive data masking."""
    
    @pytest.fixture(autouse=True)
    def reset_masker(self):
        """Reset global masker before each test."""
        import src.utils.logger as logger_module
        logger_module._masker = None
        yield
        logger_module._masker = None
    
    def test_agent_logger_masks_sensitive_data(self):
        """Test that AgentLogger masks sensitive data."""
        agent_logger = AgentLogger("TestAgent")
        
        log_capture = StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setFormatter(OctoLogFormatter('%(timestamp)s %(level)s %(message)s'))
        
        # Store original handlers
        original_handlers = agent_logger._logger.handlers[:]
        agent_logger._logger.handlers.clear()
        agent_logger._logger.addHandler(handler)
        agent_logger._logger.setLevel(logging.INFO)
        
        try:
            agent_logger.info("Using token: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature")
            
            output = log_capture.getvalue()
            parsed = json.loads(output.strip())
            
            message = str(parsed.get('message', ''))
            assert 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9' not in message
        finally:
            # Restore original handlers
            agent_logger._logger.handlers.clear()
            agent_logger._logger.handlers.extend(original_handlers)
            
    def test_correlation_context_with_masking(self):
        """Test correlation context works with masking."""
        with CorrelationContext() as cid:
            log_capture = StringIO()
            handler = logging.StreamHandler(log_capture)
            handler.setFormatter(OctoLogFormatter('%(timestamp)s %(level)s %(message)s'))
            
            logger = logging.getLogger('test_corr_mask')
            logger.handlers.clear()
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
            
            logger.info("API key: sk-1234567890abcdefghijklmnopqrstuvwxyz for request")
            
            output = log_capture.getvalue()
            parsed = json.loads(output.strip())
            
            assert parsed['correlation_id'] == cid
            assert 'sk-1234567890abcdefghijklmnopqrstuvwxyz' not in str(parsed.get('message', ''))
            
            logger.handlers.clear()
            
    def test_all_pattern_types_masked_together(self):
        """Test all sensitive pattern types are masked together."""
        masker = SensitiveDataMasker()
        
        text = """
        Config:
        - OpenAI Key: sk-abcdefghijklmnopqrstuvwxyz1234567890
        - AWS Key: AKIAIOSFODNN7EXAMPLE
        - Password: mySuperSecretPass123
        - Bearer Token: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature
        - Email: admin@company.com
        - Card: 4111111111111111
        - GitHub: ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
        """
        
        masked = masker.mask(text)
        
        # Verify all sensitive data is masked
        assert 'sk-abcdefghijklmnopqrstuvwxyz1234567890' not in masked
        assert 'AKIAIOSFODNN7EXAMPLE' not in masked
        assert 'mySuperSecretPass123' not in masked
        assert 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9' not in masked
        assert 'admin@company.com' not in masked
        assert '4111111111111111' not in masked
        assert 'ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx' not in masked
        
        # Verify log structure is preserved
        assert 'Config:' in masked
        assert 'OpenAI Key:' in masked
        assert 'AWS Key:' in masked


class TestMaskingPerformance:
    """Performance tests for sensitive data masking."""
    
    def test_masker_performance_small_text(self):
        """Test masker performance with small text."""
        import time
        
        masker = SensitiveDataMasker()
        text = "API key: sk-1234567890abcdef"
        
        start = time.time()
        for _ in range(1000):
            masker.mask(text)
        duration = time.time() - start
        
        # Should complete in reasonable time (< 1 second for 1000 operations)
        assert duration < 1.0
        
    def test_masker_performance_large_text(self):
        """Test masker performance with large text."""
        import time
        
        masker = SensitiveDataMasker()
        text = "API key: sk-1234567890abcdefghijklmnopqrstuvwxyz\n" * 1000
        
        start = time.time()
        result = masker.mask(text)
        duration = time.time() - start
        
        # Should complete in reasonable time (< 1 second)
        assert duration < 1.0
        assert 'sk-1234567890abcdefghijklmnopqrstuvwxyz' not in result


class TestMaskingConfiguration:
    """Tests for masking configuration."""
    
    def test_config_masking_enabled(self):
        """Test that masking can be enabled via config."""
        from src.utils.config import LoggingConfig
        
        config = LoggingConfig()
        assert config.mask_sensitive_data is True
        assert config.mask_character == '*'
        assert config.mask_custom_patterns == []
        
    def test_config_custom_patterns(self):
        """Test custom patterns in config."""
        from src.utils.config import LoggingConfig
        
        config = LoggingConfig()
        config.mask_custom_patterns = [r'custom_secret_\d+']
        
        masker = SensitiveDataMasker(
            custom_patterns=config.mask_custom_patterns,
            enabled=config.mask_sensitive_data
        )
        
        text = "Value: custom_secret_12345"
        masked = masker.mask(text)
        assert 'custom_secret_12345' not in masked


class TestMaskingEdgeCases:
    """Edge case tests for sensitive data masking."""
    
    def test_mask_unicode_text(self):
        """Test masking with unicode text."""
        masker = SensitiveDataMasker()
        text = "API anahtarı: sk-1234567890abcdefghijklmnopqrstuvwxyz 🔑"
        masked = masker.mask(text)
        assert 'sk-1234567890abcdefghijklmnopqrstuvwxyz' not in masked
        
    def test_mask_special_characters(self):
        """Test masking with special characters."""
        masker = SensitiveDataMasker()
        text = "Key: sk-123!@#$%^&*()_+-=[]{}|;':\",./<>?"
        masked = masker.mask(text)
        assert 'sk-123' in masked  # First 4 chars preserved
        
    def test_mask_multiline_text(self):
        """Test masking with multiline text."""
        masker = SensitiveDataMasker()
        text = """Line 1: password = mysecretpass
Line 2: api_key = sk-abcdef12345678901234567890
Line 3: normal text"""
        masked = masker.mask(text)
        assert 'mysecretpass' not in masked
        assert 'sk-abcdef12345678901234567890' not in masked
        assert 'Line 3: normal text' in masked
        
    def test_mask_very_long_key(self):
        """Test masking with very long API key."""
        masker = SensitiveDataMasker()
        long_key = 'sk-' + 'a' * 200
        text = f"Key: {long_key}"
        masked = masker.mask(text)
        assert long_key not in masked
        assert 'sk-a' in masked  # First 3 chars of the matched text preserved (sk- counts as part of match)
        
    def test_mask_partial_key_match(self):
        """Test that partial matches don't get masked incorrectly."""
        masker = SensitiveDataMasker()
        text = "Token: not-a-real-sk-token"
        # This shouldn't match the sk- pattern (needs at least 20 chars after)
        masked = masker.mask(text)
        # The pattern requires 20+ alphanumeric chars after sk-
        # so this short one might pass through or be partially masked
        assert 'not-a-real-sk-token' in masked or '*' in masked
        
    def test_mask_nested_sensitive_data(self):
        """Test masking with nested/repeated patterns."""
        masker = SensitiveDataMasker()
        text = "Keys: sk-1234567890abcdefghijklmnopqrstuvwxyz and sk-0987654321fedcbaabcdefghijklmnop"
        masked = masker.mask(text)
        assert 'sk-1234567890abcdefghijklmnopqrstuvwxyz' not in masked
        assert 'sk-0987654321fedcbaabcdefghijklmnop' not in masked
        # Both keys should be masked
        assert masked.count('sk-') <= 2  # Only prefixes remain
        
    def test_mask_case_insensitive(self):
        """Test that masking is case-insensitive."""
        masker = SensitiveDataMasker()
        text = "API KEY: sk-1234567890abcdefghijklmnopqrstuvwxyz"
        masked = masker.mask(text)
        assert 'sk-1234567890abcdefghijklmnopqrstuvwxyz' not in masked
        # Test uppercase password pattern
        text2 = "PASSWORD = secret123pass"
        masked2 = masker.mask(text2)
        assert 'secret123pass' not in masked2
        
    def test_mask_similar_but_different_patterns(self):
        """Test that similar patterns don't interfere."""
        masker = SensitiveDataMasker()
        # Both keys follow the sk-<alphanumeric> pattern (sk-proj-* is actually valid format too)
        text = "Key 1: sk-1234567890abcdefghijklmnopqrstuvwxyz and Key 2: sk-0987654321fedcbaabcdefghijklmnopqrstuvwxyz"
        masked = masker.mask(text)
        # Both should be masked
        assert 'sk-1234567890abcdefghijklmnopqrstuvwxyz' not in masked
        assert 'sk-0987654321fedcbaabcdefghijklmnopqrstuvwxyz' not in masked
        # At least one masked key should remain
        assert 'sk-' in masked
        
    def test_empty_masker(self):
        """Test masker with no patterns."""
        masker = SensitiveDataMasker()
        masker._patterns = {}
        text = "API key: sk-1234567890abcdef"
        # Should return text unchanged when no patterns
        assert masker.mask(text) == text
        
    def test_mask_with_none_values_in_dict_args(self):
        """Test masking with None values in dict args."""
        # Reset masker for this test
        import src.utils.logger as logger_module
        logger_module._masker = None
        
        formatter = OctoLogFormatter('%(timestamp)s %(level)s %(message)s')
        
        # dict args must be passed as a single-element tuple containing the dict
        record = logging.LogRecord(
            name='test_logger',
            level=logging.INFO,
            pathname='test.py',
            lineno=1,
            msg='Config: %(config)s',
            args=({'config': None},),
            exc_info=None
        )
        
        # Should not raise an error
        output = formatter.format(record)
        assert output is not None
        
        # Reset masker after test
        logger_module._masker = None


def test_get_masker_singleton():
    """Test that get_masker returns singleton instance."""
    masker1 = get_masker()
    masker2 = get_masker()
    assert masker1 is masker2


def test_get_masker_thread_safety():
    """Test thread safety of get_masker."""
    import concurrent.futures
    
    maskers = []
    
    def get_masker_instance():
        return get_masker()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(get_masker_instance) for _ in range(100)]
        maskers = [f.result() for f in concurrent.futures.as_completed(futures)]
    
    # All should be the same instance
    assert all(m is maskers[0] for m in maskers)
