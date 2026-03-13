"""Public API Index - Semantic search for public APIs.

Indexes API definitions from a JSON file into LanceDB for semantic retrieval.
"""

import json
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.utils.aws_sts import get_bedrock_client
from src.utils.config import get_config
from src.utils.logger import get_logger

logger = get_logger()

class APIIndex:
    """Semantic index for public APIs using LanceDB."""
    
    def __init__(self, json_path: Optional[str] = None) -> None:
        """Initialize the API Index.
        
        Args:
            json_path: Path to the JSON file containing API definitions
        """
        self._config = get_config()
        self._json_path = json_path or "~/.octopos/data/config/public_apis.json"
        self._db_path = self._config.lancedb.path
        self._table_name = self._config.lancedb.table_public_apis
        self._bedrock_client = None
        self._table = None
        self._initialized = False
        
    async def initialize(self) -> None:
        """Initialize database connection and sync with JSON if needed."""
        if self._initialized:
            return
            
        try:
            import lancedb
            import pyarrow as pa
            
            self._bedrock_client = get_bedrock_client()
            
            # Connect to LanceDB
            db_path = Path(self._db_path).expanduser()
            db_path.mkdir(parents=True, exist_ok=True)
            self._db = lancedb.connect(str(db_path))
            
            # Create table if it doesn't exist
            if self._table_name not in self._db.table_names():
                schema = pa.schema([
                    ("endpoint_id", pa.string()),  # api_id:endpoint_name
                    ("api_id", pa.string()),
                    ("endpoint_name", pa.string()),
                    ("description", pa.string()),
                    ("vector", pa.list_(pa.float32(), 1024)),
                    ("full_api_definition", pa.string())  # JSON string
                ])
                self._table = self._db.create_table(self._table_name, schema=schema)
                # If table is new, sync it immediately
                await self.sync_index()
            else:
                self._table = self._db.open_table(self._table_name)
                
            self._initialized = True
            logger.info(f"API Index initialized with {len(self._table.to_pandas()) if self._table else 0} endpoint entries")
            
        except Exception as e:
            logger.error(f"Failed to initialize API Index: {e}")
            raise

    async def _get_embedding(self, text: str) -> List[float]:
        """Generate embedding vector for text."""
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

    async def sync_index(self) -> None:
        """Synchronize the vector database with the JSON definition file."""
        try:
            json_file = Path(self._json_path)
            if not json_file.exists():
                logger.warning(f"API definition file not found: {self._json_path}")
                return
                
            with open(json_file, 'r') as f:
                apis = json.load(f)
            
            data_to_add = []
            for api_id, definition in apis.items():
                api_desc = definition.get("description", "")
                
                # Each endpoint gets its own record
                for e_name, e_def in definition.get("endpoints", {}).items():
                    e_desc = e_def.get('description', '')
                    # Semantic context includes API purpose and specific endpoint purpose
                    search_text = f"API: {api_id} ({api_desc})\nEndpoint: {e_name}\nFunction: {e_desc}"
                    
                    vector = await self._get_embedding(search_text)
                    data_to_add.append({
                        "endpoint_id": f"{api_id}:{e_name}",
                        "api_id": api_id,
                        "endpoint_name": e_name,
                        "description": e_desc,
                        "vector": vector,
                        "full_api_definition": json.dumps(definition)
                    })
            
            if data_to_add:
                # We use Overwrite mode for sync
                self._table.add(data_to_add, mode="overwrite")
                logger.info(f"Synchronized {len(data_to_add)} endpoints to index")
                
        except Exception as e:
            logger.error(f"Failed to sync API index: {e}")

    async def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Search for APIs matching the query.
        
        Returns:
            List of matching API definitions with relevance scores
        """
        if not self._initialized:
            await self.initialize()
            
        try:
            query_vector = await self._get_embedding(query)
            results = (
                self._table.search(query_vector)
                .limit(top_k)
                .to_pandas()
            )
            
            matches = []
            for _, row in results.iterrows():
                distance = row.get('_distance', 1.0)
                # Better similarity mapping for L2 (assuming normalized vectors)
                similarity = 1.0 - (distance / 2.0)
                similarity = max(0.0, min(1.0, similarity))
                
                matches.append({
                    "api_id": row['api_id'],
                    "endpoint_name": row['endpoint_name'],
                    "description": row['description'],
                    "definition": json.loads(row['full_api_definition']),
                    "score": similarity
                })
            return matches
        except Exception as e:
            logger.error(f"API search failed: {e}")
            return []

    async def get_all_apis(self) -> Dict[str, Any]:
        """Get all API definitions from the index."""
        if not self._initialized:
            await self.initialize()
            
        results = self._table.to_pandas()
        # Group by api_id since one record per endpoint now
        apis = {}
        for _, row in results.iterrows():
            api_id = row['api_id']
            if api_id not in apis:
                apis[api_id] = json.loads(row['full_api_definition'])
        return apis


_api_index: Optional[APIIndex] = None

async def get_api_index() -> APIIndex:
    """Get singleton instance of APIIndex."""
    global _api_index
    if _api_index is None:
        _api_index = APIIndex()
        await _api_index.initialize()
    return _api_index
