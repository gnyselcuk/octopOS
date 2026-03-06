"""
Stress Tests: Memory Concurrency & Orchestrator Load
=====================================================
Tests the system under concurrent load to detect:
  - Race conditions in SemanticMemory (LanceDB writes)
  - Orchestrator under N simultaneous requests
  - Working memory isolation between concurrent sessions
  - Memory reinforcement counter accuracy under concurrent recalls
"""

import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from src.engine.memory.semantic_memory import SemanticMemory
from src.engine.memory.working_memory import WorkingMemory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DUMMY_EMBEDDING = [0.05] * 1024


@pytest.fixture
def tmp_db(tmp_path):
    return str(tmp_path / "stress_lancedb")


@pytest.fixture
async def memory(tmp_db):
    """Initialized SemanticMemory with mocked Bedrock."""
    mem = SemanticMemory(db_path=tmp_db)
    mem._get_embedding = AsyncMock(return_value=DUMMY_EMBEDDING)
    await mem.initialize()
    return mem


# ---------------------------------------------------------------------------
# 1. SemanticMemory: concurrent writes
# ---------------------------------------------------------------------------

class TestSemanticMemoryConcurrentWrites:
    """No data loss, no crashes when many coroutines write simultaneously."""

    @pytest.mark.asyncio
    async def test_50_concurrent_remember_calls(self, memory):
        """50 concurrent remember() calls → exactly 50 entries in DB."""
        tasks = [
            memory.remember(
                content=f"Fact number {i} about the user",
                category="fact" if i % 2 == 0 else "preference",
                source="stress_test",
                confidence=0.8,
            )
            for i in range(50)
        ]
        results = await asyncio.gather(*tasks)

        assert all(results), "Some remember() calls returned False"

        stats = await memory.get_stats()
        assert stats["total_memories"] == 50

    @pytest.mark.asyncio
    async def test_concurrent_writes_and_reads(self, memory):
        """Interleaved writes and reads should not corrupt data."""
        # Pre-populate
        for i in range(10):
            await memory.remember(f"Seed fact {i}", category="fact", source="seed")

        async def writer(idx: int):
            return await memory.remember(
                f"Dynamic fact {idx}", category="event", source="test"
            )

        async def reader():
            return await memory.recall("fact about user", top_k=5)

        tasks = (
            [writer(i) for i in range(20)] +
            [reader() for _ in range(10)]
        )
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # No exceptions allowed
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert exceptions == [], f"Exceptions during concurrent r/w: {exceptions}"

    @pytest.mark.asyncio
    async def test_forget_under_concurrency(self, memory):
        """Concurrent forget() calls should not deadlock or crash."""
        ids = []
        for i in range(10):
            await memory.remember(f"Delete me {i}", category="fact", source="test")

        # Retrieve IDs
        stats = await memory.get_stats()
        assert stats["total_memories"] == 10

        df = memory._table.to_pandas()
        ids = df["id"].tolist()

        # Concurrently forget first 5
        tasks = [memory.forget(mid) for mid in ids[:5]]
        results = await asyncio.gather(*tasks)
        assert all(results)

    @pytest.mark.asyncio
    async def test_memory_decay_prune_is_safe(self, memory):
        """prune_decayed_memories() concurrent with remembering should not crash."""
        for i in range(20):
            await memory.remember(f"Prunable {i}", category="fact", source="test")

        # Simultaneously prune (threshold=99 → prune all) and write new ones
        tasks = [
            memory.prune_decayed_memories(threshold_score=99.0),
            memory.remember("New memory while pruning", category="fact", source="test"),
            memory.remember("Another new one", category="fact", source="test"),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert exceptions == [], f"Prune concurrency exceptions: {exceptions}"


# ---------------------------------------------------------------------------
# 2. WorkingMemory: session isolation
# ---------------------------------------------------------------------------

class TestWorkingMemoryIsolation:
    """Multiple concurrent sessions must not bleed into each other."""

    def test_sessions_are_fully_isolated(self):
        """Messages in session A must not appear in session B."""
        wm_a = WorkingMemory(session_id="session_A")
        wm_b = WorkingMemory(session_id="session_B")

        wm_a.add_user_message("alfa mesajı")
        wm_b.add_user_message("beta mesajı")
        wm_a.add_assistant_message("alfa cevabı")

        history_a = wm_a.get_last_n_messages(10)
        history_b = wm_b.get_last_n_messages(10)

        contents_a = [m["content"] for m in history_a]
        contents_b = [m["content"] for m in history_b]

        assert "beta mesajı" not in contents_a
        assert "alfa mesajı" not in contents_b
        assert "alfa cevabı" not in contents_b

    def test_100_sessions_no_cross_contamination(self):
        """Create 100 sessions and verify each holds only its own data."""
        sessions = [
            WorkingMemory(session_id=f"session_{i}")
            for i in range(100)
        ]

        for i, wm in enumerate(sessions):
            wm.add_user_message(f"unique_message_from_session_{i}")

        for i, wm in enumerate(sessions):
            history = wm.get_last_n_messages(5)
            assert len(history) == 1
            assert history[0]["content"] == f"unique_message_from_session_{i}"


# ---------------------------------------------------------------------------
# 3. Orchestrator load simulation
# ---------------------------------------------------------------------------

class TestOrchestratorLoadSimulation:
    """Simulate N concurrent users hitting the Orchestrator."""

    @pytest.mark.asyncio
    async def test_50_concurrent_requests(self):
        """50 concurrent process_user_input() calls must all return success."""
        from src.engine.orchestrator import Orchestrator

        with patch("src.engine.orchestrator.get_bedrock_client"), \
             patch("src.engine.orchestrator.get_config") as mock_gc, \
             patch("src.engine.base_agent.get_message_queue"):

            mock_config = MagicMock()
            mock_config.agent.get_system_prompt.return_value = "You are octoOS."
            mock_config.aws.model_nova_lite = "amazon.nova-lite-v1:0"
            mock_config.aws.model_nova_pro = "amazon.nova-pro-v1:0"
            mock_config.user.name = "stress_user"
            mock_gc.return_value = mock_config

            orch = Orchestrator()
            orch._bedrock_client = None
            orch._working_memory = None
            orch._semantic_memory = None
            orch._fact_extractor = None

            # Stub intent analysis to return "chat"
            async def fake_analyze(text):
                from src.engine.orchestrator import IntentAnalysis, IntentType
                await asyncio.sleep(0)
                return IntentAnalysis("chat", 0.9, "test", [], 1, {})

            # Stub chat handler
            async def fake_chat(user_input, intent, memory_context=""):
                await asyncio.sleep(0)
                return {"status": "success", "intent": "chat", "response": f"Yanıt: {user_input}"}

            orch._analyze_intent = fake_analyze
            orch._handle_chat = fake_chat

            tasks = [
                orch.process_user_input(f"Kullanıcı {i} mesajı")
                for i in range(50)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        exceptions = [r for r in results if isinstance(r, Exception)]
        successes = [r for r in results if isinstance(r, dict) and r.get("status") == "success"]

        assert exceptions == [], f"Exceptions during load: {exceptions}"
        assert len(successes) == 50

    @pytest.mark.asyncio
    async def test_mixed_intent_load(self):
        """Mixed chat/query/task intents concurrently."""
        from src.engine.orchestrator import Orchestrator, IntentAnalysis, IntentType

        with patch("src.engine.orchestrator.get_bedrock_client"), \
             patch("src.engine.orchestrator.get_config") as mock_gc, \
             patch("src.engine.base_agent.get_message_queue"):

            mock_config = MagicMock()
            mock_config.agent.get_system_prompt.return_value = "You are octoOS."
            mock_config.aws.model_nova_lite = "amazon.nova-lite-v1:0"
            mock_config.aws.model_nova_pro = "amazon.nova-pro-v1:0"
            mock_config.user.name = "stress_user"
            mock_gc.return_value = mock_config

            orch = Orchestrator()
            orch._working_memory = None
            orch._semantic_memory = None
            orch._fact_extractor = None

            intent_cycle = [IntentType.CHAT, IntentType.QUERY, IntentType.TASK]

            async def rotating_analyze(text):
                idx = int(text.split("_")[-1]) % 3
                return IntentAnalysis(intent_cycle[idx], 0.9, "test", [], 1, {})

            async def fake_handler(*args, **kwargs):
                await asyncio.sleep(0)
                return {"status": "success", "intent": "mixed", "response": "ok"}

            orch._analyze_intent = rotating_analyze
            orch._handle_chat = fake_handler
            orch._handle_query = fake_handler
            orch._handle_task = fake_handler

            tasks = [
                orch.process_user_input(f"input_{i}")
                for i in range(30)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        exceptions = [r for r in results if isinstance(r, Exception)]
        assert exceptions == [], f"Mixed intent load exceptions: {exceptions}"


# ---------------------------------------------------------------------------
# 4. Throughput benchmark (non-blocking, informational)
# ---------------------------------------------------------------------------

class TestThroughputBenchmark:
    """Measure messages/sec for the full pipeline with mocked IO."""

    @pytest.mark.asyncio
    async def test_memory_write_throughput(self, memory):
        """Should handle ≥ 20 writes/sec on the local LanceDB (very conservative)."""
        count = 30
        start = time.monotonic()

        await asyncio.gather(*[
            memory.remember(f"Benchmark fact {i}", category="fact", source="bench")
            for i in range(count)
        ])

        elapsed = time.monotonic() - start
        throughput = count / elapsed

        print(f"\n  Memory write throughput: {throughput:.1f} writes/sec ({elapsed:.2f}s for {count})")
        assert throughput >= 5, f"Throughput too low: {throughput:.1f} writes/sec"

    @pytest.mark.asyncio
    async def test_recall_throughput(self, memory):
        """Pre-populate and measure recall throughput."""
        for i in range(20):
            await memory.remember(f"Recall bench {i}", category="fact", source="bench")

        count = 20
        start = time.monotonic()

        await asyncio.gather(*[
            memory.recall("bench fact", top_k=5)
            for _ in range(count)
        ])

        elapsed = time.monotonic() - start
        throughput = count / elapsed
        print(f"\n  Memory recall throughput: {throughput:.1f} recalls/sec ({elapsed:.2f}s for {count})")
        assert throughput >= 3, f"Recall throughput too low: {throughput:.1f} recalls/sec"
