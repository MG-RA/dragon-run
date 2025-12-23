from typing import Literal, List
import logging
from langchain_core.tools import tool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Schema definitions help the 14B model understand inputs accurately
class SpawnMobArgs(BaseModel):
    mob_type: Literal['zombie', 'skeleton', 'spider', 'creeper', 'enderman'] = Field(..., description="The type of mob")
    near_player: str = Field(..., description="Target player name")
    count: int = Field(default=1, description="Number of mobs (1-3)")

class GiveItemArgs(BaseModel):
    player: str = Field(..., description="Target player")
    item: str = Field(..., description="Minecraft item ID (e.g. cooked_beef, diamond, iron_sword)")
    count: int = Field(default=1, description="Quantity")

class MessageArgs(BaseModel):
    player: str = Field(..., description="Target player name")
    message: str = Field(..., description="Message to send to the player")

class EffectArgs(BaseModel):
    player: str = Field(..., description="Target player name")
    effect: str = Field(..., description="Potion effect type (e.g. speed, strength, jump_boost)")
    duration: int = Field(default=60, description="Effect duration in seconds (1-600)")
    amplifier: int = Field(default=0, description="Effect amplifier level (0-5)")

class LightningArgs(BaseModel):
    player: str = Field(..., description="Target player name")

class WeatherArgs(BaseModel):
    weather_type: Literal['clear', 'rain', 'thunder'] = Field(..., description="Weather type to set")

class FireworkArgs(BaseModel):
    player: str = Field(..., description="Target player name")
    count: int = Field(default=1, description="Number of fireworks to spawn (1-5)")

class GameInterface:
    def __init__(self, ws_client):
        self.ws_client = ws_client

    def get_tools(self) -> List:
        @tool("spawn_mob", args_schema=SpawnMobArgs)
        async def spawn_mob(mob_type: str, near_player: str, count: int = 1):
            """Spawn hostile mobs near a player to challenge them."""
            logger.info(f"🔧 Tool Execution: spawn_mob(type={mob_type}, target={near_player}, count={count})")
            # The agent calls this, we execute via WebSocket
            await self.ws_client.send_command('spawn_mob',
                {'mobType': mob_type, 'nearPlayer': near_player, 'count': count},
                reason="AI Director Action"
            )
            return f"ACTION SUCCESS: Spawned {count} {mob_type} near {near_player}."

        @tool("give_item", args_schema=GiveItemArgs)
        async def give_item(player: str, item: str, count: int = 1):
            """Give items to a player to help them or reward them."""
            logger.info(f"🔧 Tool Execution: give_item(player={player}, item={item}, count={count})")
            await self.ws_client.send_command('give',
                {'player': player, 'item': item, 'count': count},
                reason="AI Director Gift"
            )
            return f"ACTION SUCCESS: Gave {count} {item} to {player}."

        @tool("broadcast")
        async def broadcast(message: str):
            """Send a chat message to the entire server."""
            logger.info(f"🔧 Tool Execution: broadcast('{message}')")
            await self.ws_client.send_command('broadcast', {'message': message})
            return f"CHAT SENT: {message}"

        @tool("message", args_schema=MessageArgs)
        async def message_player(player: str, message: str):
            """Send a targeted message to a specific player."""
            logger.info(f"🔧 Tool Execution: message_player(player={player}, message='{message}')")
            await self.ws_client.send_command('message',
                {'player': player, 'message': message},
                reason="AI Director Message"
            )
            return f"MESSAGE SENT: '{message}' to {player}."

        @tool("effect", args_schema=EffectArgs)
        async def apply_effect(player: str, effect: str, duration: int = 60, amplifier: int = 0):
            """Apply a potion effect to a player."""
            logger.info(f"🔧 Tool Execution: apply_effect(player={player}, effect={effect}, duration={duration}, amplifier={amplifier})")
            await self.ws_client.send_command('effect',
                {'player': player, 'effect': effect, 'duration': duration, 'amplifier': amplifier},
                reason="AI Director Effect"
            )
            return f"EFFECT APPLIED: {effect} (duration: {duration}s, amplifier: {amplifier}) to {player}."

        @tool("lightning", args_schema=LightningArgs)
        async def strike_lightning(player: str):
            """Strike lightning near a player for dramatic effect."""
            logger.info(f"🔧 Tool Execution: strike_lightning(player={player})")
            await self.ws_client.send_command('lightning',
                {'player': player},
                reason="AI Director Lightning"
            )
            return f"LIGHTNING STRIKE: Near {player}."

        @tool("weather", args_schema=WeatherArgs)
        async def change_weather(weather_type: str):
            """Change the weather conditions in the world."""
            logger.info(f"🔧 Tool Execution: change_weather(type={weather_type})")
            await self.ws_client.send_command('weather',
                {'weatherType': weather_type},
                reason="AI Director Weather"
            )
            return f"WEATHER CHANGED: Set to {weather_type}."

        @tool("firework", args_schema=FireworkArgs)
        async def launch_firework(player: str, count: int = 1):
            """Launch fireworks near a player for celebrations."""
            logger.info(f"🔧 Tool Execution: launch_firework(player={player}, count={count})")
            await self.ws_client.send_command('firework',
                {'player': player, 'count': count},
                reason="AI Director Firework"
            )
            return f"FIREWORKS LAUNCHED: {count} near {player}."

        return [spawn_mob, give_item, broadcast, message_player, apply_effect, strike_lightning, change_weather, launch_firework]
