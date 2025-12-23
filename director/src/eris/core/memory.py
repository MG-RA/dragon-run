"""Short-term and long-term memory management."""

import logging
from collections import deque
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class ShortTermMemory:
    """Rolling window of recent events in context."""

    def __init__(self, max_tokens: int = 25000):
        self.max_tokens = max_tokens
        self.events: deque = deque()
        self.token_estimate = 0

    def add_event(self, event: dict):
        """Add event to memory, pruning old if needed."""
        # Event is already flattened with eventType at root
        self.events.append(
            {
                "type": event.get("eventType", "unknown"),
                "data": event,  # Store entire event as data
                "time": datetime.now().isoformat(),
            }
        )

        # Estimate tokens (rough heuristic: ~1.3 tokens per character)
        self.token_estimate += self._estimate_tokens(str(event))

        # Prune to fit context
        while self.token_estimate > self.max_tokens and self.events:
            old_event = self.events.popleft()
            self.token_estimate -= self._estimate_tokens(str(old_event))

    def get_context_string(self) -> str:
        """Format memory as narrative context for LLM."""
        if not self.events:
            return "No recent events."

        lines = []
        for event in self.events:
            event_type = event.get("type", "unknown")
            data = event.get("data", {})
            time = event.get("time", "")

            if event_type == "player_chat":
                player = data.get("player", "Unknown")
                message = data.get("message", "")
                lines.append(f"[{player}] {message}")
            elif event_type == "player_death":
                player = data.get("player", "Unknown")
                cause = data.get("cause", "unknown")
                lines.append(f"⚰️  {player} died ({cause})")
            elif event_type == "dragon_killed":
                killers = data.get("killers", [])
                lines.append(f"🐉 Dragon killed by {', '.join(killers)}")
            elif event_type == "resource_milestone":
                player = data.get("player", "Unknown")
                resource = data.get("resource", "unknown")
                lines.append(f"📦 {player} obtained {resource}")
            elif event_type == "player_damaged":
                player = data.get("player", "Unknown")
                damage = data.get("damage", 0)
                health = data.get("health_after", 0)
                lines.append(f"💥 {player} took {damage} damage (health: {health})")
            elif event_type == "dimension_change":
                player = data.get("player", "Unknown")
                dimension = data.get("dimension", "unknown")
                lines.append(f"🌍 {player} entered {dimension}")
            elif event_type == "player_damaged" and data.get("isCloseCall"):
                player = data.get("player", "Unknown")
                lines.append(f"⚡ {player} nearly died!")
            elif event_type == "run_started":
                lines.append("🎬 New run started!")
            elif event_type == "run_ended":
                lines.append("⏹️  Run ended")

        return "\n".join(lines[-30:])  # Last 30 events max

    def _estimate_tokens(self, text: str) -> int:
        """Rough estimate of tokens from text."""
        return int(len(text) / 4 * 1.3)

    def clear(self):
        """Clear memory."""
        self.events.clear()
        self.token_estimate = 0


class LongTermMemory:
    """Interface to PostgreSQL for persistent memory."""

    def __init__(self, db):
        self.db = db

    async def get_player_context(self, uuid: str) -> str:
        """Get player history as context."""
        summary = await self.db.get_player_summary(uuid)

        if not summary:
            return "New player."

        nemesis = await self.db.get_player_nemesis(uuid)

        lines = [
            f"Username: {summary.get('username', 'Unknown')}",
            f"Aura: {summary.get('aura', 0)}",
            f"Total Runs: {summary.get('total_runs', 0)}",
            f"Deaths: {summary.get('total_deaths', 0)}",
            f"Dragons Killed: {summary.get('dragons_killed', 0)}",
            f"Playtime: {summary.get('hours_played', 0):.1f} hours",
            f"Achievements: {summary.get('achievement_count', 0)}",
        ]

        if nemesis:
            lines.append(f"Often killed by: {nemesis}")

        return " | ".join(lines)
