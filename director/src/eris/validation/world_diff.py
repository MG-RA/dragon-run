"""
WorldDiff - Captures state changes from events and tool calls.

Used for telemetry, debugging, and Phase 4 scoring.
Each diff represents what changed in the world from a single action.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StateChange:
    """
    Represents a single state change.

    Examples:
        StateChange("health", 20.0, 12.0)
        StateChange("dimension", "overworld", "nether")
        StateChange("alive", True, False)
        StateChange("inventory.diamond", 0, 5)
    """

    field: str
    old_value: Any
    new_value: Any

    @property
    def delta(self) -> Any:
        """For numeric values, return the difference."""
        if isinstance(self.old_value, (int, float)) and isinstance(
            self.new_value, (int, float)
        ):
            return self.new_value - self.old_value
        return None

    def to_dict(self) -> dict:
        return {
            "field": self.field,
            "old": self.old_value,
            "new": self.new_value,
        }


@dataclass
class WorldDiff:
    """
    Captures all state changes from a single event or tool call.

    Used for:
    - Telemetry and logging
    - Phase 4 scoring (did dragon die? did players survive?)
    - Debugging (what exactly changed?)
    - Replaying/rewinding state (future)
    """

    # What triggered this diff
    source_type: str  # "event" or "tool_call"
    source_name: str  # e.g., "damage", "spawn_mob", "advancement"

    # Who was affected
    player: str | None = None

    # All state changes
    changes: list[StateChange] = field(default_factory=list)

    # Metadata
    timestamp: float | None = None
    sequence_number: int = 0

    # Flags for important state transitions
    caused_death: bool = False
    caused_victory: bool = False
    triggered_phase_change: bool = False
    old_phase: str | None = None
    new_phase: str | None = None

    def add_change(self, field: str, old_value: Any, new_value: Any) -> None:
        """Add a state change to this diff."""
        if old_value != new_value:  # Only track actual changes
            self.changes.append(StateChange(field, old_value, new_value))

    def add_player_change(
        self, player: str, field: str, old_value: Any, new_value: Any
    ) -> None:
        """Add a player-specific state change."""
        if old_value != new_value:
            self.changes.append(StateChange(f"{player}.{field}", old_value, new_value))

    @property
    def has_changes(self) -> bool:
        """Check if any state actually changed."""
        return len(self.changes) > 0

    @property
    def is_significant(self) -> bool:
        """Check if this diff represents a significant event."""
        return self.caused_death or self.caused_victory or self.triggered_phase_change

    def get_health_delta(self, player: str) -> float | None:
        """Get the health change for a specific player."""
        for change in self.changes:
            if change.field == f"{player}.health":
                return change.delta
        return None

    def to_dict(self) -> dict:
        """Convert to serializable dict for JSON output."""
        result = {
            "source_type": self.source_type,
            "source_name": self.source_name,
            "player": self.player,
            "changes": [c.to_dict() for c in self.changes],
            "sequence_number": self.sequence_number,
        }

        if self.timestamp is not None:
            result["timestamp"] = self.timestamp

        if self.caused_death:
            result["caused_death"] = True
        if self.caused_victory:
            result["caused_victory"] = True
        if self.triggered_phase_change:
            result["phase_change"] = {
                "from": self.old_phase,
                "to": self.new_phase,
            }

        return result

    def __repr__(self) -> str:
        parts = [f"WorldDiff({self.source_type}:{self.source_name}"]
        if self.player:
            parts.append(f" player={self.player}")
        if self.changes:
            parts.append(f" changes={len(self.changes)}")
        if self.caused_death:
            parts.append(" DEATH")
        if self.caused_victory:
            parts.append(" VICTORY")
        parts.append(")")
        return "".join(parts)


@dataclass
class RunTrace:
    """
    Complete trace of a run for Phase 4 scoring.

    Collects all WorldDiffs from a scenario execution.
    """

    scenario_name: str
    diffs: list[WorldDiff] = field(default_factory=list)

    # Summary stats
    total_events: int = 0
    total_tool_calls: int = 0
    deaths: list[str] = field(default_factory=list)  # player names
    victory: bool = False
    final_phase: str = "normal"

    def add_diff(self, diff: WorldDiff) -> None:
        """Add a diff to the trace."""
        diff.sequence_number = len(self.diffs)
        self.diffs.append(diff)

        if diff.source_type == "event":
            self.total_events += 1
        else:
            self.total_tool_calls += 1

        if diff.caused_death and diff.player:
            self.deaths.append(diff.player)
        if diff.caused_victory:
            self.victory = True
        if diff.new_phase:
            self.final_phase = diff.new_phase

    def to_dict(self) -> dict:
        """Convert to serializable dict for JSON output."""
        return {
            "scenario_name": self.scenario_name,
            "total_events": self.total_events,
            "total_tool_calls": self.total_tool_calls,
            "deaths": self.deaths,
            "victory": self.victory,
            "final_phase": self.final_phase,
            "diffs": [d.to_dict() for d in self.diffs],
        }
