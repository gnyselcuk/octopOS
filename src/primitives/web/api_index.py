"""Public API Index - Semantic search for public APIs.

Indexes API definitions from a JSON file into LanceDB for semantic retrieval.
"""

import json
import os
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
        self._json_path = json_path or os.getenv("PUBLIC_API_CATALOG_PATH") or "~/.octopos/data/config/public_apis.json"
        self._db_path = self._config.lancedb.path
        self._table_name = self._config.lancedb.table_public_apis
        self._bedrock_client = None
        self._table = None
        self._initialized = False

    def _candidate_json_paths(self) -> List[Path]:
        """Return candidate API catalog paths ordered by preference."""
        candidates = [Path(self._json_path).expanduser()]
        repo_catalog = Path(__file__).resolve().parents[3] / "data" / "config" / "public_apis.json"
        candidates.append(repo_catalog)

        unique_candidates: List[Path] = []
        seen = set()
        for candidate in candidates:
            normalized = str(candidate)
            if normalized in seen:
                continue
            seen.add(normalized)
            unique_candidates.append(candidate)
        return unique_candidates

    def _resolve_json_path(self) -> Optional[Path]:
        """Resolve the first existing API catalog path."""
        for candidate in self._candidate_json_paths():
            if candidate.exists():
                return candidate
        return None
        
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
                if self._row_count() == 0 or self._needs_sync_with_json():
                    await self.sync_index()
                
            self._initialized = True
            logger.info(
                f"API Index initialized with {self._row_count() if self._table else 0} endpoint entries"
            )
            
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
            apis = self._load_api_definitions()
            if apis is None:
                return
            
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

    def _load_api_definitions(self) -> Optional[Dict[str, Any]]:
        """Load curated API definitions from disk."""
        json_file = self._resolve_json_path()
        if json_file is None:
            searched = ", ".join(str(path) for path in self._candidate_json_paths())
            logger.warning(f"API definition file not found. Searched: {searched}")
            return None

        if str(json_file) != str(Path(self._json_path).expanduser()):
            logger.info(f"Using fallback API catalog: {json_file}")

        with open(json_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _needs_sync_with_json(self) -> bool:
        """Return True when the persisted index is stale relative to the JSON catalog."""
        if self._table is None:
            return False

        apis = self._load_api_definitions()
        if apis is None:
            return False

        indexed_rows = self._table.to_arrow().to_pylist()
        indexed_defs: Dict[str, str] = {}
        for row in indexed_rows:
            api_id = row.get("api_id")
            if api_id and api_id not in indexed_defs:
                indexed_defs[api_id] = row.get("full_api_definition", "")

        current_defs = {
            api_id: json.dumps(definition, sort_keys=True)
            for api_id, definition in apis.items()
        }

        if set(indexed_defs.keys()) != set(current_defs.keys()):
            return True

        for api_id, current_definition in current_defs.items():
            stored_definition = indexed_defs.get(api_id)
            if stored_definition != current_definition:
                return True

        return False

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
                .to_arrow()
            )
            
            matches = []
            for row in results.to_pylist():
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
            
        results = self._table.to_arrow().to_pylist()
        # Group by api_id since one record per endpoint now
        apis = {}
        for row in results:
            api_id = row['api_id']
            if api_id not in apis:
                apis[api_id] = json.loads(row['full_api_definition'])
        return apis

    def _row_count(self) -> int:
        """Get row count without requiring pandas at runtime."""
        if self._table is None:
            return 0
        return len(self._table.to_arrow())


_api_index: Optional[APIIndex] = None

async def get_api_index() -> APIIndex:
    """Get singleton instance of APIIndex."""
    global _api_index
    if _api_index is None:
        _api_index = APIIndex()
        await _api_index.initialize()
    return _api_index
