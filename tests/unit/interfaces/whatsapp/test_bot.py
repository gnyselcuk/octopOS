"""Unit tests for interfaces/whatsapp/bot.py module.

This module tests the WhatsApp Business API client.
"""

import json
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import aiohttp
import pytest

from src.interfaces.whatsapp.bot import WhatsAppBot, WhatsAppConfig


class TestWhatsAppConfig:
    """Test WhatsApp configuration dataclass."""
    
    def test_default_config(self):
        """Test creating config with defaults."""
        config = WhatsAppConfig(
            phone_number_id="123456789",
            access_token="test_token_123"
        )
        
        assert config.phone_number_id == "123456789"
        assert config.access_token == "test_token_123"
        assert config.api_version == "v18.0"
        assert config.verify_token is None
    
    def test_custom_config(self):
        """Test creating config with custom values."""
        config = WhatsAppConfig(
            phone_number_id="987654321",
            access_token="custom_token",
            api_version="v17.0",
            verify_token="webhook_verify"
        )
        
        assert config.phone_number_id == "987654321"
        assert config.access_token == "custom_token"
        assert config.api_version == "v17.0"
        assert config.verify_token == "webhook_verify"


class AsyncContextManagerMock:
    """Helper class to mock async context managers."""
    
    def __init__(self, return_value):
        self.return_value = return_value
    
    async def __aenter__(self):
        return self.return_value
    
    async def __aexit__(self, *args):
        return False


class TestWhatsAppBot:
    """Test WhatsAppBot class."""
    
    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return WhatsAppConfig(
            phone_number_id="123456789",
            access_token="test_token_123"
        )
    
    @pytest.fixture
    def bot(self, config):
        """Create test bot instance."""
        return WhatsAppBot(config)
    
    @pytest.mark.asyncio
    async def test_bot_initialization(self, bot, config):
        """Test bot initialization."""
        assert bot.config == config
        assert bot._session is None
        assert bot._message_handlers == []
    
    @pytest.mark.asyncio
    async def test_start(self, bot):
        """Test starting the bot."""
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session
            
            await bot.start()
            
            assert bot._session is not None
            mock_session_class.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_stop(self, bot):
        """Test stopping the bot."""
        # Create a proper session mock that supports async close
        class MockSession:
            def __init__(self):
                self.closed = False
            async def close(self):
                self.closed = True
        
        mock_session = MockSession()
        bot._session = mock_session
        
        await bot.stop()
        
        # The close method was called and logged
        assert mock_session.closed is True
    
    @pytest.mark.asyncio
    async def test_stop_without_session(self, bot):
        """Test stopping bot without active session."""
        # Should not raise
        await bot.stop()
    
    @pytest.mark.asyncio
    async def test_send_message_success(self, bot):
        """Test sending a message successfully."""
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.json = AsyncMock(return_value={
            "messaging_product": "whatsapp",
            "contacts": [{"input": "1234567890", "wa_id": "1234567890"}],
            "messages": [{"id": "msg_123"}]
        })
        
        # Create async context manager mock
        post_context = AsyncContextManagerMock(mock_response)
        mock_session.post = MagicMock(return_value=post_context)
        bot._session = mock_session
        
        result = await bot.send_message("1234567890", "Hello, World!")
        
        assert result is True
        mock_session.post.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_message_without_session(self, bot):
        """Test sending message without active session."""
        result = await bot.send_message("1234567890", "Hello")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_send_message_failure(self, bot):
        """Test sending message with API error."""
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.json = AsyncMock(return_value={
            "error": {"message": "Invalid phone number"}
        })
        
        post_context = AsyncContextManagerMock(mock_response)
        mock_session.post = MagicMock(return_value=post_context)
        bot._session = mock_session
        
        result = await bot.send_message("invalid", "Hello")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_send_message_exception(self, bot):
        """Test sending message with network exception."""
        mock_session = AsyncMock()
        mock_session.post = MagicMock(side_effect=aiohttp.ClientError("Network error"))
        bot._session = mock_session
        
        result = await bot.send_message("1234567890", "Hello")
        
        assert result is False
    
    def test_on_message_handler_registration(self, bot):
        """Test registering message handlers."""
        handler1 = Mock()
        handler2 = Mock()
        
        bot.on_message(handler1)
        bot.on_message(handler2)
        
        assert len(bot._message_handlers) == 2
        assert handler1 in bot._message_handlers
        assert handler2 in bot._message_handlers
    
    def test_api_base_format(self, bot, config):
        """Test API base URL formatting."""
        expected = f"https://graph.facebook.com/{config.api_version}/{config.phone_number_id}"
        actual = bot.API_BASE.format(
            version=config.api_version,
            phone_id=config.phone_number_id
        )
        assert actual == expected
    
    @pytest.mark.asyncio
    async def test_send_message_payload_structure(self, bot):
        """Test that message payload has correct structure."""
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.json = AsyncMock(return_value={"messages": [{"id": "msg_123"}]})
        
        post_context = AsyncContextManagerMock(mock_response)
        mock_session.post = MagicMock(return_value=post_context)
        bot._session = mock_session
        
        await bot.send_message("+1234567890", "Test message")
        
        # Check the call arguments
        call_args = mock_session.post.call_args
        assert call_args is not None
        _, kwargs = call_args
        assert "json" in kwargs
        payload = kwargs["json"]
        assert payload["messaging_product"] == "whatsapp"
        assert payload["recipient_type"] == "individual"
        assert payload["to"] == "+1234567890"
        assert payload["type"] == "text"
        assert payload["text"]["body"] == "Test message"
    
    @pytest.mark.asyncio
    async def test_send_message_headers(self, bot):
        """Test that API request includes correct headers."""
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.json = AsyncMock(return_value={"messages": [{"id": "msg_123"}]})
        
        post_context = AsyncContextManagerMock(mock_response)
        mock_session.post = MagicMock(return_value=post_context)
        bot._session = mock_session
        
        await bot.send_message("1234567890", "Hello")
        
        call_args = mock_session.post.call_args
        _, kwargs = call_args
        assert "headers" in kwargs
        headers = kwargs["headers"]
        assert "Authorization" in headers
        assert f"Bearer {bot.config.access_token}" in headers["Authorization"]
