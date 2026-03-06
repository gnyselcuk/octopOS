"""Unit tests for interfaces/slack/bot.py module.

This module tests the SlackBot class for Slack API integration.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import aiohttp

from src.interfaces.slack.bot import SlackBot, SlackConfig


class TestSlackConfig:
    """Test SlackConfig dataclass."""
    
    def test_config_creation(self):
        """Test creating SlackConfig."""
        config = SlackConfig(
            bot_token="xoxb-test-token",
            signing_secret="test_secret",
            app_token="xapp-test-app-token"
        )
        
        assert config.bot_token == "xoxb-test-token"
        assert config.signing_secret == "test_secret"
        assert config.app_token == "xapp-test-app-token"
    
    def test_config_minimal(self):
        """Test creating minimal SlackConfig."""
        config = SlackConfig(
            bot_token="xoxb-token",
            signing_secret="secret"
        )
        
        assert config.bot_token == "xoxb-token"
        assert config.signing_secret == "secret"
        assert config.app_token is None


class TestSlackBotInitialization:
    """Test SlackBot initialization."""
    
    @pytest.fixture
    def config(self):
        """Create a SlackConfig fixture."""
        return SlackConfig(
            bot_token="xoxb-test-token",
            signing_secret="test_secret"
        )
    
    def test_bot_initialization(self, config):
        """Test bot initialization."""
        bot = SlackBot(config)
        
        assert bot.config == config
        assert bot._session is None
        assert bot._running is False
        assert bot._event_handlers == []
    
    def test_api_base_format(self, config):
        """Test API base URL format."""
        bot = SlackBot(config)
        
        expected = "https://slack.com/api/{method}"
        assert bot.API_BASE == expected


class TestSlackBotLifecycle:
    """Test SlackBot lifecycle methods."""
    
    @pytest.fixture
    def bot(self):
        """Create a SlackBot fixture."""
        config = SlackConfig(
            bot_token="xoxb-test-token",
            signing_secret="test_secret"
        )
        return SlackBot(config)
    
    @pytest.mark.asyncio
    async def test_start(self, bot):
        """Test bot start."""
        await bot.start()
        
        assert bot._running is True
        assert bot._session is not None
        assert isinstance(bot._session, aiohttp.ClientSession)
        
        # Check authorization header
        assert "Authorization" in bot._session._default_headers
        assert bot._session._default_headers["Authorization"] == "Bearer xoxb-test-token"
    
    @pytest.mark.asyncio
    async def test_stop(self, bot):
        """Test bot stop."""
        await bot.start()
        await bot.stop()
        
        assert bot._running is False
        assert bot._session is None
    
    @pytest.mark.asyncio
    async def test_stop_without_start(self, bot):
        """Test stopping bot that was never started."""
        # Should not raise an error
        await bot.stop()
        
        assert bot._running is False


class TestSlackBotSendMessage:
    """Test SlackBot send_message method."""
    
    @pytest.fixture
    def bot(self):
        """Create a SlackBot fixture."""
        config = SlackConfig(
            bot_token="xoxb-test-token",
            signing_secret="test_secret"
        )
        return SlackBot(config)
    
    @pytest.mark.asyncio
    async def test_send_message_success(self, bot):
        """Test successful message sending."""
        await bot.start()
        
        # Mock the session.post
        mock_response = MagicMock()
        mock_response.json = AsyncMock(return_value={"ok": True, "ts": "1234567890.123456"})
        
        with patch.object(bot._session, 'post', return_value=mock_response) as mock_post:
            result = await bot.send_message(
                channel="#general",
                text="Hello, World!"
            )
            
            assert result is True
            mock_post.assert_called_once()
            
            # Check call arguments
            call_args = mock_post.call_args
            assert "chat.postMessage" in call_args[0][0]
            assert call_args[1]["json"]["channel"] == "#general"
            assert call_args[1]["json"]["text"] == "Hello, World!"
    
    @pytest.mark.asyncio
    async def test_send_message_with_thread(self, bot):
        """Test sending message in thread."""
        await bot.start()
        
        mock_response = MagicMock()
        mock_response.json = AsyncMock(return_value={"ok": True})
        
        with patch.object(bot._session, 'post', return_value=mock_response) as mock_post:
            await bot.send_message(
                channel="#general",
                text="Thread reply",
                thread_ts="1234567890.123456"
            )
            
            call_args = mock_post.call_args
            assert call_args[1]["json"]["thread_ts"] == "1234567890.123456"
    
    @pytest.mark.asyncio
    async def test_send_message_not_started(self, bot):
        """Test sending message when bot is not started."""
        result = await bot.send_message(
            channel="#general",
            text="Hello"
        )
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_send_message_api_error(self, bot):
        """Test message sending with API error response."""
        await bot.start()
        
        mock_response = MagicMock()
        mock_response.json = AsyncMock(return_value={
            "ok": False,
            "error": "channel_not_found"
        })
        
        with patch.object(bot._session, 'post', return_value=mock_response):
            result = await bot.send_message(
                channel="#nonexistent",
                text="Hello"
            )
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_send_message_exception(self, bot):
        """Test message sending with exception."""
        await bot.start()
        
        with patch.object(bot._session, 'post', side_effect=aiohttp.ClientError("Network error")):
            result = await bot.send_message(
                channel="#general",
                text="Hello"
            )
            
            assert result is False


class TestSlackBotEventHandlers:
    """Test SlackBot event handler registration."""
    
    @pytest.fixture
    def bot(self):
        """Create a SlackBot fixture."""
        config = SlackConfig(
            bot_token="xoxb-test-token",
            signing_secret="test_secret"
        )
        return SlackBot(config)
    
    def test_on_event_registration(self, bot):
        """Test event handler registration."""
        
        async def handler(event):
            pass
        
        bot.on_event(handler)
        
        assert len(bot._event_handlers) == 1
        assert bot._event_handlers[0] == handler
    
    def test_on_event_multiple_handlers(self, bot):
        """Test registering multiple handlers."""
        
        async def handler1(event):
            pass
        
        async def handler2(event):
            pass
        
        bot.on_event(handler1)
        bot.on_event(handler2)
        
        assert len(bot._event_handlers) == 2


class TestSlackBotAPIBase:
    """Test SlackBot API URL construction."""
    
    @pytest.fixture
    def bot(self):
        """Create a SlackBot fixture."""
        config = SlackConfig(
            bot_token="xoxb-test-token",
            signing_secret="test_secret"
        )
        return SlackBot(config)
    
    def test_api_url_construction(self, bot):
        """Test API URL is constructed correctly."""
        url = bot.API_BASE.format(method="chat.postMessage")
        
        assert url == "https://slack.com/api/chat.postMessage"
    
    @pytest.mark.asyncio
    async def test_send_message_uses_correct_url(self, bot):
        """Test that send_message uses the correct API URL."""
        await bot.start()
        
        mock_response = MagicMock()
        mock_response.json = AsyncMock(return_value={"ok": True})
        
        with patch.object(bot._session, 'post', return_value=mock_response) as mock_post:
            await bot.send_message(channel="#general", text="test")
            
            call_args = mock_post.call_args
            assert "https://slack.com/api/chat.postMessage" == call_args[0][0]


class TestSlackBotAuthorization:
    """Test SlackBot authorization handling."""
    
    @pytest.mark.asyncio
    async def test_authorization_header_set(self):
        """Test that authorization header is set on session."""
        config = SlackConfig(
            bot_token="xoxb-my-bot-token",
            signing_secret="secret"
        )
        bot = SlackBot(config)
        
        await bot.start()
        
        assert bot._session._default_headers["Authorization"] == "Bearer xoxb-my-bot-token"
    
    @pytest.mark.asyncio
    async def test_no_authorization_without_token(self):
        """Test behavior when token format differs."""
        config = SlackConfig(
            bot_token="",
            signing_secret="secret"
        )
        bot = SlackBot(config)
        
        await bot.start()
        
        # Even with empty token, header is set
        assert bot._session._default_headers["Authorization"] == "Bearer "


class TestSlackBotChannels:
    """Test SlackBot channel handling."""
    
    @pytest.fixture
    def bot(self):
        """Create a SlackBot fixture."""
        config = SlackConfig(
            bot_token="xoxb-test-token",
            signing_secret="test_secret"
        )
        return SlackBot(config)
    
    @pytest.mark.asyncio
    async def test_send_message_to_channel_id(self, bot):
        """Test sending to channel ID."""
        await bot.start()
        
        mock_response = MagicMock()
        mock_response.json = AsyncMock(return_value={"ok": True})
        
        with patch.object(bot._session, 'post', return_value=mock_response) as mock_post:
            await bot.send_message(
                channel="C1234567890",
                text="Hello"
            )
            
            call_args = mock_post.call_args
            assert call_args[1]["json"]["channel"] == "C1234567890"
    
    @pytest.mark.asyncio
    async def test_send_message_to_user_id(self, bot):
        """Test sending to user ID (DM)."""
        await bot.start()
        
        mock_response = MagicMock()
        mock_response.json = AsyncMock(return_value={"ok": True})
        
        with patch.object(bot._session, 'post', return_value=mock_response) as mock_post:
            await bot.send_message(
                channel="U1234567890",
                text="Hello"
            )
            
            call_args = mock_post.call_args
            assert call_args[1]["json"]["channel"] == "U1234567890"


class TestSlackBotIntegration:
    """Integration-style tests for SlackBot."""
    
    @pytest.mark.asyncio
    async def test_bot_lifecycle_complete(self):
        """Test complete bot lifecycle."""
        config = SlackConfig(
            bot_token="xoxb-test-token",
            signing_secret="test_secret"
        )
        bot = SlackBot(config)
        
        # Start
        await bot.start()
        assert bot._running is True
        assert bot._session is not None
        
        # Register handler
        async def handler(event):
            pass
        
        bot.on_event(handler)
        assert len(bot._event_handlers) == 1
        
        # Stop
        await bot.stop()
        assert bot._running is False
    
    @pytest.mark.asyncio
    async def test_send_and_receive_workflow(self):
        """Test sending message workflow."""
        config = SlackConfig(
            bot_token="xoxb-test-token",
            signing_secret="test_secret"
        )
        bot = SlackBot(config)
        
        await bot.start()
        
        # Mock successful message send
        mock_response = MagicMock()
        mock_response.json = AsyncMock(return_value={
            "ok": True,
            "ts": "1234567890.123456",
            "message": {
                "text": "Hello, World!",
                "user": "U123"
            }
        })
        
        with patch.object(bot._session, 'post', return_value=mock_response):
            result = await bot.send_message(
                channel="#general",
                text="Hello, World!"
            )
            
            assert result is True
        
        await bot.stop()


class TestSlackBotErrorHandling:
    """Test SlackBot error handling."""
    
    @pytest.fixture
    def bot(self):
        """Create a SlackBot fixture."""
        config = SlackConfig(
            bot_token="xoxb-test-token",
            signing_secret="test_secret"
        )
        return SlackBot(config)
    
    @pytest.mark.asyncio
    async def test_rate_limit_error(self, bot):
        """Test handling rate limit error."""
        await bot.start()
        
        mock_response = MagicMock()
        mock_response.json = AsyncMock(return_value={
            "ok": False,
            "error": "ratelimited"
        })
        
        with patch.object(bot._session, 'post', return_value=mock_response):
            result = await bot.send_message(
                channel="#general",
                text="Hello"
            )
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_invalid_auth_error(self, bot):
        """Test handling invalid auth error."""
        await bot.start()
        
        mock_response = MagicMock()
        mock_response.json = AsyncMock(return_value={
            "ok": False,
            "error": "invalid_auth"
        })
        
        with patch.object(bot._session, 'post', return_value=mock_response):
            result = await bot.send_message(
                channel="#general",
                text="Hello"
            )
            
            assert result is False
