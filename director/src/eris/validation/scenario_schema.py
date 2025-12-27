"""
Pydantic models for synthetic scenario definition and validation.

A scenario represents a synthetic Minecraft run with:
- Party composition (player roles)
- Sequence of events (advancements, damage, inventory changes, etc.)
- Validation against Minecraft's actual progression rules
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ScenarioMode(str, Enum):
    """How the scenario generates events."""

    SCRIPTED = "scripted"  # Events are pre-defined in the scenario
    EMERGENT = "emergent"  # Events emerge from tarot-driven player brains


class PlayerRole(str, Enum):
    """Common player archetypes in speedruns."""

    GATHERER = "gatherer"  # Mines resources, builds tools
    NETHER_RUNNER = "nether_runner"  # Handles nether fortress, blazes
    EXPLORER = "explorer"  # Finds structures, scouts
    BASTION_RUNNER = "bastion_runner"  # Loots bastions for pearls
    END_FIGHTER = "end_fighter"  # Handles endermen, dragon fight
    SUPPORT = "support"  # Flexible role, helps others
    SOLO = "solo"  # Single player run


class PartyPreset(str, Enum):
    """Pre-defined party compositions."""

    SPEED_TRIO = "speed_trio"  # 3 players: gatherer, nether_runner, explorer
    DUO_RUSH = "duo_rush"  # 2 players: split nether/overworld
    SOLO_HARDCORE = "solo_hardcore"  # 1 player
    QUAD_SQUAD = "quad_squad"  # 4 players: full coverage
    CHAOS_FIVE = "chaos_five"  # 5 players: chaos mode


# ==================== EVENT TYPES ====================


class AdvancementEvent(BaseModel):
    """Player earns a vanilla Minecraft advancement."""

    type: Literal["advancement"] = "advancement"
    player: str
    advancement: str = Field(
        description="Advancement key (e.g., 'minecraft:story/mine_stone')"
    )


class DamageEvent(BaseModel):
    """Player takes damage from a source."""

    type: Literal["damage"] = "damage"
    player: str
    source: str = Field(description="Damage source (e.g., 'blaze', 'lava', 'fall')")
    amount: int = Field(ge=1, le=20, description="Damage in half-hearts (1-20)")


class InventoryEvent(BaseModel):
    """Player inventory changes (add/remove items)."""

    type: Literal["inventory"] = "inventory"
    player: str
    action: Literal["add", "remove"]
    item: str = Field(description="Item ID (e.g., 'blaze_rod', 'diamond_pickaxe')")
    count: int = Field(ge=1, description="Number of items")


class DimensionChangeEvent(BaseModel):
    """Player changes dimension."""

    type: Literal["dimension"] = "dimension"
    player: str
    from_dim: str = Field(description="Source dimension (overworld/nether/the_end)")
    to_dim: str = Field(description="Target dimension (overworld/nether/the_end)")


class ChatEvent(BaseModel):
    """Player sends a chat message."""

    type: Literal["chat"] = "chat"
    player: str
    message: str


class DeathEvent(BaseModel):
    """Player dies (ends the run)."""

    type: Literal["death"] = "death"
    player: str
    cause: str = Field(description="Death cause (e.g., 'blaze', 'fell', 'void')")


class DragonKillEvent(BaseModel):
    """Dragon is killed (run victory)."""

    type: Literal["dragon_kill"] = "dragon_kill"
    player: str = Field(description="Player who got the killing blow")


class MobKillEvent(BaseModel):
    """Player kills a mob."""

    type: Literal["mob_kill"] = "mob_kill"
    player: str
    mob_type: str = Field(description="Mob type (e.g., 'blaze', 'enderman', 'zombie')")
    count: int = Field(default=1, ge=1, description="Number killed")


class StructureDiscoveryEvent(BaseModel):
    """Player discovers a structure."""

    type: Literal["structure"] = "structure"
    player: str
    structure: str = Field(
        description="Structure type (e.g., 'fortress', 'stronghold', 'bastion')"
    )


class HealthChangeEvent(BaseModel):
    """Player health changes (not damage - e.g., eating, regen)."""

    type: Literal["health"] = "health"
    player: str
    amount: int = Field(description="Health delta in half-hearts (negative or positive)")


# Union of all event types
Event = (
    AdvancementEvent
    | DamageEvent
    | InventoryEvent
    | DimensionChangeEvent
    | ChatEvent
    | DeathEvent
    | DragonKillEvent
    | MobKillEvent
    | StructureDiscoveryEvent
    | HealthChangeEvent
)


# ==================== SCENARIO DEFINITION ====================


class PlayerDefinition(BaseModel):
    """Define a player in the scenario."""

    role: PlayerRole
    starting_health: int = Field(default=20, ge=1, le=20, description="Starting health")
    starting_inventory: dict[str, int] = Field(
        default_factory=dict, description="item_id -> count"
    )


class ScenarioMetadata(BaseModel):
    """Metadata about the scenario."""

    name: str = Field(description="Human-readable scenario name")
    description: str = Field(default="", description="What this scenario tests")
    difficulty: Literal["easy", "medium", "hard", "extreme"] = Field(default="medium")
    tags: list[str] = Field(default_factory=list, description="Tags for categorization")
    seed: int | None = Field(default=None, description="Random seed for reproducibility")


class Scenario(BaseModel):
    """Complete synthetic scenario definition."""

    metadata: ScenarioMetadata
    party: dict[str, PlayerDefinition] | PartyPreset = Field(
        description="Player definitions OR preset name"
    )
    events: list[Event] = Field(
        default_factory=list, description="Ordered sequence of events (scripted mode)"
    )

    # Emergent mode settings
    mode: ScenarioMode = Field(
        default=ScenarioMode.SCRIPTED, description="Scripted or emergent event generation"
    )
    max_ticks: int = Field(
        default=1000, ge=1, le=10000, description="Max ticks for emergent scenarios"
    )
    initial_tarot: dict[str, dict[str, float]] = Field(
        default_factory=dict,
        description="Initial tarot weights per player: {player: {card: weight}}",
    )
    target_phase: Literal["early", "nether", "end", "dragon"] = Field(
        default="dragon", description="Target game phase for emergent scenarios"
    )

    @field_validator("events")
    @classmethod
    def validate_player_references(cls, events: list[Event], info) -> list[Event]:
        """Ensure all player references in events exist in party definition."""
        # Extract player names from party
        party_data = info.data.get("party")
        if party_data is None:
            return events

        # If party is a preset string, we'll validate at runtime
        if isinstance(party_data, str):
            return events

        # Extract player names from dict party definition
        player_names = set(party_data.keys())

        # Check each event references valid players
        for event in events:
            if hasattr(event, "player"):
                player = event.player
                if player not in player_names:
                    raise ValueError(
                        f"Event references unknown player '{player}'. "
                        f"Known players: {player_names}"
                    )

        return events

    def get_player_names(self) -> list[str]:
        """Extract player names from party definition."""
        if isinstance(self.party, str):
            # Preset - will be expanded at load time
            return []
        return list(self.party.keys())


# ==================== PARTY PRESETS ====================

PARTY_PRESETS: dict[PartyPreset, dict[str, PlayerDefinition]] = {
    PartyPreset.SPEED_TRIO: {
        "Alice": PlayerDefinition(role=PlayerRole.GATHERER),
        "Bob": PlayerDefinition(role=PlayerRole.NETHER_RUNNER),
        "Eve": PlayerDefinition(role=PlayerRole.EXPLORER),
    },
    PartyPreset.DUO_RUSH: {
        "Player1": PlayerDefinition(role=PlayerRole.GATHERER),
        "Player2": PlayerDefinition(role=PlayerRole.NETHER_RUNNER),
    },
    PartyPreset.SOLO_HARDCORE: {
        "Solo": PlayerDefinition(role=PlayerRole.SOLO),
    },
    PartyPreset.QUAD_SQUAD: {
        "Miner": PlayerDefinition(role=PlayerRole.GATHERER),
        "NetherRunner": PlayerDefinition(role=PlayerRole.NETHER_RUNNER),
        "BastionRunner": PlayerDefinition(role=PlayerRole.BASTION_RUNNER),
        "EndFighter": PlayerDefinition(role=PlayerRole.END_FIGHTER),
    },
    PartyPreset.CHAOS_FIVE: {
        "Alpha": PlayerDefinition(role=PlayerRole.GATHERER),
        "Beta": PlayerDefinition(role=PlayerRole.NETHER_RUNNER),
        "Gamma": PlayerDefinition(role=PlayerRole.EXPLORER),
        "Delta": PlayerDefinition(role=PlayerRole.BASTION_RUNNER),
        "Epsilon": PlayerDefinition(role=PlayerRole.SUPPORT),
    },
}
