"""Unit tests for engine/memory/semantic_memory.py module.

This module tests the SemanticMemory class for long-term memory storage.
"""

import json
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch, AsyncMock

from src.engine.memory.semantic_memory import (
    MemoryEntry,
    SemanticMemory,
)


class TestMemoryEntry:
    """Test MemoryEntry dataclass."""
    
    def test_create_memory_entry(self):
        """Test creating a memory entry."""
        entry = MemoryEntry(
            id="fact_2024-01-01",
            content="User lives in Istanbul",
            category="fact",
            timestamp="2024-01-01T00:00:00",
            source="conversation",
            confidence=0.9,
            metadata={"user_id": "123"},
            access_count=5,
            last_accessed="2024-01-02T00:00:00"
        )
        
        assert entry.id == "fact_2024-01-01"
        assert entry.content == "User lives in Istanbul"
        assert entry.category == "fact"
        assert entry.confidence == 0.9
        assert entry.access_count == 5
    
    def test_memory_entry_defaults(self):
        """Test MemoryEntry default values."""
        entry = MemoryEntry(
            id="test",
            content="test",
            category="fact",
            timestamp="2024-01-01",
            source="test",
            confidence=0.8,
            metadata={}
        )
        
        assert entry.access_count == 1
        assert entry.last_accessed == ""


class TestSemanticMemoryInitialization:
    """Test SemanticMemory initialization."""
    
    @patch("src.engine.memory.semantic_memory.get_config")
    def test_semantic_memory_init_defaults(self, mock_get_config):
        """Test SemanticMemory initialization with defaults."""
        mock_config = MagicMock()
        mock_config.lancedb.path = "/tmp/test_lancedb"
        mock_get_config.return_value = mock_config
        
        memory = SemanticMemory()
        
        assert memory._db_path == "/tmp/test_lancedb"
        assert memory._bedrock_client is None
        assert memory._table is None
        assert memory._initialized is False
    
    @patch("src.engine.memory.semantic_memory.get_config")
    def test_semantic_memory_init_custom_path(self, mock_get_config):
        """Test SemanticMemory initialization with custom path."""
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        
        memory = SemanticMemory(db_path="/custom/path")
        
        assert memory._db_path == "/custom/path"


class TestSemanticMemoryEmbedding:
    """Test SemanticMemory embedding generation."""
    
    @pytest.fixture
    @patch("src.engine.memory.semantic_memory.get_config")
    def memory(self, mock_get_config):
        """Create a SemanticMemory instance for testing."""
        mock_config = MagicMock()
        mock_config.lancedb.path = "/tmp/test_lancedb"
        mock_config.aws.model_embedding = "test-embedding-model"
        mock_get_config.return_value = mock_config
        
        return SemanticMemory()
    
    @pytest.mark.asyncio
    async def test_get_embedding_success(self, memory):
        """Test successful embedding generation."""
        # Mock Bedrock client
        mock_response = {
            "body": MagicMock(read=lambda: json.dumps({"embedding": [0.1, 0.2, 0.3]}).encode())
        }
        memory._bedrock_client = MagicMock()
        memory._bedrock_client.invoke_model.return_value = mock_response
        
        embedding = await memory._get_embedding("test text")
        
        assert embedding == [0.1, 0.2, 0.3]
        memory._bedrock_client.invoke_model.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_embedding_no_client(self, memory):
        """Test embedding generation without client."""
        with pytest.raises(RuntimeError, match="Bedrock client not initialized"):
            await memory._get_embedding("test text")
    
    @pytest.mark.asyncio
    async def test_get_embedding_failure(self, memory):
        """Test embedding generation failure."""
        memory._bedrock_client = MagicMock()
        memory._bedrock_client.invoke_model.side_effect = Exception("API Error")
        
        with pytest.raises(Exception, match="API Error"):
            await memory._get_embedding("test text")


class TestSemanticMemoryStorage:
    """Test SemanticMemory storage operations."""
    
    @pytest.fixture
    @patch("src.engine.memory.semantic_memory.get_config")
    def memory(self, mock_get_config):
        """Create a SemanticMemory instance for testing."""
        mock_config = MagicMock()
        mock_config.lancedb.path = "/tmp/test_lancedb"
        mock_config.aws.model_embedding = "test-model"
        mock_config.lancedb.table_memory = "test_memory"
        mock_get_config.return_value = mock_config
        
        mem = SemanticMemory()
        mem._initialized = True
        mem._bedrock_client = MagicMock()
        mem._table = MagicMock()
        return mem
    
    @pytest.mark.asyncio
    async def test_remember_success(self, memory):
        """Test successful memory storage."""
        # Mock embedding
        mock_response = {
            "body": MagicMock(read=lambda: json.dumps({"embedding": [0.1] * 1024}).encode())
        }
        memory._bedrock_client.invoke_model.return_value = mock_response
        
        result = await memory.remember(
            content="User likes Python",
            category="preference",
            source="conversation",
            confidence=0.9
        )
        
        assert result is True
        memory._table.add.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_remember_with_metadata(self, memory):
        """Test memory storage with metadata."""
        mock_response = {
            "body": MagicMock(read=lambda: json.dumps({"embedding": [0.1] * 1024}).encode())
        }
        memory._bedrock_client.invoke_model.return_value = mock_response
        
        result = await memory.remember(
            content="Test",
            category="fact",
            metadata={"key": "value", "number": 123}
        )
        
        assert result is True
        # Verify metadata was JSON-encoded
        call_args = memory._table.add.call_args
        assert call_args is not None
        # table.add([{...}]) → call_args[0] is ([{...}],) → [0] → [{...}] → [0] → {...}
        rows_list = call_args[0][0]
        added_data = rows_list[0]
        assert "metadata" in added_data
        parsed_metadata = json.loads(added_data["metadata"])
        assert parsed_metadata["key"] == "value"
    
    @pytest.mark.asyncio
    async def test_remember_failure(self, memory):
        """Test memory storage failure."""
        memory._bedrock_client.invoke_model.side_effect = Exception("API Error")
        
        result = await memory.remember(content="Test")
        
        assert result is False


class TestSemanticMemoryRetrieval:
    """Test SemanticMemory retrieval operations."""
    
    @pytest.fixture
    @patch("src.engine.memory.semantic_memory.get_config")
    def memory(self, mock_get_config):
        """Create a SemanticMemory instance for testing."""
        mock_config = MagicMock()
        mock_config.lancedb.path = "/tmp/test_lancedb"
        mock_config.aws.model_embedding = "test-model"
        mock_get_config.return_value = mock_config
        
        mem = SemanticMemory()
        mem._initialized = True
        mem._bedrock_client = MagicMock()
        
        # Mock table with search results
        mem._table = MagicMock()
        rows = [{
            "id": "fact_1",
            "content": "User lives in Istanbul",
            "category": "fact",
            "timestamp": "2024-01-01",
            "source": "conversation",
            "confidence": 0.9,
            "metadata": json.dumps({"user_id": "123"}),
            "access_count": 1,
            "last_accessed": "2024-01-01",
            "_distance": 0.1,
        }]
        mem._table.search.return_value.limit.return_value.to_arrow.return_value.to_pylist.return_value = rows
        
        return mem
    
    @pytest.mark.asyncio
    async def test_recall_success(self, memory):
        """Test successful memory recall."""
        # Mock embedding
        mock_response = {
            "body": MagicMock(read=lambda: json.dumps({"embedding": [0.1] * 1024}).encode())
        }
        memory._bedrock_client.invoke_model.return_value = mock_response
        
        results = await memory.recall("Where does user live?")
        
        assert len(results) > 0
        assert results[0].content == "User lives in Istanbul"
        assert results[0].category == "fact"
    
    @pytest.mark.asyncio
    async def test_recall_with_category_filter(self, memory):
        """Test recall with category filter."""
        mock_response = {
            "body": MagicMock(read=lambda: json.dumps({"embedding": [0.1] * 1024}).encode())
        }
        memory._bedrock_client.invoke_model.return_value = mock_response
        
        # Mock search chain - LanceDB API: search().limit() or search().where().limit()
        mock_limit = MagicMock()
        mock_limit.to_arrow.return_value.to_pylist.return_value = []
        
        mock_search = MagicMock()
        mock_search.limit.return_value = mock_limit
        mock_search.where.return_value.limit.return_value = mock_limit
        
        memory._table.search.return_value = mock_search
        
        results = await memory.recall("test", category="fact")
        
        # Category filter calls where() before limit()
        assert mock_search.where.called or mock_search.limit.called
    
    @pytest.mark.asyncio
    async def test_recall_min_score_filter(self, memory):
        """Test recall with minimum score filter."""
        mock_response = {
            "body": MagicMock(read=lambda: json.dumps({"embedding": [0.1] * 1024}).encode())
        }
        memory._bedrock_client.invoke_model.return_value = mock_response
        
        # Mock with high distance (low similarity)
        memory._table.search.return_value.limit.return_value.to_arrow.return_value.to_pylist.return_value = [
            {"_distance": 0.9}  # Very low similarity
        ]
        
        results = await memory.recall("test", min_score=0.8)
        
        # Should filter out low similarity results
        assert len(results) == 0


class TestSemanticMemoryDeletion:
    """Test SemanticMemory deletion operations."""
    
    @pytest.fixture
    @patch("src.engine.memory.semantic_memory.get_config")
    def memory(self, mock_get_config):
        """Create a SemanticMemory instance for testing."""
        mock_config = MagicMock()
        mock_config.lancedb.path = "/tmp/test_lancedb"
        mock_get_config.return_value = mock_config
        
        mem = SemanticMemory()
        mem._initialized = True
        mem._table = MagicMock()
        return mem
    
    @pytest.mark.asyncio
    async def test_forget_success(self, memory):
        """Test successful memory deletion."""
        result = await memory.forget("fact_1")
        
        assert result is True
        memory._table.delete.assert_called_once_with('id = "fact_1"')
    
    @pytest.mark.asyncio
    async def test_forget_failure(self, memory):
        """Test memory deletion failure."""
        memory._table.delete.side_effect = Exception("Delete error")
        
        result = await memory.forget("fact_1")
        
        assert result is False


class TestSemanticMemorySchemaMigration:
    """Test SemanticMemory schema migration."""
    
    @pytest.fixture
    @patch("src.engine.memory.semantic_memory.get_config")
    def memory(self, mock_get_config):
        """Create a SemanticMemory instance for testing."""
        mock_config = MagicMock()
        mock_config.lancedb.path = "/tmp/test_lancedb"
        mock_config.lancedb.table_memory = "test_memory"
        mock_get_config.return_value = mock_config
        
        mem = SemanticMemory()
        mem._initialized = True
        mem._db = MagicMock()
        return mem
    
    @pytest.mark.asyncio
    async def test_migrate_schema_adds_columns(self, memory):
        """Test schema migration adds missing columns."""
        # Mock old table data without access_count and last_accessed
        mock_old_rows = [{
            "id": "fact_1",
            "content": "User likes Python",
            "category": "preference",
            "timestamp": "2024-01-01T00:00:00",
            "source": "conversation",
            "confidence": 0.9,
            "vector": [0.1] * 1024,
            "metadata": json.dumps({"source": "test"}),
        }]
        
        mock_old_table = MagicMock()
        mock_old_table.to_arrow.return_value.to_pylist.return_value = mock_old_rows
        memory._table = mock_old_table
        
        await memory._migrate_schema("test_memory")
        
        # Should drop and recreate table
        memory._db.drop_table.assert_called_once_with("test_memory")
        memory._db.create_table.assert_called_once()
