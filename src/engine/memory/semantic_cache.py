"""Semantic Cache - LanceDB-based caching for LLM requests.

Reduces LLM costs by caching similar requests and responses.
"""

import json
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from pathlib import Path

from src.utils.aws_sts import get_bedrock_client
from src.utils.config import get_config
from src.utils.logger import get_logger

logger = get_logger()


@dataclass
class CacheEntry:
    """A cached request-response pair."""
    query_hash: str
    query: str
    response: str
    embedding: List[float]
    timestamp: str
    hit_count: int = 0
    ttl_hours: int = 24


class SemanticCache:
    """Semantic cache using LanceDB vector search.
    
    Caches LLM requests and responses to reduce API calls.
    Uses vector similarity to find semantically similar queries.
    """
    
    def __init__(
        self,
        db_path: Optional[str] = None,
        similarity_threshold: float = 0.92,
        ttl_hours: int = 24
    ):
        """Initialize semantic cache.
        
        Args:
            db_path: LanceDB path
            similarity_threshold: Minimum similarity for cache hit (0-1)
            ttl_hours: Cache entry time-to-live
        """
        self._config = get_config()
        self._db_path = db_path or self._config.lancedb.path
        self._similarity_threshold = similarity_threshold
        self._ttl_hours = ttl_hours
        
        self._bedrock_client: Optional[Any] = None
        self._table = None
        self._initialized = False
        
        logger.info(f"SemanticCache initialized (threshold: {similarity_threshold})")
    
    async def initialize(self):
        """Initialize the cache database."""
        try:
            import lancedb
            
            self._bedrock_client = get_bedrock_client()
            
            db_path = Path(self._db_path).expanduser()
            db_path.mkdir(parents=True, exist_ok=True)
            
            self._db = lancedb.connect(str(db_path))
            
            table_name = "semantic_cache"
            if table_name in self._db.table_names():
                self._table = self._db.open_table(table_name)
                logger.info(f"Opened cache table: {table_name}")
            else:
                import pyarrow as pa
                
                schema = pa.schema([
                    ("query_hash", pa.string()),
                    ("query", pa.string()),
                    ("response", pa.string()),
                    ("vector", pa.list_(pa.float32(), 1024)),
                    ("timestamp", pa.string()),
                    ("hit_count", pa.int32()),
                    ("ttl_hours", pa.int32()),
                ])
                
                self._table = self._db.create_table(table_name, schema=schema)
                logger.info(f"Created cache table: {table_name}")
            
            self._initialized = True
            
        except Exception as e:
            logger.error(f"Failed to initialize SemanticCache: {e}")
            raise
    
    async def _get_embedding(self, text: str) -> List[float]:
        """Generate embedding for text."""
        if not self._bedrock_client:
            raise RuntimeError("Bedrock client not initialized")
        
        try:
            response = self._bedrock_client.invoke_model(
                modelId=self._config.aws.model_embedding,
                body=json.dumps({"inputText": text})
            )
            
            result = json.loads(response['body'].read())
            return result['embedding']
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise
    
    def _compute_hash(self, text: str) -> str:
        """Compute hash for query text."""
        return hashlib.sha256(text.encode()).hexdigest()[:16]
    
    def _is_expired(self, entry: Dict) -> bool:
        """Check if cache entry is expired."""
        timestamp = datetime.fromisoformat(entry["timestamp"])
        ttl = timedelta(hours=entry.get("ttl_hours", self._ttl_hours))
        return datetime.utcnow() - timestamp > ttl
    
    async def get(self, query: str) -> Optional[str]:
        """Get cached response for query.
        
        Args:
            query: User query
            
        Returns:
            Cached response if found and similar enough, None otherwise
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Generate embedding for query
            query_vector = await self._get_embedding(query)
            
            # Search for similar queries
            results = self._table.search(query_vector).limit(5).to_pandas()
            
            if len(results) == 0:
                return None
            
            # Check top result
            top_result = results.iloc[0]
            similarity = top_result.get("_distance", 0)
            
            # Convert distance to similarity (LanceDB returns distance, lower is better)
            # Cosine similarity: 1 - distance
            similarity = 1 - similarity
            
            if similarity >= self._similarity_threshold:
                # Check expiration
                if self._is_expired(top_result):
                    logger.debug("Cache hit but expired")
                    return None
                
                # Update hit count
                self._table.update(
                    where=f"query_hash = '{top_result['query_hash']}'",
                    values={"hit_count": top_result["hit_count"] + 1}
                )
                
                logger.info(f"Cache hit (similarity: {similarity:.3f})")
                return top_result["response"]
            
            logger.debug(f"Cache miss (similarity: {similarity:.3f} < {self._similarity_threshold})")
            return None
            
        except Exception as e:
            logger.error(f"Cache lookup failed: {e}")
            return None
    
    async def set(self, query: str, response: str):
        """Cache a query-response pair.
        
        Args:
            query: User query
            response: LLM response
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Generate embedding
            query_vector = await self._get_embedding(query)
            query_hash = self._compute_hash(query)
            
            # Check if already exists
            existing = self._table.search(query_vector).where(
                f"query_hash = '{query_hash}'"
            ).limit(1).to_pandas()
            
            if len(existing) > 0:
                # Update existing
                self._table.update(
                    where=f"query_hash = '{query_hash}'",
                    values={
                        "response": response,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )
                logger.debug(f"Updated cache entry: {query_hash}")
            else:
                # Add new entry
                self._table.add([{
                    "query_hash": query_hash,
                    "query": query,
                    "response": response,
                    "vector": query_vector,
                    "timestamp": datetime.utcnow().isoformat(),
                    "hit_count": 0,
                    "ttl_hours": self._ttl_hours
                }])
                logger.debug(f"Added cache entry: {query_hash}")
            
        except Exception as e:
            logger.error(f"Cache store failed: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        try:
            import pandas as pd
            
            df = self._table.to_pandas()
            
            if len(df) == 0:
                return {"total_entries": 0, "total_hits": 0}
            
            return {
                "total_entries": len(df),
                "total_hits": int(df["hit_count"].sum()),
                "avg_hits_per_entry": float(df["hit_count"].mean()),
                "cache_size_mb": df.memory_usage(deep=True).sum() / 1024 / 1024
            }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {"error": str(e)}
    
    async def clear_expired(self):
        """Remove expired cache entries."""
        try:
            # LanceDB doesn't support direct delete, we'd need to recreate
            # This is a placeholder for the operation
            logger.info("Cache cleanup would remove expired entries")
        except Exception as e:
            logger.error(f"Cache cleanup failed: {e}")


# Singleton instance
_cache_instance: Optional[SemanticCache] = None


def get_semantic_cache(
    similarity_threshold: float = 0.92,
    ttl_hours: int = 24
) -> SemanticCache:
    """Get singleton SemanticCache."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = SemanticCache(
            similarity_threshold=similarity_threshold,
            ttl_hours=ttl_hours
        )
    return _cache_instance
