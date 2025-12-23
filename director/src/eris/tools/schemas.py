"""Pydantic schemas for Minecraft action tools."""

from typing import Literal
from pydantic import BaseModel, Field


class SpawnMobArgs(BaseModel):
    """Arguments for spawning mobs."""

    mob_type: Literal["zombie", "skeleton", "spider", "creeper", "enderman"] = Field(
        ..., description="The type of mob to spawn"
    )
    near_player: str = Field(..., description="Target player name")
    count: int = Field(default=1, ge=1, le=10, description="Number of mobs (1-10)")


class GiveItemArgs(BaseModel):
    """Arguments for giving items."""

    player: str = Field(..., description="Target player")
    item: str = Field(
        ..., description="Minecraft item ID (e.g. cooked_beef, diamond, iron_sword)"
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
        description="Potion effect type (e.g. speed, strength, jump_boost, slowness, poison)",
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
