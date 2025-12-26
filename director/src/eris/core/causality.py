"""Track entities and effects caused by Eris for protection logic."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Set, Optional, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class ErisIntervention:
    """Record of an Eris intervention."""
    target_player: str
    intervention_type: str  # "mob", "tnt", "effect", "damage", "falling_block", "lightning"
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


class ErisCausalityTracker:
    """
    Track what Eris has done to each player.
    Used to determine if protection/respawn should be offered.
    """

    def __init__(self, expiry_minutes: int = 5):
        self.expiry = timedelta(minutes=expiry_minutes)
        # player_name -> list of interventions
        self.interventions: Dict[str, list[ErisIntervention]] = defaultdict(list)
        # Track protection cooldowns (player -> datetime when cooldown expires)
        self.protection_cooldowns: Dict[str, datetime] = {}
        # Track respawn uses this run
        self.respawns_used: int = 0
        self.max_respawns_per_run: int = 2

    def record_intervention(
        self,
        player: str,
        intervention_type: str,
        **metadata
    ) -> None:
        """Record that Eris did something to a player."""
        intervention = ErisIntervention(
            target_player=player,
            intervention_type=intervention_type,
            metadata=metadata
        )
        self.interventions[player].append(intervention)
        logger.info(f"Recorded Eris intervention: {intervention_type} -> {player}")
        self._cleanup()

    def has_active_intervention(self, player: str) -> bool:
        """Check if player has any recent Eris interventions."""
        self._cleanup()
        return bool(self.interventions.get(player))

    def get_recent_interventions(self, player: str) -> list[ErisIntervention]:
        """Get all recent interventions for a player."""
        self._cleanup()
        return self.interventions.get(player, [])

    def get_intervention_types(self, player: str) -> Set[str]:
        """Get the types of recent interventions for a player."""
        interventions = self.get_recent_interventions(player)
        return {i.intervention_type for i in interventions}

    def can_protect(self, player: str) -> bool:
        """Check if protection is available for player."""
        # Must have active intervention
        if not self.has_active_intervention(player):
            logger.debug(f"Cannot protect {player}: no active intervention")
            return False
        # Check cooldown (30 seconds between protections per player)
        cooldown = self.protection_cooldowns.get(player)
        if cooldown and datetime.now() < cooldown:
            logger.debug(f"Cannot protect {player}: cooldown active until {cooldown}")
            return False
        return True

    def use_protection(self, player: str) -> None:
        """Mark that protection was used for a player."""
        self.protection_cooldowns[player] = datetime.now() + timedelta(seconds=30)
        logger.info(f"Protection used for {player}, cooldown until {self.protection_cooldowns[player]}")

    def can_respawn(self) -> bool:
        """Check if respawn override is available."""
        can = self.respawns_used < self.max_respawns_per_run
        logger.debug(f"Can respawn: {can} ({self.respawns_used}/{self.max_respawns_per_run})")
        return can

    def use_respawn(self) -> None:
        """Mark that respawn was used."""
        self.respawns_used += 1
        logger.info(f"Respawn override used ({self.respawns_used}/{self.max_respawns_per_run})")

    def get_remaining_respawns(self) -> int:
        """Get remaining respawns this run."""
        return self.max_respawns_per_run - self.respawns_used

    def reset_run(self) -> None:
        """Reset tracking for new run."""
        self.interventions.clear()
        self.protection_cooldowns.clear()
        self.respawns_used = 0
        logger.info("ErisCausalityTracker reset for new run")

    def _cleanup(self) -> None:
        """Remove expired interventions."""
        now = datetime.now()
        for player in list(self.interventions.keys()):
            self.interventions[player] = [
                i for i in self.interventions[player]
                if now - i.timestamp < self.expiry
            ]
            if not self.interventions[player]:
                del self.interventions[player]


# Global instance for use across the application
_tracker: Optional[ErisCausalityTracker] = None


def get_causality_tracker() -> ErisCausalityTracker:
    """Get or create the global causality tracker."""
    global _tracker
    if _tracker is None:
        _tracker = ErisCausalityTracker()
    return _tracker


def reset_causality_tracker() -> None:
    """Reset the global causality tracker for a new run."""
    global _tracker
    if _tracker is not None:
        _tracker.reset_run()
    else:
        _tracker = ErisCausalityTracker()
