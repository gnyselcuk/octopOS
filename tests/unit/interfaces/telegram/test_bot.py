"""Unit tests for interfaces/telegram/bot.py module.

This module tests the TelegramBot class for Telegram Bot API integration.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import aiohttp

from src.interfaces.telegram.bot import TelegramBot, TelegramConfig


def make_aiohttp_context(response):
    """Build an async context manager that yields a mocked response."""
    context = AsyncMock()
    context.__aenter__.return_value = response
    context.__aexit__.return_value = False
    return context


class TestTelegramConfig:
    """Test TelegramConfig dataclass."""
    
    def test_config_creation(self):
        """Test creating TelegramConfig."""
        config = TelegramConfig(
            bot_token="test_token_123",
            webhook_url="https://example.com/webhook",
            polling_interval=5,
            allowed_updates=["message", "callback_query"]
        )
        
        assert config.bot_token == "test_token_123"
        assert config.webhook_url == "https://example.com/webhook"
        assert config.polling_interval == 5
        assert config.allowed_updates == ["message", "callback_query"]
    
    def test_config_defaults(self):
        """Test TelegramConfig default values."""
        config = TelegramConfig(bot_token="token")
        
        assert config.webhook_url is None
        assert config.polling_interval == 1
        assert config.allowed_updates == ["message", "callback_query"]
    
    def test_config_custom_allowed_updates(self):
        """Test TelegramConfig with custom allowed updates."""
        config = TelegramConfig(
            bot_token="token",
            allowed_updates=["message", "edited_message"]
        )
        
        assert config.allowed_updates == ["message", "edited_message"]


class TestTelegramBotInitialization:
    """Test TelegramBot initialization."""
    
    @pytest.fixture
    def config(self):
        """Create a TelegramConfig fixture."""
        return TelegramConfig(bot_token="test_token_123")
    
    def test_bot_initialization(self, config):
        """Test bot initialization."""
        bot = TelegramBot(config)
        
        assert bot.config == config
        assert bot._session is None
        assert bot._running is False
        assert bot._message_handlers == []
    
    def test_api_base_format(self, config):
        """Test API base URL format."""
        bot = TelegramBot(config)
        
        expected = "https://api.telegram.org/bot{token}/{method}"
        assert bot.API_BASE == expected


class TestTelegramBotLifecycle:
    """Test TelegramBot lifecycle methods."""
    
    @pytest.fixture
    def bot(self):
        """Create a TelegramBot fixture."""
        config = TelegramConfig(bot_token="test_token")
        return TelegramBot(config)
    
    @pytest.mark.asyncio
    async def test_start(self, bot):
        """Test bot start."""
        await bot.start()
        
        assert bot._running is True
        assert bot._session is not None
        assert isinstance(bot._session, aiohttp.ClientSession)
    
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


class TestTelegramBotSendMessage:
    """Test TelegramBot send_message method."""
    
    @pytest.fixture
    def bot(self):
        """Create a TelegramBot fixture with mocked session."""
        config = TelegramConfig(bot_token="test_token")
        bot = TelegramBot(config)
        return bot
    
    @pytest.mark.asyncio
    async def test_send_message_success(self, bot):
        """Test successful message sending."""
        await bot.start()
        
        # Mock the session.post
        mock_response = MagicMock()
        mock_response.status = 200
        
        with patch.object(bot._session, 'post', return_value=make_aiohttp_context(mock_response)) as mock_post:
            result = await bot.send_message(
                chat_id="123456",
                text="Hello, World!"
            )
            
            assert result is True
            mock_post.assert_called_once()
            
            # Check call arguments
            call_args = mock_post.call_args
            assert "sendMessage" in call_args[0][0]
            assert call_args[1]["json"]["chat_id"] == "123456"
            assert call_args[1]["json"]["text"] == "Hello, World!"
            assert call_args[1]["json"]["parse_mode"] == "HTML"
    
    @pytest.mark.asyncio
    async def test_send_message_with_reply(self, bot):
        """Test sending message with reply."""
        await bot.start()
        
        mock_response = MagicMock()
        mock_response.status = 200
        
        with patch.object(bot._session, 'post', return_value=make_aiohttp_context(mock_response)) as mock_post:
            await bot.send_message(
                chat_id="123456",
                text="Reply text",
                reply_to="message_789"
            )
            
            call_args = mock_post.call_args
            assert call_args[1]["json"]["reply_to_message_id"] == "message_789"
    
    @pytest.mark.asyncio
    async def test_send_message_not_started(self, bot):
        """Test sending message when bot is not started."""
        result = await bot.send_message(
            chat_id="123456",
            text="Hello"
        )
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_send_message_failure(self, bot):
        """Test message sending failure."""
        await bot.start()
        
        mock_response = MagicMock()
        mock_response.status = 400
        
        with patch.object(bot._session, 'post', return_value=make_aiohttp_context(mock_response)):
            result = await bot.send_message(
                chat_id="123456",
                text="Hello"
            )
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_send_message_exception(self, bot):
        """Test message sending with exception."""
        await bot.start()
        
        with patch.object(bot._session, 'post', side_effect=aiohttp.ClientError("Network error")):
            result = await bot.send_message(
                chat_id="123456",
                text="Hello"
            )
            
            assert result is False


class TestTelegramBotMessageHandlers:
    """Test TelegramBot message handler registration."""
    
    @pytest.fixture
    def bot(self):
        """Create a TelegramBot fixture."""
        config = TelegramConfig(bot_token="test_token")
        return TelegramBot(config)
    
    def test_on_message_registration(self, bot):
        """Test message handler registration."""
        
        async def handler(message):
            pass
        
        bot.on_message(handler)
        
        assert len(bot._message_handlers) == 1
        assert bot._message_handlers[0] == handler
    
    def test_on_message_multiple_handlers(self, bot):
        """Test registering multiple handlers."""
        
        async def handler1(message):
            pass
        
        async def handler2(message):
            pass
        
        bot.on_message(handler1)
        bot.on_message(handler2)
        
        assert len(bot._message_handlers) == 2


class TestTelegramBotAPIBase:
    """Test TelegramBot API URL construction."""
    
    @pytest.fixture
    def bot(self):
        """Create a TelegramBot fixture."""
        config = TelegramConfig(bot_token="my_bot_token")
        return TelegramBot(config)
    
    def test_api_url_construction(self, bot):
        """Test API URL is constructed correctly."""
        url = bot.API_BASE.format(
            token=bot.config.bot_token,
            method="sendMessage"
        )
        
        assert url == "https://api.telegram.org/botmy_bot_token/sendMessage"
    
    @pytest.mark.asyncio
    async def test_send_message_uses_correct_url(self, bot):
        """Test that send_message uses the correct API URL."""
        await bot.start()
        
        mock_response = MagicMock()
        mock_response.status = 200
        
        with patch.object(bot._session, 'post', return_value=make_aiohttp_context(mock_response)) as mock_post:
            await bot.send_message(chat_id="123", text="test")
            
            call_args = mock_post.call_args
            assert "https://api.telegram.org/botmy_bot_token/sendMessage" == call_args[0][0]

        await bot.stop()


class TestTelegramBotParseModes:
    """Test different parse modes for messages."""
    
    @pytest.fixture
    def bot(self):
        """Create a TelegramBot fixture."""
        config = TelegramConfig(bot_token="test_token")
        bot = TelegramBot(config)
        return bot
    
    @pytest.mark.asyncio
    async def test_send_message_html_parse_mode(self, bot):
        """Test sending message with HTML parse mode (default)."""
        await bot.start()
        
        mock_response = MagicMock()
        mock_response.status = 200
        
        with patch.object(bot._session, 'post', return_value=make_aiohttp_context(mock_response)) as mock_post:
            await bot.send_message(
                chat_id="123",
                text="<b>Bold</b> text",
                parse_mode="HTML"
            )
            
            call_args = mock_post.call_args
            assert call_args[1]["json"]["parse_mode"] == "HTML"
    
    @pytest.mark.asyncio
    async def test_send_message_markdown_parse_mode(self, bot):
        """Test sending message with Markdown parse mode."""
        await bot.start()
        
        mock_response = MagicMock()
        mock_response.status = 200
        
        with patch.object(bot._session, 'post', return_value=make_aiohttp_context(mock_response)) as mock_post:
            await bot.send_message(
                chat_id="123",
                text="*Bold* text",
                parse_mode="Markdown"
            )
            
            call_args = mock_post.call_args
            assert call_args[1]["json"]["parse_mode"] == "Markdown"


class TestTelegramBotIntegration:
    """Integration-style tests for TelegramBot."""
    
    @pytest.mark.asyncio
    async def test_bot_lifecycle_complete(self):
        """Test complete bot lifecycle."""
        config = TelegramConfig(bot_token="test_token")
        bot = TelegramBot(config)
        
        # Start
        await bot.start()
        assert bot._running is True
        
        # Register handler
        async def handler(message):
            pass
        
        bot.on_message(handler)
        assert len(bot._message_handlers) == 1
        
        # Stop
        await bot.stop()
        assert bot._running is False


class TestTelegramBotPolling:
    """Test Telegram long polling helpers."""

    @pytest.fixture
    def bot(self):
        config = TelegramConfig(bot_token="test_token")
        return TelegramBot(config)

    @pytest.mark.asyncio
    async def test_poll_once_updates_offset_and_dispatches(self, bot):
        bot.get_updates = AsyncMock(return_value=[
            {"update_id": 10, "message": {"text": "one"}},
            {"update_id": 11, "message": {"text": "two"}},
        ])
        bot.process_update = AsyncMock()

        next_offset = await bot.poll_once(timeout=5)

        assert next_offset == 12
        assert bot._update_offset == 12
        assert bot.process_update.await_count == 2
        bot.get_updates.assert_awaited_once_with(offset=0, timeout=5)

    @pytest.mark.asyncio
    async def test_poll_once_without_updates_keeps_offset(self, bot):
        bot._update_offset = 21
        bot.get_updates = AsyncMock(return_value=[])
        bot.process_update = AsyncMock()

        next_offset = await bot.poll_once()

        assert next_offset == 21
        assert bot._update_offset == 21
        bot.process_update.assert_not_awaited()
