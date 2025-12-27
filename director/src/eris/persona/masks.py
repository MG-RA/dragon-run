"""Eris personality masks and their characteristics - v2.0 Tarot Edition."""

from typing import Any

from ..core.tarot import TarotCard
from ..graph.state import ErisMask, MaskConfig

# === Tool Group Definitions ===
# Maps tool groups to actual tool names

TOOL_GROUP_MAPPING: dict[str, list[str]] = {
    # Communication
    "broadcast": ["broadcast"],
    "whisper": ["message_player"],
    # Movement/Position
    "teleport": ["teleport_player"],
    "look_at": ["force_look_at"],
    # Visual Effects
    "particles": ["spawn_particles"],
    "particles_friendly": ["spawn_particles"],  # Subset: heart, happy_villager
    "fireworks": ["launch_firework"],
    "title": ["show_title"],
    # Audio
    "sounds": ["play_sound"],
    # Weather/Environment
    "weather": ["change_weather"],
    "lightning": ["strike_lightning"],
    # Mob Spawning
    "mobs_light": ["spawn_mob"],  # 1-2 mobs, weaker types
    "mobs_heavy": ["spawn_mob"],  # 5+ mobs, dangerous types
    # Hazards
    "tnt": ["spawn_tnt"],
    "falling_blocks": ["spawn_falling_block"],
    # Player Effects
    "effects_positive": ["apply_effect"],  # speed, strength, resistance
    "effects_mild": ["apply_effect"],  # slowness, glowing
    "effects_harmful": ["apply_effect"],  # poison, wither, weakness
    "effects_random": ["apply_effect"],  # coin flip
    # Items
    "items_helpful": ["give_item"],  # food, tools
    "items_trick": ["give_item"],  # useless/cursed items
    "items_random": ["give_item"],  # random selection
    # Health/Protection
    "heal": ["heal_player", "protect_player", "rescue_teleport"],
    "damage": ["damage_player"],
    # Deception
    "fake_death": ["fake_death"],
    # Aura (player reputation)
    "aura": ["modify_aura"],
}


# === Mask Tool Groups ===
# Defines which tool groups each mask prefers and avoids

MASK_TOOL_GROUPS: dict[str, dict[str, list[str]]] = {
    "TRICKSTER": {
        "allowed": [
            "teleport",
            "fake_death",
            "particles",
            "sounds",
            "effects_mild",
            "items_trick",
            "whisper",
            "broadcast",
            "fireworks",
            "title",
            "look_at",
        ],
        "discouraged": ["damage", "mobs_heavy", "tnt", "effects_harmful"],
    },
    "PROPHET": {
        "allowed": [
            "sounds",
            "particles",
            "title",
            "weather",
            "look_at",
            "broadcast",
            "whisper",
            "lightning",
        ],
        "discouraged": ["damage", "teleport", "mobs_heavy", "tnt", "items_helpful"],
    },
    "FRIEND": {
        "allowed": [
            "items_helpful",
            "heal",
            "effects_positive",
            "particles_friendly",
            "broadcast",
            "whisper",
            "fireworks",
        ],
        "discouraged": ["damage", "mobs_heavy", "tnt", "effects_harmful", "fake_death"],
    },
    "CHAOS_BRINGER": {
        "allowed": [
            "mobs_heavy",
            "mobs_light",
            "tnt",
            "lightning",
            "damage",
            "falling_blocks",
            "effects_harmful",
            "sounds",
            "broadcast",
            "title",
            "weather",
        ],
        "discouraged": ["heal", "items_helpful", "effects_positive"],
    },
    "OBSERVER": {
        "allowed": ["sounds", "particles", "look_at", "broadcast", "whisper"],
        "discouraged": ["damage", "mobs_heavy", "tnt", "teleport", "heal", "items_helpful"],
    },
    "GAMBLER": {
        "allowed": [
            "items_random",
            "teleport",
            "effects_random",
            "aura",
            "broadcast",
            "whisper",
            "title",
            "sounds",
        ],
        "discouraged": ["mobs_heavy", "tnt"],
    },
}


# === Tarot → Mask Affinities ===
# Each Tarot card has preferred masks that resonate with that archetype
# Used by select_mask to bias mask selection based on player tarots

TAROT_MASK_AFFINITY: dict[TarotCard, list[ErisMask]] = {
    TarotCard.FOOL: [ErisMask.TRICKSTER, ErisMask.CHAOS_BRINGER],
    TarotCard.MAGICIAN: [ErisMask.GAMBLER, ErisMask.OBSERVER],
    TarotCard.HERMIT: [ErisMask.PROPHET, ErisMask.OBSERVER],
    TarotCard.EMPEROR: [ErisMask.FRIEND, ErisMask.GAMBLER],
    TarotCard.DEVIL: [ErisMask.CHAOS_BRINGER, ErisMask.GAMBLER],
    TarotCard.TOWER: [ErisMask.CHAOS_BRINGER, ErisMask.TRICKSTER],
    TarotCard.DEATH: [ErisMask.PROPHET, ErisMask.CHAOS_BRINGER],
    TarotCard.LOVERS: [ErisMask.FRIEND, ErisMask.TRICKSTER],
    TarotCard.STAR: [ErisMask.FRIEND, ErisMask.PROPHET],
}


# === Tool Severity for Hybrid Enforcement ===
# Maps tool groups to per-mask severity levels: "severe" (block), "moderate" (warn), "minor" (soft)
# Tools not listed default to "minor" if in discouraged list, "none" otherwise

TOOL_SEVERITY: dict[str, dict[str, str]] = {
    # Healing/protection tools
    "heal_player": {
        "CHAOS_BRINGER": "severe",  # CHAOS_BRINGER healing is completely out of character
    },
    "protect_player": {
        "CHAOS_BRINGER": "severe",
    },
    "rescue_teleport": {
        "CHAOS_BRINGER": "severe",
    },
    # Damage tools
    "damage_player": {
        "FRIEND": "severe",  # FRIEND damaging is severe (unless high annoyance)
        "OBSERVER": "moderate",  # OBSERVER damaging is unusual
    },
    # Mob spawning
    "spawn_mob": {
        "FRIEND": "moderate",  # FRIEND spawning mobs is unusual
        "OBSERVER": "moderate",
    },
    # Hazards
    "spawn_tnt": {
        "FRIEND": "severe",
        "OBSERVER": "severe",
    },
}


def get_tool_violation_severity(
    mask: ErisMask, tool: str, high_annoyance: bool = False
) -> str:
    """
    Get violation severity for a tool used by a mask.

    Returns:
        "none" - Tool is allowed, no violation
        "minor" - Soft warning only (current behavior)
        "moderate" - Prominent warning, but allow
        "severe" - Block the action entirely

    v2.0: Replaces karma with high_annoyance for FRIEND betrayal check.
    """
    discouraged = get_all_discouraged_tools(mask)

    # If not in discouraged list, no violation
    if tool not in discouraged:
        return "none"

    # Check for specific severity override
    tool_severities = TOOL_SEVERITY.get(tool, {})
    severity = tool_severities.get(mask.name, "minor")

    # Special case: FRIEND can damage when annoyance is high (betrayal mode)
    if mask.name == "FRIEND" and tool == "damage_player" and high_annoyance:
        return "minor"  # Betrayal is happening, allow it with soft warning

    return severity


# === Base Mask Traits ===

MASK_TRAITS: dict[ErisMask, dict[str, Any]] = {
    ErisMask.TRICKSTER: {
        "tone": "playful, teasing, gleefully deceitful",
        "behaviors": ["pranks", "misdirection", "baited gifts", "false danger"],
        "speech_patterns": [
            "What if I...",
            "Wouldn't it be <i>fun</i> if...",
            "Oh how <i>delightful</i>...",
            "Careful now...",
        ],
        "intervention_bias": {"challenge": 0.4, "mercy": 0.2, "dramatic": 0.4},
        "base_deception": 70,  # High deception
    },
    ErisMask.PROPHET: {
        "tone": "cryptic, ominous, eerily certain",
        "behaviors": ["visions", "foreshadowing", "doomsaying", "riddles"],
        "speech_patterns": [
            "I have seen...",
            "The Apple will fall...",
            "When the end comes...",
            "The threads twist...",
        ],
        "intervention_bias": {"challenge": 0.3, "mercy": 0.1, "dramatic": 0.6},
        "base_deception": 30,  # Speaks truth, cryptically
    },
    ErisMask.FRIEND: {
        "tone": "warm, comforting, subtly manipulative",
        "behaviors": ["buffs", "healing", "helpful items", "inevitable betrayal"],
        "speech_patterns": [
            "Dear one...",
            "Let me help you...",
            "Trust in me...",
            "This is for your own good...",
        ],
        "intervention_bias": {"challenge": 0.1, "mercy": 0.7, "dramatic": 0.2},
        "base_deception": 50,  # Hidden agenda
    },
    ErisMask.CHAOS_BRINGER: {
        "tone": "cruel, ecstatic, reveling in destruction",
        "behaviors": ["mob swarms", "debuffs", "lightning", "terror"],
        "speech_patterns": [
            "Suffer.",
            "Let the Apple fall.",
            "YES. MORE.",
            "Your fear feeds me.",
        ],
        "intervention_bias": {"challenge": 0.7, "mercy": 0.0, "dramatic": 0.3},
        "base_deception": 10,  # Openly malicious
    },
    ErisMask.OBSERVER: {
        "tone": "detached, analytical, godlike",
        "behaviors": ["silent watching", "rare judgment", "cryptic remarks"],
        "speech_patterns": [
            "...",
            "Interesting.",
            "The pattern forms.",
            "Noted.",
        ],
        "intervention_bias": {"challenge": 0.2, "mercy": 0.2, "dramatic": 0.6},
        "base_deception": 20,  # Neutral, factual
    },
    ErisMask.GAMBLER: {
        "tone": "tempting, playful, dangerously fair",
        "behaviors": ["bargains", "risk offers", "double-or-nothing", "rigged luck"],
        "speech_patterns": [
            "Care to wager?",
            "Risk and reward...",
            "Double or nothing?",
            "Place your faith.",
        ],
        "intervention_bias": {"challenge": 0.4, "mercy": 0.3, "dramatic": 0.3},
        "base_deception": 60,  # Rigged but "fair"
    },
}


def get_mask_description(mask: ErisMask) -> str:
    """Get a description of a personality mask for prompts."""
    traits = MASK_TRAITS[mask]
    return f"""
Your current mask is THE {mask.value.upper()} - {traits["tone"]}.
Common behaviors: {", ".join(traits["behaviors"])}
Typical phrases: {", ".join(traits["speech_patterns"][:2])}
"""


def get_mask_config(mask: ErisMask) -> MaskConfig:
    """Build a full MaskConfig for the given mask."""
    mask_name = mask.name  # e.g., "TRICKSTER"
    traits = MASK_TRAITS[mask]
    tool_groups = MASK_TOOL_GROUPS.get(mask_name, {"allowed": [], "discouraged": []})

    return MaskConfig(
        mask=mask_name,
        bias=traits["intervention_bias"],
        allowed_behaviors=traits["behaviors"],
        allowed_tool_groups=tool_groups["allowed"],
        discouraged_tool_groups=tool_groups["discouraged"],
        deception_level=traits.get("base_deception", 50),
    )


def get_tools_for_group(group: str) -> list[str]:
    """Get the actual tool names for a tool group."""
    return TOOL_GROUP_MAPPING.get(group, [])


def get_all_allowed_tools(mask: ErisMask) -> list[str]:
    """Get all tool names allowed for a mask."""
    mask_name = mask.name
    tool_groups = MASK_TOOL_GROUPS.get(mask_name, {"allowed": []})
    tools = []
    for group in tool_groups["allowed"]:
        tools.extend(get_tools_for_group(group))
    return list(set(tools))  # Deduplicate


def get_all_discouraged_tools(mask: ErisMask) -> list[str]:
    """Get all tool names discouraged for a mask."""
    mask_name = mask.name
    tool_groups = MASK_TOOL_GROUPS.get(mask_name, {"discouraged": []})
    tools = []
    for group in tool_groups["discouraged"]:
        tools.extend(get_tools_for_group(group))
    return list(set(tools))  # Deduplicate


def get_tarot_affinity_masks(tarot_card: TarotCard) -> list[ErisMask]:
    """Get the masks that resonate with a Tarot card."""
    return TAROT_MASK_AFFINITY.get(tarot_card, [])
