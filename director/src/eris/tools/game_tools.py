"""Minecraft action tools for Eris."""

import logging
from typing import TYPE_CHECKING, List

from langchain_core.tools import tool

from .schemas import (
    SpawnMobArgs,
    GiveItemArgs,
    MessagePlayerArgs,
    ApplyEffectArgs,
    StrikeLightningArgs,
    ChangeWeatherArgs,
    LaunchFireworkArgs,
)

if TYPE_CHECKING:
    from ..core.websocket import GameStateClient

logger = logging.getLogger(__name__)


def create_game_tools(ws_client: "GameStateClient") -> List:
    """Create all game tools bound to a WebSocket client."""

    @tool("spawn_mob", args_schema=SpawnMobArgs)
    async def spawn_mob(mob_type: str, near_player: str, count: int = 1):
        """Spawn hostile mobs near a player to challenge them."""
        logger.info(
            f"🔧 Tool: spawn_mob(type={mob_type}, target={near_player}, count={count})"
        )
        await ws_client.send_command(
            "spawn_mob",
            {"mobType": mob_type, "nearPlayer": near_player, "count": count},
            reason="Eris Intervention",
        )
        return f"Spawned {count} {mob_type} near {near_player}."

    @tool("give_item", args_schema=GiveItemArgs)
    async def give_item(player: str, item: str, count: int = 1):
        """Give items to a player to help them or reward them."""
        logger.info(f"🔧 Tool: give_item(player={player}, item={item}, count={count})")
        await ws_client.send_command(
            "give", {"player": player, "item": item, "count": count}, reason="Eris Gift"
        )
        return f"Gave {count} {item} to {player}."

    @tool("broadcast")
    async def broadcast(message: str):
        """Send a chat message to all players in the server."""
        logger.info(f"🔧 Tool: broadcast('{message}')")
        await ws_client.send_command("broadcast", {"message": message})
        return f"Broadcast: {message}"

    @tool("message_player", args_schema=MessagePlayerArgs)
    async def message_player(player: str, message: str):
        """Send a private message to a specific player."""
        logger.info(f"🔧 Tool: message_player(player={player}, message='{message}')")
        await ws_client.send_command(
            "message", {"player": player, "message": message}, reason="Eris Whisper"
        )
        return f"Messaged {player}: {message}"

    @tool("apply_effect", args_schema=ApplyEffectArgs)
    async def apply_effect(
        player: str, effect: str, duration: int = 60, amplifier: int = 0
    ):
        """Apply a potion effect to a player."""
        logger.info(
            f"🔧 Tool: apply_effect(player={player}, effect={effect}, duration={duration}s, amp={amplifier})"
        )
        await ws_client.send_command(
            "effect",
            {
                "player": player,
                "effect": effect,
                "duration": duration,
                "amplifier": amplifier,
            },
            reason="Eris Effect",
        )
        return f"Applied {effect} to {player} for {duration}s."

    @tool("strike_lightning", args_schema=StrikeLightningArgs)
    async def strike_lightning(player: str):
        """Strike lightning near a player for dramatic effect."""
        logger.info(f"🔧 Tool: strike_lightning(player={player})")
        await ws_client.send_command(
            "lightning", {"nearPlayer": player}, reason="Eris Lightning"
        )
        return f"Lightning struck near {player}."

    @tool("change_weather", args_schema=ChangeWeatherArgs)
    async def change_weather(weather_type: str):
        """Change the weather conditions in the world."""
        logger.info(f"🔧 Tool: change_weather(type={weather_type})")
        await ws_client.send_command(
            "weather", {"type": weather_type}, reason="Eris Weather Control"
        )
        return f"Weather changed to {weather_type}."

    @tool("launch_firework", args_schema=LaunchFireworkArgs)
    async def launch_firework(player: str, count: int = 1):
        """Launch fireworks near a player for celebrations."""
        logger.info(f"🔧 Tool: launch_firework(player={player}, count={count})")
        await ws_client.send_command(
            "firework", {"nearPlayer": player, "count": count}, reason="Eris Celebration"
        )
        return f"Launched {count} fireworks near {player}."

    return [
        spawn_mob,
        give_item,
        broadcast,
        message_player,
        apply_effect,
        strike_lightning,
        change_weather,
        launch_firework,
    ]
