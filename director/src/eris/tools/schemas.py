"""Pydantic schemas for Minecraft action tools."""

from typing import ClassVar, Literal, Set
from pydantic import BaseModel, Field


class SpawnMobArgs(BaseModel):
    """Arguments for spawning mobs."""

    mob_type: Literal[
        "zombie", "skeleton", "spider", "creeper", "enderman",
        "cave_spider", "silverfish", "witch", "phantom", "husk",
        "stray", "drowned", "zombie_villager", "pillager", "vindicator"
    ] = Field(
        ...,
        description=(
            "Mob type to spawn. Common: zombie, skeleton, spider, creeper, enderman. "
            "Annoying: cave_spider, silverfish, phantom. "
            "Dangerous: witch (potions), vindicator (axe), pillager (crossbow). "
            "Variants: husk (desert zombie), stray (ice skeleton), drowned (water zombie)"
        )
    )
    near_player: str = Field(..., description="Target player name")
    count: int = Field(default=1, ge=1, le=10, description="Number of mobs (1-10)")


class GiveItemArgs(BaseModel):
    """Arguments for giving items."""

    player: str = Field(..., description="Target player")
    item: str = Field(
        ...,
        description=(
            "Minecraft item ID. Food (helpful): cooked_beef, bread, cooked_chicken, golden_apple, baked_potato, "
            "cooked_salmon. Food (cursed): rotten_flesh, poisonous_potato, spider_eye, pufferfish. "
            "Basic tools: iron_sword, iron_pickaxe, iron_axe, bow, arrow, fishing_rod, shears, flint_and_steel. "
            "Armor (max iron): iron_helmet, iron_chestplate, iron_leggings, iron_boots, chainmail_boots, leather_helmet. "
            "Blocks: cobblestone, dirt, gravel, sand, wood, ladder, torch, bed, crafting_table. "
            "Minor useful: ender_pearl (1-2 only), boat, water_bucket, lava_bucket, compass, clock. "
            "Useless/trolling: stick, dead_bush, snowball, egg, feather, string, wheat_seeds. "
            "NEVER give: diamond items, netherite, totem_of_undying, elytra, enchanted gear, ender_eyes"
        )
    )
    count: int = Field(default=1, ge=1, le=64, description="Quantity (1-64)")


class MessagePlayerArgs(BaseModel):
    """Arguments for private messages."""

    player: str = Field(..., description="Target player name")
    message: str = Field(..., description="Message to send to the player")


class ApplyEffectArgs(BaseModel):
    """Arguments for applying potion effects."""

    player: str = Field(..., description="Target player name")
    effect: str = Field(
        ...,
        description=(
            "Potion effect type. Positive: speed, strength, jump_boost, regeneration, "
            "resistance, fire_resistance, water_breathing, invisibility, night_vision, "
            "health_boost, absorption, saturation, luck, slow_falling, hero_of_the_village, "
            "dolphins_grace, conduit_power. Negative: slowness, mining_fatigue, weakness, "
            "poison, wither, nausea, blindness, hunger, levitation, darkness, bad_omen, "
            "unluck, glowing (reveals through walls)"
        ),
    )
    duration: int = Field(
        default=30, ge=1, le=120, description="Effect duration in seconds (1-120, max 2 min)"
    )
    amplifier: int = Field(default=0, ge=0, le=5, description="Effect amplifier (0-5)")

    # Dangerous effects have lower max duration enforced in validation
    DANGEROUS_EFFECTS: ClassVar[Set[str]] = {"poison", "wither", "hunger", "levitation", "darkness", "blindness"}
    MAX_DANGEROUS_DURATION: ClassVar[int] = 30  # Max 30 seconds for dangerous effects

    def model_post_init(self, __context) -> None:
        """Enforce max duration for dangerous effects."""
        if self.effect in self.DANGEROUS_EFFECTS and self.duration > self.MAX_DANGEROUS_DURATION:
            object.__setattr__(self, 'duration', self.MAX_DANGEROUS_DURATION)


class StrikeLightningArgs(BaseModel):
    """Arguments for lightning strikes."""

    player: str = Field(..., description="Target player name")


class ChangeWeatherArgs(BaseModel):
    """Arguments for changing weather."""

    weather_type: Literal["clear", "rain", "thunder"] = Field(
        ..., description="Weather type to set"
    )


class LaunchFireworkArgs(BaseModel):
    """Arguments for launching fireworks."""

    player: str = Field(..., description="Target player name")
    count: int = Field(default=1, ge=1, le=5, description="Number of fireworks (1-5)")


class TeleportArgs(BaseModel):
    """Arguments for teleporting players."""

    player: str = Field(..., description="Target player name")
    mode: Literal["random", "swap", "isolate"] = Field(default="random", description="Teleport mode")
    target: str | None = Field(default=None, description="Second player for swap mode")
    radius: int = Field(default=100, ge=10, le=500, description="Radius for random TP")
    distance: int = Field(default=200, ge=50, le=1000, description="Distance for isolate mode")


class PlaySoundArgs(BaseModel):
    """Arguments for playing sounds."""

    sound: str = Field(
        ...,
        description=(
            "Minecraft sound ID. Atmospheric sounds: ambient.cave, ambient.crimson_forest.loop, "
            "ambient.basalt_deltas.loop, ambient.soul_sand_valley.loop, ambient.underwater.loop. "
            "Entity sounds: entity.warden.heartbeat, entity.warden.ambient, entity.ender_dragon.ambient, "
            "entity.ghast.scream, entity.enderman.scream, entity.zombie.ambient, entity.creeper.primed, "
            "entity.lightning_bolt.thunder, entity.phantom.ambient, entity.wither.ambient. "
            "Music: music_disc.13, music_disc.11, music_disc.ward. "
            "Events: block.portal.trigger, block.end_portal.spawn, entity.player.levelup, ui.toast.challenge_complete"
        )
    )
    target: str = Field(default="@a", description="Target player or @a for all")
    volume: float = Field(default=1.0, ge=0.0, le=10.0, description="Sound volume")
    pitch: float = Field(default=1.0, ge=0.5, le=2.0, description="Sound pitch")


class ShowTitleArgs(BaseModel):
    """Arguments for showing titles."""

    player: str = Field(..., description="Target player name")
    title: str = Field(default="", description="Title text (can be empty)")
    subtitle: str = Field(default="", description="Subtitle text (can be empty)")
    fade_in: int = Field(default=10, ge=0, le=100, description="Fade in time (ticks)")
    stay: int = Field(default=70, ge=0, le=200, description="Stay time (ticks)")
    fade_out: int = Field(default=20, ge=0, le=100, description="Fade out time (ticks)")


class DamagePlayerArgs(BaseModel):
    """Arguments for damaging players."""

    player: str = Field(..., description="Target player name")
    amount: int = Field(default=4, ge=1, le=10, description="Damage amount (half hearts)")


class HealPlayerArgs(BaseModel):
    """Arguments for healing players."""

    player: str = Field(..., description="Target player name")
    full: bool = Field(default=True, description="Full heal or partial (3 hearts)")


class ModifyAuraArgs(BaseModel):
    """Arguments for modifying player aura."""

    player: str = Field(..., description="Target player name")
    amount: int = Field(..., ge=-100, le=100, description="Aura amount to add/remove (-100 to 100)")
    reason: str = Field(..., description="Reason for aura change (shown to player)")


class SpawnTNTArgs(BaseModel):
    """Arguments for spawning primed TNT."""

    near_player: str = Field(..., description="Target player name")
    count: int = Field(default=1, ge=1, le=5, description="Number of TNT to spawn (1-5)")
    fuse_ticks: int = Field(default=60, ge=20, le=100, description="Fuse time in ticks (20-100, default 60 = 3s)")


class SpawnFallingBlockArgs(BaseModel):
    """Arguments for spawning falling blocks."""

    block_type: Literal["anvil", "pointed_dripstone", "sand", "gravel", "concrete_powder"] = Field(
        ...,
        description=(
            "Block type to drop. Dangerous: anvil (heavy damage), pointed_dripstone (impale). "
            "Annoying: sand, gravel (buries player). Random: concrete_powder (turns to concrete on impact)"
        )
    )
    near_player: str = Field(..., description="Target player name")
    count: int = Field(default=1, ge=1, le=8, description="Number of blocks (1-8)")
    height: int = Field(default=15, ge=5, le=30, description="Height above player to spawn (5-30 blocks)")


class ForceLookAtArgs(BaseModel):
    """Arguments for forcing a player to look at a position or entity."""

    player: str = Field(..., description="Player to control camera")
    mode: Literal["position", "entity"] = Field(..., description="Look at position or entity")
    x: int | None = Field(default=None, description="X coordinate (for position mode)")
    y: int | None = Field(default=None, description="Y coordinate (for position mode)")
    z: int | None = Field(default=None, description="Z coordinate (for position mode)")
    target: str | None = Field(default=None, description="Target player name (for entity mode)")


class SpawnParticlesArgs(BaseModel):
    """Arguments for spawning particle effects."""

    particle: Literal[
        "soul", "soul_fire_flame", "smoke", "large_smoke", "flame", "lava",
        "dripping_water", "falling_water", "portal", "reverse_portal", "enchant",
        "crit", "explosion", "firework", "heart", "angry_villager",
        "happy_villager", "mycelium", "enchanted_hit", "note", "witch",
        "dragon_breath", "end_rod", "damage_indicator", "sweep_attack",
        "falling_dust", "sculk_soul", "sculk_charge", "sonic_boom", "shriek"
    ] = Field(..., description="Particle type to spawn")
    near_player: str = Field(..., description="Target player name")
    count: int = Field(default=20, ge=1, le=100, description="Number of particles (1-100)")
    spread: float = Field(default=1.0, ge=0.0, le=5.0, description="Spread radius in blocks")


class FakeDeathArgs(BaseModel):
    """Arguments for broadcasting a fake death message."""

    player: str = Field(..., description="Player to fake death for")
    cause: Literal[
        "fell", "lava", "fire", "suffocated", "drowned", "exploded",
        "magic", "wither", "anvil", "lightning", "kinetic", "void"
    ] = Field(default="fell", description="Fake death cause")


# ==================== DIVINE PROTECTION SCHEMAS ====================


class ProtectPlayerArgs(BaseModel):
    """Arguments for divine protection (heal + resistance)."""

    player: str = Field(..., description="Player to protect (must be endangered by Eris)")
    aura_cost: int = Field(
        default=25,
        ge=10,
        le=100,
        description="Aura cost for the saved player (10-100). Higher for more dangerous situations."
    )


class RescueTeleportArgs(BaseModel):
    """Arguments for rescue teleport (move away from danger)."""

    player: str = Field(..., description="Player to rescue (must be endangered by Eris)")
    aura_cost: int = Field(
        default=20,
        ge=10,
        le=50,
        description="Aura cost for the teleported player (10-50)."
    )


class RespawnOverrideArgs(BaseModel):
    """Arguments for respawn override (undo Eris-caused death)."""

    player: str = Field(..., description="Player who died from Eris's actions")
    aura_cost: int = Field(
        default=50,
        ge=25,
        le=200,
        description="Aura cost for the respawned player (25-200). Higher = more dramatic."
    )
