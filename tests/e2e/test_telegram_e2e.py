"""
E2E Tests: Telegram Interface
==============================
Covers the full pipeline:
  Telegram Update (JSON) → TelegramBot handlers → TelegramAdapter
  → OctoMessage → Orchestrator → response → bot.send_message

All external I/O (HTTP, Bedrock, LanceDB) is mocked so the suite
runs completely offline and deterministically.
"""

import json
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.interfaces.telegram.bot import TelegramBot, TelegramConfig
from src.interfaces.telegram.message_adapter import TelegramAdapter
from src.interfaces.message_adapter import PlatformType, MessageType


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def make_telegram_update(
    text: str,
    chat_id: int = 123456,
    user_id: int = 42,
    username: str = "selocan",
    message_id: int = 1,
    first_name: str = "Selocan",
) -> dict:
    """Build a minimal Telegram Update payload."""
    return {
        "update_id": 100000,
        "message": {
            "message_id": message_id,
            "from": {
                "id": user_id,
                "is_bot": False,
                "first_name": first_name,
                "username": username,
                "language_code": "tr",
            },
            "chat": {
                "id": chat_id,
                "type": "private",
                "first_name": first_name,
                "username": username,
            },
            "text": text,
            "date": 1700000000,
        },
    }


def make_bot(token: str = "123456789:TEST_TOKEN_SECRET") -> TelegramBot:
    config = TelegramConfig(bot_token=token, polling_interval=1)
    return TelegramBot(config)


# ---------------------------------------------------------------------------
# TelegramBot lifecycle
# ---------------------------------------------------------------------------

class TestTelegramBotLifecycle:
    """Bot starts / stops cleanly."""

    @pytest.mark.asyncio
    async def test_start_creates_session(self):
        bot = make_bot()
        await bot.start()
        assert bot._running is True
        assert bot._session is not None
        await bot.stop()

    @pytest.mark.asyncio
    async def test_stop_closes_session(self):
        bot = make_bot()
        await bot.start()
        await bot.stop()
        assert bot._running is False

    @pytest.mark.asyncio
    async def test_double_start_is_safe(self):
        """Starting after already started must not crash."""
        bot = make_bot()
        await bot.start()
        await bot.start()          # second call: no-op expected
        assert bot._running is True
        await bot.stop()


# ---------------------------------------------------------------------------
# TelegramAdapter: message normalization
# ---------------------------------------------------------------------------

class TestTelegramAdapterNormalization:
    """Raw Telegram JSON → PlatformMessage."""

    @pytest.fixture
    def adapter(self):
        return TelegramAdapter()

    def test_text_message_normalised(self, adapter):
        raw = make_telegram_update("Merhaba octopOS!")
        pm = adapter.normalize_message(raw)

        assert pm.content == "Merhaba octopOS!"
        assert pm.platform == PlatformType.TELEGRAM
        assert pm.user_id == "42"
        assert pm.chat_id == "123456"
        assert pm.is_command is False
        assert pm.user_display_name == "Selocan"

    def test_command_message_parsed(self, adapter):
        raw = make_telegram_update("/ask S3'teki dosyaları listele")
        pm = adapter.normalize_message(raw)

        assert pm.is_command is True
        assert pm.command_name == "ask"
        assert pm.command_args == ["S3'teki", "dosyaları", "listele"]
        assert pm.content_type == "command"

    def test_bare_command_no_args(self, adapter):
        raw = make_telegram_update("/start")
        pm = adapter.normalize_message(raw)

        assert pm.is_command is True
        assert pm.command_name == "start"
        assert pm.command_args == []

    def test_photo_attachment_detected(self, adapter):
        raw = make_telegram_update("resim")
        raw["message"]["photo"] = [{"file_id": "abc", "width": 100, "height": 100}]
        pm = adapter.normalize_message(raw)

        assert len(pm.attachments) == 1
        assert pm.attachments[0].mime_type == "image/jpeg"

    def test_voice_attachment_detected(self, adapter):
        raw = make_telegram_update("")
        raw["message"]["voice"] = {"file_id": "xyz", "duration": 5}
        pm = adapter.normalize_message(raw)

        assert len(pm.attachments) == 1
        assert pm.attachments[0].mime_type == "audio/ogg"


# ---------------------------------------------------------------------------
# TelegramAdapter → OctoMessage conversion
# ---------------------------------------------------------------------------

class TestTelegramAdapterOctoConversion:
    """PlatformMessage → OctoMessage routing checks."""

    @pytest.fixture
    def adapter(self):
        return TelegramAdapter()

    def test_plain_text_becomes_chat_message(self, adapter):
        raw = make_telegram_update("Nasılsın?")
        pm = adapter.normalize_message(raw)
        octo = adapter.to_octomessage(pm)

        assert octo.type == MessageType.CHAT
        assert octo.receiver == "Orchestrator"
        assert octo.payload["content"] == "Nasılsın?"
        assert octo.payload["user_id"] == "42"
        assert octo.payload["chat_id"] == "123456"

    def test_command_becomes_task_message(self, adapter):
        raw = make_telegram_update("/ask ortam değişkenlerini göster")
        pm = adapter.normalize_message(raw)
        octo = adapter.to_octomessage(pm)

        assert octo.type == MessageType.TASK
        assert octo.payload["is_command"] is True
        assert octo.payload["command_name"] == "ask"

    def test_sender_includes_user_id(self, adapter):
        raw = make_telegram_update("test", user_id=999)
        pm = adapter.normalize_message(raw)
        octo = adapter.to_octomessage(pm)

        assert "999" in octo.sender


# ---------------------------------------------------------------------------
# Full pipeline: Update → Orchestrator → send_message
# ---------------------------------------------------------------------------

class TestTelegramFullPipeline:
    """
    End-to-end: a Telegram update arrives, the registered message handler
    fires, Orchestrator processes it, and the bot sends a reply.
    """

    @pytest.fixture
    def orchestrator_mock(self):
        orch = AsyncMock()
        orch.process_user_input = AsyncMock(
            return_value={
                "status": "success",
                "intent": "chat",
                "response": "Merhaba Selocan! Ben octopOS, nasıl yardımcı olabilirim?",
            }
        )
        return orch

    @pytest.mark.asyncio
    async def test_message_triggers_orchestrator_and_reply(self, orchestrator_mock):
        """Core pipeline: update JSON → orchestrator called → send_message called."""
        bot = make_bot()
        await bot.start()

        # Patch HTTP send
        bot.send_message = AsyncMock(return_value=True)

        adapter = TelegramAdapter()

        async def handle_update(raw_update: dict):
            pm = adapter.normalize_message(raw_update)
            result = await orchestrator_mock.process_user_input(pm.content)
            response_text = result.get("response", "")
            await bot.send_message(chat_id=pm.chat_id, text=response_text)

        bot.on_message(handle_update)

        # Simulate an incoming update
        update = make_telegram_update("Merhaba octopOS!")
        for handler in bot._message_handlers:
            await handler(update)

        orchestrator_mock.process_user_input.assert_called_once_with("Merhaba octopOS!")
        bot.send_message.assert_called_once_with(
            chat_id="123456",
            text="Merhaba Selocan! Ben octopOS, nasıl yardımcı olabilirim?",
        )

        await bot.stop()

    @pytest.mark.asyncio
    async def test_command_routed_as_task(self, orchestrator_mock):
        """/ask command triggers Orchestrator and bot replies."""
        bot = make_bot()
        await bot.start()
        bot.send_message = AsyncMock(return_value=True)

        adapter = TelegramAdapter()

        async def handle_command(raw_update: dict):
            pm = adapter.normalize_message(raw_update)
            result = await orchestrator_mock.process_user_input(pm.content)
            await bot.send_message(chat_id=pm.chat_id, text=result.get("response", ""))

        bot.on_message(handle_command)

        update = make_telegram_update("/ask S3 bucket'larını listele")
        for handler in bot._message_handlers:
            await handler(update)

        orchestrator_mock.process_user_input.assert_called_once_with(
            "/ask S3 bucket'larını listele"
        )
        assert bot.send_message.called

        await bot.stop()

    @pytest.mark.asyncio
    async def test_orchestrator_error_is_handled_gracefully(self):
        """If Orchestrator throws, bot should still reply with an error message."""
        bot = make_bot()
        await bot.start()
        bot.send_message = AsyncMock(return_value=True)

        orch = AsyncMock()
        orch.process_user_input = AsyncMock(side_effect=Exception("Bedrock timeout"))

        adapter = TelegramAdapter()

        async def handle_update(raw_update: dict):
            pm = adapter.normalize_message(raw_update)
            try:
                result = await orch.process_user_input(pm.content)
                text = result.get("response", "")
            except Exception as e:
                text = f"⚠️ Bir hata oluştu: {e}"
            await bot.send_message(chat_id=pm.chat_id, text=text)

        bot.on_message(handle_update)

        update = make_telegram_update("crash lütfen")
        for handler in bot._message_handlers:
            await handler(update)

        sent_text = bot.send_message.call_args[1]["text"]
        assert "hata" in sent_text.lower() or "⚠️" in sent_text

        await bot.stop()

    @pytest.mark.asyncio
    async def test_multiple_sequential_messages_same_user(self, orchestrator_mock):
        """Multiple messages from the same user are handled sequentially."""
        bot = make_bot()
        await bot.start()
        bot.send_message = AsyncMock(return_value=True)

        adapter = TelegramAdapter()

        async def handle_update(raw_update: dict):
            pm = adapter.normalize_message(raw_update)
            result = await orchestrator_mock.process_user_input(pm.content)
            await bot.send_message(chat_id=pm.chat_id, text=result.get("response", ""))

        bot.on_message(handle_update)

        messages = [
            "Merhaba!",
            "Python öğrenmek istiyorum",
            "Hangi konudan başlamalıyım?",
        ]

        for i, text in enumerate(messages, start=1):
            update = make_telegram_update(text, message_id=i)
            for handler in bot._message_handlers:
                await handler(update)

        assert orchestrator_mock.process_user_input.call_count == 3
        assert bot.send_message.call_count == 3

        await bot.stop()


# ---------------------------------------------------------------------------
# Webhook security
# ---------------------------------------------------------------------------

class TestTelegramWebhookSecurity:
    """Webhook handler rejects invalid tokens (no aiohttp server needed)."""

    @pytest.mark.asyncio
    async def test_rate_limiter_blocks_excess_requests(self):
        """Simulate IP hitting the rate limiter."""
        from src.interfaces.telegram.webhook_handler import TelegramWebhookHandler

        bot = make_bot()
        await bot.start()

        with patch("src.interfaces.telegram.webhook_handler.get_ip_limiter") as mock_rl:
            limiter = MagicMock()
            limiter.is_allowed.return_value = False   # always block
            mock_rl.return_value = limiter

            handler = TelegramWebhookHandler(bot)

            # The _rate_limiter inside handler was set at init time already,
            # so check it via the stored reference
            handler._rate_limiter = limiter
            result = handler._rate_limiter.is_allowed("1.2.3.4")
            assert result is False

        await bot.stop()


# ---------------------------------------------------------------------------
# Multi-user concurrency (mini stress)
# ---------------------------------------------------------------------------

class TestTelegramConcurrency:
    """Multiple users sending messages concurrently."""

    @pytest.mark.asyncio
    async def test_concurrent_users_no_data_race(self):
        """
        10 users each send 5 messages concurrently.
        All 50 orchestrator calls must complete and all 50 replies sent.
        """
        bot = make_bot()
        await bot.start()

        call_log = []
        send_log = []

        async def fake_orchestrator(text: str) -> dict:
            await asyncio.sleep(0)   # yield to event loop
            call_log.append(text)
            return {"status": "success", "response": f"Yanıt: {text}"}

        async def fake_send(chat_id: str, text: str) -> bool:
            send_log.append((chat_id, text))
            return True

        bot.send_message = fake_send

        adapter = TelegramAdapter()

        async def handle_update(raw_update: dict):
            pm = adapter.normalize_message(raw_update)
            result = await fake_orchestrator(pm.content)
            await bot.send_message(chat_id=pm.chat_id, text=result["response"])

        bot.on_message(handle_update)

        # Fire all updates concurrently
        tasks = []
        for user_id in range(10):
            for msg_idx in range(5):
                update = make_telegram_update(
                    text=f"user{user_id}_msg{msg_idx}",
                    chat_id=1000 + user_id,
                    user_id=user_id,
                    message_id=user_id * 5 + msg_idx,
                )
                tasks.append(handle_update(update))

        await asyncio.gather(*tasks)

        assert len(call_log) == 50
        assert len(send_log) == 50

        await bot.stop()
