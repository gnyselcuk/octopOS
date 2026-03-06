"""Search Engine - Web search with Brave API and DuckDuckGo fallback.

Provides web search capabilities using Brave Search API as primary,
with DuckDuckGo as anonymous fallback.

Example:
    >>> from src.primitives.web.search_engine import SearchEngine
    >>> engine = SearchEngine()
    >>> result = await engine.execute(
    ...     query="python best practices",
    ...     num_results=5
    ... )
"""

import os
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
import asyncio

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

try:
    from ddgs import DDGS
    HAS_DUCKDUCKGO = True
except ImportError:
    HAS_DUCKDUCKGO = False

from src.primitives.base_primitive import BasePrimitive, PrimitiveResult, register_primitive
from src.utils.config import get_config
from src.utils.logger import get_logger

logger = get_logger()


class SearchProvider(str, Enum):
    """Available search providers."""
    BRAVE = "brave"
    DUCKDUCKGO = "duckduckgo"
    AUTO = "auto"  # Try Brave first, fallback to DuckDuckGo


@dataclass
class SearchResult:
    """A single search result."""
    title: str
    url: str
    snippet: str
    source: str  # Provider that returned this result
    rank: int


class SearchEngine(BasePrimitive):
    """Web search with multiple provider support.
    
    Primary: Brave Search API (requires API key, higher quality)
    Fallback: DuckDuckGo (no API key needed, anonymous)
    
    The search engine automatically falls back to DuckDuckGo if:
    - Brave API key is not configured
    - Brave API returns an error
    - Rate limit is hit
    """
    
    # Brave API settings
    BRAVE_API_URL = "https://api.search.brave.com/res/v1/web/search"
    BRAVE_DEFAULT_RESULTS = 5
    BRAVE_MAX_RESULTS = 20
    
    def __init__(self) -> None:
        """Initialize Search Engine."""
        super().__init__()
        self._brave_api_key: Optional[str] = None
        self._http_client: Optional[Any] = None
        self._duckduckgo_client: Optional[Any] = None
    
    def _get_brave_api_key(self) -> Optional[str]:
        """Get Brave API key from centralized config."""
        if self._brave_api_key is None:
            config = get_config()
            self._brave_api_key = config.web.brave_api_key
        
        return self._brave_api_key
    
    @property
    def name(self) -> str:
        return "web_search"
    
    @property
    def description(self) -> str:
        return (
            "Search the web for information. Uses Brave Search API by default "
            "(if API key configured) with automatic fallback to DuckDuckGo. "
            "Returns top results with title, URL, and snippet."
        )
    
    @property
    def parameters(self) -> Dict[str, Dict[str, Any]]:
        return {
            "query": {
                "type": "string",
                "description": "Search query",
                "required": True
            },
            "num_results": {
                "type": "integer",
                "description": "Number of results to return (1-20, default: 5)",
                "required": False,
                "default": 5
            },
            "provider": {
                "type": "string",
                "description": "Search provider: brave, duckduckgo, or auto",
                "required": False,
                "default": "auto",
                "enum": [p.value for p in SearchProvider]
            },
            "safesearch": {
                "type": "string",
                "description": "Safe search level: strict, moderate, off",
                "required": False,
                "default": "moderate",
                "enum": ["strict", "moderate", "off"]
            }
        }
    
    async def execute(self, **kwargs) -> PrimitiveResult:
        """Execute web search.
        
        Args:
            query: Search query string
            num_results: Number of results (default: 5)
            provider: Search provider (default: auto)
            safesearch: Safe search level (default: moderate)
            
        Returns:
            PrimitiveResult with search results
        """
        query = kwargs.get("query", "").strip()
        num_results = min(kwargs.get("num_results", 5), self.BRAVE_MAX_RESULTS)
        provider_str = kwargs.get("provider", "auto")
        safesearch = kwargs.get("safesearch", "moderate")
        
        if not query:
            return PrimitiveResult(
                success=False,
                data=None,
                message="Search query is required",
                error="MissingQuery"
            )
        
        try:
            provider = SearchProvider(provider_str)
        except ValueError:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Invalid provider: {provider_str}",
                error="InvalidProvider"
            )
        
        results: List[SearchResult] = []
        used_provider: Optional[str] = None
        errors: List[str] = []
        
        # Determine which providers to try
        providers_to_try = []
        
        if provider == SearchProvider.AUTO:
            # Try Brave first if API key available, then DuckDuckGo
            if self._get_brave_api_key():
                providers_to_try.append(SearchProvider.BRAVE)
            providers_to_try.append(SearchProvider.DUCKDUCKGO)
        else:
            providers_to_try.append(provider)
        
        # Try each provider
        for prov in providers_to_try:
            try:
                if prov == SearchProvider.BRAVE:
                    results = await self._search_brave(query, num_results, safesearch)
                    used_provider = "brave"
                elif prov == SearchProvider.DUCKDUCKGO:
                    results = await self._search_duckduckgo(query, num_results, safesearch)
                    used_provider = "duckduckgo"
                
                if results:
                    break  # Got results, stop trying
                    
            except Exception as e:
                error_msg = f"{prov.value} failed: {str(e)}"
                logger.warning(error_msg)
                errors.append(error_msg)
                continue
        
        if not results:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"All search providers failed. Errors: {'; '.join(errors)}",
                error="AllProvidersFailed"
            )
        
        # Format results
        formatted_results = [
            {
                "rank": r.rank,
                "title": r.title,
                "url": r.url,
                "snippet": r.snippet,
                "source": r.source
            }
            for r in results[:num_results]
        ]
        
        return PrimitiveResult(
            success=True,
            data={
                "query": query,
                "provider": used_provider,
                "results": formatted_results,
                "count": len(formatted_results)
            },
            message=f"Found {len(formatted_results)} results using {used_provider}",
            metadata={
                "providers_attempted": [p.value for p in providers_to_try],
                "errors": errors if errors else None
            }
        )
    
    async def _search_brave(
        self,
        query: str,
        num_results: int,
        safesearch: str
    ) -> List[SearchResult]:
        """Search using Brave API.
        
        Args:
            query: Search query
            num_results: Number of results
            safesearch: Safe search level
            
        Returns:
            List of search results
        """
        if not HAS_HTTPX:
            raise ImportError("httpx is required for Brave search")
        
        api_key = self._get_brave_api_key()
        if not api_key:
            raise ValueError("Brave API key not configured")
        
        # Map safesearch to Brave format
        safesearch_map = {
            "strict": "strict",
            "moderate": "moderate",
            "off": "off"
        }
        brave_safesearch = safesearch_map.get(safesearch, "moderate")
        
        headers = {
            "X-Subscription-Token": api_key,
            "Accept": "application/json"
        }
        
        params = {
            "q": query,
            "count": num_results,
            "safesearch": brave_safesearch,
            "text_decorations": False,
            "search_lang": "en"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.BRAVE_API_URL,
                headers=headers,
                params=params,
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
        
        results = []
        web_results = data.get("web", {}).get("results", [])
        
        for idx, item in enumerate(web_results[:num_results], 1):
            result = SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("description", ""),
                source="brave",
                rank=idx
            )
            results.append(result)
        
        return results
    
    async def _search_duckduckgo(
        self,
        query: str,
        num_results: int,
        safesearch: str
    ) -> List[SearchResult]:
        """Search using DuckDuckGo.
        
        Args:
            query: Search query
            num_results: Number of results
            safesearch: Safe search level
            
        Returns:
            List of search results
        """
        if not HAS_DUCKDUCKGO:
            raise ImportError("ddgs is required")
        
        # Map safesearch to DDG format (v8+ supports 'strict', 'moderate', 'off')
        ddg_safesearch = "strict" if safesearch == "strict" else "moderate"
        if safesearch == "off":
            ddg_safesearch = "off"
        
        def _ddg_search():
            config = get_config()
            region = config.web.ddg_region
            with DDGS() as ddgs:
                return list(ddgs.text(
                    query,
                    max_results=num_results,
                    safesearch=ddg_safesearch,
                    region=region
                ))
        
        try:
            ddg_results = await asyncio.to_thread(_ddg_search)
        except Exception as e:
            logger.error(f"DuckDuckGo search error: {e}")
            raise
        
        results = []
        for idx, item in enumerate(ddg_results[:num_results], 1):
            result = SearchResult(
                title=item.get("title", ""),
                url=item.get("href", ""),
                snippet=item.get("body", ""),
                source="duckduckgo",
                rank=idx
            )
            results.append(result)
        
        return results


def register_all() -> None:
    """Register search engine primitives."""
    register_primitive(SearchEngine())
