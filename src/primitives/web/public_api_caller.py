"""Public API Caller - Curated public API integration.

Provides access to popular free public APIs from the GitHub public-apis list.
Includes pre-configured schemas and endpoints for common use cases.

Example:
    >>> from src.primitives.web.public_api_caller import PublicAPICaller
    >>> caller = PublicAPICaller()
    >>> result = await caller.execute(
    ...     api_name="space_station",
    ...     endpoint="astros"
    ... )
"""

import json
from typing import Any, Dict, List, Optional
import asyncio

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

from src.primitives.base_primitive import BasePrimitive, PrimitiveResult, register_primitive
from src.utils.logger import get_logger
from src.primitives.web.api_index import get_api_index

logger = get_logger()


class PublicAPICaller(BasePrimitive):
    """Call curated public APIs.
    
    Provides access to popular free APIs without requiring API keys:
    - Space data (ISS location, astronauts)
    - Random data (users, facts, quotes)
    - Fun APIs (jokes, activities)
    - Utility APIs (IP lookup, name prediction)
    - GitHub public API
    """
    
    def __init__(self) -> None:
        """Initialize Public API Caller."""
        super().__init__()
        self._http_client: Optional[Any] = None
        self._index = None
    
    async def _initialize_index(self):
        if self._index is None:
            self._index = await get_api_index()

    @property
    def name(self) -> str:
        return "public_api_call"
    
    @property
    def description(self) -> str:
        return (
            "Call curated public APIs from a semantically indexed database. "
            "No API keys required. Includes space data, financial data, "
            "dictionary, random facts, jokes, and more. "
            "If you specify a general intent as api_name, it will find the best match."
        )
    
    @property
    def parameters(self) -> Dict[str, Dict[str, Any]]:
        return {
            "api_name": {
                "type": "string",
                "description": "Target API name OR semantic query (e.g., 'crypto prices' or 'jokes')",
                "required": True
            },
            "endpoint": {
                "type": "string",
                "description": "Endpoint name for the API",
                "required": True
            },
            "params": {
                "type": "object",
                "description": "Query parameters for the request",
                "required": False,
                "default": {}
            },
            "path_params": {
                "type": "object",
                "description": "URL path parameters (e.g., {username}, {word})",
                "required": False,
                "default": {}
            }
        }
    
    async def execute(self, **kwargs) -> PrimitiveResult:
        """Execute public API call.
        
        Args:
            api_name: Name of the API to use
            endpoint: Endpoint to call
            params: Query parameters
            path_params: URL path parameters
            
        Returns:
            PrimitiveResult with API response
        """
        await self._initialize_index()
        api_definitions = await self._index.get_all_apis()
        
        api_name_input = kwargs.get("api_name", "").lower()
        endpoint = kwargs.get("endpoint", "")
        params = kwargs.get("params", {})
        path_params = kwargs.get("path_params", {})
        
        if not HAS_HTTPX:
            return PrimitiveResult(
                success=False,
                data=None,
                message="httpx is required for API calls",
                error="MissingDependency"
            )
        
        api_config = None
        api_name = None

        # 1. Try exact match
        if api_name_input in api_definitions:
            api_config = api_definitions[api_name_input]
            api_name = api_name_input
        else:
            # 2. Try semantic search
            logger.info(f"Semantic search for API: {api_name_input}")
            matches = await self._index.search(api_name_input, top_k=1)
            if matches and matches[0]['score'] > 0.4:
                api_config = matches[0]['definition']
                api_name = matches[0]['api_id']
                logger.info(f"Matched '{api_name_input}' to '{api_name}' (score: {matches[0]['score']:.2f})")
        
        # Validate API
        if not api_config:
            available = ", ".join(sorted(api_definitions.keys()))
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Unknown API or search failed for: {api_name_input}. Use one of: {available}",
                error="UnknownAPI"
            )
        
        # Validate endpoint
        if endpoint not in api_config["endpoints"]:
            available = ", ".join(api_config["endpoints"].keys())
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Unknown endpoint: {endpoint}. Available: {available}",
                error="UnknownEndpoint"
            )
        
        endpoint_config = api_config["endpoints"][endpoint]
        
        try:
            # Build URL
            path = endpoint_config["path"]
            for key, value in path_params.items():
                path = path.replace(f"{{{key}}}", str(value))
            
            url = f"{api_config['base_url']}{path}"
            
            # Check required params
            required = endpoint_config.get("required_params", [])
            missing = [p for p in required if p not in params]
            if missing:
                return PrimitiveResult(
                    success=False,
                    data=None,
                    message=f"Missing required parameters: {', '.join(missing)}",
                    error="MissingParameters"
                )
            
            # Make request
            method = endpoint_config.get("method", "GET")
            
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                if method == "GET":
                    response = await client.get(url, params=params)
                elif method == "POST":
                    response = await client.post(url, json=params)
                else:
                    return PrimitiveResult(
                        success=False,
                        data=None,
                        message=f"Unsupported method: {method}",
                        error="UnsupportedMethod"
                    )
                
                response.raise_for_status()
                
                # Parse response
                try:
                    data = response.json()
                except json.JSONDecodeError:
                    data = {"text": response.text}
            
            return PrimitiveResult(
                success=True,
                data={
                    "api": api_name,
                    "endpoint": endpoint,
                    "url": str(response.url),
                    "response": data
                },
                message=f"Successfully called {api_name}.{endpoint}",
                metadata={
                    "status_code": response.status_code,
                    "response_time_ms": getattr(response, 'elapsed', None)
                }
            )
            
        except httpx.HTTPStatusError as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"HTTP error {e.response.status_code}: {e.response.text[:200]}",
                error=f"HTTP{e.response.status_code}"
            )
        except Exception as e:
            logger.error(f"API call error: {e}")
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"API call failed: {e}",
                error=str(e)
            )


def register_all() -> None:
    """Register public API caller primitive."""
    register_primitive(PublicAPICaller())
