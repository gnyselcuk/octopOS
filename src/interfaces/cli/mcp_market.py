"""MCP Market CLI - Visual Marketplace for MCP servers."""

import asyncio
import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional

import typer
import questionary
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from src.utils.config import load_config, save_config, MCPServerConfig
from src.primitives.mcp_adapter import MCPManager

console = Console()
app = typer.Typer(help="Manage MCP servers via the octopOS market.")

REGISTRY_PATH = Path("data/config/mcp_registry.json")


def _registry_candidates() -> List[Path]:
    """Return candidate registry locations ordered by preference."""
    candidates: List[Path] = []
    if env_path := os.getenv("MCP_REGISTRY_PATH"):
        candidates.append(Path(env_path).expanduser())
    candidates.append(Path.cwd() / REGISTRY_PATH)
    candidates.append(Path(__file__).resolve().parents[3] / "data" / "config" / "mcp_registry.json")

    seen = set()
    unique: List[Path] = []
    for candidate in candidates:
        normalized = str(candidate)
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(candidate)
    return unique


def _resolve_registry_path() -> Optional[Path]:
    """Resolve the first existing MCP registry path."""
    for candidate in _registry_candidates():
        if candidate.exists():
            return candidate
    return None


def _load_registry() -> List[Dict[str, Any]]:
    """Load the available MCP servers from the curated registry."""
    registry_path = _resolve_registry_path()
    if registry_path is None:
        searched = ", ".join(str(path) for path in _registry_candidates())
        console.print(f"[bold red]Error:[/bold red] MCP Registry not found. Searched: {searched}")
        return []
    try:
        with open(registry_path, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        console.print("[bold red]Error:[/bold red] Invalid JSON in MCP Registry.")
        return []


def _get_installed() -> Dict[str, MCPServerConfig]:
    """Get currently installed MCP servers from the active profile."""
    config = load_config()
    return config.mcp.servers


def _build_server_config(
    mcp_spec: Dict[str, Any],
    env_vars: Dict[str, str],
    command_args: List[str],
) -> MCPServerConfig:
    """Create a persisted MCP server config from a registry entry."""
    return MCPServerConfig(
        name=mcp_spec["id"],
        transport=mcp_spec["transport"],
        command=mcp_spec.get("command"),
        args=command_args,
        env=env_vars,
        url=mcp_spec.get("url"),
        headers=mcp_spec.get("headers", {}),
        enabled=True,
    )


async def _validate_mcp_server(server_config: MCPServerConfig) -> bool:
    """Try a live connection before persisting the MCP server."""
    manager = MCPManager()
    try:
        if server_config.transport == "stdio":
            ok = await manager.add_server_stdio(
                name=server_config.name,
                command=server_config.command,
                args=server_config.args,
                env=server_config.env,
                auto_discover=False,
            )
        elif server_config.transport == "sse":
            ok = await manager.add_server_sse(
                name=server_config.name,
                url=server_config.url,
                headers=server_config.headers,
                auto_discover=False,
            )
        else:
            console.print(f"[bold red]Error:[/bold red] Unsupported MCP transport: {server_config.transport}")
            return False

        if ok:
            await manager.remove_server(server_config.name)
        return ok
    finally:
        await manager.close_all()


def _install_mcp(mcp_spec: Dict[str, Any]) -> None:
    """Install and configure a selected MCP server."""
    console.print(Panel(f"Installing [bold cyan]{mcp_spec['name']}[/bold cyan]...", expand=False))
    
    env_vars = {}
    
    # Prompt for required environment variables
    for env_req in mcp_spec.get('env_requirements', []):
        val = questionary.password(f"[{mcp_spec['name']}] Enter value for {env_req}:").ask()
        if not val:
            console.print("[bold yellow]Installation cancelled: Missing required environment variable.[/bold yellow]")
            return
        env_vars[env_req] = val
        
    # Optional arguments that require user input (e.g. allowed_directories)
    command_args = mcp_spec.get('args', []).copy()
    for prompt_req in mcp_spec.get('arg_prompts', []):
        val = questionary.text(prompt_req['message']).ask()
        if not val:
            console.print("[bold yellow]Installation cancelled: Missing required argument.[/bold yellow]")
            return
        # Append the user input to the args list
        command_args.append(val)
    
    server_config = _build_server_config(mcp_spec, env_vars, command_args)

    console.print("[dim]Validating MCP server connection...[/dim]")
    if not asyncio.run(_validate_mcp_server(server_config)):
        console.print(f"[bold red]✗ Failed to validate {mcp_spec['name']}.[/bold red]")
        console.print("[dim]The server was not saved because octopOS could not connect to it.[/dim]")
        return

    # Save the configuration
    config = load_config()

    config.mcp.servers[mcp_spec['id']] = server_config

    save_config(config, persist_mcp_env=True)
    if env_vars:
        console.print("[bold yellow]Note:[/bold yellow] MCP env values were saved to your local profile so this server can reconnect on restart.")
    console.print(f"[bold green]✅ {mcp_spec['name']} successfully installed, validated, and activated![/bold green]")


def _uninstall_mcp(mcp_id: str, mcp_name: str) -> None:
    """Uninstall an MCP server removing it from the configuration."""
    confirm = questionary.confirm(f"Are you sure you want to uninstall {mcp_name}?").ask()
    if confirm:
        config = load_config()
        if mcp_id in config.mcp.servers:
            del config.mcp.servers[mcp_id]
            save_config(config)
            console.print(f"[bold red]❌ {mcp_name} uninstalled.[/bold red]")
        else:
            console.print("[bold yellow]Error: Attempted to uninstall an MCP that isn't active.[/bold yellow]")


@app.callback(invoke_without_command=True)
def market_tui(ctx: typer.Context):
    """Open the interactive MCP Market TUI."""
    if ctx.invoked_subcommand is not None:
        return
        
    registry = _load_registry()
    if not registry:
        return
        
    installed = _get_installed()
    
    console.print("\n[bold magenta]🐙 octopOS MCP Market[/bold magenta]")
    console.print("Enhance your agent's capabilities with officially supported plugins!\n")
    
    # Create the visual menu choices
    choices = []
    
    for item in registry:
        mcp_id = item['id']
        name = item['name']
        desc = item['description']
        
        if mcp_id in installed:
            status = "[✅ Installed]"
            choices.append(questionary.Choice(f"{status:<15} {name:<20} - {desc}", value={"action": "uninstall", "data": item}))
        else:
            status = "[  Not Inst ]"
            choices.append(questionary.Choice(f"{status:<15} {name:<20} - {desc}", value={"action": "install", "data": item}))
            
    choices.append(questionary.Choice("--> Exit Market", value={"action": "exit"}))

    selection = questionary.select(
        "Select an MCP to Install or Manage:",
        choices=choices,
        use_indicator=True,
    ).ask()
    
    if not selection or selection["action"] == "exit":
        console.print("[dim]Exiting Market...[/dim]")
        return
        
    if selection["action"] == "install":
        _install_mcp(selection["data"])
    elif selection["action"] == "uninstall":
        _uninstall_mcp(selection["data"]["id"], selection["data"]["name"])
        
    # Loop back to market to show changes, but we'll just exit gracefully for now as a CLI
    console.print("\n[dim]Run 'octo mcp' again to manage other servers.[/dim]\n")
