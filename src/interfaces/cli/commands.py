"""CLI Commands - Additional commands for octopOS management.

Provides:
- octo status:      System status and agent health
- octo budget:      Token budget monitoring
- octo cache-stats: Semantic cache statistics
- octo dlq:         Dead Letter Queue management
- octo browse:      Autonomous browser mission (Nova Act)
- octo voice:       Interactive voice session (Nova Sonic)
"""

import asyncio
from typing import Dict, List, Optional
from uuid import UUID

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich import box

from src.utils.token_budget import get_token_budget_manager
from src.engine.memory.semantic_cache import get_semantic_cache
from src.engine.dead_letter_queue import get_dead_letter_queue
from src.workers import get_worker_pool
from src.specialist import get_manager_agent
from src.utils.logger import get_logger

console = Console()
app = typer.Typer()


@app.command("status")
def status(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed status")
):
    """Show octopOS system status and agent health."""
    console.print(Panel.fit("🐙 octopOS System Status", style="bold blue"))
    
    # Manager Agent Status
    manager = get_manager_agent()
    registry = manager.get_registry()
    
    table = Table(title="Agent Registry", box=box.ROUNDED)
    table.add_column("Agent ID", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Status", style="green")
    table.add_column("Tasks", justify="right")
    
    health_summary = registry.get_health_summary()
    
    for agent in registry.get_all_agents():
        status_color = {
            "idle": "green",
            "busy": "yellow",
            "error": "red",
            "offline": "dim"
        }.get(agent.status.value, "white")
        
        table.add_row(
            agent.agent_id,
            agent.agent_type,
            f"[{status_color}]{agent.status.value}[/{status_color}]",
            str(agent.task_count)
        )
    
    console.print(table)
    console.print(f"\n[dim]Total: {health_summary['total_agents']} agents "
                  f"(Idle: {health_summary['idle']}, "
                  f"Busy: {health_summary['busy']}, "
                  f"Error: {health_summary.get('error', 0)})[/dim]")
    
    # Worker Pool Status
    pool = get_worker_pool()
    pool_stats = pool.get_stats()
    
    console.print(f"\n[bold]Worker Pool:[/bold]")
    console.print(f"  Workers: {pool_stats['available_workers']} available / "
                  f"{pool_stats['busy_workers']} busy / "
                  f"{pool_stats['total_workers']} total")
    console.print(f"  Queue: {pool_stats['queue_size']} pending tasks")
    
    if verbose:
        console.print(f"\n[dim]Config: min={pool_stats['config']['min_workers']}, "
                      f"max={pool_stats['config']['max_workers']}[/dim]")


@app.command("budget")
def budget(
    session_id: str = typer.Option("default", "--session", "-s", help="Session ID"),
    create: Optional[float] = typer.Option(None, "--create", help="Create budget with limit (USD)"),
    all_sessions: bool = typer.Option(False, "--all", "-a", help="Show all sessions")
):
    """Manage token budgets and costs."""
    budget_mgr = get_token_budget_manager()
    
    if create:
        budget_obj = budget_mgr.create_budget(
            session_id=session_id,
            user_id="cli_user",
            budget_limit=create
        )
        console.print(f"[green]✓ Created budget for {session_id}: ${create}[/green]")
        return
    
    if all_sessions:
        console.print(Panel.fit("💰 All Session Budgets", style="bold green"))
        # Note: Would need to track all sessions in budget manager
        console.print("[dim]Use --session to view specific session budget[/dim]")
        return
    
    # Show specific session
    budget_obj = budget_mgr.get_budget(session_id)
    
    if not budget_obj:
        console.print(f"[yellow]No budget found for session {session_id}[/yellow]")
        console.print(f"[dim]Create one with: octo budget --session {session_id} --create 10.0[/dim]")
        return
    
    summary = budget_obj.get_summary()
    
    console.print(Panel.fit(f"💰 Budget: {session_id}", style="bold green"))
    
    # Progress bar
    pct_used = (summary['total_cost_usd'] / summary['budget_limit_usd']) * 100
    bar_width = 30
    filled = int((pct_used / 100) * bar_width)
    bar = "█" * filled + "░" * (bar_width - filled)
    
    color = "green" if pct_used < 50 else "yellow" if pct_used < 80 else "red"
    
    console.print(f"\nCost: [{color}]{bar}[/{color}] ${summary['total_cost_usd']:.2f} / ${summary['budget_limit_usd']:.2f} ({pct_used:.1f}%)")
    console.print(f"Remaining: ${summary['remaining_usd']:.2f}")
    console.print(f"Total Tokens: {summary['total_tokens']:,}")
    console.print(f"API Calls: {summary['usage_count']}")
    
    if summary['stopped']:
        console.print("\n[red bold]⚠ BUDGET EXCEEDED - No new requests allowed[/red bold]")


@app.command("cache-stats")
def cache_stats(
    clear: bool = typer.Option(False, "--clear", help="Clear expired entries")
):
    """Show semantic cache statistics."""
    cache = get_semantic_cache()
    
    # Need to run async init
    async def get_stats():
        await cache.initialize()
        return cache.get_stats()
    
    stats = asyncio.run(get_stats())
    
    console.print(Panel.fit("📊 Semantic Cache Statistics", style="bold cyan"))
    
    if "error" in stats:
        console.print(f"[red]Error: {stats['error']}[/red]")
        return
    
    table = Table(box=box.ROUNDED)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="magenta")
    
    table.add_row("Total Entries", str(stats.get('total_entries', 0)))
    table.add_row("Total Cache Hits", str(stats.get('total_hits', 0)))
    table.add_row("Avg Hits/Entry", f"{stats.get('avg_hits_per_entry', 0):.2f}")
    table.add_row("Cache Size", f"{stats.get('cache_size_mb', 0):.2f} MB")
    
    console.print(table)
    
    hits = stats.get('total_hits', 0)
    entries = stats.get('total_entries', 0)
    if entries > 0:
        efficiency = (hits / entries) * 100
        console.print(f"\n[dim]Cache Efficiency: {efficiency:.1f}% (higher is better)[/dim]")
        console.print(f"[dim]Estimated Cost Savings: ~${hits * 0.001:.2f}[/dim]")
    
    if clear:
        asyncio.run(cache.clear_expired())
        console.print("[green]✓ Cleared expired cache entries[/green]")


@app.command("dlq")
def dlq_command(
    list_entries: bool = typer.Option(False, "--list", "-l", help="List all DLQ entries"),
    stats: bool = typer.Option(False, "--stats", "-s", help="Show DLQ statistics"),
    process: bool = typer.Option(False, "--process", help="Process pending entries with Self-Healing"),
    clear_resolved: bool = typer.Option(False, "--clear-resolved", help="Clear old resolved entries")
):
    """Manage Dead Letter Queue (failed messages)."""
    dlq = get_dead_letter_queue()
    
    if stats or not any([list_entries, process, clear_resolved]):
        # Show stats by default
        dlq_stats = dlq.get_stats()
        
        console.print(Panel.fit("📥 Dead Letter Queue", style="bold red"))
        
        table = Table(box=box.ROUNDED)
        table.add_column("Status", style="cyan")
        table.add_column("Count", style="magenta", justify="right")
        
        table.add_row("Total Entries", str(dlq_stats['total_entries']))
        table.add_row("Pending", f"[yellow]{dlq_stats['pending']}[/yellow]")
        table.add_row("Analyzing", str(dlq_stats['analyzing']))
        table.add_row("Resolved", f"[green]{dlq_stats['resolved']}[/green]")
        table.add_row("Failed", f"[red]{dlq_stats['failed']}[/red]")
        
        console.print(table)
        
        if dlq_stats['error_types']:
            console.print("\n[bold]Error Types:[/bold]")
            for error_type, count in dlq_stats['error_types'].items():
                console.print(f"  • {error_type}: {count}")
    
    if list_entries:
        pending = dlq.get_pending(limit=20)
        
        if pending:
            console.print(f"\n[bold]Pending Entries ({len(pending)}):[/bold]")
            
            table = Table(box=box.ROUNDED)
            table.add_column("ID", style="dim")
            table.add_column("Agent", style="cyan")
            table.add_column("Error Type", style="red")
            table.add_column("Failed At", style="magenta")
            
            for entry in pending:
                table.add_row(
                    entry.id[:8],
                    entry.agent_name,
                    entry.error_type,
                    entry.failed_at[:19]
                )
            
            console.print(table)
        else:
            console.print("\n[green]No pending entries in DLQ[/green]")
    
    if process:
        console.print("[yellow]Processing DLQ entries with Self-Healing Agent...[/yellow]")
        from src.specialist import get_self_healing_agent
        
        async def process_dlq():
            healer = get_self_healing_agent()
            await healer.start()
            return await dlq.process_with_healer(healer, batch_size=10)
        
        result = asyncio.run(process_dlq())
        
        console.print(f"[green]✓ Processed {result['processed']} entries[/green]")
        console.print(f"  Resolved: {result['resolved']}")
        console.print(f"  Failed: {result['failed']}")
    
    if clear_resolved:
        count = dlq.clear_resolved(older_than_hours=24)
        console.print(f"[green]✓ Cleared {count} resolved entries[/green]")


@app.command("ask")
def ask(
    prompt: str = typer.Argument(..., help="What do you want to ask or assign to the agent?"),
):
    """Ask octopOS a question or give it a task."""
    from src.engine.orchestrator import get_orchestrator
    
    console.print(Panel.fit(f"🤔 [dim]Processing:[/dim] {prompt}", border_style="cyan"))
    
    async def run_query():
        orchestrator = get_orchestrator()
        await orchestrator.on_start()
        return await orchestrator.process_user_input(prompt)
        
    try:
        result = asyncio.run(run_query())
        
        if result.get("status") == "success":
            if "response" in result:
                console.print(f"\n[bold orange3]🐙 octopOS:[/bold orange3] {result['response']}")
            else:
                import json
                console.print(f"\n[bold green]✓ Task Created[/bold green]")
                console.print(json.dumps(result, indent=2))
        else:
            console.print(f"\n[bold red]✗ Agent Error:[/bold red] {result.get('message', result)}")
    except Exception as e:
        console.print(f"\n[bold red]✗ Execution Failed:[/bold red] {e}")


@app.command("chat")
def chat():
    """Start an interactive chat session with octopOS."""
    from src.engine.orchestrator import get_orchestrator
    
    console.print(Panel.fit("🐙 [bold orange3]octopOS Chat Mode[/bold orange3] starting...\nType 'exit' or 'quit' to leave.", border_style="cyan"))
    
    async def chat_loop():
        orchestrator = get_orchestrator()
        await orchestrator.on_start()
        
        while True:
            try:
                user_input = Prompt.ask("\n[bold cyan]You[/bold cyan]")
                if not user_input.strip():
                    continue
                if user_input.strip().lower() in ['exit', 'quit', ':q']:
                    console.print("[dim]Ending chat session...[/dim]")
                    break
                    
                result = await orchestrator.process_user_input(user_input)
                
                if result.get("status") == "success":
                    if "response" in result:
                        console.print(f"[bold orange3]🐙 octopOS:[/bold orange3] {result['response']}")
                    else:
                        import json
                        console.print(f"[bold green]✓ Task Completed[/bold green]")
                        console.print(json.dumps(result, indent=2))
                else:
                    console.print(f"[bold red]✗ Error:[/bold red] {result.get('message', result)}")
                    
            except (KeyboardInterrupt, EOFError):
                console.print("\n[dim]Ending chat session...[/dim]")
                break
            except Exception as e:
                console.print(f"\n[bold red]✗ Execution Failed:[/bold red] {e}")

    asyncio.run(chat_loop())


@app.command("browse")
def browse(
    mission: str = typer.Argument(..., help="Browser mission / task in natural language"),
    url: str = typer.Option("about:blank", "--url", "-u", help="Starting URL (optional)"),
    max_steps: int = typer.Option(20, "--max-steps", "-n", help="Max OAV loop steps"),
    headless: bool = typer.Option(True, "--headless/--visible", help="Run headless or show browser"),
):
    """Run an autonomous browser mission powered by Nova Act.

    octopOS will observe the page, decide actions (click/type/scroll/…),
    execute them, verify results — up to --max-steps times — then report.

    Example:
        octo browse "go to news.ycombinator.com and get top 10 posts"
        octo browse "find cheapest laptop on amazon" --url https://amazon.com --visible
    """
    from src.utils.feature_flags import FeatureFlags

    if not FeatureFlags.nova_act_enabled():
        console.print("[yellow]⚠ Nova Act is not enabled.[/yellow]")
        console.print("[dim]Set OCTOPOS_FEATURE_NOVA_ACT=true to enable browser automation.[/dim]")
        raise typer.Exit(1)

    from uuid import uuid4

    async def run_browser_mission():
        try:
            from src.primitives.web.nova_act_driver import NovaActDriver
            from src.primitives.web.browser_session import get_session_manager
            from src.utils.aws_sts import get_bedrock_client
        except ImportError as e:
            console.print(f"[bold red]✗ Missing dependency:[/bold red] {e}")
            console.print("[dim]Install with: pip install playwright && playwright install chromium[/dim]")
            raise typer.Exit(1)

        mission_id = str(uuid4())[:8]
        console.print(Panel(
            f"[bold cyan]🌐 Browser Mission[/bold cyan]\n\n"
            f"[white]{mission}[/white]\n\n"
            f"[dim]Start URL: {url} | Max steps: {max_steps} | ID: {mission_id}[/dim]",
            title="octopOS Nova Act",
            border_style="cyan"
        ))

        try:
            bedrock = get_bedrock_client()
            driver = NovaActDriver(
                bedrock_client=bedrock,
                max_steps=max_steps,
            )

            with console.status("[bold cyan]Running browser mission…[/bold cyan]"):
                result = await driver.run_mission(
                    mission_id=mission_id,
                    initial_url=url if url != "about:blank" else "https://www.google.com",
                    mission_context=mission,
                    user_id="cli",
                    max_steps=max_steps,
                )

            # Results table
            table = Table(title=f"Mission {mission_id} — {'✅ Success' if result.success else '❌ Failed'}", box=box.ROUNDED)
            table.add_column("Step", style="dim", width=6)
            table.add_column("Action", style="cyan")
            table.add_column("Target", style="white")
            table.add_column("✓", width=4)
            table.add_column("Duration", style="dim")

            for step in result.steps:
                ok = "✅" if (step.verification and step.verification.success) else "❌"
                table.add_row(
                    str(step.step_number),
                    step.decision.action.value,
                    (step.decision.target or step.decision.value or "")[:50],
                    ok,
                    f"{step.duration_ms:.0f}ms",
                )

            console.print(table)

            if result.final_data:
                console.print(Panel(
                    str(result.final_data),
                    title="📦 Extracted Data",
                    border_style="green"
                ))

            console.print(
                f"\n[dim]Total: {len(result.steps)} steps, "
                f"{result.total_duration_ms:.0f}ms[/dim]"
            )

        except Exception as e:
            console.print(f"[bold red]✗ Mission failed:[/bold red] {e}")
            raise typer.Exit(1)

    asyncio.run(run_browser_mission())


@app.command("voice")
def voice(
    wake_word: str = typer.Option("hey octo", "--wake-word", "-w", help="Wake word to activate"),
    language: str = typer.Option("tr-TR", "--lang", "-l", help="Language code (tr-TR / en-US / …)"),
):
    """Start a real-time voice session powered by Nova Sonic.

    Say the wake word, then speak. octopOS will transcribe your speech,
    process the intent, and respond with synthesised audio.

    Example:
        octo voice
        octo voice --lang en-US --wake-word "hey octo"
    """
    from src.utils.feature_flags import FeatureFlags

    if not FeatureFlags.nova_sonic_enabled():
        console.print("[yellow]⚠ Nova Sonic is not enabled.[/yellow]")
        console.print("[dim]Set OCTOPOS_FEATURE_NOVA_SONIC=true to enable voice interface.[/dim]")
        raise typer.Exit(1)

    async def run_voice_session():
        try:
            from src.interfaces.voice.nova_sonic import NovaSonicClient
            from src.engine.orchestrator import get_orchestrator
        except ImportError as e:
            console.print(f"[bold red]✗ Missing dependency:[/bold red] {e}")
            raise typer.Exit(1)

        console.print(Panel(
            f"[bold magenta]🎙️  Voice Session[/bold magenta]\n\n"
            f"[white]Say [bold]'{wake_word}'[/bold] to activate, [bold]'exit'[/bold] to quit.[/white]\n"
            f"[dim]Language: {language}[/dim]",
            title="octopOS Nova Sonic",
            border_style="magenta"
        ))

        sonic = NovaSonicClient()
        orchestrator = get_orchestrator()
        await orchestrator.start()

        if not sonic.is_available():
            console.print("[yellow]⚠ Nova Sonic unavailable — microphone input not supported in this environment.[/yellow]")
            console.print("[dim]You can still use 'octo chat' for text-based interaction.[/dim]")
            return

        console.print("[dim]Listening… (Ctrl-C to stop)[/dim]")

        try:
            async for event in sonic.start_session(language=language, wake_word=wake_word):
                if event["type"] == "wake":
                    console.print("[bold magenta]🎙 Listening…[/bold magenta]")

                elif event["type"] == "transcript":
                    text = event["text"]
                    console.print(f"[white]You:[/white] {text}")

                    with console.status("[magenta]Thinking…[/magenta]"):
                        result = await orchestrator.process_user_input(text)

                    response = result.get("response") or result.get("message", "")
                    console.print(f"[bold magenta]🐙 octopOS:[/bold magenta] {response}")

                    # Speak the response
                    audio = await sonic.text_to_speech(response)
                    if audio:
                        await sonic.play_audio(audio)

                elif event["type"] == "error":
                    console.print(f"[red]Voice error:[/red] {event.get('message')}")

                elif event["type"] == "exit":
                    console.print("[dim]Voice session ended.[/dim]")
                    break

        except KeyboardInterrupt:
            console.print("\n[dim]Voice session interrupted.[/dim]")
        finally:
            await sonic.close()
            await orchestrator.stop()

    asyncio.run(run_voice_session())


# Export commands
__all__ = ["app", "status", "budget", "cache_stats", "dlq_command", "ask", "chat", "browse", "voice"]
