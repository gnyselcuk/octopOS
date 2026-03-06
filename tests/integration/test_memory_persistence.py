import pytest
import asyncio
from unittest.mock import AsyncMock
from datetime import datetime, timedelta

from src.engine.memory.semantic_memory import SemanticMemory, MemoryEntry

@pytest.fixture
def mock_embedding():
    """Provides a dummy 1024-dimensional embedding vector."""
    return [0.1] * 1024

@pytest.mark.asyncio
async def test_memory_persistence_and_recall(tmp_path, mock_embedding):
    """
    Test that LanceDB memory survives restarts, can be recalled,
    and supports memory decay/reinforcement (synaptic pruning bounds).
    """
    db_path = str(tmp_path / "lancedb_test")
    memory = SemanticMemory(db_path=db_path)
    
    # Mock _get_embedding to avoid AWS Bedrock calls
    memory._get_embedding = AsyncMock(return_value=mock_embedding)
    
    # Initialize
    await memory.initialize()
    
    # 1. Remember some facts
    await memory.remember("User lives in Istanbul", category="fact", source="test_1")
    await memory.remember("User prefers Node.js for backend", category="preference", source="test_2")
    
    # Verify they are stored
    stats = await memory.get_stats()
    assert stats["total_memories"] == 2
    
    # 2. Simulate System Restart (close and reopen)
    memory_restarted = SemanticMemory(db_path=db_path)
    memory_restarted._get_embedding = AsyncMock(return_value=mock_embedding)
    await memory_restarted.initialize()
    
    # Verify persistence
    stats_restarted = await memory_restarted.get_stats()
    assert stats_restarted["total_memories"] == 2
    
    # 3. Test Recall and Reinforcement
    results = await memory_restarted.recall("Where does user live?")
    
    # Since mock vectors are identical, distance is 0, both are returned
    assert len(results) == 2
    
    # Before the recall, access_count was 1. Recall triggers _reinforce_memories
    # Let's do another recall to check if access_count was incremented to 2
    results_after_reinforce = await memory_restarted.recall("Where does user live?")
    
    # Check if access_count was incremented
    assert results_after_reinforce[0].access_count >= 2
    
    # 4. Test Memory Pruning (Garbage Collection)
    # We will set a high threshold (e.g., 5.0) which should prune our memories since score is ~2 * 1.0 - 0 = 2.0
    pruned_count = await memory_restarted.prune_decayed_memories(threshold_score=5.0)
    assert pruned_count == 2
    
    # Verify they were deleted
    stats_final = await memory_restarted.get_stats()
    assert stats_final["total_memories"] == 0
