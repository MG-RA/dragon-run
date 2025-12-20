"""
Proactive Engine for Eris AI Director.

Analyzes game state to find interesting moments that warrant commentary
WITHOUT requiring explicit events. This enables Eris to initiate
conversations and make observations during normal gameplay.
"""

import time
import math
from typing import Dict, List, Optional, Any, Set
from collections import deque
import logging

logger = logging.getLogger(__name__)


class ProactiveEngine:
    """
    Analyzes game state to find interesting moments without explicit events.

    This allows Eris to:
    - Comment on close call recoveries
    - Notice player patterns (grouping, solo danger)
    - Observe progress anomalies (fast/slow progress)
    - Break silence during quiet moments
    """

    def __init__(self, config: Dict[str, Any]):
        proactive_config = config.get('proactive', {})
        self.enabled = proactive_config.get('enabled', True)
        self.cooldown = proactive_config.get('cooldown_seconds', 75)  # 60-90 second range
        self.quiet_threshold = proactive_config.get('quiet_threshold_seconds', 120)

        # State tracking
        self.last_proactive_time = 0
        self.observation_history: Set[str] = set()  # Avoid repeating observations
        self.player_health_history: Dict[str, deque] = {}  # Track health over time
        self.state_history: deque = deque(maxlen=30)  # ~2.5 min of state at 5s intervals
        self.last_event_time = time.time()

    def record_event(self):
        """Record that an event occurred (resets quiet timer)."""
        self.last_event_time = time.time()

    def should_analyze(self) -> bool:
        """Check if we should run proactive analysis."""
        if not self.enabled:
            return False
        return time.time() - self.last_proactive_time >= self.cooldown

    def analyze_state(self, state: Dict, events: List[Dict]) -> Optional[Dict]:
        """
        Analyze current state and return an observation if something interesting is found.

        Returns observation dict with:
        - type: observation type
        - prompt: description for LLM
        - priority: how important (1-10)
        - id: unique identifier to avoid repeats

        Returns None if nothing interesting.
        """
        if not self.enabled:
            return None

        # Update state history
        self.state_history.append({
            'state': state,
            'timestamp': time.time()
        })

        # Update player health history
        self._update_health_history(state.get('players', []))

        # Collect all observations
        observations = []

        # Check various interesting situations
        observations.extend(self._check_close_call_recovery(state))
        observations.extend(self._check_player_patterns(state))
        observations.extend(self._check_progress_anomalies(state))
        observations.extend(self._check_quiet_moments(state))

        if not observations:
            return None

        # Filter out recently made observations
        new_observations = [
            obs for obs in observations
            if obs['id'] not in self.observation_history
        ]

        if not new_observations:
            return None

        # Pick highest priority observation
        best = max(new_observations, key=lambda x: x.get('priority', 0))

        # Record this observation
        self.observation_history.add(best['id'])
        self.last_proactive_time = time.time()

        # Limit observation history size
        if len(self.observation_history) > 100:
            # Remove oldest (convert to list, slice, convert back)
            self.observation_history = set(list(self.observation_history)[-50:])

        return best

    def _update_health_history(self, players: List[Dict]):
        """Track player health over time for trend detection."""
        for player in players:
            name = player.get('username')
            health = player.get('health', 20)

            if name not in self.player_health_history:
                self.player_health_history[name] = deque(maxlen=12)  # ~1 min of data

            self.player_health_history[name].append({
                'health': health,
                'timestamp': time.time()
            })

    def _check_close_call_recovery(self, state: Dict) -> List[Dict]:
        """Detect players who recovered from near-death."""
        observations = []

        for player in state.get('players', []):
            name = player.get('username')
            current_health = player.get('health', 20)

            history = self.player_health_history.get(name, [])
            if len(history) < 5:
                continue

            # Look at recent health values
            recent_healths = [h['health'] for h in list(history)[-6:]]
            min_recent = min(recent_healths[:-1]) if len(recent_healths) > 1 else 20

            # Significant recovery: was below 4 HP, now above 12 HP
            if min_recent < 4 and current_health > 12:
                obs_id = f"recovery_{name}_{int(time.time() // 120)}"  # 2-min window
                observations.append({
                    'id': obs_id,
                    'type': 'close_call_recovery',
                    'player': name,
                    'priority': 7,
                    'prompt': f"{name} recovered from a close call! Was at {min_recent:.1f} HP, now at {current_health:.1f} HP. They narrowly escaped death.",
                    'min_health': min_recent,
                    'current_health': current_health
                })

        return observations

    def _check_player_patterns(self, state: Dict) -> List[Dict]:
        """Detect interesting player behavior patterns."""
        observations = []
        players = state.get('players', [])

        if len(players) < 2:
            return observations

        # Calculate distances between players
        distances = self._calculate_player_distances(players)

        # Check for players grouping up
        grouped_pairs = []
        for name, info in distances.items():
            if info.get('distance', float('inf')) < 30:  # Within 30 blocks
                pair = tuple(sorted([name, info['nearest']]))
                if pair not in grouped_pairs:
                    grouped_pairs.append(pair)

        if grouped_pairs:
            # Players working together
            all_grouped = set()
            for p1, p2 in grouped_pairs:
                all_grouped.add(p1)
                all_grouped.add(p2)

            if len(all_grouped) >= 2:
                obs_id = f"teamwork_{hash(tuple(sorted(all_grouped)))}"
                grouped_list = list(all_grouped)[:3]  # Max 3 names
                observations.append({
                    'id': obs_id,
                    'type': 'teamwork',
                    'players': grouped_list,
                    'priority': 3,
                    'prompt': f"{' and '.join(grouped_list)} are traveling together, working as a team."
                })

        # Check for solo player in dangerous situation
        for player in players:
            name = player.get('username')
            dimension = player.get('dimension', 'overworld')
            health = player.get('health', 20)

            dist_info = distances.get(name, {})
            is_alone = dist_info.get('distance', float('inf')) > 100

            if dimension in ['nether', 'end'] and is_alone and health < 12:
                obs_id = f"solo_danger_{name}_{dimension}"
                observations.append({
                    'id': obs_id,
                    'type': 'solo_danger',
                    'player': name,
                    'priority': 5,
                    'prompt': f"{name} is alone in the {dimension} with only {health:.1f} HP. No backup nearby."
                })

        return observations

    def _check_progress_anomalies(self, state: Dict) -> List[Dict]:
        """Detect unusual progress patterns."""
        observations = []
        run_duration = state.get('runDuration', 0)

        for player in state.get('players', []):
            name = player.get('username')
            diamonds = player.get('diamondCount', 0)
            armor = player.get('armorTier', 'none')
            dimension = player.get('dimension', 'overworld')

            # Fast progress - diamonds within 5 minutes
            if run_duration < 300 and diamonds >= 3:
                obs_id = f"fast_progress_{name}_{run_duration // 60}"
                observations.append({
                    'id': obs_id,
                    'type': 'fast_progress',
                    'player': name,
                    'priority': 5,
                    'prompt': f"{name} found {diamonds} diamonds in just {run_duration // 60} minutes! Speedrunner vibes."
                })

            # Fast nether entry
            if run_duration < 420 and dimension == 'nether':  # 7 min
                obs_id = f"fast_nether_{name}"
                observations.append({
                    'id': obs_id,
                    'type': 'fast_nether',
                    'player': name,
                    'priority': 4,
                    'prompt': f"{name} reached the Nether in under {run_duration // 60} minutes. Moving fast."
                })

            # Slow progress - still basic armor after 15 minutes
            if run_duration > 900 and armor in ['none', 'leather', 'gold']:
                obs_id = f"struggling_{name}_{run_duration // 300}"  # 5-min windows
                observations.append({
                    'id': obs_id,
                    'type': 'struggling',
                    'player': name,
                    'priority': 3,
                    'prompt': f"{name} is {run_duration // 60} minutes in with only {armor or 'no'} armor. Having a rough time."
                })

        return observations

    def _check_quiet_moments(self, state: Dict) -> List[Dict]:
        """Detect extended quiet periods."""
        observations = []

        time_since_event = time.time() - self.last_event_time
        players = state.get('players', [])

        # Only comment on quiet if there are players and it's been quiet for 2+ min
        if len(players) > 0 and time_since_event > self.quiet_threshold:
            obs_id = f"quiet_{int(time.time() // 180)}"  # 3-min windows

            # Customize based on what players are doing
            dimensions = [p.get('dimension', 'overworld') for p in players]

            if 'end' in dimensions:
                prompt = "It's quiet... players are in the End. The tension is palpable."
            elif 'nether' in dimensions:
                prompt = "The nether is unusually calm. Something brewing?"
            else:
                prompt = "It's been quiet for a while. Everyone focused on gathering resources?"

            observations.append({
                'id': obs_id,
                'type': 'quiet_moment',
                'priority': 2,  # Low priority
                'prompt': prompt
            })

        return observations

    def _calculate_player_distances(self, players: List[Dict]) -> Dict[str, Dict]:
        """Calculate distances between all players."""
        distances = {}

        for player in players:
            name = player.get('username')
            x1, y1, z1 = player.get('x', 0), player.get('y', 0), player.get('z', 0)
            dim1 = player.get('dimension', 'overworld')

            min_dist = float('inf')
            nearest = None

            for other in players:
                other_name = other.get('username')
                if other_name == name:
                    continue

                # Only compare same dimension
                if other.get('dimension') != dim1:
                    continue

                x2, y2, z2 = other.get('x', 0), other.get('y', 0), other.get('z', 0)
                dist = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2 + (z2 - z1) ** 2)

                if dist < min_dist:
                    min_dist = dist
                    nearest = other_name

            distances[name] = {
                'distance': min_dist,
                'nearest': nearest
            }

        return distances
