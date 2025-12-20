import time
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)

class CommentaryEngine:
    """Determines when and what to narrate based on game events."""

    def __init__(self, config: Dict[str, Any]):
        self.enabled = config.get('commentary', {}).get('enabled', True)
        self.cooldown = config.get('commentary', {}).get('cooldown_seconds', 5)
        self.style = config.get('commentary', {}).get('style', 'detached_observer')
        self.triggers = config.get('commentary', {}).get('triggers', {})
        self.last_commentary_time = 0

    def should_comment(self, event: Dict[str, Any]) -> bool:
        """Determine if an event warrants commentary."""
        if not self.enabled:
            return False

        event_type = event.get('eventType', '')
        if not event_type:
            return False

        # Check if this event type is enabled
        trigger_map: Dict[str, bool] = {
            'run_ended': self.triggers.get('player_death', True),
            'player_death_detailed': self.triggers.get('player_death', True),
            'player_dimension_change': self.triggers.get('dimension_change', True),
            'player_near_death': self.triggers.get('near_death', True),
            'player_damaged': self.triggers.get('player_damaged', True),  # Close calls and big hits
            'player_milestone': self.triggers.get('milestone', True),
            'dragon_phase_change': self.triggers.get('dragon_phase', True),
            'player_chat': self.triggers.get('player_chat', False),
            'player_joined': self.triggers.get('player_join', True),
            'run_started': self.triggers.get('run_start', True),
            'dragon_killed': True,  # Always announce dragon kills!
            'achievement_unlocked': self.triggers.get('achievement', True),
            'first_iron_obtained': self.triggers.get('milestone', True),
            'first_diamond_obtained': self.triggers.get('milestone', True),
            'blaze_rod_obtained': self.triggers.get('milestone', True),
            'ender_eye_crafted': self.triggers.get('milestone', True),
            'player_combat': self.triggers.get('combat', False),  # Only notable kills
        }

        # Check if event type is enabled
        if not trigger_map.get(event_type, False):
            return False

        # Priority events that bypass cooldown (always comment on these)
        priority_events = [
            'player_chat',      # Instant chat responses
            'player_joined',    # Welcome players immediately
            'run_started',      # Always announce run start
            'run_ended',        # Always announce deaths/victories
            'player_death_detailed',  # Always comment on deaths
            'dragon_killed'     # ALWAYS celebrate dragon kills!
        ]
        if event_type in priority_events:
            return True

        # Check cooldown for less important events
        if time.time() - self.last_commentary_time < self.cooldown:
            return False

        return True

    def build_prompt(self, event: Dict, state: Dict, history: List[Dict]) -> str:
        """Build Ollama prompt with context."""
        event_type = event.get('eventType', 'unknown')
        event_data = event.get('data', {})

        # Build context
        context = self._build_context(state, history)

        # Build event description
        event_desc = self._describe_event(str(event_type), event_data)

        # Select system prompt based on style
        system_style = self._get_style_prompt()

        # Customize instructions based on event type
        instructions = self._get_event_instructions(str(event_type), event_data)

        prompt = f"""{system_style}

CURRENT SITUATION:
{context}

EVENT THAT JUST HAPPENED:
{event_desc}

{instructions}
"""

        return prompt

    def _get_style_prompt(self) -> str:
        """Get style guidance - now simplified since main prompt defines Eris personality."""
        # The main system prompt in main.py defines Eris's personality
        # This just provides additional context hints
        return "Remember: Be casual, entertaining, and brief. React naturally to what happened."

    def _build_context(self, state: Dict, history: List[Dict]) -> str:
        """Build compact context summary."""
        parts = []

        # Run info
        run_duration = state.get('runDuration', 0)
        minutes = run_duration // 60
        seconds = run_duration % 60
        parts.append(f"Run Duration: {minutes}m {seconds}s")

        # Players
        players = state.get('players', [])
        alive_count = len(players)
        total_count = state.get('totalPlayers', alive_count)
        parts.append(f"Players: {alive_count}/{total_count} alive")

        # Dragon
        if state.get('dragonAlive'):
            dragon_hp = state.get('dragonHealth', 200)
            parts.append(f"Dragon: Alive ({dragon_hp:.0f} HP)")
        else:
            parts.append("Dragon: Defeated")

        # Player details (if few enough)
        if alive_count <= 5:
            parts.append("\nPlayer Status:")
            for player in players:
                name = player.get('username')
                health = player.get('health', 0)
                dim = player.get('dimension', '?')
                parts.append(f"- {name}: {health:.1f} HP in {dim}")

        # Recent events (last 3)
        if history:
            parts.append("\nRecent Events:")
            for ev in history[-3:]:
                ev_type = ev.get('eventType')
                parts.append(f"- {ev_type}")

        return "\n".join(parts)

    def _get_event_instructions(self, event_type: str, data: Dict) -> str:
        """Get specific instructions based on event type."""
        instructions = {
            'player_joined': self._get_greeting_instructions(data),
            'run_started': """Provide a dramatic 1-2 sentence opening narration for the run starting.
Build excitement and tension. Welcome everyone to the challenge ahead!""",
            'run_ended': """Provide a 1-2 sentence dramatic narration of this event. Be engaging and entertaining, like you're calling a crucial play in a high-stakes game.""",
            'player_death_detailed': """Provide a 1-2 sentence dramatic narration of this event. Be engaging and entertaining, like you're calling a crucial play in a high-stakes game.""",
        }

        # Default instruction for other events
        default = """Provide a 1-2 sentence dramatic narration of this event. Be engaging and entertaining, like you're calling a crucial play in a high-stakes game."""

        return instructions.get(event_type, default)

    def _get_greeting_instructions(self, data: Dict) -> str:
        """Get greeting instructions based on player status."""
        is_new = data.get('isNewPlayer', False)
        aura = data.get('aura', 0)
        player = data.get('player', 'player')

        if is_new:
            return f"""Welcome {player} to Dragon Run! This is their first time joining.
Give them a warm, exciting welcome in 1-2 sentences. Make them feel the thrill of what awaits!"""
        else:
            return f"""Welcome back {player} (Aura: {aura}) to Dragon Run!
Greet them in 1-2 sentences. Acknowledge their aura/experience if it's notable."""

    def _describe_event(self, event_type: str, data: Dict) -> str:
        """Create human-readable event description."""
        descriptions = {
            'player_joined': self._describe_player_join(data),
            'run_started': self._describe_run_start(data),
            'run_ended': self._describe_run_end(data),
            'player_death_detailed': self._describe_death(data),
            'player_dimension_change': f"{data.get('player')} entered the {data.get('to')}",
            'player_near_death': f"{data.get('player')} is critically low on health!",
            'player_damaged': self._describe_damage(data),
            'player_milestone': self._describe_milestone(data),
            'achievement_unlocked': f"{data.get('player')} unlocked achievement: {data.get('achievementName', data.get('achievement', 'unknown'))}",
            'player_chat': f"{data.get('player')} said: \"{data.get('message')}\"",
            'dragon_killed': self._describe_dragon_kill(data),
            'first_iron_obtained': f"{data.get('player')} got their first iron!",
            'first_diamond_obtained': f"{data.get('player')} found diamonds!",
            'blaze_rod_obtained': f"{data.get('player')} got blaze rods - nether fortress found!",
            'ender_eye_crafted': f"{data.get('player')} crafted an eye of ender - heading to the End!",
            'player_combat': self._describe_combat(data),
        }

        return descriptions.get(event_type, f"Event: {event_type} - {data}")

    def _describe_dragon_kill(self, data: Dict) -> str:
        player = data.get('player', 'Unknown')
        duration = data.get('duration', 0)
        mins = duration // 60
        secs = duration % 60
        return f"{player} has slain the Ender Dragon! Time: {mins}m {secs}s. VICTORY!"

    def _describe_player_join(self, data: Dict) -> str:
        player = data.get('player', 'Unknown')
        aura = data.get('aura', 0)
        is_new = data.get('isNewPlayer', False)
        if is_new:
            return f"{player} joined the server for the first time!"
        else:
            return f"{player} joined the server (Aura: {aura})"

    def _describe_run_start(self, data: Dict) -> str:
        run_id = data.get('runId', '?')
        world_name = data.get('worldName', 'unknown')
        return f"Run #{run_id} has begun! The adventure starts now."

    def _describe_run_end(self, data: Dict) -> str:
        outcome = data.get('outcome')
        if outcome == 'DRAGON_KILLED':
            duration = data.get('duration', 0)
            mins = duration // 60
            return f"The dragon has been slain in {mins} minutes! Victory!"
        else:
            return f"The last player has fallen. Run over."

    def _describe_death(self, data: Dict) -> str:
        player = data.get('player', 'Unknown')
        cause = data.get('cause', 'unknown')
        dimension = data.get('dimension', 'unknown')
        return f"{player} died to {cause} in the {dimension}"

    def _describe_milestone(self, data: Dict) -> str:
        player = data.get('player', 'Unknown')
        milestone = data.get('milestone', 'something')
        return f"{player} achieved {milestone}"

    def _describe_damage(self, data: Dict) -> str:
        """Describe a damage event."""
        player = data.get('player', 'Unknown')
        damage = data.get('damage', 0)
        source = data.get('source', 'unknown')
        health_after = data.get('healthAfter', 0)
        is_close_call = data.get('isCloseCall', False)

        if is_close_call:
            return f"{player} took {damage:.1f} damage from {source} and is down to {health_after:.1f} HP! Close call!"
        else:
            return f"{player} took a big hit ({damage:.1f} damage) from {source}, now at {health_after:.1f} HP"

    def _describe_combat(self, data: Dict) -> str:
        """Describe a combat/kill event."""
        player = data.get('player', 'Unknown')
        mob_type = data.get('mobType', 'unknown').replace('_', ' ')
        total_kills = data.get('totalKills', 0)

        if data.get('isSignificant'):
            return f"{player} killed a {mob_type}! Total kills this run: {total_kills}"
        return f"{player} killed a {mob_type} ({total_kills} total)"

    def mark_commentary_sent(self):
        """Update last commentary timestamp."""
        self.last_commentary_time = time.time()
