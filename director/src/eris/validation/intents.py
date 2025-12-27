"""
Player intents - what players actually do in Minecraft.

These are behavior-driven, not role-driven. A player doesn't "tank" or "heal" -
they explore, hoard, build, destroy, help, or hide.
"""

from dataclasses import dataclass
from enum import Enum


class Intent(str, Enum):
    """What players actually do in Minecraft."""

    # === Exploration (Fool, Hermit, Death) ===
    EXPLORE = "explore"  # Wander into unknown territory
    ENTER_DANGER = "enter_danger"  # Push into Nether/End/dangerous biomes
    CHASE_RARE = "chase_rare"  # Pursue rare items, mobs, or structures
    RUSH_STRUCTURE = "rush_structure"  # Beeline to fortress/stronghold/bastion
    SCOUT = "scout"  # Reconnaissance without engagement
    FLEE = "flee"  # Run from danger

    # === Building (Emperor, Magician) ===
    BUILD_BASE = "build_base"  # Construct shelter/base
    SECURE_AREA = "secure_area"  # Light up, wall off, make safe
    BUILD_FARM = "build_farm"  # Create automated/semi-automated farms
    LIGHT_AREA = "light_area"  # Place torches, prevent spawns
    CRAFT_OPTIMAL = "craft_optimal"  # Efficient crafting, min-max gear
    FORTIFY = "fortify"  # Strengthen existing structures

    # === Resource Control (Devil) ===
    HOARD = "hoard"  # Collect and keep resources
    CONTROL_PORTAL = "control_portal"  # Dominate Nether portal access
    WITHHOLD_RESOURCES = "withhold_resources"  # Refuse to share
    HIDE_CHEST = "hide_chest"  # Stash items in hidden location
    MONOPOLIZE = "monopolize"  # Control critical resource (blaze rods, eyes)

    # === Chaos (Tower) ===
    GRIEF = "grief"  # Destroy other players' work
    TRIGGER_MOBS = "trigger_mobs"  # Aggro mobs toward players
    LURE_DANGER = "lure_danger"  # Lead enemies to others
    IGNITE = "ignite"  # Set fires, use TNT, cause explosions
    SABOTAGE = "sabotage"  # Break farms, traps, infrastructure

    # === Progression (Death, Fool) ===
    RUSH_ENDGAME = "rush_endgame"  # Push toward dragon kill
    SACRIFICE = "sacrifice"  # Risk self for team progress
    HIGH_RISK = "high_risk"  # Take dangerous shortcuts
    PUSH_ADVANCEMENT = "push_advancement"  # Target specific advancements
    SPEEDRUN = "speedrun"  # Optimize for time, ignore safety

    # === Social (Lovers, Star) ===
    FOLLOW_PLAYER = "follow_player"  # Stay close to specific player
    SHARE_SPACE = "share_space"  # Work in same area as others
    TRADE = "trade"  # Exchange resources with others
    REBUILD = "rebuild"  # Fix griefed/destroyed structures
    HELP_STRAGGLERS = "help_stragglers"  # Assist players who fell behind
    PROTECT = "protect"  # Shield others from danger
    RESCUE = "rescue"  # Save player in immediate danger

    # === Survival (any card under pressure) ===
    HIDE = "hide"  # Go underground, avoid threats
    RETURN_TO_PLAYER = "return_to_player"  # Regroup with team
    RUSH_PORTAL = "rush_portal"  # Emergency escape through portal
    DROP_ITEMS = "drop_items"  # Sacrifice inventory to survive
    HEAL = "heal"  # Eat food, use potions, regenerate
    RETREAT = "retreat"  # Tactical withdrawal

    # === Meta / Waiting ===
    WAIT = "wait"  # Do nothing, observe
    PLAN = "plan"  # Pause to strategize (internal state)
    RESPOND_TO_ERIS = "respond_to_eris"  # React to Eris's actions


# Intent categories for filtering and analysis
INTENT_CATEGORIES: dict[str, list[Intent]] = {
    "exploration": [
        Intent.EXPLORE,
        Intent.ENTER_DANGER,
        Intent.CHASE_RARE,
        Intent.RUSH_STRUCTURE,
        Intent.SCOUT,
        Intent.FLEE,
    ],
    "building": [
        Intent.BUILD_BASE,
        Intent.SECURE_AREA,
        Intent.BUILD_FARM,
        Intent.LIGHT_AREA,
        Intent.CRAFT_OPTIMAL,
        Intent.FORTIFY,
    ],
    "control": [
        Intent.HOARD,
        Intent.CONTROL_PORTAL,
        Intent.WITHHOLD_RESOURCES,
        Intent.HIDE_CHEST,
        Intent.MONOPOLIZE,
    ],
    "chaos": [
        Intent.GRIEF,
        Intent.TRIGGER_MOBS,
        Intent.LURE_DANGER,
        Intent.IGNITE,
        Intent.SABOTAGE,
    ],
    "progression": [
        Intent.RUSH_ENDGAME,
        Intent.SACRIFICE,
        Intent.HIGH_RISK,
        Intent.PUSH_ADVANCEMENT,
        Intent.SPEEDRUN,
    ],
    "social": [
        Intent.FOLLOW_PLAYER,
        Intent.SHARE_SPACE,
        Intent.TRADE,
        Intent.REBUILD,
        Intent.HELP_STRAGGLERS,
        Intent.PROTECT,
        Intent.RESCUE,
    ],
    "survival": [
        Intent.HIDE,
        Intent.RETURN_TO_PLAYER,
        Intent.RUSH_PORTAL,
        Intent.DROP_ITEMS,
        Intent.HEAL,
        Intent.RETREAT,
    ],
    "meta": [
        Intent.WAIT,
        Intent.PLAN,
        Intent.RESPOND_TO_ERIS,
    ],
}


@dataclass
class IntentResult:
    """Result of an intent decision with context."""

    intent: Intent
    target_player: str | None = None  # For social intents
    target_location: str | None = None  # For exploration/building
    urgency: float = 0.5  # 0-1, how urgently this should happen
    reason: str = ""  # Why this intent was chosen (for logging)

    def to_dict(self) -> dict:
        """Serialize for logging."""
        return {
            "intent": self.intent.value,
            "target_player": self.target_player,
            "target_location": self.target_location,
            "urgency": round(self.urgency, 2),
            "reason": self.reason,
        }


def get_intent_category(intent: Intent) -> str | None:
    """Get the category an intent belongs to."""
    for category, intents in INTENT_CATEGORIES.items():
        if intent in intents:
            return category
    return None


def is_aggressive_intent(intent: Intent) -> bool:
    """Check if an intent could harm other players."""
    return intent in INTENT_CATEGORIES["chaos"]


def is_cooperative_intent(intent: Intent) -> bool:
    """Check if an intent helps other players."""
    return intent in INTENT_CATEGORIES["social"]


def is_risky_intent(intent: Intent) -> bool:
    """Check if an intent puts the player at risk."""
    risky = {
        Intent.ENTER_DANGER,
        Intent.RUSH_STRUCTURE,
        Intent.HIGH_RISK,
        Intent.SACRIFICE,
        Intent.SPEEDRUN,
        Intent.IGNITE,
        Intent.TRIGGER_MOBS,
    }
    return intent in risky
