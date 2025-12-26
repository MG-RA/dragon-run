"""Fear and Chaos management for Eris Director - v1.1.

This module manages in-memory tension state that resets per run:
- Player fear levels (0-100 per player)
- Player chaos contribution (per player)
- Global chaos level (0-100)

Fear and chaos influence:
- Mask selection probabilities
- Decision escalation caps
- Protection likelihood
- Eris's overall behavior intensity
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, List

logger = logging.getLogger("eris.tension")


# === Fear Triggers ===
# How much fear changes based on events

FEAR_TRIGGERS: Dict[str, int] = {
    # Eris-caused dangers
    "eris_close_call": 15,
    "eris_spawned_mob": 5,       # Per mob spawned near player
    "eris_tnt_near": 20,
    "eris_lightning_near": 10,
    "eris_falling_block": 8,
    "eris_effect_harmful": 5,
    "eris_damage": 12,

    # External dangers
    "player_damaged": 3,
    "player_damaged_close_call": 10,
    "teammate_death": 25,
    "boss_encounter": 15,

    # Relief (negative = fear reduction)
    "eris_protection_used": -10,
    "eris_heal": -8,
    "eris_gift": -5,
    "dimension_arrived_safely": -3,
    "achievement_positive": -2,

    # Time-based
    "long_silence": -5,  # Eris hasn't acted in a while
}

# === Chaos Triggers ===
# How much global chaos changes based on events

CHAOS_TRIGGERS: Dict[str, int] = {
    # Major events
    "player_death": 30,
    "dragon_killed": -50,  # Victory reduces chaos
    "run_started": 10,
    "run_ended": -20,

    # Eris interventions
    "eris_intervention": 5,      # Any tool use
    "eris_mob_spawn": 3,         # Per mob
    "eris_tnt": 15,
    "eris_lightning": 8,
    "eris_falling_block": 5,
    "eris_damage": 10,
    "eris_protection": -5,       # Protection reduces chaos slightly

    # Progression
    "dimension_change": 5,
    "boss_killed": 10,
    "structure_discovered": 3,

    # Time-based
    "idle_chaos_decay": -2,      # Per minute of calm
}


class TensionManager:
    """
    Manages fear and chaos state for the current run.
    All state is in-memory and resets when the run ends.
    """

    def __init__(self):
        self.player_fear: Dict[str, int] = {}        # username -> 0-100
        self.player_chaos: Dict[str, int] = {}       # username -> contribution
        self.global_chaos: int = 0                    # 0-100
        self.last_update: datetime = datetime.now()
        self.last_decay: datetime = datetime.now()

        # Peak tracking for analytics
        self.peak_chaos: int = 0
        self.peak_fear: Dict[str, int] = {}

        logger.info("TensionManager initialized")

    def reset_for_new_run(self):
        """Reset all tension state for a new run."""
        self.player_fear.clear()
        self.player_chaos.clear()
        self.global_chaos = 0
        self.last_update = datetime.now()
        self.last_decay = datetime.now()
        self.peak_chaos = 0
        self.peak_fear.clear()
        logger.info("TensionManager reset for new run")

    # === Fear Management ===

    def get_player_fear(self, player: str) -> int:
        """Get current fear level for a player (0-100)."""
        return self.player_fear.get(player, 0)

    def apply_fear_delta(self, player: str, delta: int, reason: str = "") -> int:
        """
        Apply a fear change to a player.
        Returns the new fear level (clamped 0-100).
        """
        current = self.player_fear.get(player, 0)
        new_fear = max(0, min(100, current + delta))
        self.player_fear[player] = new_fear

        # Track peak
        if new_fear > self.peak_fear.get(player, 0):
            self.peak_fear[player] = new_fear

        if delta != 0:
            logger.debug(f"😨 {player} fear: {current} -> {new_fear} ({'+' if delta > 0 else ''}{delta}) [{reason}]")

        self.last_update = datetime.now()
        return new_fear

    def apply_fear_trigger(self, player: str, trigger: str) -> int:
        """Apply a fear trigger by name. Returns new fear level."""
        delta = FEAR_TRIGGERS.get(trigger, 0)
        if delta != 0:
            return self.apply_fear_delta(player, delta, reason=trigger)
        return self.get_player_fear(player)

    def decay_fear(self, minutes: float = 1.0):
        """
        Decay fear for all players over time.
        Called periodically during idle periods.
        """
        decay_amount = int(2 * minutes)  # 2 fear per minute
        if decay_amount <= 0:
            return

        for player in list(self.player_fear.keys()):
            current = self.player_fear[player]
            if current > 0:
                new_fear = max(0, current - decay_amount)
                self.player_fear[player] = new_fear
                if new_fear != current:
                    logger.debug(f"😌 {player} fear decayed: {current} -> {new_fear}")

        self.last_decay = datetime.now()

    def get_all_fear(self) -> Dict[str, int]:
        """Get fear levels for all players."""
        return self.player_fear.copy()

    # === Chaos Management ===

    def get_global_chaos(self) -> int:
        """Get current global chaos level (0-100)."""
        return self.global_chaos

    def apply_chaos_delta(self, delta: int, reason: str = "") -> int:
        """
        Apply a chaos change to the global level.
        Returns the new chaos level (clamped 0-100).
        """
        current = self.global_chaos
        new_chaos = max(0, min(100, current + delta))
        self.global_chaos = new_chaos

        # Track peak
        if new_chaos > self.peak_chaos:
            self.peak_chaos = new_chaos

        if delta != 0:
            logger.info(f"🌀 Global chaos: {current} -> {new_chaos} ({'+' if delta > 0 else ''}{delta}) [{reason}]")

        self.last_update = datetime.now()
        return new_chaos

    def apply_chaos_trigger(self, trigger: str, count: int = 1) -> int:
        """Apply a chaos trigger by name. Returns new chaos level."""
        delta = CHAOS_TRIGGERS.get(trigger, 0) * count
        if delta != 0:
            return self.apply_chaos_delta(delta, reason=f"{trigger}x{count}" if count > 1 else trigger)
        return self.global_chaos

    def add_player_chaos_contribution(self, player: str, amount: int):
        """Track chaos contribution from a specific player."""
        current = self.player_chaos.get(player, 0)
        self.player_chaos[player] = current + amount

    def decay_chaos(self, minutes: float = 1.0):
        """
        Decay global chaos over time.
        Called during idle periods.
        """
        decay_amount = int(2 * minutes)  # 2 chaos per minute
        if decay_amount > 0 and self.global_chaos > 0:
            new_chaos = max(0, self.global_chaos - decay_amount)
            if new_chaos != self.global_chaos:
                logger.debug(f"🌀 Chaos decayed: {self.global_chaos} -> {new_chaos}")
                self.global_chaos = new_chaos

        self.last_decay = datetime.now()

    # === Combined Updates ===

    def process_event(self, event_type: str, player: Optional[str] = None, data: Optional[Dict] = None):
        """
        Process an event and update tension state accordingly.
        Called by event_processor when events come in.
        """
        data = data or {}

        # Map event types to triggers
        event_to_fear_trigger = {
            "eris_close_call": "eris_close_call",
            "player_damaged": "player_damaged",
            "eris_protection_used": "eris_protection_used",
            "eris_rescue_used": "eris_protection_used",
            "achievement_unlocked": "achievement_positive" if data.get("category") != "negative" else None,
        }

        event_to_chaos_trigger = {
            "player_death": "player_death",
            "dragon_killed": "dragon_killed",
            "run_starting": "run_started",
            "run_ended": "run_ended",
            "dimension_change": "dimension_change",
            "boss_killed": "boss_killed",
            "structure_discovered": "structure_discovered",
        }

        # Apply fear trigger if applicable
        if player:
            fear_trigger = event_to_fear_trigger.get(event_type)
            if fear_trigger:
                self.apply_fear_trigger(player, fear_trigger)

            # Special case: close call with low health
            if event_type == "player_damaged" and data.get("isCloseCall"):
                self.apply_fear_trigger(player, "player_damaged_close_call")

        # Apply chaos trigger if applicable
        chaos_trigger = event_to_chaos_trigger.get(event_type)
        if chaos_trigger:
            self.apply_chaos_trigger(chaos_trigger)

    def process_eris_action(self, tool_name: str, player: Optional[str] = None, args: Optional[Dict] = None):
        """
        Process an Eris action and update tension state.
        Called when Eris uses a tool.
        """
        args = args or {}

        # General intervention adds chaos
        self.apply_chaos_trigger("eris_intervention")

        # Tool-specific effects
        if tool_name == "spawn_mob":
            count = args.get("count", 1)
            self.apply_chaos_trigger("eris_mob_spawn", count)
            if player:
                for _ in range(count):
                    self.apply_fear_trigger(player, "eris_spawned_mob")

        elif tool_name == "spawn_tnt":
            count = args.get("count", 1)
            self.apply_chaos_trigger("eris_tnt", count)
            if player:
                self.apply_fear_trigger(player, "eris_tnt_near")

        elif tool_name == "strike_lightning":
            self.apply_chaos_trigger("eris_lightning")
            if player:
                self.apply_fear_trigger(player, "eris_lightning_near")

        elif tool_name == "spawn_falling_block":
            count = args.get("count", 1)
            self.apply_chaos_trigger("eris_falling_block", count)
            if player:
                self.apply_fear_trigger(player, "eris_falling_block")

        elif tool_name == "damage_player":
            self.apply_chaos_trigger("eris_damage")
            if player:
                self.apply_fear_trigger(player, "eris_damage")

        elif tool_name == "apply_effect":
            effect = args.get("effect", "")
            if effect in ("poison", "wither", "weakness", "slowness", "blindness"):
                if player:
                    self.apply_fear_trigger(player, "eris_effect_harmful")

        elif tool_name in ("protect_player", "rescue_teleport"):
            self.apply_chaos_trigger("eris_protection")
            if player:
                self.apply_fear_trigger(player, "eris_protection_used")

        elif tool_name == "heal_player":
            if player:
                self.apply_fear_trigger(player, "eris_heal")

        elif tool_name == "give_item":
            if player:
                self.apply_fear_trigger(player, "eris_gift")

    # === Query Methods ===

    def get_state_for_graph(self) -> Dict:
        """Get tension state to merge into graph state."""
        return {
            "player_fear": self.player_fear.copy(),
            "player_chaos": self.player_chaos.copy(),
            "global_chaos": self.global_chaos,
        }

    def get_analytics(self) -> Dict:
        """Get analytics data for run end."""
        return {
            "peak_chaos": self.peak_chaos,
            "final_chaos": self.global_chaos,
            "peak_fear": self.peak_fear.copy(),
            "total_player_chaos": self.player_chaos.copy(),
        }

    def should_back_off(self, player: Optional[str] = None) -> bool:
        """
        Check if Eris should back off due to high tension.
        Used by decision_node for mercy/restraint.
        """
        if self.global_chaos > 80:
            return True
        if player and self.get_player_fear(player) > 70:
            return True
        return False

    def get_max_safe_escalation(self) -> int:
        """
        Get the maximum safe escalation level based on current chaos.
        Higher chaos = lower safe escalation.
        """
        # At chaos 0: max 100
        # At chaos 50: max 75
        # At chaos 80: max 60
        # At chaos 100: max 50
        return max(50, 100 - int(self.global_chaos * 0.5))


# === Fracture System (v1.3) ===
# Fracture = global_chaos + total_karma + max_player_fear
# Tracks overall system stress leading to phase transitions and apocalypse

class FractureTracker:
    """
    Tracks fracture level and phase transitions.
    Fracture is a composite metric: chaos + karma + max fear.
    """

    # Phase thresholds from spec
    PHASE_THRESHOLDS = {
        50: "rising",
        80: "critical",
        120: "locked",
        150: "apocalypse",
    }

    def __init__(self, tension_manager: TensionManager):
        self.tension_manager = tension_manager
        self.total_karma: int = 0  # Sum of all karma across all players
        self.apocalypse_triggered: bool = False
        self._last_fracture: int = 0
        self._last_phase: str = "normal"

    def reset_for_new_run(self):
        """Reset fracture state for a new run."""
        self.total_karma = 0
        self.apocalypse_triggered = False
        self._last_fracture = 0
        self._last_phase = "normal"
        logger.info("FractureTracker reset for new run")

    def update_total_karma(self, karma_sum: int):
        """Update total karma from player_karmas state."""
        self.total_karma = karma_sum

    def calculate_fracture(self) -> int:
        """
        Calculate current fracture level.
        fracture = global_chaos + total_karma + max_player_fear
        """
        global_chaos = self.tension_manager.get_global_chaos()
        max_fear = max(self.tension_manager.player_fear.values()) if self.tension_manager.player_fear else 0

        fracture = global_chaos + self.total_karma + max_fear
        return fracture

    def get_phase(self, fracture: Optional[int] = None) -> str:
        """
        Get current phase based on fracture level.

        Returns: "normal", "rising", "critical", "locked", or "apocalypse"
        """
        if fracture is None:
            fracture = self.calculate_fracture()

        if fracture >= 150:
            return "apocalypse"
        elif fracture >= 120:
            return "locked"
        elif fracture >= 80:
            return "critical"
        elif fracture >= 50:
            return "rising"
        return "normal"

    def check_phase_transition(self) -> Optional[str]:
        """
        Check if phase has changed since last check.
        Returns new phase name if transition occurred, None otherwise.
        """
        current_fracture = self.calculate_fracture()
        current_phase = self.get_phase(current_fracture)

        if current_phase != self._last_phase:
            old_phase = self._last_phase
            self._last_phase = current_phase
            self._last_fracture = current_fracture
            logger.info(f"🔥 PHASE TRANSITION: {old_phase} → {current_phase} (fracture={current_fracture})")
            return current_phase

        self._last_fracture = current_fracture
        return None

    def should_trigger_apocalypse(self) -> bool:
        """
        Check if apocalypse should be triggered.
        Returns True if fracture >= 200 and apocalypse not yet triggered.
        """
        if self.apocalypse_triggered:
            return False

        fracture = self.calculate_fracture()
        return fracture >= 200

    def mark_apocalypse_triggered(self):
        """Mark apocalypse as triggered for this run."""
        self.apocalypse_triggered = True
        logger.warning("🍎 APOCALYPSE TRIGGERED - THE APPLE HAS FALLEN")

    def get_state_for_graph(self) -> Dict:
        """Get fracture state to merge into graph state."""
        fracture = self.calculate_fracture()
        return {
            "fracture": fracture,
            "phase": self.get_phase(fracture),
            "apocalypse_triggered": self.apocalypse_triggered,
        }

    def get_analytics(self) -> Dict:
        """Get fracture analytics for run end."""
        return {
            "final_fracture": self.calculate_fracture(),
            "final_phase": self.get_phase(),
            "apocalypse_triggered": self.apocalypse_triggered,
            "total_karma": self.total_karma,
        }


# === Global Instances ===
# Singleton pattern for easy access across the codebase

_tension_manager: Optional[TensionManager] = None
_fracture_tracker: Optional[FractureTracker] = None


def get_tension_manager() -> TensionManager:
    """Get the global TensionManager instance."""
    global _tension_manager
    if _tension_manager is None:
        _tension_manager = TensionManager()
    return _tension_manager


def get_fracture_tracker() -> FractureTracker:
    """Get the global FractureTracker instance."""
    global _fracture_tracker, _tension_manager
    if _fracture_tracker is None:
        if _tension_manager is None:
            _tension_manager = TensionManager()
        _fracture_tracker = FractureTracker(_tension_manager)
    return _fracture_tracker


def reset_tension_manager():
    """Reset the global TensionManager and FractureTracker for a new run."""
    global _tension_manager, _fracture_tracker
    if _tension_manager is not None:
        _tension_manager.reset_for_new_run()
    else:
        _tension_manager = TensionManager()

    if _fracture_tracker is not None:
        _fracture_tracker.reset_for_new_run()
    else:
        _fracture_tracker = FractureTracker(_tension_manager)
