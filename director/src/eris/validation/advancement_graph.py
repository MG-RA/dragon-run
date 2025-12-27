"""
Advancement DAG for validating Minecraft progression sequences.

Format: parent_advancement -> [children it unlocks]
To validate: check that prerequisites appear before their dependents.
"""

import logging

logger = logging.getLogger(__name__)

# Parent -> Children (what it unlocks)
# Based on Minecraft's actual advancement tree for speedrun-critical path
ADVANCEMENT_GRAPH: dict[str, list[str]] = {
    "minecraft:story/mine_stone": ["minecraft:story/upgrade_tools"],
    "minecraft:story/upgrade_tools": ["minecraft:story/smelt_iron"],
    "minecraft:story/smelt_iron": [
        "minecraft:story/obtain_armor",
        "minecraft:story/iron_tools",
        "minecraft:story/lava_bucket",
    ],
    "minecraft:story/lava_bucket": ["minecraft:story/form_obsidian"],
    "minecraft:story/form_obsidian": ["minecraft:story/enter_the_nether"],
    "minecraft:story/enter_the_nether": [
        "minecraft:nether/obtain_blaze_rod",
        "minecraft:nether/find_fortress",
    ],
    "minecraft:nether/obtain_blaze_rod": ["minecraft:story/follow_ender_eye"],
    "minecraft:story/follow_ender_eye": ["minecraft:story/enter_the_end"],
    "minecraft:story/enter_the_end": ["minecraft:end/kill_dragon"],
}

# Inverted: child -> parent (prerequisites)
# Built automatically from ADVANCEMENT_GRAPH
PREREQUISITES: dict[str, str] = {}
for parent, children in ADVANCEMENT_GRAPH.items():
    for child in children:
        PREREQUISITES[child] = parent


def get_prerequisites(advancement: str) -> set[str]:
    """Get all prerequisites (transitive) for an advancement.

    Args:
        advancement: The advancement key to check (e.g., "minecraft:end/kill_dragon")

    Returns:
        Set of all prerequisite advancement keys that must be obtained first.
    """
    result: set[str] = set()
    current = advancement
    while current in PREREQUISITES:
        parent = PREREQUISITES[current]
        result.add(parent)
        current = parent
    return result


def is_valid_progression(path: list[str]) -> bool:
    """Check if a sequence of advancements is valid.

    Each advancement must have its direct prerequisite earlier in the path.
    Advancements not in our tracked DAG are ignored (always valid).

    Args:
        path: List of advancement keys in the order they were obtained.

    Returns:
        True if valid progression, False if impossible sequence detected.
    """
    seen: set[str] = set()
    for advancement in path:
        # Check if this advancement has a prerequisite
        if advancement in PREREQUISITES:
            required = PREREQUISITES[advancement]
            if required not in seen:
                return False
        seen.add(advancement)
    return True


def find_missing_prerequisites(path: list[str]) -> dict[str, str]:
    """Find which advancements are missing their prerequisites.

    Args:
        path: List of advancement keys in the order they were obtained.

    Returns:
        Dict mapping advancement -> missing prerequisite for invalid entries.
    """
    seen: set[str] = set()
    missing: dict[str, str] = {}
    for advancement in path:
        if advancement in PREREQUISITES:
            required = PREREQUISITES[advancement]
            if required not in seen:
                missing[advancement] = required
        seen.add(advancement)
    return missing
