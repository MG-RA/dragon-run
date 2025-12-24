"""Pydantic schemas for Minecraft action tools."""

from typing import Literal
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
        default=60, ge=1, le=600, description="Effect duration in seconds (1-600)"
    )
    amplifier: int = Field(default=0, ge=0, le=5, description="Effect amplifier (0-5)")


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
