"""Semantic Memory - Long-term memory storage using LanceDB.

This module implements the long-term memory system that stores:
- User facts and preferences
- Important information from conversations
- Agent learning and experiences
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from pathlib import Path

from src.utils.aws_sts import get_bedrock_client
from src.utils.config import get_config
from src.utils.logger import get_logger

logger = get_logger()


@dataclass
class MemoryEntry:
    """A single memory entry."""
    
    id: str
    content: str
    category: str  # "fact", "preference", "event", "learning"
    timestamp: str
    source: str  # Where this memory came from
    confidence: float  # 0.0-1.0
    metadata: Dict[str, Any]
    access_count: int = 1
    last_accessed: str = ""


class SemanticMemory:
    """Long-term semantic memory for the agent.
    
    Stores user facts, preferences, and learned information
    using vector embeddings for semantic retrieval.
    
    Example:
        >>> memory = SemanticMemory()
        >>> await memory.initialize()
        >>> await memory.remember(
        ...     "User lives in Istanbul",
        ...     category="fact",
        ...     source="conversation"
        ... )
        >>> facts = await memory.recall("Where does user live?")
    """
    
    def __init__(self, db_path: Optional[str] = None) -> None:
        """Initialize semantic memory.
        
        Args:
            db_path: Path to LanceDB database
        """
        self._config = get_config()
        self._db_path = db_path or self._config.lancedb.path
        self._bedrock_client: Optional[Any] = None
        self._table = None
        self._initialized = False
        
        logger.info(f"SemanticMemory initialized with db: {self._db_path}")
    
    async def initialize(self) -> None:
        """Initialize the database connection."""
        try:
            import lancedb
            
            # Initialize Bedrock client
            self._bedrock_client = get_bedrock_client()
            
            # Connect to LanceDB
            db_path = Path(self._db_path).expanduser()
            db_path.mkdir(parents=True, exist_ok=True)
            
            self._db = lancedb.connect(str(db_path))
            
            # Get or create memory table
            table_name = self._config.lancedb.table_memory
            if table_name in self._db.table_names():
                self._table = self._db.open_table(table_name)
                logger.info(f"Opened existing memory table: {table_name}")
                
                # Schema migration: ensure new columns exist
                existing_cols = [f.name for f in self._table.schema]
                if "access_count" not in existing_cols or "last_accessed" not in existing_cols:
                    logger.info("Migrating memory table schema to add decay columns...")
                    await self._migrate_schema(table_name)
            else:
                # Create table
                import pyarrow as pa
                
                schema = pa.schema([
                    ("id", pa.string()),
                    ("content", pa.string()),
                    ("category", pa.string()),
                    ("timestamp", pa.string()),
                    ("source", pa.string()),
                    ("confidence", pa.float32()),
                    ("access_count", pa.int32()),
                    ("last_accessed", pa.string()),
                    ("vector", pa.list_(pa.float32(), 1024)),
                    ("metadata", pa.string()),
                ])
                
                self._table = self._db.create_table(table_name, schema=schema)
                logger.info(f"Created new memory table: {table_name}")

            
            self._initialized = True
            logger.info("SemanticMemory initialized successfully")
            
        except ImportError as e:
            logger.error(f"Failed to import LanceDB: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize SemanticMemory: {e}")
            raise
    
    async def _migrate_schema(self, table_name: str) -> None:
        """Migrate existing memory table to include decay columns.
        
        Reads all existing rows, adds default values for missing columns,
        drops the old table, and re-creates with the full schema.
        """
        import pyarrow as pa
        
        try:
            df = self._table.to_pandas()
            
            if "access_count" not in df.columns:
                df["access_count"] = 1
            if "last_accessed" not in df.columns:
                df["last_accessed"] = df["timestamp"]
            
            # Ensure correct types
            df["access_count"] = df["access_count"].astype("int32")
            df["last_accessed"] = df["last_accessed"].astype(str)
            
            # Drop and recreate
            self._db.drop_table(table_name)
            
            schema = pa.schema([
                ("id", pa.string()),
                ("content", pa.string()),
                ("category", pa.string()),
                ("timestamp", pa.string()),
                ("source", pa.string()),
                ("confidence", pa.float32()),
                ("access_count", pa.int32()),
                ("last_accessed", pa.string()),
                ("vector", pa.list_(pa.float32(), 1024)),
                ("metadata", pa.string()),
            ])
            
            if len(df) > 0:
                self._table = self._db.create_table(table_name, data=df, schema=schema)
            else:
                self._table = self._db.create_table(table_name, schema=schema)
            
            logger.info(f"Schema migration complete. {len(df)} memories preserved.")
            
        except Exception as e:
            logger.error(f"Schema migration failed: {e}")
            raise
    
    async def _get_embedding(self, text: str) -> List[float]:
        """Generate embedding for text.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector
        """
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
    
    async def remember(
        self,
        content: str,
        category: str = "fact",
        source: str = "conversation",
        confidence: float = 0.8,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Store a new memory.
        
        Args:
            content: The information to remember
            category: Type of memory (fact, preference, event, learning)
            source: Where this came from
            confidence: Confidence level (0-1)
            metadata: Additional metadata
            
        Returns:
            True if successful
        """
        if not self._initialized:
            await self.initialize()
        
        logger.info(f"Storing memory: {content[:100]}...")
        
        try:
            # Generate embedding
            vector = await self._get_embedding(content)
            
            # Create entry
            entry_id = f"{category}_{datetime.utcnow().isoformat()}"
            
            self._table.add([{
                "id": entry_id,
                "content": content,
                "category": category,
                "timestamp": datetime.utcnow().isoformat(),
                "source": source,
                "confidence": confidence,
                "access_count": 1,
                "last_accessed": datetime.utcnow().isoformat(),
                "vector": vector,
                "metadata": json.dumps(metadata or {})
            }])
            
            logger.info(f"Memory stored successfully: {entry_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store memory: {e}")
            return False
    
    async def recall(
        self,
        query: str,
        category: Optional[str] = None,
        top_k: int = 5,
        min_score: float = 0.5
    ) -> List[MemoryEntry]:
        """Retrieve relevant memories.
        
        Args:
            query: Query text
            category: Filter by category (optional)
            top_k: Number of results
            min_score: Minimum relevance score
            
        Returns:
            List of matching memories
        """
        if not self._initialized:
            await self.initialize()
        
        logger.info(f"Recalling memories for: {query[:100]}...")
        
        try:
            # Generate query embedding
            query_vector = await self._get_embedding(query)
            
            # Search
            search = self._table.search(query_vector).limit(top_k * 2)
            
            # Apply category filter if specified
            if category:
                search = search.where(f'category = "{category}"')
            
            results = search.to_pandas()
            
            entries = []
            for _, row in results.iterrows():
                distance = float(row.get('_distance', 2.0))
                # Convert L2/Cosine distance to a 0-1 similarity score safely
                similarity = 1.0 / (1.0 + distance)
                
                if similarity >= min_score:
                    entry = MemoryEntry(
                        id=row['id'],
                        content=row['content'],
                        category=row['category'],
                        timestamp=row['timestamp'],
                        source=row['source'],
                        confidence=row['confidence'],
                        metadata=json.loads(row.get('metadata', '{}')),
                        access_count=row.get('access_count', 1),
                        last_accessed=row.get('last_accessed', datetime.utcnow().isoformat())
                    )
                    entries.append(entry)
            
            # Sort by confidence and limit
            entries.sort(key=lambda x: x.confidence, reverse=True)
            entries = entries[:top_k]
            
            # Reinforce recalled memories (Synaptic matching)
            if entries:
                await self._reinforce_memories([e.id for e in entries])
            
            logger.info(f"Recalled {len(entries)} memories")
            return entries
            
        except Exception as e:
            logger.error(f"Failed to recall memories: {e}")
            return []
    
    async def forget(self, memory_id: str) -> bool:
        """Delete a specific memory.
        
        Args:
            memory_id: ID of memory to delete
            
        Returns:
            True if successful
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            self._table.delete(f'id = "{memory_id}"')
            logger.info(f"Forgot memory: {memory_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to forget memory: {e}")
            return False
            
    async def _reinforce_memories(self, memory_ids: List[str]) -> None:
        """Increase the access count and update last_accessed for matching memories.
        This simulates synaptic strengthening in the brain.
        """
        try:
            now = datetime.utcnow().isoformat()
            # Current LanceDB Python API allows updating rows with a where clause.
            # We will iterate through IDs or do it in one go if possible.
            for mem_id in memory_ids:
                try:
                    # Incrementing requires reading the old value or using an update statement.
                    # We'll fetch the old row, increment, and replace (safe fallback if no raw SQL update exists)
                    rows = self._table.search().where(f'id = "{mem_id}"').limit(1).to_pandas()
                    if len(rows) > 0:
                        old_count = rows.iloc[0].get('access_count', 1)
                        # Delete old row
                        self._table.delete(f'id = "{mem_id}"')
                        # Insert new row with updated values
                        row_dict = rows.iloc[0].to_dict()
                        row_dict["access_count"] = old_count + 1
                        row_dict["last_accessed"] = now
                        self._table.add([row_dict])
                except Exception as e:
                    logger.warning(f"Failed to reinforce memory {mem_id}: {e}")
        except Exception as e:
            logger.error(f"Error during memory reinforcement: {e}")
            
    async def prune_decayed_memories(self, threshold_score: float = 0.0, decay_rate: float = 0.1, weight: float = 1.0) -> int:
        """Delete memories that have decayed below the threshold.
        
        Importance Score = (access_count * weight) - (days_since_last_access * decay_rate)
        
        Returns:
            Number of forgotten (deleted) memories.
        """
        if not self._initialized:
            await self.initialize()
            
        try:
            df = self._table.to_pandas()
            if len(df) == 0:
                return 0
                
            now = datetime.utcnow()
            to_delete = []
            
            for _, row in df.iterrows():
                mem_id = row['id']
                access_count = row.get('access_count', 1)
                last_acc_str = row.get('last_accessed')
                
                try:
                    if last_acc_str:
                        last_acc = datetime.fromisoformat(last_acc_str)
                    else:
                        last_acc = datetime.fromisoformat(row['timestamp'])
                except ValueError:
                    last_acc = now
                    
                days_since = (now - last_acc).days
                score = (access_count * weight) - (days_since * decay_rate)
                
                if score < threshold_score:
                    to_delete.append(mem_id)
            
            deleted_count = 0
            for mem_id in to_delete:
                if await self.forget(mem_id):
                    deleted_count += 1
                    
            if deleted_count > 0:
                logger.info(f"Pruned {deleted_count} decayed memories (Memory Garbage Collection).")
                
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to prune decayed memories: {e}")
            return 0
    
    async def update_confidence(self, memory_id: str, new_confidence: float) -> bool:
        """Update the confidence of a memory.
        
        Args:
            memory_id: ID of memory
            new_confidence: New confidence value
            
        Returns:
            True if successful
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Get existing entry
            results = (
                self._table.search()
                .where(f'id = "{memory_id}"')
                .limit(1)
                .to_pandas()
            )
            
            if len(results) == 0:
                logger.warning(f"Memory not found: {memory_id}")
                return False
            
            row = results.iloc[0]
            
            # Delete old
            self._table.delete(f'id = "{memory_id}"')
            
            # Add updated
            self._table.add([{
                "id": row['id'],
                "content": row['content'],
                "category": row['category'],
                "timestamp": row['timestamp'],
                "source": row['source'],
                "confidence": new_confidence,
                "vector": row['vector'],
                "metadata": row['metadata']
            }])
            
            logger.info(f"Updated confidence for memory: {memory_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update memory confidence: {e}")
            return False
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics.
        
        Returns:
            Statistics dictionary
        """
        if not self._initialized:
            return {"status": "not_initialized"}
        
        try:
            df = self._table.to_pandas()
            
            stats = {
                "status": "initialized",
                "total_memories": len(df),
                "by_category": {},
                "avg_confidence": float(df['confidence'].mean()) if len(df) > 0 else 0
            }
            
            # Count by category
            for category in df['category'].unique():
                count = len(df[df['category'] == category])
                stats["by_category"][category] = count
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get memory stats: {e}")
            return {"status": "error", "message": str(e)}
    
    async def extract_and_store_facts(self, conversation: str) -> List[str]:
        """Extract facts from conversation and store them.
        
        Uses LLM to extract important facts about the user.
        
        Args:
            conversation: Conversation text
            
        Returns:
            List of extracted and stored fact IDs
        """
        if not self._bedrock_client:
            logger.error("Bedrock client not available for fact extraction")
            return []
        
        logger.info("Extracting facts from conversation")
        
        try:
            prompt = f"""Analyze this conversation and extract important facts about the user.

Conversation:
{conversation}

Extract facts like:
- Personal information (name, location, preferences)
- Professional context (job, skills, interests)
- Important relationships or connections
- Goals or objectives mentioned

Respond with a JSON array of facts:
[
    {{
        "content": "the fact",
        "category": "fact|preference|event",
        "confidence": 0.0-1.0
    }}
]

Only include high-confidence facts."""

            response = self._bedrock_client.converse(
                modelId=self._config.aws.model_nova_lite,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"temperature": 0.2, "maxTokens": 1000}
            )
            
            response_text = response['output']['message']['content'][0]['text']
            
            # Parse JSON
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]
            
            facts = json.loads(response_text.strip())
            
            stored_ids = []
            for fact in facts:
                success = await self.remember(
                    content=fact["content"],
                    category=fact.get("category", "fact"),
                    source="fact_extraction",
                    confidence=fact.get("confidence", 0.7)
                )
                if success:
                    stored_ids.append(fact["content"][:50])  # Use content preview as ID ref
            
            logger.info(f"Extracted and stored {len(stored_ids)} facts")
            return stored_ids
            
        except Exception as e:
            logger.error(f"Failed to extract facts: {e}")
            return []


# Singleton instance
_semantic_memory: Optional[SemanticMemory] = None


async def get_semantic_memory() -> SemanticMemory:
    """Get the global SemanticMemory instance.
    
    Returns:
        Singleton SemanticMemory instance (initialized)
    """
    global _semantic_memory
    if _semantic_memory is None:
        _semantic_memory = SemanticMemory()
        await _semantic_memory.initialize()
    return _semantic_memory