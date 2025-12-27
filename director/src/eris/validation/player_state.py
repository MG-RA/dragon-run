"""
Player state tracking for SyntheticWorld simulation.

Provides dataclasses for tracking individual player state and spawned mobs
that mirror the Java PlayerStateSnapshot and game entities.
"""

from dataclasses import dataclass, field
from enum import Enum

from .scenario_schema import PlayerRole


class Dimension(str, Enum):
    """Minecraft dimensions."""

    OVERWORLD = "overworld"
    NETHER = "nether"
    THE_END = "the_end"


@dataclass
class PlayerState:
    """
    Tracks the state of a single player in the synthetic world.

    Mirrors the Java PlayerStateSnapshot with additional fields
    for simulation tracking.
    """

    # Identity
    name: str
    role: PlayerRole

    # Health (mirrors PlayerStateSnapshot)
    health: float = 20.0
    max_health: float = 20.0
    food_level: int = 20
    saturation: float = 5.0

    # Location (mirrors PlayerStateSnapshot)
    dimension: Dimension = Dimension.OVERWORLD
    x: float = 0.0
    y: float = 64.0
    z: float = 0.0

    # Status
    alive: bool = True
    game_mode: str = "SURVIVAL"

    # Progress tracking
    advancements: set[str] = field(default_factory=set)
    inventory: dict[str, int] = field(default_factory=dict)

    # Run statistics
    mob_kills: int = 0
    damage_taken: float = 0.0
    entered_nether: bool = False
    entered_end: bool = False

    # Eris tracking
    fear: float = 0.0
    aura: int = 50  # reputation/karma (0-100)

    # Computed properties (mirrors PlayerStateSnapshot convenience fields)
    @property
    def diamond_count(self) -> int:
        return self.inventory.get("diamond", 0)

    @property
    def ender_pearl_count(self) -> int:
        return self.inventory.get("ender_pearl", 0)

    @property
    def blaze_rod_count(self) -> int:
        return self.inventory.get("blaze_rod", 0)

    @property
    def has_elytra(self) -> bool:
        return self.inventory.get("elytra", 0) > 0

    @property
    def armor_tier(self) -> str:
        """Determine armor tier from inventory."""
        # Check in order of best to worst
        armor_pieces = ["helmet", "chestplate", "leggings", "boots"]
        tiers = ["netherite", "diamond", "iron", "chainmail", "gold", "leather"]

        for tier in tiers:
            for piece in armor_pieces:
                if self.inventory.get(f"{tier}_{piece}", 0) > 0:
                    return tier
        return "none"

    def take_damage(self, amount: float) -> bool:
        """
        Apply damage to player. Returns True if player died.

        Args:
            amount: Damage in half-hearts

        Returns:
            True if this damage killed the player
        """
        self.damage_taken += amount
        self.health = max(0, self.health - amount)

        if self.health <= 0:
            self.alive = False
            return True
        return False

    def heal(self, amount: float) -> float:
        """
        Heal the player. Returns actual amount healed.

        Args:
            amount: Healing in half-hearts

        Returns:
            Actual amount healed (may be less if at max health)
        """
        old_health = self.health
        self.health = min(self.max_health, self.health + amount)
        return self.health - old_health

    def add_item(self, item: str, count: int = 1) -> None:
        """Add items to inventory."""
        self.inventory[item] = self.inventory.get(item, 0) + count

    def remove_item(self, item: str, count: int = 1) -> bool:
        """
        Remove items from inventory. Returns True if successful.

        Args:
            item: Item ID
            count: Number to remove

        Returns:
            True if items were removed, False if not enough
        """
        current = self.inventory.get(item, 0)
        if current < count:
            return False

        new_count = current - count
        if new_count <= 0:
            del self.inventory[item]
        else:
            self.inventory[item] = new_count
        return True

    def change_dimension(self, dimension: Dimension) -> None:
        """Change player's dimension and update tracking flags."""
        self.dimension = dimension

        if dimension == Dimension.NETHER:
            self.entered_nether = True
        elif dimension == Dimension.THE_END:
            self.entered_end = True

    def add_advancement(self, advancement: str) -> bool:
        """
        Add an advancement. Returns True if newly earned.

        Args:
            advancement: Advancement key (e.g., 'minecraft:story/mine_stone')

        Returns:
            True if this is a new advancement, False if already had it
        """
        if advancement in self.advancements:
            return False
        self.advancements.add(advancement)
        return True

    def to_snapshot(self) -> dict:
        """
        Convert to format matching Java PlayerStateSnapshot.

        Returns dict compatible with what WebSocket sends to Python.
        """
        return {
            "username": self.name,
            "health": self.health,
            "maxHealth": self.max_health,
            "foodLevel": self.food_level,
            "saturation": self.saturation,
            "dimension": self.dimension.value,
            "location": {"x": round(self.x, 1), "y": round(self.y, 1), "z": round(self.z, 1)},
            "gameMode": self.game_mode,
            "diamondCount": self.diamond_count,
            "enderPearlCount": self.ender_pearl_count,
            "hasElytra": self.has_elytra,
            "armorTier": self.armor_tier,
            "mobKills": self.mob_kills,
            "aliveSeconds": 0,  # Would need run timer
            "enteredNether": self.entered_nether,
            "enteredEnd": self.entered_end,
            "aura": self.aura,
        }


@dataclass
class SpawnedMob:
    """
    Tracks a mob spawned in the synthetic world.

    Used for tracking Eris-spawned mobs and their potential effects.
    """

    mob_type: str
    near_player: str
    count: int = 1
    spawned_by_eris: bool = False

    # Optional tracking
    spawn_time: float | None = None  # timestamp
    alive_count: int = field(init=False)

    def __post_init__(self):
        self.alive_count = self.count

    def kill(self, count: int = 1) -> int:
        """
        Kill some mobs. Returns actual number killed.
        """
        killed = min(count, self.alive_count)
        self.alive_count -= killed
        return killed

    @property
    def all_dead(self) -> bool:
        return self.alive_count <= 0


@dataclass
class ActiveEffect:
    """
    Tracks an active potion effect on a player.

    Used for simulating effect duration and stacking.
    """

    effect_type: str
    amplifier: int = 0
    duration_seconds: int = 60
    remaining_seconds: float = field(init=False)
    applied_by_eris: bool = False

    def __post_init__(self):
        self.remaining_seconds = float(self.duration_seconds)

    def tick(self, seconds: float) -> bool:
        """
        Advance time. Returns True if effect expired.
        """
        self.remaining_seconds -= seconds
        return self.remaining_seconds <= 0

    @property
    def expired(self) -> bool:
        return self.remaining_seconds <= 0
