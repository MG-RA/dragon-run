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
    TeleportArgs,
    PlaySoundArgs,
    ShowTitleArgs,
    DamagePlayerArgs,
    HealPlayerArgs,
    ModifyAuraArgs,
    SpawnTNTArgs,
    SpawnFallingBlockArgs,
    ForceLookAtArgs,
    SpawnParticlesArgs,
    FakeDeathArgs,
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

    @tool("teleport_player", args_schema=TeleportArgs)
    async def teleport_player(player: str, mode: str = "random", target: str | None = None, radius: int = 100, distance: int = 200):
        """Teleport a player - random location, swap with another, or isolate far away."""
        logger.info(f"🔧 Tool: teleport_player(player={player}, mode={mode})")
        params = {"player": player, "mode": mode}
        if mode == "swap" and target:
            params["target"] = target
        elif mode == "random":
            params["radius"] = radius
        elif mode == "isolate":
            params["distance"] = distance
        await ws_client.send_command("teleport", params, reason="Eris Teleport")
        return f"Teleported {player} ({mode} mode)."

    @tool("play_sound", args_schema=PlaySoundArgs)
    async def play_sound(sound: str, target: str = "@a", volume: float = 1.0, pitch: float = 1.0):
        """Play a cinematic sound effect for psychological tension."""
        logger.info(f"🔧 Tool: play_sound(sound={sound}, target={target})")
        await ws_client.send_command("sound", {"sound": sound, "target": target, "volume": volume, "pitch": pitch})
        return f"Played {sound} to {target}."

    @tool("show_title", args_schema=ShowTitleArgs)
    async def show_title(player: str, title: str = "", subtitle: str = "", fade_in: int = 10, stay: int = 70, fade_out: int = 20):
        """Show a cinematic title/subtitle to a player for storytelling."""
        logger.info(f"🔧 Tool: show_title(player={player}, title={title})")
        await ws_client.send_command("title", {"player": player, "title": title, "subtitle": subtitle, "fadeIn": fade_in, "stay": stay, "fadeOut": fade_out})
        return f"Showed title to {player}."

    @tool("damage_player", args_schema=DamagePlayerArgs)
    async def damage_player(player: str, amount: int = 4):
        """Deal non-lethal damage to create tension (never kills)."""
        logger.info(f"🔧 Tool: damage_player(player={player}, amount={amount})")
        await ws_client.send_command("damage", {"player": player, "amount": amount})
        return f"Damaged {player} for {amount} half-hearts."

    @tool("heal_player", args_schema=HealPlayerArgs)
    async def heal_player(player: str, full: bool = True):
        """Heal a player fully or partially (3 hearts)."""
        logger.info(f"🔧 Tool: heal_player(player={player}, full={full})")
        await ws_client.send_command("heal", {"player": player, "full": full})
        return f"{'Fully' if full else 'Partially'} healed {player}."

    @tool("modify_aura", args_schema=ModifyAuraArgs)
    async def modify_aura(player: str, amount: int, reason: str):
        """Reward or punish players by modifying their aura based on their actions."""
        logger.info(f"🔧 Tool: modify_aura(player={player}, amount={amount}, reason='{reason}')")
        await ws_client.send_command("aura", {"player": player, "amount": amount, "reason": reason})
        action = "Rewarded" if amount > 0 else "Punished"
        return f"{action} {player} with {amount} aura: {reason}"

    @tool("spawn_tnt", args_schema=SpawnTNTArgs)
    async def spawn_tnt(near_player: str, count: int = 1, fuse_ticks: int = 60):
        """Spawn primed TNT near a player for explosive chaos. TNT has a fuse before detonation."""
        logger.info(f"🔧 Tool: spawn_tnt(target={near_player}, count={count}, fuse={fuse_ticks})")
        await ws_client.send_command(
            "spawn_tnt",
            {"nearPlayer": near_player, "count": count, "fuseTicks": fuse_ticks},
            reason="Eris Explosive"
        )
        return f"Spawned {count} primed TNT near {near_player} with {fuse_ticks/20:.1f}s fuse."

    @tool("spawn_falling_block", args_schema=SpawnFallingBlockArgs)
    async def spawn_falling_block(block_type: str, near_player: str, count: int = 1, height: int = 15):
        """Drop falling blocks (anvil, dripstone, sand, gravel) from above a player."""
        logger.info(f"🔧 Tool: spawn_falling_block(type={block_type}, target={near_player}, count={count}, height={height})")
        await ws_client.send_command(
            "spawn_falling",
            {"blockType": block_type, "nearPlayer": near_player, "count": count, "height": height},
            reason="Eris Falling Sky"
        )
        return f"Spawned {count} falling {block_type} {height} blocks above {near_player}."

    @tool("force_look_at", args_schema=ForceLookAtArgs)
    async def force_look_at(player: str, mode: str, x: int | None = None, y: int | None = None, z: int | None = None, target: str | None = None):
        """Force a player's camera to look at coordinates or another player. Use to reveal hidden structures (fortress they missed), redirect attention (creeper behind them), or create dramatic moments (make them witness a teammate in danger). Works through walls - perfect for foreshadowing."""
        if mode == "position" and x is not None and y is not None and z is not None:
            logger.info(f"🔧 Tool: force_look_at(player={player}, position=({x}, {y}, {z}))")
            await ws_client.send_command(
                "lookat_position",
                {"player": player, "x": x, "y": y, "z": z},
                reason="Eris Camera Control"
            )
            return f"Forced {player} to look at ({x}, {y}, {z})."
        elif mode == "entity" and target is not None:
            logger.info(f"🔧 Tool: force_look_at(player={player}, entity={target})")
            await ws_client.send_command(
                "lookat_entity",
                {"player": player, "target": target},
                reason="Eris Camera Control"
            )
            return f"Forced {player} to look at {target}."
        else:
            return "Invalid arguments: position mode needs x/y/z, entity mode needs target."

    @tool("spawn_particles", args_schema=SpawnParticlesArgs)
    async def spawn_particles(particle: str, near_player: str, count: int = 20, spread: float = 1.0):
        """Spawn particle effects for atmosphere, warnings, or celebrations. 'soul' for ominous moments, 'dragon_breath' when near End, 'explosion' as danger warning, 'portal' when nether portal is nearby, 'heart' for achievements, 'angry_villager' when upset, 'sculk_soul' for death foreshadowing. Purely visual - doesn't hurt players."""
        logger.info(f"🔧 Tool: spawn_particles(type={particle}, target={near_player}, count={count}, spread={spread})")
        await ws_client.send_command(
            "spawn_particles",
            {"particle": particle, "nearPlayer": near_player, "count": count, "spread": spread},
            reason="Eris Particles"
        )
        return f"Spawned {count} {particle} particles near {player}."

    @tool("fake_death", args_schema=FakeDeathArgs)
    async def fake_death(player: str, cause: str = "fell"):
        """Broadcast a realistic fake death message in chat. Player is NOT actually dead - this is pure psychological warfare. Creates panic, tests team communication, forces players to verify teammate status. Best used when they're separated or in dangerous situations. Use 'lava' in Nether, 'void' in End, 'fell' anywhere."""
        logger.info(f"🔧 Tool: fake_death(player={player}, cause={cause})")
        await ws_client.send_command(
            "fake_death",
            {"player": player, "cause": cause},
            reason="Eris Deception"
        )
        return f"Broadcast fake death for {player} ({cause})."

    return [
        spawn_mob,
        give_item,
        broadcast,
        message_player,
        apply_effect,
        strike_lightning,
        change_weather,
        launch_firework,
        teleport_player,
        play_sound,
        show_title,
        damage_player,
        heal_player,
        modify_aura,
        spawn_tnt,
        spawn_falling_block,
        force_look_at,
        spawn_particles,
        fake_death,
    ]
