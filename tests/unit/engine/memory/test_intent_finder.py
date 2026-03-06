"""Unit tests for engine/memory/intent_finder.py module.

This module tests the IntentFinder class for semantic tool matching.
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from src.engine.memory.intent_finder import (
    IntentFinder,
    PrimitiveMatch,
)


class TestPrimitiveMatch:
    """Test PrimitiveMatch dataclass."""
    
    def test_create_primitive_match(self):
        """Test creating a primitive match."""
        match = PrimitiveMatch(
            name="file_upload",
            description="Upload a file to S3",
            code="def upload(): pass",
            score=0.95,
            metadata={"author": "test"}
        )
        
        assert match.name == "file_upload"
        assert match.description == "Upload a file to S3"
        assert match.code == "def upload(): pass"
        assert match.score == 0.95
        assert match.metadata == {"author": "test"}


class TestIntentFinderInitialization:
    """Test IntentFinder initialization."""
    
    @patch("src.engine.memory.intent_finder.get_config")
    def test_intent_finder_init_defaults(self, mock_get_config):
        """Test IntentFinder initialization with defaults."""
        mock_config = MagicMock()
        mock_config.lancedb.path = "/tmp/test_lancedb"
        mock_get_config.return_value = mock_config
        
        finder = IntentFinder()
        
        assert finder._db_path == "/tmp/test_lancedb"
        assert finder._bedrock_client is None
        assert finder._table is None
        assert finder._initialized is False
    
    @patch("src.engine.memory.intent_finder.get_config")
    def test_intent_finder_init_custom_path(self, mock_get_config):
        """Test IntentFinder initialization with custom path."""
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        
        finder = IntentFinder(db_path="/custom/path")
        
        assert finder._db_path == "/custom/path"


class TestIntentFinderEmbedding:
    """Test IntentFinder embedding generation."""
    
    @pytest.fixture
    @patch("src.engine.memory.intent_finder.get_config")
    def finder(self, mock_get_config):
        """Create an IntentFinder instance for testing."""
        mock_config = MagicMock()
        mock_config.lancedb.path = "/tmp/test_lancedb"
        mock_config.aws.model_embedding = "test-embedding-model"
        mock_get_config.return_value = mock_config
        
        return IntentFinder()
    
    @pytest.mark.asyncio
    async def test_get_embedding_success(self, finder):
        """Test successful embedding generation."""
        mock_response = {
            "body": MagicMock(read=lambda: json.dumps({"embedding": [0.1, 0.2, 0.3]}).encode())
        }
        finder._bedrock_client = MagicMock()
        finder._bedrock_client.invoke_model.return_value = mock_response
        
        embedding = await finder._get_embedding("upload file")
        
        assert embedding == [0.1, 0.2, 0.3]
        finder._bedrock_client.invoke_model.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_embedding_no_client(self, finder):
        """Test embedding generation without client."""
        with pytest.raises(RuntimeError, match="Bedrock client not initialized"):
            await finder._get_embedding("test")


class TestIntentFinderPrimitives:
    """Test IntentFinder primitive operations."""
    
    @pytest.fixture
    @patch("src.engine.memory.intent_finder.get_config")
    def finder(self, mock_get_config):
        """Create an IntentFinder instance for testing."""
        mock_config = MagicMock()
        mock_config.lancedb.path = "/tmp/test_lancedb"
        mock_config.aws.model_embedding = "test-model"
        mock_config.lancedb.table_primitives = "test_primitives"
        mock_get_config.return_value = mock_config
        
        f = IntentFinder()
        f._initialized = True
        f._bedrock_client = MagicMock()
        f._table = MagicMock()
        return f
    
    @pytest.mark.asyncio
    async def test_find_primitives_success(self, finder):
        """Test finding primitives for a query."""
        # Mock embedding
        mock_response = {
            "body": MagicMock(read=lambda: json.dumps({"embedding": [0.1] * 1024}).encode())
        }
        finder._bedrock_client.invoke_model.return_value = mock_response
        
        # Mock search results
        mock_df = MagicMock()
        mock_df.iterrows.return_value = [
            (0, {
                "name": "file_upload",
                "description": "Upload files",
                "code": "def upload(): pass",
                "metadata": json.dumps({"author": "test"}),
                "_distance": 0.1
            }),
            (1, {
                "name": "file_download",
                "description": "Download files",
                "code": "def download(): pass",
                "metadata": json.dumps({}),
                "_distance": 0.2
            })
        ]
        finder._table.search.return_value.limit.return_value.to_pandas.return_value = mock_df
        
        results = await finder.find_primitives("upload a file", top_k=3)
        
        assert len(results) == 2
        assert results[0].name == "file_upload"
        assert results[0].score > 0.5
        assert results[1].name == "file_download"
    
    @pytest.mark.asyncio
    async def test_find_primitives_min_score_filter(self, finder):
        """Test finding primitives with minimum score filter."""
        mock_response = {
            "body": MagicMock(read=lambda: json.dumps({"embedding": [0.1] * 1024}).encode())
        }
        finder._bedrock_client.invoke_model.return_value = mock_response
        
        # Mock with high distance (low similarity)
        mock_df = MagicMock()
        mock_df.iterrows.return_value = [
            (0, {
                "name": "low_match",
                "description": "Low match",
                "code": "pass",
                "metadata": json.dumps({}),
                "_distance": 0.9  # Very low similarity
            })
        ]
        finder._table.search.return_value.limit.return_value.to_pandas.return_value = mock_df
        
        results = await finder.find_primitives("test", min_score=0.8)
        
        # Should filter out low similarity results
        assert len(results) == 0
    
    @pytest.mark.asyncio
    async def test_add_primitive_success(self, finder):
        """Test adding a primitive."""
        mock_response = {
            "body": MagicMock(read=lambda: json.dumps({"embedding": [0.1] * 1024}).encode())
        }
        finder._bedrock_client.invoke_model.return_value = mock_response
        
        result = await finder.add_primitive(
            name="new_primitive",
            description="A new primitive",
            code="def new(): pass",
            metadata={"author": "test"}
        )
        
        assert result is True
        finder._table.add.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_add_primitive_failure(self, finder):
        """Test adding a primitive failure."""
        finder._bedrock_client.invoke_model.side_effect = Exception("API Error")
        
        result = await finder.add_primitive("test", "test", "pass")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_update_primitive_success(self, finder):
        """Test updating a primitive."""
        mock_response = {
            "body": MagicMock(read=lambda: json.dumps({"embedding": [0.1] * 1024}).encode())
        }
        finder._bedrock_client.invoke_model.return_value = mock_response
        
        result = await finder.update_primitive(
            name="existing_primitive",
            description="Updated description",
            code="def updated(): pass"
        )
        
        assert result is True
        finder._table.delete.assert_called_once_with('name = "existing_primitive"')
    
    @pytest.mark.asyncio
    async def test_update_primitive_missing_fields(self, finder):
        """Test updating primitive without required fields."""
        result = await finder.update_primitive(name="test")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_delete_primitive_success(self, finder):
        """Test deleting a primitive."""
        result = await finder.delete_primitive("old_primitive")
        
        assert result is True
        finder._table.delete.assert_called_once_with('name = "old_primitive"')
    
    @pytest.mark.asyncio
    async def test_delete_primitive_failure(self, finder):
        """Test deleting a primitive failure."""
        finder._table.delete.side_effect = Exception("Delete error")
        
        result = await finder.delete_primitive("test")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_list_primitives(self, finder):
        """Test listing all primitives."""
        mock_df = MagicMock()
        mock_df.iterrows.return_value = [
            (0, {
                "name": "prim1",
                "description": "First primitive",
                "created_at": "2024-01-01",
                "metadata": json.dumps({"author": "test"})
            }),
            (1, {
                "name": "prim2",
                "description": "Second primitive",
                "created_at": "2024-01-02",
                "metadata": json.dumps({})
            })
        ]
        finder._table.to_pandas.return_value = mock_df
        
        results = await finder.list_primitives()
        
        assert len(results) == 2
        assert results[0]["name"] == "prim1"
        assert results[0]["description"] == "First primitive"
        assert results[0]["metadata"] == {"author": "test"}
    
    @pytest.mark.asyncio
    async def test_get_primitive_success(self, finder):
        """Test getting a specific primitive."""
        mock_df = MagicMock()
        mock_df.__len__ = MagicMock(return_value=1)
        mock_df.iloc = [{
            "name": "found_primitive",
            "description": "A primitive",
            "code": "def found(): pass",
            "metadata": json.dumps({"author": "test"})
        }]
        finder._table.search.return_value.where.return_value.limit.return_value.to_pandas.return_value = mock_df
        
        result = await finder.get_primitive("found_primitive")
        
        assert result is not None
        assert result.name == "found_primitive"
    
    @pytest.mark.asyncio
    async def test_get_primitive_not_found(self, finder):
        """Test getting a non-existent primitive."""
        mock_df = MagicMock()
        mock_df.__len__ = MagicMock(return_value=0)
        finder._table.search.return_value.where.return_value.limit.return_value.to_pandas.return_value = mock_df
        
        result = await finder.get_primitive("nonexistent")
        
        assert result is None


class TestIntentFinderErrorHandling:
    """Test IntentFinder error handling."""
    
    @pytest.fixture
    @patch("src.engine.memory.intent_finder.get_config")
    def finder(self, mock_get_config):
        """Create an IntentFinder instance for testing."""
        mock_config = MagicMock()
        mock_config.lancedb.path = "/tmp/test_lancedb"
        mock_get_config.return_value = mock_config
        
        f = IntentFinder()
        f._initialized = True
        return f
    
    @pytest.mark.asyncio
    async def test_find_primitives_not_initialized(self, finder):
        """Test find_primitives when not initialized."""
        finder._initialized = False
        finder._bedrock_client = MagicMock()
        finder._table = MagicMock()
        
        # Should try to initialize first
        with patch.object(finder, 'initialize') as mock_init:
            mock_response = {
                "body": MagicMock(read=lambda: json.dumps({"embedding": [0.1] * 1024}).encode())
            }
            finder._bedrock_client.invoke_model.return_value = mock_response
            finder._table.search.return_value.limit.return_value.to_pandas.return_value = MagicMock(iterrows=MagicMock(return_value=[]))
            
            await finder.find_primitives("test")
            
            mock_init.assert_called_once()
