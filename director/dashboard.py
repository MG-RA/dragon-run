"""
Rich console dashboard for Dragon Run Director AI.
Displays real-time state, events, AI activity, and metrics in a compact view.
"""

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich import box
from datetime import datetime
from typing import Dict, List, Any, Optional
from collections import deque
import time

console = Console()


class DirectorDashboard:
    """Real-time dashboard for monitoring AI Director activity."""

    def __init__(self):
        self.layout = Layout()
        self.live = None

        # Activity tracking
        self.recent_events = deque(maxlen=8)
        self.recent_messages = deque(maxlen=5)
        self.ai_activity_log = deque(maxlen=6)

        # Metrics
        self.total_events = 0
        self.total_commentary = 0
        self.total_interventions = 0
        self.session_start = time.time()
        self.last_update = time.time()

        # AI state
        self.current_ai_status = "🟢 Idle"
        self.context_tokens = 0
        self.last_model_call = None
        self.last_tool_used = None

        # Game state cache
        self.game_state_cache = {}
        self.player_state_cache = []

        self._setup_layout()

    def _setup_layout(self):
        """Set up the dashboard layout structure."""
        # Create main layout sections
        self.layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="footer", size=3)
        )

        # Split main into left and right
        self.layout["main"].split_row(
            Layout(name="left", ratio=3),
            Layout(name="right", ratio=2)
        )

        # Split left into game state and player state
        self.layout["left"].split_column(
            Layout(name="game_state", size=8),
            Layout(name="player_state", ratio=1)
        )

        # Split right into events, AI activity, and messages
        self.layout["right"].split_column(
            Layout(name="events", ratio=2),
            Layout(name="ai_activity", ratio=2),
            Layout(name="messages", ratio=1)
        )

    def start(self):
        """Start the live dashboard."""
        self.live = Live(self.layout, console=console, refresh_per_second=2, screen=True)
        self.live.start()

    def stop(self):
        """Stop the live dashboard."""
        if self.live:
            self.live.stop()

    def update(self):
        """Update all dashboard panels."""
        if not self.live:
            return

        self.last_update = time.time()

        # Update all sections
        self.layout["header"].update(self._render_header())
        self.layout["game_state"].update(self._render_game_state())
        self.layout["player_state"].update(self._render_player_state())
        self.layout["events"].update(self._render_events())
        self.layout["ai_activity"].update(self._render_ai_activity())
        self.layout["messages"].update(self._render_messages())
        self.layout["footer"].update(self._render_footer())

    def _render_header(self) -> Panel:
        """Render the header panel."""
        uptime = int(time.time() - self.session_start)
        uptime_str = f"{uptime // 3600}h {(uptime % 3600) // 60}m {uptime % 60}s"

        header_text = Text()
        header_text.append("🔮 DRAGON RUN DIRECTOR AI ", style="bold cyan")
        header_text.append(f"| Status: {self.current_ai_status} ", style="white")
        header_text.append(f"| Uptime: {uptime_str} ", style="dim")
        header_text.append(f"| Events: {self.total_events} ", style="yellow")
        header_text.append(f"| Commentary: {self.total_commentary} ", style="green")
        header_text.append(f"| Interventions: {self.total_interventions}", style="red")

        return Panel(header_text, style="cyan", box=box.HEAVY)

    def _render_game_state(self) -> Panel:
        """Render game state panel."""
        state = self.game_state_cache

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Key", style="cyan", width=18)
        table.add_column("Value", style="white")

        run_id = state.get('runId', '?')
        game_state = state.get('gameState', 'UNKNOWN')
        duration = state.get('runDuration', 0)
        duration_str = f"{duration // 60}m {duration % 60}s"

        dragon_alive = state.get('dragonAlive', False)
        dragon_health = state.get('dragonHealth', 0)
        if dragon_health > 0:
            dragon_status = f"{dragon_health:.0f}/200 HP"
            dragon_style = "red" if dragon_health < 100 else "yellow"
        elif dragon_alive:
            dragon_status = "Not spawned"
            dragon_style = "dim"
        else:
            dragon_status = "Dead"
            dragon_style = "green"

        total_players = state.get('totalPlayers', 0)
        lobby_players = state.get('lobbyPlayers', 0)
        hardcore_players = state.get('hardcorePlayers', 0)

        weather = state.get('weatherState', 'unknown')
        time_of_day = state.get('timeOfDay', 0)
        mc_time = f"Day {time_of_day // 24000}, {(time_of_day % 24000) // 1000}h"

        table.add_row("🎮 Run ID", f"#{run_id}")
        table.add_row("📊 Game State", f"[bold]{game_state}[/bold]")
        table.add_row("⏱️  Duration", duration_str)
        table.add_row("🐉 Dragon", f"[{dragon_style}]{dragon_status}[/{dragon_style}]")
        table.add_row("👥 Players", f"{hardcore_players} active / {total_players} total / {lobby_players} lobby")
        table.add_row("🌦️  Weather", weather.title())
        table.add_row("🕐 World Time", mc_time)

        return Panel(table, title="[bold cyan]🎯 Game State[/bold cyan]", border_style="cyan")

    def _render_player_state(self) -> Panel:
        """Render player state panel."""
        players = self.player_state_cache

        if not players:
            return Panel(
                "[dim]No players in active run[/dim]",
                title="[bold cyan]👥 Player State[/bold cyan]",
                border_style="cyan"
            )

        table = Table(show_header=True, box=box.SIMPLE, padding=(0, 1), expand=True)
        table.add_column("Player", style="cyan", width=12, no_wrap=True)
        table.add_column("Dim", width=4, no_wrap=True)
        table.add_column("❤️", justify="right", width=5)
        table.add_column("🍖", justify="right", width=4)
        table.add_column("💎", justify="right", width=4)
        table.add_column("Status", width=20)

        # Group by dimension
        dims = {'overworld': '🌍', 'nether': '🔥', 'end': '🌌', 'lobby': '💤'}

        for player in players[:10]:  # Limit to 10 players
            name = player.get('username', '?')[:12]
            dim = player.get('dimension', '?')
            dim_emoji = dims.get(dim, '?')

            health = player.get('health', 0)
            hunger = player.get('foodLevel', 0)
            diamonds = player.get('diamondCount', 0)

            # Determine status
            status_parts = []
            if health < 6:
                status_parts.append("[red]⚠️ DANGER[/red]")
            kills = player.get('mobKills', 0)
            if kills > 50:
                status_parts.append(f"[yellow]⚔️{kills}[/yellow]")

            armor = player.get('armorTier', 'none')
            if armor in ['diamond', 'netherite']:
                status_parts.append(f"[green]{armor}[/green]")

            status = " ".join(status_parts) if status_parts else "[dim]ok[/dim]"

            # Health color coding
            health_str = f"{health:.0f}"
            if health < 6:
                health_str = f"[red]{health_str}[/red]"
            elif health < 12:
                health_str = f"[yellow]{health_str}[/yellow]"
            else:
                health_str = f"[green]{health_str}[/green]"

            table.add_row(
                name,
                dim_emoji,
                health_str,
                str(hunger),
                str(diamonds) if diamonds > 0 else "[dim]0[/dim]",
                status
            )

        if len(players) > 10:
            table.add_row("[dim]...[/dim]", "", "", "", "", f"[dim]+{len(players) - 10} more[/dim]")

        return Panel(table, title="[bold cyan]👥 Player State[/bold cyan]", border_style="cyan")

    def _render_events(self) -> Panel:
        """Render recent events panel."""
        if not self.recent_events:
            content = "[dim]No events yet...[/dim]"
        else:
            lines = []
            for timestamp, event_type, data in self.recent_events:
                time_str = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")

                # Format event type with color
                if "death" in event_type.lower():
                    event_style = "red"
                    event_icon = "💀"
                elif "dimension" in event_type.lower():
                    event_style = "magenta"
                    event_icon = "🌀"
                elif "chat" in event_type.lower():
                    event_style = "blue"
                    event_icon = "💬"
                elif "dragon" in event_type.lower():
                    event_style = "yellow"
                    event_icon = "🐉"
                else:
                    event_style = "white"
                    event_icon = "📌"

                # Extract key info from data
                info = ""
                if isinstance(data, dict):
                    player = data.get('player', '')
                    message = data.get('message', '')
                    if player:
                        info = f"{player}"
                    if message:
                        info += f": {message[:30]}..."

                lines.append(
                    f"[dim]{time_str}[/dim] {event_icon} [{event_style}]{event_type}[/{event_style}] {info}"
                )

            content = "\n".join(lines)

        return Panel(content, title="[bold yellow]🎯 Recent Events[/bold yellow]", border_style="yellow")

    def _render_ai_activity(self) -> Panel:
        """Render AI activity log panel."""
        if not self.ai_activity_log:
            content = "[dim]AI idle...[/dim]"
        else:
            lines = []
            for timestamp, activity_type, details in self.ai_activity_log:
                time_str = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")

                # Style based on activity type
                if activity_type == "commentary":
                    icon = "🎤"
                    style = "green"
                elif activity_type == "intervention":
                    icon = "⚡"
                    style = "red"
                elif activity_type == "thinking":
                    icon = "🧠"
                    style = "cyan"
                elif activity_type == "tool":
                    icon = "🔧"
                    style = "yellow"
                else:
                    icon = "ℹ️"
                    style = "white"

                lines.append(
                    f"[dim]{time_str}[/dim] {icon} [{style}]{details}[/{style}]"
                )

            content = "\n".join(lines)

        return Panel(content, title="[bold green]🤖 AI Activity[/bold green]", border_style="green")

    def _render_messages(self) -> Panel:
        """Render AI messages sent to game."""
        if not self.recent_messages:
            content = "[dim]No messages sent yet[/dim]"
        else:
            lines = []
            for timestamp, message in self.recent_messages:
                time_str = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
                # Truncate long messages
                msg_preview = message[:50] + "..." if len(message) > 50 else message
                lines.append(f"[dim]{time_str}[/dim] {msg_preview}")

            content = "\n".join(lines)

        return Panel(content, title="[bold magenta]📢 AI Messages[/bold magenta]", border_style="magenta")

    def _render_footer(self) -> Panel:
        """Render footer with AI metrics."""
        footer_text = Text()

        # AI Status
        footer_text.append(f"AI: {self.current_ai_status} ", style="white")

        # Context tokens
        if self.context_tokens > 0:
            tokens_pct = (self.context_tokens / 32768) * 100
            tokens_style = "green" if tokens_pct < 50 else "yellow" if tokens_pct < 80 else "red"
            footer_text.append(f"| Context: {self.context_tokens}/32k tokens ({tokens_pct:.0f}%) ", style=tokens_style)

        # Last model call
        if self.last_model_call:
            elapsed = int(time.time() - self.last_model_call)
            footer_text.append(f"| Last AI call: {elapsed}s ago ", style="dim")

        # Last tool
        if self.last_tool_used:
            footer_text.append(f"| Tool: {self.last_tool_used}", style="yellow")

        return Panel(footer_text, style="white", box=box.HEAVY)

    # Event logging methods

    def log_event(self, event_type: str, data: Dict[str, Any]):
        """Log a game event."""
        self.recent_events.append((time.time(), event_type, data))
        self.total_events += 1
        self.update()

    def log_ai_activity(self, activity_type: str, details: str):
        """Log AI activity."""
        self.ai_activity_log.append((time.time(), activity_type, details))

        if activity_type == "commentary":
            self.total_commentary += 1
        elif activity_type == "intervention":
            self.total_interventions += 1

        self.update()

    def log_message(self, message: str):
        """Log an AI message sent to the game."""
        self.recent_messages.append((time.time(), message))
        self.update()

    def update_ai_status(self, status: str):
        """Update AI status indicator."""
        self.current_ai_status = status
        self.update()

    def update_context_tokens(self, tokens: int):
        """Update context token count."""
        self.context_tokens = tokens
        self.update()

    def update_model_call(self):
        """Mark that a model call just happened."""
        self.last_model_call = time.time()
        self.update()

    def update_tool_used(self, tool_name: str):
        """Update the last tool used."""
        self.last_tool_used = tool_name
        self.update()

    def update_game_state(self, state: Dict[str, Any]):
        """Update game state cache."""
        self.game_state_cache = state
        self.update()

    def update_player_state(self, players: List[Dict[str, Any]]):
        """Update player state cache."""
        self.player_state_cache = players
        self.update()
