"""Intent Finder - Semantic search for tool and primitive selection.

This module implements the Intent Finder that uses vector embeddings
to semantically match user requests with available tools/primitives.
"""

import json
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from src.utils.aws_sts import get_bedrock_client
from src.utils.config import get_config
from src.utils.logger import get_logger

logger = get_logger()


@dataclass
class PrimitiveMatch:
    """A matched primitive with relevance score."""
    
    name: str
    description: str
    code: str
    score: float
    metadata: Dict[str, Any]


class IntentFinder:
    """Semantic search for matching user intent to primitives.
    
    Uses vector embeddings and LanceDB to find the most relevant
tools for a given user request.
    
    Example:
        >>> finder = IntentFinder()
        >>> matches = await finder.find_primitives("upload a file to S3")
        >>> for match in matches:
        ...     print(f"{match.name}: {match.score}")
    """
    
    def __init__(self, db_path: Optional[str] = None) -> None:
        """Initialize the Intent Finder.
        
        Args:
            db_path: Path to LanceDB database (defaults to config)
        """
        self._config = get_config()
        self._db_path = db_path or self._config.lancedb.path
        self._bedrock_client: Optional[Any] = None
        self._table = None
        self._initialized = False
        
        logger.info(f"IntentFinder initialized with db: {self._db_path}")
    
    async def initialize(self) -> None:
        """Initialize the database connection and embedding model."""
        try:
            import lancedb
            
            # Initialize Bedrock client for embeddings
            self._bedrock_client = get_bedrock_client()
            
            # Connect to LanceDB
            db_path = Path(self._db_path).expanduser()
            db_path.mkdir(parents=True, exist_ok=True)
            
            self._db = lancedb.connect(str(db_path))
            
            # Get or create primitives table
            table_name = self._config.lancedb.table_primitives
            if table_name in self._db.table_names():
                self._table = self._db.open_table(table_name)
                logger.info(f"Opened existing table: {table_name}")
            else:
                # Create table with schema
                import pyarrow as pa
                
                schema = pa.schema([
                    ("name", pa.string()),
                    ("description", pa.string()),
                    ("code", pa.string()),
                    ("vector", pa.list_(pa.float32(), 1024)),  # Titan embedding size
                    ("metadata", pa.string()),  # JSON string
                    ("created_at", pa.string()),
                ])
                
                self._table = self._db.create_table(table_name, schema=schema)
                logger.info(f"Created new table: {table_name}")
            
            self._initialized = True
            logger.info("IntentFinder initialized successfully")
            
        except ImportError as e:
            logger.error(f"Failed to import LanceDB: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize IntentFinder: {e}")
            raise
    
    async def _get_embedding(self, text: str) -> List[float]:
        """Generate embedding vector for text using Bedrock.
        
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
    
    async def find_primitives(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.5
    ) -> List[PrimitiveMatch]:
        """Find primitives matching the user query.
        
        Args:
            query: User's natural language query
            top_k: Number of top matches to return
            min_score: Minimum similarity score (0-1)
            
        Returns:
            List of matching primitives sorted by relevance
        """
        if not self._initialized:
            await self.initialize()
        
        logger.info(f"Finding primitives for query: {query[:100]}...")
        
        try:
            # Generate query embedding
            query_vector = await self._get_embedding(query)
            
            # Search LanceDB
            results = (
                self._table.search(query_vector)
                .limit(top_k * 2)  # Get extra for filtering
                .to_pandas()
            )
            
            matches = []
            for _, row in results.iterrows():
                # Convert distance to similarity score (assuming cosine distance)
                # LanceDB returns distance, lower is better
                distance = row.get('_distance', 0.5)
                similarity = 1.0 - min(distance, 1.0)  # Convert to similarity
                
                if similarity >= min_score:
                    match = PrimitiveMatch(
                        name=row['name'],
                        description=row['description'],
                        code=row['code'],
                        score=similarity,
                        metadata=json.loads(row.get('metadata', '{}'))
                    )
                    matches.append(match)
            
            # Sort by score and limit
            matches.sort(key=lambda x: x.score, reverse=True)
            matches = matches[:top_k]
            
            logger.info(f"Found {len(matches)} matching primitives")
            return matches
            
        except Exception as e:
            logger.error(f"Failed to find primitives: {e}")
            return []
    
    async def add_primitive(
        self,
        name: str,
        description: str,
        code: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Add a new primitive to the vector store.
        
        Args:
            name: Unique name for the primitive
            description: Human-readable description
            code: Python code for the primitive
            metadata: Additional metadata
            
        Returns:
            True if successful
        """
        if not self._initialized:
            await self.initialize()
        
        logger.info(f"Adding primitive: {name}")
        
        try:
            # Generate embedding from description + code preview
            text_to_embed = f"{description}\n\nCode preview:\n{code[:500]}"
            vector = await self._get_embedding(text_to_embed)
            
            from datetime import datetime
            
            # Add to table
            self._table.add([{
                "name": name,
                "description": description,
                "code": code,
                "vector": vector,
                "metadata": json.dumps(metadata or {}),
                "created_at": datetime.utcnow().isoformat()
            }])
            
            logger.info(f"Successfully added primitive: {name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add primitive: {e}")
            return False
    
    async def update_primitive(
        self,
        name: str,
        description: Optional[str] = None,
        code: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Update an existing primitive.
        
        Args:
            name: Name of primitive to update
            description: New description (optional)
            code: New code (optional)
            metadata: New metadata (optional)
            
        Returns:
            True if successful
        """
        if not self._initialized:
            await self.initialize()
        
        logger.info(f"Updating primitive: {name}")
        
        try:
            # Delete existing
            self._table.delete(f'name = "{name}"')
            
            # Re-add with updated fields
            # First get existing data if not replacing
            # (For simplicity, we require all fields for updates)
            if description and code:
                return await self.add_primitive(name, description, code, metadata)
            else:
                logger.error("Update requires both description and code")
                return False
                
        except Exception as e:
            logger.error(f"Failed to update primitive: {e}")
            return False
    
    async def delete_primitive(self, name: str) -> bool:
        """Delete a primitive from the store.
        
        Args:
            name: Name of primitive to delete
            
        Returns:
            True if successful
        """
        if not self._initialized:
            await self.initialize()
        
        logger.info(f"Deleting primitive: {name}")
        
        try:
            self._table.delete(f'name = "{name}"')
            logger.info(f"Successfully deleted primitive: {name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete primitive: {e}")
            return False
    
    async def list_primitives(self) -> List[Dict[str, Any]]:
        """List all primitives in the store.
        
        Returns:
            List of primitive info (without code and vectors)
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            results = self._table.to_pandas()
            
            primitives = []
            for _, row in results.iterrows():
                primitives.append({
                    "name": row['name'],
                    "description": row['description'],
                    "created_at": row.get('created_at', 'unknown'),
                    "metadata": json.loads(row.get('metadata', '{}'))
                })
            
            return primitives
            
        except Exception as e:
            logger.error(f"Failed to list primitives: {e}")
            return []
    
    async def get_primitive(self, name: str) -> Optional[PrimitiveMatch]:
        """Get a specific primitive by name.
        
        Args:
            name: Name of primitive
            
        Returns:
            PrimitiveMatch if found, None otherwise
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            results = (
                self._table.search()
                .where(f'name = "{name}"')
                .limit(1)
                .to_pandas()
            )
            
            if len(results) == 0:
                return None
            
            row = results.iloc[0]
            return PrimitiveMatch(
                name=row['name'],
                description=row['description'],
                code=row['code'],
                score=1.0,  # Exact match
                metadata=json.loads(row.get('metadata', '{}'))
            )
            
        except Exception as e:
            logger.error(f"Failed to get primitive: {e}")
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the primitive store.
        
        Returns:
            Statistics dictionary
        """
        if not self._initialized or self._table is None:
            return {"status": "not_initialized"}
        
        try:
            count = len(self._table.to_pandas())
            return {
                "status": "initialized",
                "total_primitives": count,
                "database_path": self._db_path,
                "table_name": self._config.lancedb.table_primitives
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}


# Singleton instance
_intent_finder: Optional[IntentFinder] = None


async def get_intent_finder() -> IntentFinder:
    """Get the global IntentFinder instance.
    
    Returns:
        Singleton IntentFinder instance (initialized)
    """
    global _intent_finder
    if _intent_finder is None:
        _intent_finder = IntentFinder()
        await _intent_finder.initialize()
    return _intent_finder