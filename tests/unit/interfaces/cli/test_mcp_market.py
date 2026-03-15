"""Tests for the MCP market CLI helpers."""

from unittest.mock import AsyncMock, patch

from src.interfaces.cli import mcp_market
from src.utils.config import OctoConfig


def test_build_server_config_keeps_transport_specific_fields():
    spec = {
        "id": "remote",
        "transport": "sse",
        "url": "https://example.com/sse",
        "headers": {"Authorization": "Bearer token"},
    }

    server = mcp_market._build_server_config(spec, env_vars={}, command_args=[])

    assert server.name == "remote"
    assert server.transport == "sse"
    assert server.url == "https://example.com/sse"
    assert server.headers == {"Authorization": "Bearer token"}


def test_load_registry_uses_resolved_path(tmp_path):
    registry_path = tmp_path / "mcp_registry.json"
    registry_path.write_text('[{"id": "memory", "name": "Memory"}]', encoding="utf-8")

    with patch("src.interfaces.cli.mcp_market._resolve_registry_path", return_value=registry_path):
        registry = mcp_market._load_registry()

    assert registry == [{"id": "memory", "name": "Memory"}]


def test_install_mcp_aborts_when_validation_fails():
    spec = {
        "id": "memory",
        "name": "Memory",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-memory"],
    }
    config = OctoConfig()

    with patch("src.interfaces.cli.mcp_market._validate_mcp_server", new=AsyncMock()) as mock_validate, \
         patch("src.interfaces.cli.mcp_market.asyncio.run", side_effect=lambda coro: (coro.close(), False)[1]), \
         patch("src.interfaces.cli.mcp_market.load_config", return_value=config), \
         patch("src.interfaces.cli.mcp_market.save_config") as mock_save:
        mcp_market._install_mcp(spec)

    assert "memory" not in config.mcp.servers
    mock_validate.assert_called_once()
    mock_save.assert_not_called()


def test_install_mcp_saves_validated_server_with_env_persistence():
    spec = {
        "id": "memory",
        "name": "Memory",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-memory"],
        "env_requirements": ["MEMORY_API_KEY"],
    }
    config = OctoConfig()

    with patch("src.interfaces.cli.mcp_market.questionary.password") as mock_password, \
         patch("src.interfaces.cli.mcp_market._validate_mcp_server", new=AsyncMock()) as mock_validate, \
         patch("src.interfaces.cli.mcp_market.asyncio.run", side_effect=lambda coro: (coro.close(), True)[1]), \
         patch("src.interfaces.cli.mcp_market.load_config", return_value=config), \
         patch("src.interfaces.cli.mcp_market.save_config") as mock_save:
        mock_password.return_value.ask.return_value = "secret"
        mcp_market._install_mcp(spec)

    assert config.mcp.servers["memory"].env == {"MEMORY_API_KEY": "secret"}
    mock_validate.assert_called_once()
    mock_save.assert_called_once_with(config, persist_mcp_env=True)
