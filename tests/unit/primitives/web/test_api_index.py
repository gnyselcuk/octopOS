"""Unit tests for primitives/web/api_index.py."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.primitives.web.api_index import APIIndex


@pytest.mark.asyncio
async def test_initialize_resyncs_existing_empty_table(tmp_path):
    json_path = tmp_path / "public_apis.json"
    json_path.write_text('{"coinbase": {"endpoints": {}}}', encoding="utf-8")

    with patch("src.primitives.web.api_index.get_config") as mock_get_config, \
         patch("src.primitives.web.api_index.get_bedrock_client"):
        config = MagicMock()
        config.lancedb.path = str(tmp_path / "lancedb")
        config.lancedb.table_public_apis = "public_apis"
        mock_get_config.return_value = config

        index = APIIndex(json_path=str(json_path))

    mock_table = MagicMock()
    mock_table.to_arrow.return_value.to_pylist.return_value = []
    mock_db = MagicMock()
    mock_db.table_names.return_value = ["public_apis"]
    mock_db.open_table.return_value = mock_table

    fake_lancedb = SimpleNamespace(connect=lambda _: mock_db)
    fake_pyarrow = SimpleNamespace(
        schema=lambda fields: fields,
        string=lambda: "string",
        float32=lambda: "float32",
        list_=lambda inner, size=None: (inner, size),
    )

    with patch.dict("sys.modules", {"lancedb": fake_lancedb, "pyarrow": fake_pyarrow}), \
         patch.object(index, "sync_index", new=AsyncMock()) as mock_sync:
        await index.initialize()

    mock_sync.assert_awaited_once()


@pytest.mark.asyncio
async def test_initialize_resyncs_when_catalog_definition_changed(tmp_path):
    json_path = tmp_path / "public_apis.json"
    json_path.write_text(
        '{"coinbase": {"default_endpoint": "spot_price", "endpoints": {"spot_price": {"path": "/spot"}}}}',
        encoding="utf-8",
    )

    with patch("src.primitives.web.api_index.get_config") as mock_get_config, \
         patch("src.primitives.web.api_index.get_bedrock_client"):
        config = MagicMock()
        config.lancedb.path = str(tmp_path / "lancedb")
        config.lancedb.table_public_apis = "public_apis"
        mock_get_config.return_value = config

        index = APIIndex(json_path=str(json_path))

    mock_table = MagicMock()
    mock_table.to_arrow.return_value.to_pylist.return_value = [{
        "api_id": "coinbase",
        "full_api_definition": json.dumps({"endpoints": {"spot_price": {"path": "/spot"}}}, sort_keys=True),
    }]
    mock_db = MagicMock()
    mock_db.table_names.return_value = ["public_apis"]
    mock_db.open_table.return_value = mock_table

    fake_lancedb = SimpleNamespace(connect=lambda _: mock_db)
    fake_pyarrow = SimpleNamespace(
        schema=lambda fields: fields,
        string=lambda: "string",
        float32=lambda: "float32",
        list_=lambda inner, size=None: (inner, size),
    )

    with patch.dict("sys.modules", {"lancedb": fake_lancedb, "pyarrow": fake_pyarrow}), \
         patch.object(index, "sync_index", new=AsyncMock()) as mock_sync:
        await index.initialize()

    mock_sync.assert_awaited_once()


def test_load_api_definitions_expands_user_home(tmp_path, monkeypatch):
    home_dir = tmp_path / "home"
    catalog_dir = home_dir / ".octopos" / "data" / "config"
    catalog_dir.mkdir(parents=True)
    catalog_path = catalog_dir / "public_apis.json"
    catalog_path.write_text('{"coinbase": {"endpoints": {}}}', encoding="utf-8")

    with patch("src.primitives.web.api_index.get_config") as mock_get_config, \
         patch("src.primitives.web.api_index.get_bedrock_client"):
        config = MagicMock()
        config.lancedb.path = str(tmp_path / "lancedb")
        config.lancedb.table_public_apis = "public_apis"
        mock_get_config.return_value = config
        monkeypatch.setenv("HOME", str(home_dir))
        index = APIIndex()

    definitions = index._load_api_definitions()

    assert definitions == {"coinbase": {"endpoints": {}}}


def test_load_api_definitions_uses_repo_fallback_when_user_catalog_missing(tmp_path):
    repo_catalog = tmp_path / "data" / "config"
    repo_catalog.mkdir(parents=True)
    repo_catalog_path = repo_catalog / "public_apis.json"
    repo_catalog_path.write_text('{"coingecko": {"endpoints": {}}}', encoding="utf-8")

    with patch("src.primitives.web.api_index.get_config") as mock_get_config, \
         patch("src.primitives.web.api_index.get_bedrock_client"):
        config = MagicMock()
        config.lancedb.path = str(tmp_path / "lancedb")
        config.lancedb.table_public_apis = "public_apis"
        mock_get_config.return_value = config
        index = APIIndex(json_path=str(tmp_path / "missing.json"))

    with patch.object(index, "_candidate_json_paths", return_value=[tmp_path / "missing.json", repo_catalog_path]):
        definitions = index._load_api_definitions()

    assert definitions == {"coingecko": {"endpoints": {}}}
