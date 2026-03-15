"""Unit tests for primitives/web/public_api_caller.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.primitives.web.public_api_caller import PublicAPICaller


class _MockResponse:
    def __init__(self, payload, status_code=200, url="https://api.example.test"):
        self._payload = payload
        self.status_code = status_code
        self.url = url
        self.elapsed = None

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _MockClient:
    def __init__(self, response):
        self._response = response
        self.last_url = None
        self.last_params = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, params=None):
        self.last_url = url
        self.last_params = params
        return self._response


@pytest.mark.asyncio
async def test_empty_index_returns_clear_error():
    caller = PublicAPICaller()
    caller._initialize_index = AsyncMock()

    mock_index = MagicMock()
    mock_index.get_all_apis = AsyncMock(return_value={})
    caller._index = mock_index

    result = await caller.execute(api_name="bitcoin price", endpoint="price")

    assert result.success is False
    assert result.error == "EmptyAPIIndex"


@pytest.mark.asyncio
async def test_unknown_endpoint_is_resolved_to_curated_match():
    caller = PublicAPICaller()
    caller._initialize_index = AsyncMock()

    coinbase_definition = {
        "base_url": "https://api.coinbase.com",
        "endpoints": {
            "spot_price": {
                "path": "/v2/prices/{pair}/spot",
                "method": "GET",
                "description": "Get current spot price for a crypto pair",
                "required_params": []
            }
        }
    }
    mock_index = MagicMock()
    mock_index.get_all_apis = AsyncMock(return_value={"coinbase": coinbase_definition})
    mock_index.search = AsyncMock(return_value=[{
        "score": 0.95,
        "definition": coinbase_definition,
        "api_id": "coinbase",
    }])
    caller._index = mock_index

    response = _MockResponse({"data": {"amount": "82000.12"}}, url="https://api.coinbase.com/v2/prices/BTC-USD/spot")
    client = _MockClient(response)
    with patch("src.primitives.web.public_api_caller.httpx.AsyncClient", return_value=client):
        result = await caller.execute(
            api_name="bitcoin price",
            endpoint="current_price",
            path_params={"pair": "BTC-USD"},
        )

    assert result.success is True
    assert result.data["api"] == "coinbase"
    assert result.data["endpoint"] == "spot_price"
    assert result.data["normalized"] == {
        "kind": "price_quote",
        "answer_text": "The current price of BTC is 82000.12 USD.",
        "confidence": 0.95,
        "entities": {
            "pair": "BTC-USD",
            "asset": "BTC",
            "quote": "USD",
        },
        "observations": {"price": "82000.12"},
        "missing_requirements": [],
        "source": "coinbase",
        "endpoint": "spot_price",
        "asset": "BTC",
        "quote": "USD",
        "price": "82000.12",
    }
    assert client.last_url.endswith("/v2/prices/BTC-USD/spot")


@pytest.mark.asyncio
async def test_coinbase_autofills_pair_from_semantic_query():
    caller = PublicAPICaller()
    caller._initialize_index = AsyncMock()

    coinbase_definition = {
        "base_url": "https://api.coinbase.com",
        "default_endpoint": "spot_price",
        "entity_resolution": {
            "asset_aliases": {"bitcoin": "BTC", "btc": "BTC"},
            "quote_aliases": {"usd": "USD", "dollar": "USD"},
        },
        "endpoints": {
            "spot_price": {
                "path": "/v2/prices/{pair}/spot",
                "method": "GET",
                "description": "Get current spot price for a crypto pair",
                "required_params": [],
                "path_param_templates": {
                    "pair": {
                        "separator": "-",
                        "parts": [
                            {"entity": "asset", "required": True, "transform": "upper"},
                            {"entity": "quote", "default": "USD", "transform": "upper"},
                        ],
                    }
                },
            }
        },
    }
    mock_index = MagicMock()
    mock_index.get_all_apis = AsyncMock(return_value={"coinbase": coinbase_definition})
    mock_index.search = AsyncMock(return_value=[{
        "score": 0.95,
        "definition": coinbase_definition,
        "api_id": "coinbase",
    }])
    caller._index = mock_index

    response = _MockResponse({"data": {"amount": "82000.12"}}, url="https://api.coinbase.com/v2/prices/BTC-USD/spot")
    client = _MockClient(response)
    with patch("src.primitives.web.public_api_caller.httpx.AsyncClient", return_value=client):
        result = await caller.execute(api_name="bitcoin current price", endpoint="spot_price")

    assert result.success is True
    assert client.last_url.endswith("/v2/prices/BTC-USD/spot")
    assert result.data["normalized"]["asset"] == "BTC"
    assert result.data["normalized"]["quote"] == "USD"


def test_select_endpoint_uses_catalog_default_when_hint_missing():
    caller = PublicAPICaller()
    api_config = {
        "default_endpoint": "spot_price",
        "endpoints": {
            "spot_price": {"description": "Current spot price"},
            "buy_price": {"description": "Current buy price"},
        },
    }

    endpoint = caller._select_endpoint("btc current price", "", api_config)

    assert endpoint == "spot_price"


@pytest.mark.asyncio
async def test_semantic_match_uses_endpoint_from_index_result():
    caller = PublicAPICaller()
    caller._initialize_index = AsyncMock()

    rest_countries_definition = {
        "base_url": "https://restcountries.com",
        "endpoints": {
            "by_code": {
                "path": "/v3.1/alpha/{code}",
                "method": "GET",
                "description": "Search a country by code.",
                "required_params": [],
            },
            "by_currency": {
                "path": "/v3.1/currency/{currency}",
                "method": "GET",
                "description": "Search countries by currency code or name.",
                "required_params": [],
            },
        },
    }
    mock_index = MagicMock()
    mock_index.get_all_apis = AsyncMock(return_value={"rest_countries": rest_countries_definition})
    mock_index.search = AsyncMock(return_value=[{
        "score": 0.57,
        "definition": rest_countries_definition,
        "api_id": "rest_countries",
        "endpoint_name": "by_currency",
    }])
    caller._index = mock_index

    response = _MockResponse([{"name": {"common": "United States"}}], url="https://restcountries.com/v3.1/currency/usd")
    client = _MockClient(response)
    with patch("src.primitives.web.public_api_caller.httpx.AsyncClient", return_value=client):
        result = await caller.execute(
            api_name="country by currency",
            path_params={"currency": "usd"},
        )

    assert result.success is True
    assert result.data["api"] == "rest_countries"
    assert result.data["endpoint"] == "by_currency"
    assert client.last_url.endswith("/v3.1/currency/usd")


@pytest.mark.asyncio
async def test_missing_requirements_are_exposed_in_normalized_contract():
    caller = PublicAPICaller()
    caller._initialize_index = AsyncMock()

    rest_countries_definition = {
        "base_url": "https://restcountries.com",
        "endpoints": {
            "by_currency": {
                "path": "/v3.1/currency/{currency}",
                "method": "GET",
                "description": "Search countries by currency code or name.",
                "required_params": [],
                "path_param_templates": {
                    "currency": {
                        "parts": [{"entity": "currency", "required": True}],
                    }
                },
            },
        },
    }
    mock_index = MagicMock()
    mock_index.get_all_apis = AsyncMock(return_value={"rest_countries": rest_countries_definition})
    mock_index.search = AsyncMock(return_value=[{
        "score": 0.57,
        "definition": rest_countries_definition,
        "api_id": "rest_countries",
        "endpoint_name": "by_currency",
    }])
    caller._index = mock_index

    result = await caller.execute(api_name="country by currency")

    assert result.success is False
    assert result.error == "MissingPathParameters"
    assert result.data["normalized"] == {
        "kind": "missing_requirements",
        "answer_text": None,
        "confidence": 0.0,
        "entities": {},
        "observations": {},
        "missing_requirements": [
            {"name": "currency", "location": "path", "entities": ["currency"]}
        ],
        "source": "rest_countries",
        "endpoint": "by_currency",
    }
