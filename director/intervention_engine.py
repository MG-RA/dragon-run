import time
import random
from typing import Dict, List, Optional, Any
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class InterventionEngine:
    """
    Narrative-aware intervention system that creates memorable moments.

    Instead of random interventions, this engine:
    - Identifies narrative opportunities based on game state
    - Scores opportunities by entertainment value
    - Enforces fairness rules (no targeting same player repeatedly)
    - Ensures interventions are survivable (no unfair deaths)
    """

    def __init__(self, config: Dict[str, Any]):
        intervention_config = config.get('intervention', {})
        self.enabled = intervention_config.get('enabled', True)
        self.base_cooldown = intervention_config.get('cooldown_seconds', 180)  # 3 min default
        self.types = intervention_config.get('types', {})

        # Tracking state
        self.last_intervention_time = 0
        self.intervention_history: List[Dict] = []
        self.player_condition_tracker: Dict[str, Dict] = defaultdict(dict)

    def evaluate_intervention(self, state: Dict, events: List[Dict]) -> Optional[Dict]:
        """
        Analyze game state and determine if intervention is appropriate.
        Returns intervention dict or None.
        """
        if not self.enabled:
            return None

        # Basic cooldown check
        if time.time() - self.last_intervention_time < self.base_cooldown:
            return None

        # Never intervene in first 2 minutes of run
        run_duration = state.get('runDuration', 0)
        if run_duration < 120:
            return None

        # Never intervene during dragon fight (< 150 HP)
        dragon_health = state.get('dragonHealth', 0)
        if 0 < dragon_health < 150:
            return None

        players = state.get('players', [])
        if not players:
            return None

        # Update condition tracker
        self._update_condition_tracker(players)

        # Find narrative opportunities
        opportunities = self._find_opportunities(players, state, events)

        if not opportunities:
            return None

        # Score and filter opportunities
        valid_opportunities = [
            opp for opp in opportunities
            if self._passes_fairness_check(opp, state)
        ]

        if not valid_opportunities:
            return None

        # Pick best opportunity (highest score)
        best = max(valid_opportunities, key=lambda x: x.get('score', 0))

        # Record this intervention
        self._record_intervention(best)

        return best

    def _update_condition_tracker(self, players: List[Dict]):
        """Track how long players have been in certain conditions."""
        current_time = time.time()

        for player in players:
            name = player.get('username')
            health = player.get('health', 20)
            food = player.get('foodLevel', 20)

            tracker = self.player_condition_tracker[name]

            # Track starvation
            if food <= 3:
                if 'starving_since' not in tracker:
                    tracker['starving_since'] = current_time
            else:
                tracker.pop('starving_since', None)

            # Track critical health
            if health < 5:
                if 'critical_since' not in tracker:
                    tracker['critical_since'] = current_time
            else:
                tracker.pop('critical_since', None)

    def _get_condition_duration(self, player_name: str, condition: str) -> float:
        """Get how long a player has been in a condition (seconds)."""
        tracker = self.player_condition_tracker.get(player_name, {})
        since_key = f'{condition}_since'
        if since_key in tracker:
            return time.time() - tracker[since_key]
        return 0

    def _find_opportunities(self, players: List[Dict], state: Dict, events: List[Dict]) -> List[Dict]:
        """Find all current intervention opportunities."""
        opportunities = []

        for player in players:
            name = player.get('username')
            health = player.get('health', 20)
            food = player.get('foodLevel', 20)
            armor = player.get('armorTier', 'none')
            dimension = player.get('dimension', 'overworld')

            # === MERCY OPPORTUNITIES ===
            if self.types.get('mercy', True):
                # Starvation relief - player starving for 30+ seconds
                starvation_duration = self._get_condition_duration(name, 'starving')
                if food <= 3 and starvation_duration > 30:
                    urgency = 8 if health < 6 else 5
                    opportunities.append({
                        'type': 'mercy',
                        'subtype': 'starvation_relief',
                        'player': name,
                        'score': urgency + min(starvation_duration / 30, 3),  # Higher score for longer starvation
                        'reason': f"{name} has been starving for {int(starvation_duration)}s",
                        'command': 'give',
                        'parameters': {
                            'player': name,
                            'item': 'cooked_beef',
                            'count': 4
                        }
                    })

                # Critical health relief - low health for 45+ seconds
                critical_duration = self._get_condition_duration(name, 'critical')
                if health < 5 and critical_duration > 45:
                    opportunities.append({
                        'type': 'mercy',
                        'subtype': 'health_gift',
                        'player': name,
                        'score': 7 + min(critical_duration / 30, 3),
                        'reason': f"{name} has been at critical health ({health:.1f} HP) for {int(critical_duration)}s",
                        'command': 'give',
                        'parameters': {
                            'player': name,
                            'item': 'golden_apple',
                            'count': 1
                        }
                    })

            # === CHALLENGE OPPORTUNITIES ===
            if self.types.get('challenge', True):
                # Well-equipped player cruising in overworld
                if (armor in ['diamond', 'netherite'] and
                    health > 16 and
                    dimension == 'overworld' and
                    food > 10):

                    # Check if they've been safe for a while (no recent damage)
                    recent_damage = any(
                        e.get('eventType') == 'player_damaged' and
                        e.get('data', {}).get('player') == name
                        for e in events[-10:]
                    )

                    if not recent_damage:
                        mob = random.choice(['zombie', 'skeleton', 'spider'])
                        opportunities.append({
                            'type': 'challenge',
                            'subtype': 'test_the_worthy',
                            'player': name,
                            'score': 4,  # Lower priority than mercy
                            'reason': f"{name} is well-equipped ({armor} armor, {health:.0f} HP) and unchallenged",
                            'command': 'spawn_mob',
                            'parameters': {
                                'mobType': mob,
                                'nearPlayer': name,
                                'count': 2
                            }
                        })

            # === DRAMATIC OPPORTUNITIES ===
            if self.types.get('dramatic', True):
                # First time entering nether (check recent events)
                nether_entry = any(
                    e.get('eventType') == 'player_dimension_change' and
                    e.get('data', {}).get('player') == name and
                    e.get('data', {}).get('to') == 'nether' and
                    time.time() - e.get('timestamp', 0) / 1000 < 30  # Within last 30 seconds
                    for e in events
                )

                if nether_entry:
                    # Use lightning instead of weather (works in all dimensions)
                    opportunities.append({
                        'type': 'dramatic',
                        'subtype': 'nether_welcome',
                        'player': name,
                        'score': 5,
                        'reason': f"{name} just entered the Nether",
                        'command': 'lightning',
                        'parameters': {
                            'nearPlayer': name
                        }
                    })

        # === GLOBAL DRAMATIC OPPORTUNITIES ===
        if self.types.get('dramatic', True):
            run_duration = state.get('runDuration', 0)

            # Long quiet run - add some atmosphere (only if players are in overworld)
            # Weather only works in overworld, so only trigger if someone is there
            has_overworld_players = any(
                p.get('dimension', 'overworld') == 'overworld'
                for p in players
            )

            if run_duration > 600 and has_overworld_players and random.random() < 0.15:
                opportunities.append({
                    'type': 'dramatic',
                    'subtype': 'atmosphere',
                    'score': 2,  # Low priority
                    'reason': "Creating atmosphere for long run",
                    'command': 'weather',
                    'parameters': {
                        'type': random.choice(['rain', 'thunder'])
                    }
                })

        return opportunities

    def _passes_fairness_check(self, opportunity: Dict, state: Dict) -> bool:
        """Ensure we don't unfairly target or help the same player repeatedly."""
        player = opportunity.get('player')

        # Global interventions (no specific player) always pass
        if not player:
            return True

        # Check recent intervention history for this player
        recent = [
            i for i in self.intervention_history
            if i.get('player') == player and
            time.time() - i.get('timestamp', 0) < 300  # Last 5 minutes
        ]

        # Max 2 interventions per player per 5 minutes
        if len(recent) >= 2:
            return False

        # Don't challenge players who are struggling
        if opportunity['type'] == 'challenge':
            player_data = next(
                (p for p in state.get('players', []) if p['username'] == player),
                None
            )
            if player_data:
                # Don't challenge if health < 10 or food < 6
                if player_data.get('health', 20) < 10:
                    return False
                if player_data.get('foodLevel', 20) < 6:
                    return False

        return True

    def _record_intervention(self, intervention: Dict):
        """Record an intervention for fairness tracking."""
        self.last_intervention_time = time.time()

        record = {
            'type': intervention['type'],
            'subtype': intervention.get('subtype'),
            'player': intervention.get('player'),
            'timestamp': time.time(),
            'command': intervention['command']
        }

        self.intervention_history.append(record)

        # Keep only last 50 interventions
        if len(self.intervention_history) > 50:
            self.intervention_history = self.intervention_history[-50:]
