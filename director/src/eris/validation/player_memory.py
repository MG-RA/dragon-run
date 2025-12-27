"""
Player memory system - what players remember about others.

This tracks grudges, trust, debts, and relationships that influence
behavior in emergent scenarios. Memory decays over time but significant
events leave lasting marks.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PlayerMemory:
    """
    What a player remembers about their interactions with others.

    This isn't objective truth - it's subjective perception.
    A player might remember being "abandoned" when the other
    player was actually fighting for their life.
    """

    # Harm tracking
    damage_received_from: dict[str, int] = field(default_factory=dict)  # Total damage
    kill_attempts_by: dict[str, int] = field(default_factory=dict)  # Near-death moments

    # Resource interactions
    loot_taken_by: dict[str, int] = field(default_factory=dict)  # Items "stolen"
    loot_given_by: dict[str, int] = field(default_factory=dict)  # Items received

    # Social interactions
    rescues_by: dict[str, int] = field(default_factory=dict)  # Times saved
    abandonments_by: dict[str, int] = field(default_factory=dict)  # Left to die
    betrayals_by: dict[str, int] = field(default_factory=dict)  # Explicit betrayals

    # Proximity tracking
    time_spent_with: dict[str, int] = field(default_factory=dict)  # Ticks together

    # Eris-specific memories
    eris_harm_count: int = 0  # Times Eris hurt this player
    eris_help_count: int = 0  # Times Eris helped this player
    eris_last_interaction: str | None = None  # Last thing Eris did

    def record_damage(self, from_player: str, amount: int) -> None:
        """Record damage received from another player."""
        self.damage_received_from[from_player] = (
            self.damage_received_from.get(from_player, 0) + amount
        )

    def record_near_death(self, from_player: str) -> None:
        """Record a near-death experience caused by another player."""
        self.kill_attempts_by[from_player] = (
            self.kill_attempts_by.get(from_player, 0) + 1
        )

    def record_loot_taken(self, by_player: str, value: int = 1) -> None:
        """Record items taken by another player."""
        self.loot_taken_by[by_player] = (
            self.loot_taken_by.get(by_player, 0) + value
        )

    def record_loot_given(self, by_player: str, value: int = 1) -> None:
        """Record items received from another player."""
        self.loot_given_by[by_player] = (
            self.loot_given_by.get(by_player, 0) + value
        )

    def record_rescue(self, by_player: str) -> None:
        """Record being saved by another player."""
        self.rescues_by[by_player] = self.rescues_by.get(by_player, 0) + 1

    def record_abandonment(self, by_player: str) -> None:
        """Record being left to die by another player."""
        self.abandonments_by[by_player] = (
            self.abandonments_by.get(by_player, 0) + 1
        )

    def record_betrayal(self, by_player: str) -> None:
        """Record an explicit betrayal (stealing, sabotage, etc)."""
        self.betrayals_by[by_player] = self.betrayals_by.get(by_player, 0) + 1

    def record_proximity(self, with_player: str, ticks: int = 1) -> None:
        """Record time spent near another player."""
        self.time_spent_with[with_player] = (
            self.time_spent_with.get(with_player, 0) + ticks
        )

    def record_eris_interaction(self, was_helpful: bool, description: str) -> None:
        """Record an interaction with Eris."""
        if was_helpful:
            self.eris_help_count += 1
        else:
            self.eris_harm_count += 1
        self.eris_last_interaction = description

    def get_trust(self, player: str) -> float:
        """
        Calculate trust score for another player.

        Returns a value from -1 (enemy) to 1 (ally).
        0 means neutral/unknown.
        """
        # Positive factors
        rescues = self.rescues_by.get(player, 0) * 10
        gifts = self.loot_given_by.get(player, 0) * 2
        time_together = min(self.time_spent_with.get(player, 0) / 100, 5)  # Cap at 5

        positive = rescues + gifts + time_together

        # Negative factors
        damage = self.damage_received_from.get(player, 0) / 5  # Scaled down
        near_deaths = self.kill_attempts_by.get(player, 0) * 15
        stolen = self.loot_taken_by.get(player, 0) * 3
        abandoned = self.abandonments_by.get(player, 0) * 8
        betrayed = self.betrayals_by.get(player, 0) * 20

        negative = damage + near_deaths + stolen + abandoned + betrayed

        # Calculate normalized trust
        total = positive + negative
        if total == 0:
            return 0.0

        raw_trust = (positive - negative) / total
        return max(-1.0, min(1.0, raw_trust))

    def get_eris_trust(self) -> float:
        """
        Calculate trust toward Eris.

        Returns -1 (hostile) to 1 (trusting).
        """
        total = self.eris_help_count + self.eris_harm_count
        if total == 0:
            return 0.0
        return (self.eris_help_count - self.eris_harm_count) / total

    def get_closest_ally(self) -> str | None:
        """Get the player this player trusts most."""
        all_players = set(self.rescues_by.keys()) | set(self.loot_given_by.keys()) | set(self.time_spent_with.keys())
        if not all_players:
            return None
        return max(all_players, key=lambda p: self.get_trust(p))

    def get_worst_enemy(self) -> str | None:
        """Get the player this player trusts least."""
        all_players = set(self.damage_received_from.keys()) | set(self.betrayals_by.keys()) | set(self.abandonments_by.keys())
        if not all_players:
            return None
        return min(all_players, key=lambda p: self.get_trust(p))

    def decay(self, factor: float = 0.95) -> None:
        """
        Decay all memories slightly over time.

        Significant events (rescues, betrayals) decay slower than
        minor ones (small damage, proximity).
        """
        # Fast decay for minor interactions
        for player in list(self.damage_received_from.keys()):
            self.damage_received_from[player] = int(
                self.damage_received_from[player] * factor
            )
            if self.damage_received_from[player] <= 0:
                del self.damage_received_from[player]

        for player in list(self.loot_taken_by.keys()):
            self.loot_taken_by[player] = int(self.loot_taken_by[player] * factor)
            if self.loot_taken_by[player] <= 0:
                del self.loot_taken_by[player]

        for player in list(self.loot_given_by.keys()):
            self.loot_given_by[player] = int(self.loot_given_by[player] * factor)
            if self.loot_given_by[player] <= 0:
                del self.loot_given_by[player]

        # Slower decay for significant events (rescues, betrayals persist)
        slow_factor = (factor + 1) / 2  # e.g., 0.95 -> 0.975

        for player in list(self.rescues_by.keys()):
            self.rescues_by[player] = int(self.rescues_by[player] * slow_factor)
            if self.rescues_by[player] <= 0:
                del self.rescues_by[player]

        # Betrayals decay slowest
        for player in list(self.betrayals_by.keys()):
            self.betrayals_by[player] = int(self.betrayals_by[player] * slow_factor)
            if self.betrayals_by[player] <= 0:
                del self.betrayals_by[player]

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging/storage."""
        return {
            "damage_from": dict(self.damage_received_from),
            "loot_taken": dict(self.loot_taken_by),
            "loot_given": dict(self.loot_given_by),
            "rescues": dict(self.rescues_by),
            "abandonments": dict(self.abandonments_by),
            "betrayals": dict(self.betrayals_by),
            "time_with": dict(self.time_spent_with),
            "eris_harm": self.eris_harm_count,
            "eris_help": self.eris_help_count,
        }

    def get_relationship_summary(self, player: str) -> str:
        """Get a human-readable summary of relationship with a player."""
        trust = self.get_trust(player)

        if trust > 0.7:
            return f"deeply trusts {player}"
        elif trust > 0.3:
            return f"trusts {player}"
        elif trust > -0.3:
            return f"neutral toward {player}"
        elif trust > -0.7:
            return f"distrusts {player}"
        else:
            return f"hates {player}"
