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
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

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

    def _build_normalized_payload(
        self,
        *,
        kind: str,
        api_name: str,
        endpoint: str,
        confidence: float,
        answer_text: Optional[str] = None,
        entities: Optional[Dict[str, Any]] = None,
        observations: Optional[Dict[str, Any]] = None,
        missing_requirements: Optional[List[Dict[str, Any]]] = None,
        **extra: Any,
    ) -> Dict[str, Any]:
        """Build a common normalized result contract for query adjudication."""
        payload: Dict[str, Any] = {
            "kind": kind,
            "answer_text": answer_text,
            "confidence": confidence,
            "entities": entities or {},
            "observations": observations or {},
            "missing_requirements": missing_requirements or [],
            "source": api_name,
            "endpoint": endpoint,
        }
        payload.update(extra)
        return payload

    def _extract_entities_from_request(
        self,
        params: Dict[str, Any],
        path_params: Dict[str, Any],
        entity_memory: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Collect simple entities from request arguments for generic query-state reuse."""
        entities: Dict[str, Any] = {}
        for source in (entity_memory or {}, params, path_params):
            for key, value in source.items():
                if isinstance(value, (str, int, float, bool)) and value not in ("", None):
                    entities[str(key)] = value

        pair = path_params.get("pair")
        if isinstance(pair, str) and "-" in pair:
            asset, quote = pair.split("-", 1)
            entities.setdefault("asset", asset)
            entities.setdefault("quote", quote)

        return entities

    def _build_missing_requirements(
        self,
        endpoint_config: Dict[str, Any],
        missing_path_params: List[str],
        missing_params: List[str],
    ) -> List[Dict[str, Any]]:
        """Describe unresolved path/query requirements in a model-independent shape."""
        requirements: List[Dict[str, Any]] = []

        for param_name in missing_path_params:
            template = endpoint_config.get("path_param_templates", {}).get(param_name, {})
            entities = [
                part["entity"]
                for part in template.get("parts", [])
                if part.get("entity")
            ]
            requirements.append({
                "name": param_name,
                "location": "path",
                "entities": entities,
            })

        for param_name in missing_params:
            resolver = endpoint_config.get("param_resolvers", {}).get(param_name, {})
            entities = [resolver["entity"]] if resolver.get("entity") else []
            requirements.append({
                "name": param_name,
                "location": "query",
                "entities": entities,
            })

        return requirements

    def _normalize_response(
        self,
        api_name: str,
        endpoint: str,
        data: Any,
        params: Dict[str, Any],
        path_params: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Build a compact normalized view for common curated API responses."""
        entities = self._extract_entities_from_request(params, path_params)

        if api_name == "coinbase" and isinstance(data, dict):
            payload = data.get("data", {})
            amount = payload.get("amount")
            currency = payload.get("currency")
            pair = path_params.get("pair", "")
            asset = pair.split("-")[0] if "-" in pair else None
            quote = pair.split("-")[1] if "-" in pair else currency
            if amount is not None:
                answer_text = f"The current price of {asset or 'the asset'} is {amount} {quote or currency}."
                entities.update({"asset": asset, "quote": quote or currency})
                return self._build_normalized_payload(
                    kind="price_quote",
                    api_name=api_name,
                    endpoint=endpoint,
                    confidence=0.95,
                    answer_text=answer_text,
                    entities=entities,
                    observations={"price": amount},
                    asset=asset,
                    quote=quote or currency,
                    price=amount,
                )

        if api_name == "coingecko" and endpoint == "simple_price" and isinstance(data, dict):
            if len(data) == 1:
                asset, quote_map = next(iter(data.items()))
                if isinstance(quote_map, dict) and quote_map:
                    quote, price = next(iter(quote_map.items()))
                    answer_text = f"The current price of {asset} is {price} {str(quote).upper()}."
                    entities.update({"asset": asset, "quote": str(quote).upper()})
                    return self._build_normalized_payload(
                        kind="price_quote",
                        api_name=api_name,
                        endpoint=endpoint,
                        confidence=0.9,
                        answer_text=answer_text,
                        entities=entities,
                        observations={"price": price},
                        asset=asset,
                        quote=str(quote).upper(),
                        price=price,
                    )

        return None

    def _select_endpoint(
        self,
        api_name_input: str,
        endpoint_hint: str,
        api_config: Dict[str, Any],
        matched_endpoint: Optional[str] = None,
    ) -> Optional[str]:
        """Resolve an endpoint hint to the closest curated endpoint."""
        endpoints = api_config.get("endpoints", {})
        if not endpoints:
            return None

        if endpoint_hint in endpoints:
            return endpoint_hint

        if matched_endpoint in endpoints and (not endpoint_hint or endpoint_hint == api_name_input):
            return matched_endpoint

        default_endpoint = api_config.get("default_endpoint")
        if not endpoint_hint and default_endpoint in endpoints:
            return default_endpoint

        if not endpoint_hint and len(endpoints) == 1:
            return next(iter(endpoints.keys()))

        query = f"{api_name_input} {endpoint_hint}".strip().lower()
        best_name = None
        best_score = 0.0
        for endpoint_name, endpoint_def in endpoints.items():
            haystack = " ".join([
                endpoint_name,
                endpoint_def.get("description", ""),
                endpoint_def.get("path", ""),
            ]).lower()
            score = SequenceMatcher(None, query, haystack).ratio()
            if endpoint_hint and endpoint_hint.lower() in haystack:
                score += 0.4
            if score > best_score:
                best_score = score
                best_name = endpoint_name

        if best_score >= 0.25:
            logger.info(
                f"Matched endpoint hint '{endpoint_hint or api_name_input}' to '{best_name}' "
                f"(score: {best_score:.2f})"
            )
            return best_name

        return None

    def _apply_transform(self, value: Any, transform: Optional[str]) -> Any:
        """Apply a simple catalog-defined transform to a resolved value."""
        if not isinstance(value, str) or not transform:
            return value
        if transform == "upper":
            return value.upper()
        if transform == "lower":
            return value.lower()
        return value

    def _resolve_entity_value(
        self,
        query_text: str,
        entity: str,
        api_config: Dict[str, Any],
        entity_memory: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Resolve a semantic entity from the catalog's alias metadata."""
        if entity_memory and entity in entity_memory and entity_memory[entity] not in (None, ""):
            return str(entity_memory[entity])

        entity_resolution = api_config.get("entity_resolution", {})
        alias_map = entity_resolution.get(f"{entity}_aliases", {})
        lowered_query = query_text.lower()

        best_match = None
        for alias, value in alias_map.items():
            pattern = r"\b" + re.escape(alias.lower()) + r"\b"
            match = re.search(pattern, lowered_query)
            if not match:
                continue
            if best_match is None or len(alias) > len(best_match[0]):
                best_match = (alias, value)

        return best_match[1] if best_match else None

    def _autofill_request_arguments(
        self,
        api_name_input: str,
        endpoint_hint: str,
        api_config: Dict[str, Any],
        endpoint_config: Dict[str, Any],
        params: Dict[str, Any],
        path_params: Dict[str, Any],
        entity_memory: Optional[Dict[str, Any]] = None,
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """Fill missing request args using catalog metadata and the semantic query."""
        resolved_params = dict(params)
        resolved_path_params = dict(path_params)
        query_text = " ".join(part for part in [api_name_input, endpoint_hint] if part).strip()

        for param_name, template in endpoint_config.get("path_param_templates", {}).items():
            current_value = resolved_path_params.get(param_name)
            if current_value not in (None, ""):
                continue

            parts = []
            missing_required = False
            for part in template.get("parts", []):
                value = part.get("value")
                if value is None and part.get("entity"):
                    value = self._resolve_entity_value(query_text, part["entity"], api_config, entity_memory)
                if value is None:
                    value = part.get("default")
                if value is None and part.get("required", True):
                    missing_required = True
                    break
                if value is not None:
                    parts.append(str(self._apply_transform(value, part.get("transform"))))

            if not missing_required and parts:
                separator = template.get("separator", "")
                resolved_path_params[param_name] = separator.join(parts)

        for param_name, resolver in endpoint_config.get("param_resolvers", {}).items():
            current_value = resolved_params.get(param_name)
            if current_value not in (None, ""):
                continue

            value = None
            if resolver.get("entity"):
                value = self._resolve_entity_value(query_text, resolver["entity"], api_config, entity_memory)
            if value is None:
                value = resolver.get("default")
            if value is not None:
                resolved_params[param_name] = self._apply_transform(value, resolver.get("transform"))

        return resolved_params, resolved_path_params

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
                "description": "Endpoint name for the API. Optional if you want the tool to choose the closest curated endpoint.",
                "required": False,
                "default": ""
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
        query_text = str(kwargs.get("query_text") or api_name_input)
        endpoint = kwargs.get("endpoint", "")
        params = kwargs.get("params", {})
        path_params = kwargs.get("path_params", {})
        entity_memory = kwargs.get("entity_memory", {}) if isinstance(kwargs.get("entity_memory", {}), dict) else {}

        if not api_definitions:
            return PrimitiveResult(
                success=False,
                data=None,
                message=(
                    "Public API index is empty. Curated API definitions are unavailable; "
                    "use another tool or sync public_apis.json first."
                ),
                error="EmptyAPIIndex"
            )
        
        if not HAS_HTTPX:
            return PrimitiveResult(
                success=False,
                data=None,
                message="httpx is required for API calls",
                error="MissingDependency"
            )
        
        api_config = None
        api_name = None
        matched_endpoint = None

        # 1. Try exact match
        if api_name_input in api_definitions:
            api_config = api_definitions[api_name_input]
            api_name = api_name_input
        else:
            # 2. Try semantic search
            logger.info(f"Semantic search for API: {query_text}")
            matches = await self._index.search(query_text, top_k=3)
            if matches and matches[0]['score'] > 0.25:
                best_match = matches[0]
                api_config = best_match['definition']
                api_name = best_match['api_id']
                matched_endpoint = best_match.get('endpoint_name')
                logger.info(
                    f"Matched '{query_text}' to '{api_name}'"
                    f"/{matched_endpoint or 'unknown'} (score: {best_match['score']:.2f})"
                )
        
        # Validate API
        if not api_config:
            available = ", ".join(sorted(api_definitions.keys()))
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Unknown API or search failed for: {api_name_input}. Use one of: {available}",
                error="UnknownAPI"
            )
        
        resolved_endpoint = self._select_endpoint(
            query_text,
            endpoint,
            api_config,
            matched_endpoint=matched_endpoint,
        )
        if not resolved_endpoint:
            available = ", ".join(api_config["endpoints"].keys())
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Unknown endpoint: {endpoint}. Available: {available}",
                error="UnknownEndpoint"
            )

        endpoint = resolved_endpoint
        endpoint_config = api_config["endpoints"][endpoint]
        params, path_params = self._autofill_request_arguments(
            query_text,
            endpoint,
            api_config,
            endpoint_config,
            params,
            path_params,
            entity_memory,
        )
        
        try:
            # Build URL
            path = endpoint_config["path"]
            for key, value in path_params.items():
                path = path.replace(f"{{{key}}}", str(value))

            missing_path_params = re.findall(r"\{([^}]+)\}", path)
            if missing_path_params:
                normalized = self._build_normalized_payload(
                    kind="missing_requirements",
                    api_name=api_name,
                    endpoint=endpoint,
                    confidence=0.0,
                    entities=self._extract_entities_from_request(params, path_params, entity_memory),
                    missing_requirements=self._build_missing_requirements(
                        endpoint_config,
                        missing_path_params,
                        [],
                    ),
                )
                return PrimitiveResult(
                    success=False,
                    data={"api": api_name, "endpoint": endpoint, "normalized": normalized},
                    message=f"Missing path parameters: {', '.join(missing_path_params)}",
                    error="MissingPathParameters"
                )
            
            url = f"{api_config['base_url']}{path}"
            
            # Check required params
            required = endpoint_config.get("required_params", [])
            missing = [p for p in required if p not in params]
            if missing:
                normalized = self._build_normalized_payload(
                    kind="missing_requirements",
                    api_name=api_name,
                    endpoint=endpoint,
                    confidence=0.0,
                    entities=self._extract_entities_from_request(params, path_params, entity_memory),
                    missing_requirements=self._build_missing_requirements(
                        endpoint_config,
                        [],
                        missing,
                    ),
                )
                return PrimitiveResult(
                    success=False,
                    data={"api": api_name, "endpoint": endpoint, "normalized": normalized},
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
                    "response": data,
                    "normalized": self._normalize_response(
                        api_name,
                        endpoint,
                        data,
                        params,
                        path_params,
                    ),
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
