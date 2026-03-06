"""MCP Market CLI - Visual Marketplace for MCP servers."""

import json
from pathlib import Path
from typing import Dict, Any, List

import typer
import questionary
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from src.utils.config import load_config, save_config, MCPServerConfig

console = Console()
app = typer.Typer(help="Manage MCP servers via the octopOS market.")

REGISTRY_PATH = Path("data/config/mcp_registry.json")


def _load_registry() -> List[Dict[str, Any]]:
    """Load the available MCP servers from the curated registry."""
    if not REGISTRY_PATH.exists():
        console.print(f"[bold red]Error:[/bold red] MCP Registry not found at {REGISTRY_PATH}")
        return []
    try:
        with open(REGISTRY_PATH, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        console.print("[bold red]Error:[/bold red] Invalid JSON in MCP Registry.")
        return []


def _get_installed() -> Dict[str, MCPServerConfig]:
    """Get currently installed MCP servers from the active profile."""
    config = load_config()
    return config.mcp.servers


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
    
    # Save the configuration
    config = load_config()
    
    config.mcp.servers[mcp_spec['id']] = MCPServerConfig(
        name=mcp_spec['id'],
        transport=mcp_spec['transport'],
        command=mcp_spec['command'],
        args=command_args,
        env=env_vars,
        enabled=True
    )
    
    save_config(config)
    console.print(f"[bold green]✅ {mcp_spec['name']} successfully installed and activated![/bold green]")


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
