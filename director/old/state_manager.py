from typing import Dict, List, Optional, Any
from collections import deque
import logging

logger = logging.getLogger(__name__)

class GameStateManager:
    """Manages current game state and event history (short-term memory)."""

    def __init__(self):
        self.current_state: Optional[Dict[str, Any]] = None
        self.event_history: deque = deque(maxlen=50)
        self.player_cache: Dict[str, Dict] = {}
        self.state_history: deque = deque(maxlen=12)  # Last 1 minute of state (5s intervals)
        self.player_deltas: Dict[str, Dict[str, Any]] = {}  # Track health/hunger changes

    def update_state(self, state: Dict[str, Any]):
        """Process full state update (received every 5 seconds)."""
        # Store previous state in history before updating
        if self.current_state:
            self.state_history.append(self.current_state.copy())

        self.current_state = state
        self._update_player_cache(state.get('players', []))
        self._calculate_player_deltas()

        logger.debug(f"State updated: {state.get('gameState')} - Run {state.get('runId')}")

    def _update_player_cache(self, players: List[Dict]):
        """Update player cache with latest player data."""
        self.player_cache.clear()
        for player in players:
            self.player_cache[player['username']] = player

    def add_event(self, event: Dict[str, Any]):
        """Add real-time event to history."""
        self.event_history.append(event)
        logger.debug(f"Event added: {event.get('eventType')}")

    def get_player(self, name: str) -> Optional[Dict]:
        """Get player data by name."""
        return self.player_cache.get(name)

    def get_players_in_dimension(self, dimension: str) -> List[Dict]:
        """Get all players in a specific dimension."""
        return [
            player for player in self.player_cache.values()
            if player.get('dimension') == dimension
        ]

    def get_run_stats(self) -> Dict[str, Any]:
        """Get current run statistics."""
        if not self.current_state:
            return {}

        return {
            'runId': self.current_state.get('runId'),
            'duration': self.current_state.get('runDuration'),
            'gameState': self.current_state.get('gameState'),
            'dragonAlive': self.current_state.get('dragonAlive'),
            'dragonHealth': self.current_state.get('dragonHealth'),
            'playersAlive': len(self.player_cache),
            'totalPlayers': self.current_state.get('totalPlayers')
        }

    def get_recent_events(self, count: int = 10) -> List[Dict]:
        """Get last N events."""
        return list(self.event_history)[-count:]

    def get_context_summary(self, max_events: int = 10) -> str:
        """Generate compact context summary for AI."""
        if not self.current_state:
            return "No game state available"

        summary_parts = []

        # Current state
        summary_parts.append(f"**Game State:** {self.current_state.get('gameState')}")
        summary_parts.append(f"**Run #{self.current_state.get('runId')}** - Duration: {self.current_state.get('runDuration')}s")

        # Dragon status
        if self.current_state.get('dragonAlive'):
            health = self.current_state.get('dragonHealth', 0)
            summary_parts.append(f"**Dragon:** Alive ({health:.0f} HP)")
        else:
            summary_parts.append("**Dragon:** Dead")

        # Players
        summary_parts.append(f"**Players:** {len(self.player_cache)} active")

        # Player details
        if self.player_cache:
            summary_parts.append("\n**Player Status:**")
            for name, player in self.player_cache.items():
                health = player.get('health', 0)
                food = player.get('foodLevel', 0)
                dim = player.get('dimension', 'unknown')
                armor = player.get('armorTier', 'none')
                summary_parts.append(
                    f"- {name}: {health:.1f}❤ {food}🍖 [{dim}] ({armor} armor)"
                )

        # Recent events
        recent = list(self.event_history)[-max_events:]
        if recent:
            summary_parts.append("\n**Recent Events:**")
            for event in recent:
                event_type = event.get('eventType')
                data = event.get('data', {})
                summary_parts.append(f"- {event_type}: {self._format_event_data(data)}")

        return "\n".join(summary_parts)

    def _format_event_data(self, data: Dict) -> str:
        """Format event data for display."""
        if not data:
            return ""

        # Format based on common event data structures
        if 'player' in data:
            parts = [data['player']]
            if 'message' in data:
                parts.append(f'said "{data["message"]}"')
            elif 'outcome' in data:
                parts.append(data['outcome'])
            return " ".join(parts)

        # Default: just show key-value pairs
        return ", ".join(f"{k}={v}" for k, v in data.items())

    def has_state(self) -> bool:
        """Check if we have received initial state."""
        return self.current_state is not None

    def _calculate_player_deltas(self):
        """Calculate health/hunger deltas for danger detection."""
        if not self.state_history:
            return

        previous_state = self.state_history[-1]
        previous_players = {p['username']: p for p in previous_state.get('players', [])}

        for username, current in self.player_cache.items():
            if username not in previous_players:
                continue

            prev = previous_players[username]

            # Calculate deltas
            health_delta = current.get('health', 0) - prev.get('health', 0)
            hunger_delta = current.get('foodLevel', 0) - prev.get('foodLevel', 0)

            self.player_deltas[username] = {
                'health_delta': health_delta,
                'hunger_delta': hunger_delta,
                'health_trend': self._calculate_trend(username, 'health'),
                'hunger_trend': self._calculate_trend(username, 'hunger'),
                'is_danger': health_delta < -3 or current.get('health', 20) < 6
            }

    def _calculate_trend(self, username: str, stat: str) -> float:
        """Calculate trend over last N states (positive = improving, negative = declining)."""
        if len(self.state_history) < 3:
            return 0.0

        values = []
        for state in list(self.state_history)[-6:]:  # Last 30 seconds
            for player in state.get('players', []):
                if player['username'] == username:
                    values.append(player.get(stat, 0))
                    break

        if len(values) < 2:
            return 0.0

        # Simple linear trend: difference between recent avg and older avg
        mid = len(values) // 2
        old_avg = sum(values[:mid]) / mid
        new_avg = sum(values[mid:]) / (len(values) - mid)
        return new_avg - old_avg

    def get_player_delta(self, name: str) -> Dict[str, Any]:
        """Get health/hunger delta data for a player."""
        return self.player_deltas.get(name, {
            'health_delta': 0,
            'hunger_delta': 0,
            'health_trend': 0,
            'hunger_trend': 0,
            'is_danger': False
        })

    def calculate_player_distances(self) -> Dict[str, Dict[str, Any]]:
        """Calculate distances between all players (grouped by dimension)."""
        distances = {}

        # Group players by dimension for efficient calculation
        dimensions = {}
        for username, player in self.player_cache.items():
            dim = player.get('dimension', 'unknown')
            if dim not in dimensions:
                dimensions[dim] = []
            dimensions[dim].append((username, player))

        # Calculate distances within each dimension
        for dim, players in dimensions.items():
            for i, (name1, player1) in enumerate(players):
                loc1 = player1.get('location', {})
                x1, y1, z1 = loc1.get('x', 0), loc1.get('y', 0), loc1.get('z', 0)

                nearest = None
                min_dist = float('inf')

                for j, (name2, player2) in enumerate(players):
                    if i == j:
                        continue

                    loc2 = player2.get('location', {})
                    x2, y2, z2 = loc2.get('x', 0), loc2.get('y', 0), loc2.get('z', 0)

                    # 3D Euclidean distance
                    dist = ((x2-x1)**2 + (y2-y1)**2 + (z2-z1)**2) ** 0.5

                    if dist < min_dist:
                        min_dist = dist
                        nearest = name2

                distances[name1] = {
                    'nearest_player': nearest,
                    'nearest_distance': min_dist if nearest else -1,
                    'is_grouped': min_dist < 50 if nearest else False  # Within 50 blocks = grouped
                }

        return distances
