"""Unit tests for utils/config.py module.

This module tests the configuration management for octopOS.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, Mock, mock_open, patch

import pytest

from src.utils.config import (
    AgentConfig,
    AgentPersona,
    AWSConfig,
    BrowserConfig,
    ConfigLoader,
    LanceDBConfig,
    LogDestination,
    LogLevel,
    LoggingConfig,
    MCPConfig,
    MCPConfig,
    OctoConfig,
    SecurityConfig,
    TaskConfig,
    UserConfig,
    WebConfig,
    get_config,
    load_config,
    save_config,
)


class TestEnums:
    """Test configuration enums."""
    
    def test_log_level_values(self):
        """Test LogLevel enum values."""
        assert LogLevel.DEBUG == "DEBUG"
        assert LogLevel.INFO == "INFO"
        assert LogLevel.WARNING == "WARNING"
        assert LogLevel.ERROR == "ERROR"
        assert LogLevel.CRITICAL == "CRITICAL"
    
    def test_log_destination_values(self):
        """Test LogDestination enum values."""
        assert LogDestination.STDOUT == "stdout"
        assert LogDestination.FILE == "file"
        assert LogDestination.CLOUDWATCH == "cloudwatch"
    
    def test_agent_persona_values(self):
        """Test AgentPersona enum values."""
        assert AgentPersona.FRIENDLY == "friendly"
        assert AgentPersona.PROFESSIONAL == "professional"
        assert AgentPersona.TECHNICAL == "technical"


class TestAWSConfig:
    """Test AWSConfig dataclass."""
    
    def test_default_values(self):
        """Test default AWS config values."""
        config = AWSConfig()
        
        assert config.region == "us-east-1"
        assert config.profile is None
        assert config.access_key_id is None
        assert config.role_session_name == "octopos-session"
        
        # Model defaults
        assert "nova-lite" in config.model_nova_lite
        assert "nova-pro" in config.model_nova_pro
    
    def test_custom_values(self):
        """Test custom AWS config values."""
        config = AWSConfig(
            region="eu-west-1",
            profile="my-profile",
            access_key_id="AKIAIOSFODNN7EXAMPLE"
        )
        
        assert config.region == "eu-west-1"
        assert config.profile == "my-profile"
        assert config.access_key_id == "AKIAIOSFODNN7EXAMPLE"


class TestAgentConfig:
    """Test AgentConfig dataclass."""
    
    def test_default_values(self):
        """Test default agent config values."""
        config = AgentConfig()
        
        assert config.name == "octoOS"
        assert config.persona == AgentPersona.FRIENDLY
        assert config.language == "en"
    
    def test_system_prompt_friendly(self):
        """Test friendly persona system prompt."""
        config = AgentConfig(persona=AgentPersona.FRIENDLY)
        prompt = config.get_system_prompt()
        
        assert "octoOS" in prompt
        assert "friendly" in prompt.lower()
    
    def test_system_prompt_professional(self):
        """Test professional persona system prompt."""
        config = AgentConfig(persona=AgentPersona.PROFESSIONAL)
        prompt = config.get_system_prompt()
        
        assert "octoOS" in prompt
        assert "professional" in prompt.lower()
    
    def test_system_prompt_technical(self):
        """Test technical persona system prompt."""
        config = AgentConfig(persona=AgentPersona.TECHNICAL)
        prompt = config.get_system_prompt()
        
        assert "octoOS" in prompt
        assert "technical" in prompt.lower()


class TestLoggingConfig:
    """Test LoggingConfig dataclass."""
    
    def test_default_values(self):
        """Test default logging config."""
        config = LoggingConfig()
        
        assert config.level == LogLevel.INFO
        assert config.destination == LogDestination.STDOUT
        assert config.format == "text"
        assert config.enable_correlation_id is True
        assert config.mask_sensitive_data is True


class TestSecurityConfig:
    """Test SecurityConfig dataclass."""
    
    def test_default_values(self):
        """Test default security config."""
        config = SecurityConfig()
        
        assert config.require_approval_for_code is True
        assert config.require_approval_for_deletions is True
        assert config.auto_approve_safe_operations is False
        assert config.docker_network == "octopos-sandbox"


class TestBrowserConfig:
    """Test BrowserConfig dataclass."""
    
    def test_default_values(self):
        """Test default browser config."""
        config = BrowserConfig()
        
        assert config.headless is False
        assert config.timeout == 30000
        assert config.viewport_width == 1920
        assert config.viewport_height == 1080
        assert config.persist_cookies is True


class TestConfigLoader:
    """Test ConfigLoader class."""
    
    @pytest.fixture
    def loader(self):
        """Create config loader."""
        return ConfigLoader()
    
    def test_load_default_config(self, loader):
        """Test loading default configuration."""
        config = loader.load()
        
        assert isinstance(config, OctoConfig)
        assert config.aws.region == "us-east-1"
        assert config.agent.name == "octoOS"
    
    @patch.dict(os.environ, {"AWS_REGION": "eu-west-1"}, clear=True)
    def test_load_from_env_region(self, loader):
        """Test loading AWS region from environment."""
        config = loader.load()
        
        assert config.aws.region == "eu-west-1"
    
    @patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}, clear=True)
    def test_load_from_env_log_level(self, loader):
        """Test loading log level from environment."""
        config = loader.load()
        
        assert config.logging.level == LogLevel.DEBUG
    
    @patch.dict(os.environ, {"OCTO_AGENT_NAME": "CustomAgent"}, clear=True)
    def test_load_from_env_agent_name(self, loader):
        """Test loading agent name from environment."""
        config = loader.load()
        
        assert config.agent.name == "CustomAgent"
    
    @patch.dict(os.environ, {"MOCK_AWS": "true"}, clear=True)
    def test_load_from_env_mock_aws(self, loader):
        """Test loading mock AWS flag from environment."""
        config = loader.load()
        
        assert config.mock_aws is True
    
    @patch.dict(os.environ, {"DEBUG": "true", "TEST_MODE": "true"}, clear=True)
    def test_load_from_env_development_flags(self, loader):
        """Test loading development flags from environment."""
        config = loader.load()
        
        assert config.debug is True
        assert config.test_mode is True
    
    def test_load_from_profile(self, loader, tmp_path):
        """Test loading configuration from profile file."""
        profile_content = """
aws:
  region: ap-southeast-1
  profile: test-profile
agent:
  name: TestAgent
  persona: technical
user:
  name: TestUser
  timezone: Asia/Tokyo
"""
        profile_path = tmp_path / ".octopos" / "profile.yaml"
        profile_path.parent.mkdir(parents=True)
        profile_path.write_text(profile_content)
        
        with patch('pathlib.Path.home', return_value=tmp_path):
            config = loader.load()
        
        assert config.aws.region == "ap-southeast-1"
        assert config.agent.name == "TestAgent"
        assert config.agent.persona == AgentPersona.TECHNICAL
        assert config.user.name == "TestUser"
    
    def test_save_profile(self, loader, tmp_path):
        """Test saving configuration to profile."""
        config = OctoConfig()
        config.aws.region = "us-west-2"
        config.agent.name = "SavedAgent"
        
        profile_path = tmp_path / "profile.yaml"
        
        loader.save_profile(config, profile_path)
        
        assert profile_path.exists()
        content = profile_path.read_text()
        assert "us-west-2" in content
        assert "SavedAgent" in content


class TestGetConfig:
    """Test get_config function."""
    
    def test_returns_config(self):
        """Test that get_config returns OctoConfig."""
        config = get_config()
        
        assert isinstance(config, OctoConfig)
    
    def test_same_instance(self):
        """Test that get_config returns same instance."""
        config1 = get_config()
        config2 = get_config()
        
        assert config1 is config2


class TestLoadSaveConfig:
    """Test load_config and save_config functions."""
    
    def test_load_config(self):
        """Test load_config convenience function."""
        with patch('src.utils.config.get_config') as mock_get:
            mock_config = MagicMock()
            mock_get.return_value = mock_config
            
            result = load_config()
            
            assert result == mock_config
    
    def test_save_config(self, tmp_path):
        """Test save_config convenience function."""
        config = OctoConfig()
        
        with patch('src.utils.config.ConfigLoader') as mock_loader_class:
            mock_loader = MagicMock()
            mock_loader_class.return_value = mock_loader
            
            save_config(config)
            
            mock_loader.save_profile.assert_called_once_with(config, None)


class TestOctoConfig:
    """Test OctoConfig main configuration class."""
    
    def test_default_sections(self):
        """Test that all config sections exist."""
        config = OctoConfig()
        
        assert isinstance(config.aws, AWSConfig)
        assert isinstance(config.agent, AgentConfig)
        assert isinstance(config.user, UserConfig)
        assert isinstance(config.lancedb, LanceDBConfig)
        assert isinstance(config.logging, LoggingConfig)
        assert isinstance(config.task, TaskConfig)
        assert isinstance(config.security, SecurityConfig)
        assert isinstance(config.web, WebConfig)
        assert isinstance(config.browser, BrowserConfig)
        assert isinstance(config.mcp, MCPConfig)
    
    def test_development_flags(self):
        """Test development flags."""
        config = OctoConfig()
        
        assert config.mock_aws is False
        assert config.debug is False
        assert config.test_mode is False


class TestMCPConfig:
    """Test MCPConfig dataclass."""
    
    def test_default_values(self):
        """Test default MCP config."""
        config = MCPConfig()
        
        assert config.auto_connect is True
        assert config.servers == {}
