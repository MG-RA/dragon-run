"""Short-term and long-term memory management - v1.1."""

import logging
from collections import deque
from datetime import datetime

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
            # Event data is stored as {"eventType": ..., "data": {...}}
            # Extract the nested data payload
            raw_data = event.get("data", {})
            data = raw_data.get("data", {}) if isinstance(raw_data, dict) else {}

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
                is_close_call = data.get("isCloseCall", False)
                if is_close_call:
                    lines.append(f"⚡ {player} nearly died! (health: {health})")
                else:
                    lines.append(f"💥 {player} took {damage} damage (health: {health})")
            elif event_type == "dimension_change":
                player = data.get("player", "Unknown")
                dimension = data.get("dimension", "unknown")
                lines.append(f"🌍 {player} entered {dimension}")
            elif event_type == "run_started":
                lines.append("🎬 New run started!")
            elif event_type == "run_ending":
                lines.append("⏹️  Run ending...")
            elif event_type == "run_ended":
                lines.append("⏹️  Run ended")
            elif event_type == "player_joined":
                player = data.get("player", "Unknown")
                lines.append(f"👋 {player} joined the game")
            elif event_type == "player_dimension_change":
                player = data.get("player", "Unknown")
                from_dim = data.get("from", "unknown")
                to_dim = data.get("to", "unknown")
                lines.append(f"🌍 {player} traveled from {from_dim} to {to_dim}")
            elif event_type == "boss_killed":
                player = data.get("player", "Unknown")
                mob_type = data.get("mobType", "boss")
                weapon = data.get("weapon", "unknown")
                lines.append(f"🏆 {player} killed {mob_type} with {weapon}!")
            elif event_type == "mob_kills_batch":
                # Aggregated kill data - format as summary
                player_kills = data.get("playerKills", [])
                total = data.get("totalKills", 0)
                if player_kills:
                    summaries = []
                    for pk in player_kills[:3]:  # Top 3 players
                        name = pk.get("player", "Unknown")
                        count = pk.get("count", 0)
                        summaries.append(f"{name}: {count}")
                    lines.append(f"⚔️ Mob kills (30s): {', '.join(summaries)} | Total: {total}")
            elif event_type == "structure_discovered":
                player = data.get("player", "Unknown")
                structure = data.get("structureName", data.get("structureType", "structure"))
                priority = data.get("priority", "low")
                if priority == "critical":
                    lines.append(f"🎯 {player} found the {structure}! (Critical milestone)")
                elif priority == "high":
                    lines.append(f"🏰 {player} discovered a {structure}")
                else:
                    lines.append(f"📍 {player} found a {structure}")
            elif event_type == "advancement_made":
                player = data.get("player", "Unknown")
                adv_name = data.get("advancementName", "advancement")
                is_critical = data.get("isCritical", False)
                if is_critical:
                    lines.append(f"⭐ {player} achieved: {adv_name} (Critical!)")
                else:
                    lines.append(f"📜 {player}: {adv_name}")
            elif event_type == "achievement_unlocked":
                player = data.get("player", "Unknown")
                title = data.get("title", "achievement")
                aura = data.get("auraReward", 0)
                lines.append(f"🏅 {player} unlocked: {title} (+{aura} aura)")
            elif event_type == "item_collected":
                player = data.get("player", "Unknown")
                item = data.get("itemType", "item").replace("_", " ").lower()
                qty = data.get("quantity", 1)
                is_enchanted = data.get("isEnchanted", False)
                if is_enchanted:
                    lines.append(f"✨ {player} picked up enchanted {item}")
                else:
                    lines.append(f"📦 {player} picked up {qty}x {item}")
            elif event_type == "entity_leashed":
                player = data.get("player", "Unknown")
                entity = data.get("entityType", "creature").replace("_", " ")
                entity_name = data.get("entityName")
                if entity_name:
                    lines.append(f"🐕 {player} leashed {entity_name} ({entity})")
                else:
                    lines.append(f"🐕 {player} leashed a {entity}")
            elif event_type == "vehicle_entered":
                player = data.get("player", "Unknown")
                vehicle = data.get("vehicleType", "vehicle").replace("_", " ")
                lines.append(f"🚗 {player} entered a {vehicle}")
            elif event_type == "vehicle_exited":
                player = data.get("player", "Unknown")
                vehicle = data.get("vehicleType", "vehicle").replace("_", " ")
                lines.append(f"🚗 {player} exited a {vehicle}")
            # Protection system events
            elif event_type == "eris_close_call":
                player = data.get("player", "Unknown")
                health = data.get("healthAfter", 0)
                source = data.get("source", "unknown")
                lines.append(
                    f"⚠️ {player} nearly died to {source}! (health: {health}) [ERIS-CAUSED]"
                )
            elif event_type == "eris_caused_death":
                player = data.get("player", "Unknown")
                cause = data.get("cause", "unknown")
                lines.append(f"💀 {player} KILLED by Eris intervention ({cause})!")
            elif event_type == "eris_protection_used":
                player = data.get("player", "Unknown")
                aura_cost = data.get("auraCost", 0)
                protection_type = data.get("protectionType", "protection")
                lines.append(f"🛡️ Eris SAVED {player} with {protection_type} (-{aura_cost} aura)")
            elif event_type == "eris_respawn_override":
                player = data.get("player", "Unknown")
                aura_cost = data.get("auraCost", 0)
                lines.append(f"✨ DIVINE INTERVENTION: Eris respawned {player} (-{aura_cost} aura)")

        return "\n".join(lines[-30:])  # Last 30 events max

    def get_context_with_tension(
        self,
        player_fear: dict[str, int] | None = None,
        global_chaos: int = 0,
    ) -> str:
        """
        Format memory as narrative context with tension state - v1.1.

        Includes fear/chaos summary for LLM context.
        """
        context = self.get_context_string()

        # Add tension summary
        tension_lines = []
        if global_chaos > 0:
            chaos_label = "LOW"
            if global_chaos >= 70:
                chaos_label = "CRITICAL"
            elif global_chaos >= 50:
                chaos_label = "HIGH"
            elif global_chaos >= 30:
                chaos_label = "MODERATE"
            tension_lines.append(f"🌀 Global Chaos: {global_chaos}/100 ({chaos_label})")

        if player_fear:
            high_fear_players = [f"{p}: {f}" for p, f in player_fear.items() if f >= 30]
            if high_fear_players:
                tension_lines.append(f"😨 Elevated Fear: {', '.join(high_fear_players)}")

        if tension_lines:
            return context + "\n\n=== TENSION STATE ===\n" + "\n".join(tension_lines)

        return context

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
