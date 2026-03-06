"""Unit tests for interfaces/cli/main.py module.

This module tests the main CLI entry point and setup wizard.
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from typer.testing import CliRunner

from src.interfaces.cli.main import (
    OCTOPUS_ART,
    VERSION,
    app,
    main,
    setup,
)

runner = CliRunner()


class TestMainCLI:
    """Test the main CLI entry point."""
    
    def test_version_flag(self):
        """Test --version flag."""
        result = runner.invoke(app, ["--version"])
        
        assert result.exit_code == 0
        assert VERSION in result.output
        assert "octopOS" in result.output
    
    def test_verbose_flag(self):
        """Test --verbose flag."""
        result = runner.invoke(app, ["--verbose"])
        
        assert result.exit_code == 0
        assert "Verbose" in result.output or "verbose" in result.output.lower()
    
    def test_no_command_shows_welcome(self):
        """Test that running without command shows welcome screen."""
        result = runner.invoke(app, [])
        
        assert result.exit_code == 0
        assert "octopOS" in result.output or "Welcome" in result.output
        # Should show ASCII art
        assert "Agentic Operating System" in result.output or "octopOS" in result.output
    
    def test_help_shows_commands(self):
        """Test that help shows available commands."""
        result = runner.invoke(app, ["--help"])
        
        assert result.exit_code == 0
        assert "setup" in result.output
        assert "ask" in result.output
        assert "chat" in result.output
        assert "agent-status" in result.output


class TestSetupCommand:
    """Test the setup wizard command."""
    
    @pytest.fixture
    def mock_config(self):
        """Create mock configuration."""
        with patch('src.interfaces.cli.main.load_config') as mock_load, \
             patch('src.interfaces.cli.main.save_config') as mock_save:
            config = MagicMock()
            config.aws.region = "us-east-1"
            config.aws.profile = None
            config.aws.access_key_id = None
            config.aws.secret_access_key = None
            config.aws.role_arn = None
            mock_load.return_value = config
            yield config, mock_save
    
    @pytest.fixture
    def mock_aws_env(self):
        """Create mock AWS environment detection."""
        with patch('src.interfaces.cli.main.detect_aws_environment') as mock_detect:
            env = MagicMock()
            env.value = "local"
            mock_detect.return_value = env
            yield mock_detect
    
    @pytest.fixture
    def mock_auth_manager(self):
        """Create mock auth manager."""
        with patch('src.interfaces.cli.main.get_auth_manager') as mock_get:
            auth = MagicMock()
            auth.validate_credentials.return_value = True
            mock_get.return_value = auth
            yield auth
    
    @patch('src.interfaces.cli.main.Path.exists')
    @patch('src.interfaces.cli.main.Confirm.ask')
    @patch('src.interfaces.cli.main.Prompt.ask')
    def test_setup_new_config(
        self,
        mock_prompt,
        mock_confirm,
        mock_exists,
        mock_config,
        mock_aws_env,
        mock_auth_manager
    ):
        """Test setup wizard for new configuration."""
        mock_exists.return_value = False
        mock_confirm.return_value = True
        mock_prompt.side_effect = [
            "us-west-2",  # region
            "profile",    # cred method
            "default",    # profile name
        ]
        
        result = runner.invoke(app, ["setup"])
        
        assert result.exit_code == 0
        assert "Setup Wizard" in result.output or "Welcome" in result.output
    
    @patch('src.interfaces.cli.main.Path.exists')
    def test_setup_existing_config_no_force(self, mock_exists):
        """Test setup with existing config without force flag."""
        mock_exists.return_value = True
        
        result = runner.invoke(app, ["setup"])
        
        assert result.exit_code == 0
        # Should show existing config message
        assert "already exists" in result.output.lower() or "reconfigure" in result.output.lower()
    
    @patch('src.interfaces.cli.main.Path.exists')
    @patch('src.interfaces.cli.main.Confirm.ask')
    @patch('src.interfaces.cli.main.Prompt.ask')
    def test_setup_force_reconfigure(
        self,
        mock_prompt,
        mock_confirm,
        mock_exists,
        mock_config,
        mock_aws_env,
        mock_auth_manager
    ):
        """Test force reconfiguration."""
        mock_exists.return_value = True
        mock_confirm.return_value = True  # User wants to reconfigure
        mock_prompt.side_effect = [
            "us-west-2",  # region
            "profile",    # cred method
            "my-profile", # profile name
        ]
        
        result = runner.invoke(app, ["setup", "--force"])
        
        assert result.exit_code == 0
        assert "Setup Wizard" in result.output or "Welcome" in result.output
    
    @patch('src.interfaces.cli.main.Path.exists')
    @patch('src.interfaces.cli.main.Confirm.ask')
    @patch('src.interfaces.cli.main.Prompt.ask')
    def test_setup_direct_credentials(
        self,
        mock_prompt,
        mock_confirm,
        mock_exists,
        mock_config,
        mock_aws_env,
        mock_auth_manager
    ):
        """Test setup with direct credentials."""
        mock_exists.return_value = False
        mock_prompt.side_effect = [
            "us-west-2",           # region
            "direct",              # cred method
            "AKIAIOSFODNN7EXAMPLE", # access key
            "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", # secret key
        ]
        
        result = runner.invoke(app, ["setup"])
        
        assert result.exit_code == 0
    
    @patch('src.interfaces.cli.main.Path.exists')
    @patch('src.interfaces.cli.main.Confirm.ask')
    @patch('src.interfaces.cli.main.Prompt.ask')
    def test_setup_role_credentials(
        self,
        mock_prompt,
        mock_confirm,
        mock_exists,
        mock_config,
        mock_aws_env,
        mock_auth_manager
    ):
        """Test setup with IAM role credentials."""
        mock_exists.return_value = False
        mock_prompt.side_effect = [
            "us-west-2",  # region
            "role",       # cred method
            "arn:aws:iam::123456789012:role/MyRole", # role ARN
        ]
        
        result = runner.invoke(app, ["setup"])
        
        assert result.exit_code == 0
    
    @patch('src.interfaces.cli.main.Path.exists')
    @patch('src.interfaces.cli.main.Confirm.ask')
    @patch('src.interfaces.cli.main.Prompt.ask')
    def test_setup_invalid_credentials_continue(
        self,
        mock_prompt,
        mock_confirm,
        mock_exists,
        mock_config,
        mock_aws_env,
        mock_auth_manager
    ):
        """Test continuing with invalid credentials."""
        mock_exists.return_value = False
        mock_auth_manager.validate_credentials.return_value = False
        mock_confirm.return_value = True  # Continue anyway
        mock_prompt.side_effect = [
            "us-west-2",  # region
            "profile",    # cred method
            "default",    # profile name
        ]
        
        result = runner.invoke(app, ["setup"])
        
        assert result.exit_code == 0
        assert "Failed" in result.output or "continue" in result.output.lower()
    
    @patch('src.interfaces.cli.main.Path.exists')
    @patch('src.interfaces.cli.main.Confirm.ask')
    @patch('src.interfaces.cli.main.Prompt.ask')
    def test_setup_invalid_credentials_abort(
        self,
        mock_prompt,
        mock_confirm,
        mock_exists,
        mock_config,
        mock_aws_env,
        mock_auth_manager
    ):
        """Test aborting with invalid credentials."""
        mock_exists.return_value = False
        mock_auth_manager.validate_credentials.return_value = False
        mock_confirm.return_value = False  # Don't continue
        mock_prompt.side_effect = [
            "us-west-2",  # region
            "profile",    # cred method
            "default",    # profile name
        ]
        
        result = runner.invoke(app, ["setup"])
        
        assert result.exit_code == 1  # Exit with error


class TestCLIArtAndVersion:
    """Test ASCII art and version constants."""
    
    def test_octopus_art_exists(self):
        """Test that octopus ASCII art is defined."""
        assert OCTOPUS_ART is not None
        assert len(OCTOPUS_ART) > 0
        # Should contain some art elements
        assert any(c in OCTOPUS_ART for c in ['█', 'X', '+', '$', '&'])
    
    def test_version_format(self):
        """Test version follows semantic versioning."""
        parts = VERSION.split('.')
        assert len(parts) >= 2
        # Major and minor should be integers
        assert parts[0].isdigit()
        assert parts[1].isdigit()
