"""octopOS CLI - Command-line interface for the Agentic Operating System.

This module provides the main entry point for the octopOS CLI using Typer.
"""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

from src.utils.aws_sts import detect_aws_environment, get_auth_manager
from src.utils.config import (
    AgentPersona,
    get_config,
    load_config,
    save_config,
)
from src.utils.logger import get_logger
from src.interfaces.cli import commands as cli_commands
from src.interfaces.cli.mcp_market import app as mcp_app

# Create Typer app
app = typer.Typer(
    name="octo",
    help="octopOS - Agentic Operating System",
    add_completion=True,
)

# Include additional commands
app.command(name="agent-status", help="Show octopOS system status and agent health.")(cli_commands.status)
app.command(name="budget", help="Manage token budgets and costs.")(cli_commands.budget)
app.command(name="cache-stats", help="Show semantic cache statistics.")(cli_commands.cache_stats)
app.command(name="dlq", help="Manage Dead Letter Queue (failed messages).")(cli_commands.dlq_command)
app.command(name="ask", help="Ask octopOS a question or assign it a task.")(cli_commands.ask)
app.command(name="chat", help="Start an interactive continuous chat session.")(cli_commands.chat)
app.command(name="browse", help="Run an autonomous browser mission (Nova Act).")(cli_commands.browse)
app.command(name="voice", help="Start a real-time voice session (Nova Sonic).")(cli_commands.voice)

# Add MCP Market command group
app.add_typer(mcp_app, name="mcp")


# Initialize Rich console
console = Console()

# Version
VERSION = "0.1.0"

# Octopus ASCII Art
OCTOPUS_ART = r'''
[bold dark_orange] 
                                              
                     .::;::.                     
                   ;+++++++++:                   
                  +++;++++xxxx:                  
          :XX:   ;xx+++++xXXX$;  .;;.   .        
       ::;X:X++  .$X+xXXXXXX$&. .+++x;  ::       
       ;++x+:     .&+$XXX$X+X;   .:+xX:++:       
         :+xx++++++X$XxxXX$$$XXXXXXX$+;          
           .;X$XXx+++x+;+XXXX$$$$$$+  ;X+:       
     ;X:;   :+++xxXXXX+XX+X$XXX$;.    ::;X.      
     +x+++X$Xx$$&&$X$X+X$x+X$$$XX:     :+x       
      .xX+.        :x+X$x$xXX&$$$XX+::xxX;       
                  .xxXXX +x+x+. ;X$$$X$x:        
                  ++X$X. .XXxXX                  
          ;$;;+:.xxX$+.   :XXxX:                 
         .X: :++XX$x$      .+$$X;;x;$;           
          :xXXX+;X$$:+x:  ::.X$$$X;:xX           
                .X$$::++ xX:.X$&.;+++.           
                 +&&$$x.  +X$$X.                                                              
[/bold dark_orange]
[bold orange3]
 ██████╗  ██████╗████████╗ ██████╗ ██████╗  ██████╗ ███████╗
██╔═══██╗██╔════╝╚══██╔══╝██╔═══██╗██╔══██╗██╔═══██╗██╔════╝
██║   ██║██║        ██║   ██║   ██║██████╔╝██║   ██║███████╗
██║   ██║██║        ██║   ██║   ██║██╔═══╝ ██║   ██║╚════██║
╚██████╔╝╚██████╗   ██║   ╚██████╔╝██║     ╚██████╔╝███████║
 ╚═════╝  ╚═════╝   ╚═╝    ╚═════╝ ╚═╝      ╚═════╝ ╚══════╝[/bold orange3]

            [dim]Agentic Operating System[/dim]
'''


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Optional[bool] = typer.Option(
        None, "--version", "-v", help="Show version and exit"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", help="Enable verbose output"
    ),
) -> None:
    """octopOS CLI - Your AI-powered agentic operating system."""
    if version:
        console.print(f"octopOS version {VERSION}")
        raise typer.Exit()
    
    if verbose:
        console.print("[dim]Verbose mode enabled[/dim]")
    
    # Show welcome screen when no command is invoked
    if ctx.invoked_subcommand is None:
        console.print(OCTOPUS_ART)
        console.print("\n[bold cyan]Welcome to octopOS - Your Agentic Operating System[/bold cyan]")
        console.print("\n[dim]Run [bold]octo --help[/bold] to see available commands[/dim]\n")


@app.command()
def setup(
    force: bool = typer.Option(
        False, "--force", "-f", help="Force re-setup even if already configured"
    ),
) -> None:
    """Interactive setup wizard for octopOS.
    
    Guides you through configuring:
    - AWS credentials and region
    - Agent identity and personality
    - User preferences
    - Workspace settings
    """
    console.print(Panel.fit(
        "[bold blue]Welcome to octopOS![/bold blue]\n"
        "Let's get your AI agent configured.",
        title="Setup Wizard",
        border_style="blue"
    ))
    
    # Check existing config
    profile_path = Path.home() / ".octopos" / "profile.yaml"
    if profile_path.exists() and not force:
        console.print("[yellow]Configuration already exists. Use --force to reconfigure.[/yellow]")
        if not Confirm.ask("Do you want to reconfigure?"):
            console.print("Setup cancelled.")
            raise typer.Exit()
    
    # Load current config or defaults
    config = load_config()
    
    # Step 1: Environment Detection
    console.print("\n[bold]Step 1: Environment Detection[/bold]")
    env = detect_aws_environment()
    console.print(f"Detected environment: [green]{env.value}[/green]")
    
    # Step 2: AWS Configuration
    console.print("\n[bold]Step 2: AWS Configuration[/bold]")
    
    # Region
    region = Prompt.ask(
        "AWS Region",
        default=config.aws.region,
        choices=["us-east-1", "us-west-2", "eu-west-1", "eu-central-1", "ap-southeast-1"]
    )
    config.aws.region = region
    
    # Credentials method
    if env.value == "local":
        cred_method = Prompt.ask(
            "How would you like to configure AWS credentials?",
            choices=["profile", "direct", "role"],
            default="profile"
        )
        
        if cred_method == "profile":
            profile = Prompt.ask("AWS Profile name", default=config.aws.profile or "default")
            config.aws.profile = profile
            config.aws.access_key_id = None
            config.aws.secret_access_key = None
            config.aws.role_arn = None
            
        elif cred_method == "direct":
            console.print("[yellow]Warning: Direct credentials are less secure.[/yellow]")
            access_key = Prompt.ask("AWS Access Key ID", password=True)
            secret_key = Prompt.ask("AWS Secret Access Key", password=True)
            config.aws.access_key_id = access_key
            config.aws.secret_access_key = secret_key
            config.aws.profile = None
            config.aws.role_arn = None
            
        elif cred_method == "role":
            role_arn = Prompt.ask("IAM Role ARN")
            config.aws.role_arn = role_arn
            config.aws.profile = None
            config.aws.access_key_id = None
            config.aws.secret_access_key = None
    
    # Test AWS credentials
    console.print("\n[dim]Testing AWS credentials...[/dim]")
    try:
        auth_manager = get_auth_manager()
        if auth_manager.validate_credentials():
            console.print("[green]✓ AWS credentials validated successfully![/green]")
        else:
            console.print("[red]✗ Failed to validate AWS credentials[/red]")
            if not Confirm.ask("Continue anyway?"):
                raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]✗ Error validating credentials: {e}[/red]")
        if not Confirm.ask("Continue anyway?"):
            raise typer.Exit(1)
    
    # Step 3: Agent Identity
    console.print("\n[bold]Step 3: Agent Identity[/bold]")
    
    agent_name = Prompt.ask(
        "What would you like to name your agent?",
        default=config.agent.name
    )
    config.agent.name = agent_name
    
    console.print("\nChoose a personality for your agent:")
    console.print("  [cyan]friendly[/cyan]     - Casual, conversational tone")
    console.print("  [cyan]professional[/cyan] - Formal, business-appropriate")
    console.print("  [cyan]technical[/cyan]    - Detailed, assumes technical knowledge")
    
    persona_str = Prompt.ask(
        "Personality",
        choices=["friendly", "professional", "technical"],
        default=config.agent.persona.value
    )
    config.agent.persona = AgentPersona(persona_str)
    
    # Step 4: User Information
    console.print("\n[bold]Step 4: User Information[/bold]")
    
    user_name = Prompt.ask("Your name", default=config.user.name or "")
    config.user.name = user_name
    
    timezone = Prompt.ask(
        "Your timezone",
        default=config.user.timezone
    )
    config.user.timezone = timezone
    
    # Step 5: Workspace
    console.print("\n[bold]Step 5: Workspace Configuration[/bold]")
    
    workspace = Prompt.ask(
        "Workspace directory",
        default=config.user.workspace_path
    )
    config.user.workspace_path = workspace
    
    # Expand ~ to home directory
    workspace_path = Path(workspace).expanduser()
    workspace_path.mkdir(parents=True, exist_ok=True)
    
    # Save configuration
    console.print("\n[dim]Saving configuration...[/dim]")
    try:
        save_config(config)
        console.print(f"[green]✓ Configuration saved to {profile_path}[/green]")
    except Exception as e:
        console.print(f"[red]✗ Failed to save configuration: {e}[/red]")
        raise typer.Exit(1)
    
    # Summary
    console.print("\n")
    console.print(Panel.fit(
        f"[bold green]Setup Complete![/bold green]\n\n"
        f"Agent Name: [cyan]{config.agent.name}[/cyan]\n"
        f"Personality: [cyan]{config.agent.persona.value}[/cyan]\n"
        f"AWS Region: [cyan]{config.aws.region}[/cyan]\n"
        f"Workspace: [cyan]{config.user.workspace_path}[/cyan]\n\n"
        "Run [bold]octo status[/bold] to check system status.",
        title="Summary",
        border_style="green"
    ))


@app.command()
def status(
    detailed: bool = typer.Option(
        False, "--detailed", "-d", help="Show detailed status"
    ),
) -> None:
    """Show octopOS system status.
    
    Displays information about:
    - Configuration status
    - AWS connectivity
    - Agent state
    - Recent activity
    """
    config = get_config()
    
    console.print(Panel.fit(
        f"[bold blue]octopOS Status[/bold blue]",
        border_style="blue"
    ))
    
    # Configuration table
    config_table = Table(title="Configuration", show_header=False)
    config_table.add_column("Setting", style="cyan")
    config_table.add_column("Value", style="green")
    
    config_table.add_row("Agent Name", config.agent.name)
    config_table.add_row("Personality", config.agent.persona.value)
    config_table.add_row("Language", config.agent.language)
    config_table.add_row("AWS Region", config.aws.region)
    config_table.add_row("Workspace", config.user.workspace_path)
    
    profile_path = Path.home() / ".octopos" / "profile.yaml"
    config_table.add_row(
        "Profile",
        "[green]✓ Configured[/green]" if profile_path.exists() else "[red]✗ Not found[/red]"
    )
    
    console.print(config_table)
    
    # AWS Status
    console.print("\n")
    aws_table = Table(title="AWS Connectivity", show_header=False)
    aws_table.add_column("Service", style="cyan")
    aws_table.add_column("Status", style="green")
    
    try:
        env = detect_aws_environment()
        aws_table.add_row("Environment", f"[green]{env.value}[/green]")
        
        auth_manager = get_auth_manager()
        if auth_manager.validate_credentials():
            aws_table.add_row("Credentials", "[green]✓ Valid[/green]")
        else:
            aws_table.add_row("Credentials", "[red]✗ Invalid[/red]")
        
        # Try to create Bedrock client
        try:
            client = auth_manager.get_bedrock_client()
            aws_table.add_row("Bedrock", "[green]✓ Accessible[/green]")
        except Exception as e:
            aws_table.add_row("Bedrock", f"[red]✗ Error: {e}[/red]")
            
    except Exception as e:
        aws_table.add_row("Status", f"[red]✗ Error: {e}[/red]")
    
    console.print(aws_table)
    
    # Detailed info
    if detailed:
        console.print("\n")
        detail_table = Table(title="Detailed Information", show_header=False)
        detail_table.add_column("Property", style="cyan")
        detail_table.add_column("Value", style="dim")
        
        detail_table.add_row("Log Level", config.logging.level.value)
        detail_table.add_row("Log Destination", config.logging.destination.value)
        detail_table.add_row("LanceDB Path", config.lancedb.path)
        detail_table.add_row("Task DB Path", config.task.db_path)
        detail_table.add_row("Debug Mode", str(config.debug))
        detail_table.add_row("Mock AWS", str(config.mock_aws))
        
        console.print(detail_table)
    
    console.print("\n[dim]Use 'octo setup' to reconfigure or 'octo --help' for more commands.[/dim]")


@app.command()
def config_show(
    sensitive: bool = typer.Option(
        False, "--sensitive", "-s", help="Show sensitive values"
    ),
) -> None:
    """Display current configuration."""
    config = get_config()
    
    console.print(Panel.fit(
        "[bold blue]Current Configuration[/bold blue]",
        border_style="blue"
    ))
    
    table = Table(show_header=False)
    table.add_column("Section", style="bold cyan")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="green")
    
    # AWS
    table.add_row("AWS", "Region", config.aws.region)
    table.add_row("AWS", "Profile", config.aws.profile or "(none)")
    if sensitive and config.aws.access_key_id:
        table.add_row("AWS", "Access Key", config.aws.access_key_id[:8] + "...")
    if config.aws.role_arn:
        table.add_row("AWS", "Role ARN", config.aws.role_arn)
    table.add_row("AWS", "Nova Lite Model", config.aws.model_nova_lite)
    
    # Agent
    table.add_row("Agent", "Name", config.agent.name)
    table.add_row("Agent", "Persona", config.agent.persona.value)
    table.add_row("Agent", "Language", config.agent.language)
    
    # User
    table.add_row("User", "Name", config.user.name or "(not set)")
    table.add_row("User", "Timezone", config.user.timezone)
    table.add_row("User", "Workspace", config.user.workspace_path)
    
    # Paths
    table.add_row("Paths", "LanceDB", config.lancedb.path)
    table.add_row("Paths", "Task DB", config.task.db_path)
    
    console.print(table)


@app.command()
def doctor() -> None:
    """Run diagnostics and check system health.
    
    Performs various checks:
    - Configuration validity
    - AWS connectivity
    - Required directories
    - Dependencies
    """
    console.print(Panel.fit(
        "[bold blue]octopOS System Doctor[/bold blue]",
        border_style="blue"
    ))
    
    issues = []
    warnings = []
    
    # Check 1: Configuration file
    console.print("\n[dim]Checking configuration...[/dim]")
    profile_path = Path.home() / ".octopos" / "profile.yaml"
    if profile_path.exists():
        console.print("  [green]✓[/green] Configuration file exists")
    else:
        console.print("  [red]✗[/red] Configuration file not found")
        issues.append("Run 'octo setup' to create configuration")
    
    # Check 2: AWS credentials
    console.print("[dim]Checking AWS credentials...[/dim]")
    try:
        auth_manager = get_auth_manager()
        if auth_manager.validate_credentials():
            console.print("  [green]✓[/green] AWS credentials valid")
        else:
            console.print("  [red]✗[/red] AWS credentials invalid")
            issues.append("AWS credentials are invalid or expired")
    except Exception as e:
        console.print(f"  [red]✗[/red] AWS error: {e}")
        issues.append(f"AWS connection error: {e}")
    
    # Check 3: Workspace directory
    console.print("[dim]Checking workspace...[/dim]")
    config = get_config()
    workspace = Path(config.user.workspace_path).expanduser()
    if workspace.exists():
        console.print(f"  [green]✓[/green] Workspace exists: {workspace}")
    else:
        console.print(f"  [yellow]![/yellow] Workspace does not exist: {workspace}")
        warnings.append(f"Workspace directory will be created on first use")
    
    # Check 4: Data directories
    console.print("[dim]Checking data directories...[/dim]")
    data_dir = Path("./data")
    if not data_dir.exists():
        data_dir.mkdir(parents=True, exist_ok=True)
        console.print(f"  [green]✓[/green] Created data directory")
    else:
        console.print(f"  [green]✓[/green] Data directory exists")
    
    # Check 5: Dependencies
    console.print("[dim]Checking dependencies...[/dim]")
    try:
        import boto3
        console.print("  [green]✓[/green] boto3 installed")
    except ImportError:
        console.print("  [red]✗[/red] boto3 not installed")
        issues.append("Install boto3: pip install boto3")
    
    try:
        import lancedb
        console.print("  [green]✓[/green] lancedb installed")
    except ImportError:
        console.print("  [yellow]![/yellow] lancedb not installed (optional for Phase 1)")
        warnings.append("Install lancedb for vector storage: pip install lancedb")
    
    # Summary
    console.print("\n" + "=" * 50)
    if not issues and not warnings:
        console.print("[bold green]All checks passed! System is healthy.[/bold green]")
    else:
        if issues:
            console.print(f"[bold red]Found {len(issues)} issue(s):[/bold red]")
            for issue in issues:
                console.print(f"  [red]-[/red] {issue}")
        if warnings:
            console.print(f"[bold yellow]Found {len(warnings)} warning(s):[/bold yellow]")
            for warning in warnings:
                console.print(f"  [yellow]-[/yellow] {warning}")


if __name__ == "__main__":
    app()
