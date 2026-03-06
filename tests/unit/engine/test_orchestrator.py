"""Unit tests for engine/orchestrator.py - Main Brain Orchestrator.

Tests the Orchestrator's intent routing, agent lifecycle,
and core processing pipeline using mocked external dependencies.
"""

import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from src.engine.orchestrator import (
    Orchestrator,
    IntentType,
    IntentAnalysis,
    SubTask,
    get_orchestrator,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_bedrock_client():
    """Return a mock Bedrock client."""
    return MagicMock()


@pytest.fixture
def orchestrator(mock_bedrock_client):
    """Fully constructed Orchestrator with mocked dependencies."""
    with patch("src.engine.orchestrator.get_bedrock_client", return_value=mock_bedrock_client), \
         patch("src.engine.orchestrator.get_config") as mock_gc, \
         patch("src.engine.base_agent.get_message_queue") as mock_mq:

        mock_config = MagicMock()
        mock_config.agent.get_system_prompt.return_value = "You are octoOS."
        mock_config.agent.name = "octoOS"
        mock_config.aws.model_nova_lite = "amazon.nova-lite-v1:0"
        mock_config.aws.model_nova_pro = "amazon.nova-pro-v1:0"
        mock_config.user.name = "test_user"
        mock_gc.return_value = mock_config

        mock_mq.return_value = MagicMock()

        orch = Orchestrator()
        orch._bedrock_client = mock_bedrock_client
        orch._working_memory = None
        orch._semantic_memory = None
        orch._fact_extractor = None
        return orch


# ---------------------------------------------------------------------------
# IntentAnalysis
# ---------------------------------------------------------------------------

class TestIntentAnalysis:
    """Test IntentAnalysis dataclass."""

    def test_create_intent(self):
        intent = IntentAnalysis(
            intent_type=IntentType.CHAT,
            confidence=0.9,
            description="Casual chat",
            required_agents=["MainBrain"],
            estimated_steps=1,
            context={},
        )
        assert intent.intent_type == "chat"
        assert intent.confidence == 0.9
        assert intent.estimated_steps == 1

    def test_intent_types_defined(self):
        assert IntentType.CHAT == "chat"
        assert IntentType.TASK == "task"
        assert IntentType.CODE == "code"
        assert IntentType.DEBUG == "debug"
        assert IntentType.QUERY == "query"
        assert IntentType.MISSION == "mission"
        assert IntentType.BROWSER == "browser"


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

class TestOrchestratorInit:
    """Test Orchestrator initialization."""

    def test_name_set(self, orchestrator):
        assert orchestrator.name == "MainBrain"

    def test_memory_components_none_on_init(self, orchestrator):
        assert orchestrator._working_memory is None
        assert orchestrator._semantic_memory is None
        assert orchestrator._fact_extractor is None


# ---------------------------------------------------------------------------
# _analyze_intent
# ---------------------------------------------------------------------------

class TestAnalyzeIntent:
    """Test intent analysis via Bedrock."""

    def _mock_bedrock_response(self, client, intent_type, confidence=0.95):
        payload = json.dumps({
            "intent_type": intent_type,
            "confidence": confidence,
            "description": f"test {intent_type}",
            "required_agents": ["MainBrain"],
            "estimated_steps": 1,
            "context": {},
        })
        client.converse.return_value = {
            "output": {
                "message": {
                    "content": [{"text": payload}]
                }
            }
        }

    @pytest.mark.asyncio
    async def test_chat_intent(self, orchestrator, mock_bedrock_client):
        self._mock_bedrock_response(mock_bedrock_client, "chat")
        intent = await orchestrator._analyze_intent("Merhaba nasılsın?")
        assert intent.intent_type == IntentType.CHAT
        assert intent.confidence == 0.95

    @pytest.mark.asyncio
    async def test_task_intent(self, orchestrator, mock_bedrock_client):
        self._mock_bedrock_response(mock_bedrock_client, "task")
        intent = await orchestrator._analyze_intent("S3'e dosya yükle")
        assert intent.intent_type == IntentType.TASK

    @pytest.mark.asyncio
    async def test_query_intent(self, orchestrator, mock_bedrock_client):
        self._mock_bedrock_response(mock_bedrock_client, "query")
        intent = await orchestrator._analyze_intent("Disk kullanımı nedir?")
        assert intent.intent_type == IntentType.QUERY

    @pytest.mark.asyncio
    async def test_fallback_on_error(self, orchestrator, mock_bedrock_client):
        mock_bedrock_client.converse.side_effect = Exception("API Error")
        intent = await orchestrator._analyze_intent("anything")
        # Should gracefully fall back to chat
        assert intent.intent_type == IntentType.CHAT
        assert intent.confidence == 0.5

    @pytest.mark.asyncio
    async def test_json_codeblock_parsing(self, orchestrator, mock_bedrock_client):
        """Test that ```json ``` wrappers are stripped correctly."""
        payload = json.dumps({
            "intent_type": "code",
            "confidence": 0.88,
            "description": "Write code",
            "required_agents": [],
            "estimated_steps": 2,
            "context": {},
        })
        mock_bedrock_client.converse.return_value = {
            "output": {
                "message": {
                    "content": [{"text": f"```json\n{payload}\n```"}]
                }
            }
        }
        intent = await orchestrator._analyze_intent("Bir Python scripti yaz")
        assert intent.intent_type == IntentType.CODE
        assert intent.confidence == 0.88


# ---------------------------------------------------------------------------
# _handle_chat
# ---------------------------------------------------------------------------

class TestHandleChat:
    """Test _handle_chat method."""

    @pytest.fixture
    def chat_intent(self):
        return IntentAnalysis("chat", 0.9, "chat", [], 1, {})

    @pytest.mark.asyncio
    async def test_chat_success(self, orchestrator, mock_bedrock_client, chat_intent):
        mock_bedrock_client.converse.return_value = {
            "output": {
                "message": {"content": [{"text": "Merhaba! Nasıl yardımcı olabilirim?"}]}
            }
        }
        result = await orchestrator._handle_chat("Merhaba", chat_intent)
        assert result["status"] == "success"
        assert result["intent"] == "chat"
        assert "response" in result
        assert len(result["response"]) > 0

    @pytest.mark.asyncio
    async def test_chat_with_memory_context(self, orchestrator, mock_bedrock_client, chat_intent):
        mock_bedrock_client.converse.return_value = {
            "output": {
                "message": {"content": [{"text": "İstanbul'dasınız, harika!"}]}
            }
        }
        result = await orchestrator._handle_chat(
            "Şehir etkinlikleri neler?", chat_intent,
            memory_context="- Kullanıcı İstanbul'da yaşıyor"
        )
        assert result["status"] == "success"
        # Verify system prompt included memory context
        call_kwargs = mock_bedrock_client.converse.call_args
        system_text = call_kwargs[1]["system"][0]["text"]
        assert "İstanbul" in system_text

    @pytest.mark.asyncio
    async def test_chat_bedrock_error(self, orchestrator, mock_bedrock_client, chat_intent):
        mock_bedrock_client.converse.side_effect = Exception("Timeout")
        result = await orchestrator._handle_chat("hi", chat_intent)
        assert result["status"] == "error"
        assert "message" in result


# ---------------------------------------------------------------------------
# process_user_input routing
# ---------------------------------------------------------------------------

class TestProcessUserInput:
    """Test that process_user_input routes to the correct handler."""

    def _stub_intent(self, orchestrator, intent_type):
        intent = IntentAnalysis(intent_type, 0.95, "test", [], 1, {})
        mock_analyze = AsyncMock(return_value=intent)
        orchestrator._analyze_intent = mock_analyze
        return intent

    @pytest.mark.asyncio
    async def test_routes_chat(self, orchestrator):
        self._stub_intent(orchestrator, IntentType.CHAT)
        orchestrator._handle_chat = AsyncMock(return_value={"status": "success", "response": "hi"})

        result = await orchestrator.process_user_input("Merhaba")
        orchestrator._handle_chat.assert_called_once()
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_routes_query(self, orchestrator):
        self._stub_intent(orchestrator, IntentType.QUERY)
        orchestrator._handle_query = AsyncMock(return_value={"status": "success", "response": "disk: 50%"})

        result = await orchestrator.process_user_input("Disk kullanımı nedir?")
        orchestrator._handle_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_task(self, orchestrator):
        self._stub_intent(orchestrator, IntentType.TASK)
        orchestrator._handle_task = AsyncMock(return_value={"status": "success", "results": []})

        result = await orchestrator.process_user_input("Dosyaları yedekle")
        orchestrator._handle_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_stores_messages_in_working_memory(self, orchestrator):
        self._stub_intent(orchestrator, IntentType.CHAT)
        orchestrator._handle_chat = AsyncMock(return_value={"status": "success", "response": "Yanıt"})

        mock_wm = MagicMock()
        orchestrator._working_memory = mock_wm

        await orchestrator.process_user_input("Test mesajı")

        mock_wm.add_user_message.assert_called_once_with("Test mesajı")
        mock_wm.add_assistant_message.assert_called_once_with("Yanıt")

    @pytest.mark.asyncio
    async def test_unknown_intent_falls_back_to_chat(self, orchestrator):
        self._stub_intent(orchestrator, "unknown_intent")
        orchestrator._handle_chat = AsyncMock(return_value={"status": "success", "response": "fallback"})

        await orchestrator.process_user_input("Belirsiz mesaj")
        orchestrator._handle_chat.assert_called_once()


# ---------------------------------------------------------------------------
# execute_task action routing
# ---------------------------------------------------------------------------

class TestExecuteTask:
    """Test execute_task dispatch."""

    @pytest.mark.asyncio
    async def test_process_user_input_action(self, orchestrator):
        orchestrator.process_user_input = AsyncMock(return_value={"status": "success", "response": "ok"})
        task = MagicMock()
        task.action = "process_user_input"
        task.params = {"input": "hello"}

        result = await orchestrator.execute_task(task)
        orchestrator.process_user_input.assert_called_once_with("hello")
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_analyze_intent_action(self, orchestrator):
        orchestrator._analyze_intent = AsyncMock(
            return_value=IntentAnalysis("chat", 0.9, "test", [], 1, {})
        )
        task = MagicMock()
        task.action = "analyze_intent"
        task.params = {"text": "test text"}

        await orchestrator.execute_task(task)
        orchestrator._analyze_intent.assert_called_once_with("test text")

    @pytest.mark.asyncio
    async def test_prune_memory_action(self, orchestrator):
        mock_sm = AsyncMock()
        mock_sm.prune_decayed_memories = AsyncMock(return_value=3)
        orchestrator._semantic_memory = mock_sm

        task = MagicMock()
        task.action = "prune_memory"
        task.params = {}

        result = await orchestrator.execute_task(task)
        assert result["status"] == "success"
        assert result["pruned_count"] == 3

    @pytest.mark.asyncio
    async def test_prune_memory_no_semantic_memory(self, orchestrator):
        orchestrator._semantic_memory = None
        task = MagicMock()
        task.action = "prune_memory"
        task.params = {}

        result = await orchestrator.execute_task(task)
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_unknown_action(self, orchestrator):
        task = MagicMock()
        task.action = "nonexistent_action"
        task.params = {}

        result = await orchestrator.execute_task(task)
        assert result["status"] == "error"
        assert "Unknown action" in result["message"]


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

class TestGetOrchestrator:
    """Test get_orchestrator singleton."""

    def test_singleton_returns_same_instance(self):
        with patch("src.engine.orchestrator.get_config"), \
             patch("src.engine.base_agent.get_message_queue"):
            import src.engine.orchestrator as mod
            mod._orchestrator = None

            o1 = get_orchestrator()
            o2 = get_orchestrator()
            assert o1 is o2

            # Cleanup
            mod._orchestrator = None
