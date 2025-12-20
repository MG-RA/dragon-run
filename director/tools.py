from typing import Literal, List
from langchain_core.tools import tool
from pydantic import BaseModel, Field

# Schema definitions help the 14B model understand inputs accurately
class SpawnMobArgs(BaseModel):
    mob_type: Literal['zombie', 'skeleton', 'spider', 'creeper', 'enderman'] = Field(..., description="The type of mob")
    near_player: str = Field(..., description="Target player name")
    count: int = Field(default=1, description="Number of mobs (1-3)")

class GiveItemArgs(BaseModel):
    player: str = Field(..., description="Target player")
    item: str = Field(..., description="Minecraft item ID (e.g. cooked_beef, diamond, iron_sword)")
    count: int = Field(default=1, description="Quantity")

class GameInterface:
    def __init__(self, ws_client):
        self.ws_client = ws_client

    def get_tools(self) -> List:
        @tool("spawn_mob", args_schema=SpawnMobArgs)
        async def spawn_mob(mob_type: str, near_player: str, count: int = 1):
            """Spawn hostile mobs near a player to challenge them."""
            # The agent calls this, we execute via WebSocket
            await self.ws_client.send_command('spawn_mob', 
                {'mobType': mob_type, 'nearPlayer': near_player, 'count': count},
                reason="AI Director Action"
            )
            return f"ACTION SUCCESS: Spawned {count} {mob_type} near {near_player}."

        @tool("give_item", args_schema=GiveItemArgs)
        async def give_item(player: str, item: str, count: int = 1):
            """Give items to a player to help them or reward them."""
            await self.ws_client.send_command('give', 
                {'player': player, 'item': item, 'count': count},
                reason="AI Director Gift"
            )
            return f"ACTION SUCCESS: Gave {count} {item} to {player}."

        @tool("broadcast_message")
        async def broadcast_message(message: str):
            """Send a chat message to the entire server."""
            await self.ws_client.send_command('broadcast', {'message': message})
            return f"CHAT SENT: {message}"

        return [spawn_mob, give_item, broadcast_message]
