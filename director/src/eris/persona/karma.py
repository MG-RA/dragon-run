"""Karma vector system for Eris masks.

Each mask accumulates karma based on its actions. When karma exceeds thresholds,
it influences mask selection probability and intent weights, creating:
- Delayed punishments
- Sudden betrayals
- Narrative arcs
- Phase transitions toward apocalypse

Renamed from "debt" to "karma" for consistency with mask expansion spec.
"""

import logging
import random
from enum import Enum

from ..graph.state import ErisIntent, ErisMask
from .masks import MASK_KARMA_FIELDS, MASK_TRAITS

logger = logging.getLogger("eris.karma")


# === Karma Configuration ===

KARMA_THRESHOLD = 50  # When karma becomes influential
KARMA_MAX = 100  # Maximum karma value
KARMA_BOOST_FACTOR = 0.5  # Max 50% boost at threshold

# How much karma increases per action type
# Keys match KarmaVector fields: betrayal, risk, irony, doom, wrath, inevitability
KARMA_ACCUMULATION = {
    # FRIEND accumulates betrayal when being helpful
    "betrayal": {
        "heal_player": 8,
        "protect_player": 10,
        "give_item": 5,
        "apply_effect_positive": 6,
    },
    # GAMBLER accumulates risk when playing safe
    "risk": {
        "safe_gamble": 10,  # When gamble has low stakes
        "refused_bet": 15,  # When player declines and Eris doesn't punish
    },
    # TRICKSTER accumulates irony with harmless pranks
    "irony": {
        "fake_death": 5,
        "teleport_player": 3,
        "harmless_scare": 4,
    },
    # PROPHET accumulates doom with unfulfilled prophecies
    "doom": {
        "prophecy_made": 15,
        "prophecy_unfulfilled": 10,  # Per minute prophecy remains unfulfilled
    },
    # CHAOS_BRINGER accumulates wrath when restrained
    "wrath": {
        "restrained_action": 10,  # When chaos is high but Eris backs off
        "mercy_shown": 15,
    },
    # OBSERVER accumulates inevitability while watching
    "inevitability": {
        "silent_observation": 2,  # Per event observed without action
        "withheld_judgment": 5,
    },
}

# How karma resets when resolved
# Keys match KarmaVector fields
KARMA_RESOLUTION = {
    "betrayal": {
        "triggered_by": ["curse", "test"],  # FRIEND betrays
        "reset_amount": 40,  # How much to reduce after betrayal
    },
    "risk": {
        "triggered_by": ["test"],  # GAMBLER forces high-stakes
        "reset_amount": 35,
    },
    "irony": {
        "triggered_by": ["test", "confuse"],  # TRICKSTER does dangerous prank
        "reset_amount": 30,
    },
    "doom": {
        "triggered_by": ["reveal"],  # PROPHET fulfills prophecy
        "reset_amount": 50,
    },
    "wrath": {
        "triggered_by": ["curse"],  # CHAOS_BRINGER unleashes
        "reset_amount": 45,
    },
    "inevitability": {
        "triggered_by": ["reveal", "curse"],  # OBSERVER finally speaks/acts
        "reset_amount": 40,
    },
}


# === Phase System ===


class ErisPhase(Enum):
    """Phases of Eris's psychological state based on fracture level."""

    NORMAL = "normal"  # Fracture 0-49: All masks available
    RISING = "rising"  # Fracture 50-79: CHAOS_BRINGER boosted
    CRITICAL = "critical"  # Fracture 80-119: PROPHET dominates
    LOCKED = "locked"  # Fracture 120-149: OBSERVER fading, CHAOS_BRINGER rising
    APOCALYPSE = "apocalypse"  # Fracture 150+: Only CHAOS_BRINGER, PROPHET, GAMBLER


# Phase thresholds from spec
PHASE_THRESHOLDS = {
    50: ErisPhase.RISING,
    80: ErisPhase.CRITICAL,
    120: ErisPhase.LOCKED,
    150: ErisPhase.APOCALYPSE,
}

# Dead masks after apocalypse
DEAD_MASKS_POST_APOCALYPSE = ["FRIEND", "OBSERVER"]


def get_phase_from_fracture(fracture: int) -> ErisPhase:
    """Determine current phase based on fracture level."""
    if fracture >= 150:
        return ErisPhase.APOCALYPSE
    elif fracture >= 120:
        return ErisPhase.LOCKED
    elif fracture >= 80:
        return ErisPhase.CRITICAL
    elif fracture >= 50:
        return ErisPhase.RISING
    return ErisPhase.NORMAL


def get_fracture_mask_modifiers(fracture: int, phase: ErisPhase) -> dict[str, float]:
    """
    Get mask probability modifiers based on fracture and phase.

    Returns multipliers for each mask's selection probability.
    """
    modifiers = {mask.name: 1.0 for mask in ErisMask}

    if phase == ErisPhase.RISING:
        # Fracture 50+: CHAOS_BRINGER +50%
        modifiers["CHAOS_BRINGER"] = 1.5

    elif phase == ErisPhase.CRITICAL:
        # Fracture 80+: PROPHET dominates (+100%), CHAOS_BRINGER still boosted
        modifiers["PROPHET"] = 2.0
        modifiers["CHAOS_BRINGER"] = 1.5

    elif phase == ErisPhase.LOCKED:
        # Fracture 120+: OBSERVER fading (-90%), CHAOS_BRINGER strong
        modifiers["OBSERVER"] = 0.1
        modifiers["CHAOS_BRINGER"] = 2.0
        modifiers["PROPHET"] = 1.5
        modifiers["FRIEND"] = 0.5  # FRIEND starting to fade

    elif phase == ErisPhase.APOCALYPSE:
        # Fracture 150+: Only CHAOS_BRINGER, PROPHET, GAMBLER allowed
        modifiers["FRIEND"] = 0.0
        modifiers["OBSERVER"] = 0.0
        modifiers["TRICKSTER"] = 0.3  # Heavily reduced
        modifiers["CHAOS_BRINGER"] = 3.0
        modifiers["PROPHET"] = 2.0
        modifiers["GAMBLER"] = 1.5

    return modifiers


def calculate_mask_probabilities(
    player_karmas: dict[str, int],
    base_weights: dict[str, float] | None = None,
    global_chaos: int = 0,
    fracture: int = 0,
    apocalypse_triggered: bool = False,
) -> dict[str, float]:
    """
    Calculate mask selection probabilities influenced by karma and fracture.

    Karma increases probability of selecting that mask (pressure to resolve karma).
    High chaos also influences mask selection (favors CHAOS_BRINGER, TRICKSTER).
    Fracture applies phase-based modifiers.

    Args:
        player_karmas: Dict mapping karma field names to values (e.g., {"betrayal_karma": 45})
        base_weights: Optional base weights for each mask. Defaults to equal weights.
        global_chaos: Current global chaos level (0-100)
        fracture: Current fracture level (0-200+)
        apocalypse_triggered: Whether apocalypse has been triggered this run

    Returns:
        Dict mapping mask names to selection probabilities (normalized to sum to 1.0)
    """
    if base_weights is None:
        base_weights = {mask.name: 1.0 for mask in ErisMask}

    # Get phase and fracture modifiers
    phase = get_phase_from_fracture(fracture)
    fracture_modifiers = get_fracture_mask_modifiers(fracture, phase)

    # If apocalypse triggered, force dead masks to 0
    if apocalypse_triggered:
        for mask_name in DEAD_MASKS_POST_APOCALYPSE:
            fracture_modifiers[mask_name] = 0.0

    adjusted = {}
    for mask in ErisMask:
        mask_name = mask.name
        base = base_weights.get(mask_name, 1.0)

        # Get this mask's karma field and current karma
        karma_field = MASK_KARMA_FIELDS.get(mask_name, "generic_karma")
        karma = player_karmas.get(karma_field, 0)

        # Karma influence: higher karma = higher selection probability
        karma_multiplier = 1 + min(karma / KARMA_THRESHOLD, 1) * KARMA_BOOST_FACTOR

        # Chaos influence: high chaos favors CHAOS_BRINGER, TRICKSTER
        chaos_multiplier = 1.0
        if global_chaos > 60:
            if mask_name == "CHAOS_BRINGER":
                chaos_multiplier = 1.3
            elif mask_name == "TRICKSTER":
                chaos_multiplier = 1.2
            elif mask_name in ["FRIEND", "OBSERVER"]:
                chaos_multiplier = 0.7  # Less likely when chaos is high

        # Fracture modifier from phase
        fracture_multiplier = fracture_modifiers.get(mask_name, 1.0)

        adjusted[mask_name] = base * karma_multiplier * chaos_multiplier * fracture_multiplier

    # Normalize to probabilities
    total = sum(adjusted.values())
    if total == 0:
        # Fallback: only allow non-dead masks
        available = (
            [m for m in ErisMask if m.name not in DEAD_MASKS_POST_APOCALYPSE]
            if apocalypse_triggered
            else list(ErisMask)
        )
        return {mask.name: 1.0 / len(available) if mask in available else 0.0 for mask in ErisMask}

    return {k: v / total for k, v in adjusted.items()}


def get_intent_weights(
    mask: ErisMask,
    player_karma: int,
    global_chaos: int = 0,
) -> dict[str, float]:
    """
    Get intent selection weights for a mask, influenced by karma.

    When karma is high, the mask is more likely to select intents that resolve the karma.

    Args:
        mask: Current active mask
        player_karma: Karma value for this mask's karma field
        global_chaos: Current global chaos level (0-100)

    Returns:
        Dict mapping intent names to selection weights
    """
    # Base weights from intervention_bias
    traits = MASK_TRAITS.get(mask, {})
    bias = traits.get("intervention_bias", {"challenge": 0.4, "mercy": 0.3, "dramatic": 0.3})

    # Map intervention_bias to intents
    base_weights = {
        ErisIntent.BLESS.value: bias.get("mercy", 0.3),
        ErisIntent.CURSE.value: bias.get("challenge", 0.4) * 0.5,
        ErisIntent.TEST.value: bias.get("challenge", 0.4) * 0.5,
        ErisIntent.CONFUSE.value: bias.get("dramatic", 0.3) * 0.4,
        ErisIntent.REVEAL.value: bias.get("dramatic", 0.3) * 0.4,
        ErisIntent.LIE.value: bias.get("dramatic", 0.3) * 0.2,
    }

    # Karma influence on intent
    if player_karma >= KARMA_THRESHOLD:
        karma_field = MASK_KARMA_FIELDS.get(mask.name, "generic_karma")
        resolution = KARMA_RESOLUTION.get(karma_field, {})
        resolution_intents = resolution.get("triggered_by", [])

        # Boost intents that resolve karma
        karma_boost = 0.3 * min(player_karma / KARMA_MAX, 1.0)
        for intent in resolution_intents:
            if intent in base_weights:
                base_weights[intent] += karma_boost

    # Chaos influence: high chaos reduces BLESS, increases CURSE/TEST
    if global_chaos > 70:
        base_weights[ErisIntent.BLESS.value] *= 0.5
        base_weights[ErisIntent.CURSE.value] *= 1.4
        base_weights[ErisIntent.TEST.value] *= 1.3

    # Normalize
    total = sum(base_weights.values())
    return {k: v / total for k, v in base_weights.items()}


def select_intent_weighted(weights: dict[str, float]) -> str:
    """Select an intent based on weighted probabilities."""
    intents = list(weights.keys())
    probs = list(weights.values())
    return random.choices(intents, weights=probs, k=1)[0]


# Base karma added per action (ensures karma always grows)
BASE_KARMA_PER_ACTION = 2


def calculate_karma_delta(
    action_tool: str,
    action_purpose: str,
    mask: ErisMask,
) -> int:
    """
    Calculate how much karma to add for an action.

    Args:
        action_tool: The tool used (e.g., "heal_player")
        action_purpose: The purpose annotation (e.g., "mercy", "terror")
        mask: The mask performing the action

    Returns:
        Karma delta (positive = increase). Always returns at least BASE_KARMA_PER_ACTION
        to ensure karma accumulates over time.
    """
    karma_field = MASK_KARMA_FIELDS.get(mask.name, "generic")
    accumulation = KARMA_ACCUMULATION.get(karma_field, {})

    # Check for specific tool accumulation (higher values)
    if action_tool in accumulation:
        return accumulation[action_tool]

    # Check for purpose-based accumulation
    purpose_mapping = {
        "mercy": 5,
        "help": 5,
        "safe": 3,
        "harmless": 2,
        "restrained": 4,
        "silent": 1,
    }
    for keyword, delta in purpose_mapping.items():
        if keyword in action_purpose.lower():
            return delta

    # Base accumulation: ANY action by a mask adds small karma
    # This ensures karma always grows over time, preventing narrative stagnation
    return BASE_KARMA_PER_ACTION


def check_karma_resolution(
    intent: str,
    mask: ErisMask,
    current_karma: int,
) -> int:
    """
    Check if an intent resolves karma and calculate the reduction.

    Args:
        intent: The intent being executed
        mask: Current mask
        current_karma: Current karma value

    Returns:
        Amount to reduce karma by (negative delta)
    """
    karma_field = MASK_KARMA_FIELDS.get(mask.name, "generic_karma")
    resolution = KARMA_RESOLUTION.get(karma_field, {})

    if intent in resolution.get("triggered_by", []):
        if current_karma >= KARMA_THRESHOLD:
            reduction = resolution.get("reset_amount", 30)
            logger.info(
                f"Karma resolution triggered! {mask.name} {karma_field}: "
                f"{current_karma} -> {max(0, current_karma - reduction)}"
            )
            return -reduction

    return 0


def get_karma_narrative_hint(mask: ErisMask, karma: int) -> str | None:
    """
    Get a narrative hint based on karma level for LLM prompts.

    Returns None if karma is below threshold.
    """
    if karma < KARMA_THRESHOLD:
        return None

    karma_field = MASK_KARMA_FIELDS.get(mask.name, "generic_karma")
    pressure = min(karma / KARMA_MAX, 1.0)

    # Keys match KarmaVector fields
    hints = {
        "betrayal": (
            f"You have been too kind. The karma weighs on you (pressure: {pressure:.0%}). "
            "The time for betrayal approaches..."
        ),
        "risk": (
            f"You have played too safe. Fortune demands balance (pressure: {pressure:.0%}). "
            "Force a high-stakes gamble..."
        ),
        "irony": (
            f"Your pranks have been too harmless (pressure: {pressure:.0%}). "
            "Time for a prank with real consequences..."
        ),
        "doom": (
            f"Your prophecies remain unfulfilled (pressure: {pressure:.0%}). "
            "The threads demand resolution. Make doom manifest..."
        ),
        "wrath": (
            f"You have held back too long (pressure: {pressure:.0%}). "
            "The wrath must be unleashed. NO MERCY."
        ),
        "inevitability": (
            f"You have watched in silence long enough (pressure: {pressure:.0%}). "
            "Speak. Judge. Act. Your words carry weight now..."
        ),
    }

    return hints.get(karma_field)


def calculate_total_karma(player_karmas: dict[str, int]) -> int:
    """Calculate total karma across all masks for fracture calculation."""
    return sum(player_karmas.values())


def calculate_effective_stability(
    base_stability: float,
    player_aura: int,
    global_chaos: int,
    total_karma: int,
) -> float:
    """
    Calculate dynamic mask stability based on world state.

    Formula from spec:
    effective_stability = base_stability + (player_aura / 200) - (global_chaos / 100) - (total_karma / 300)

    Args:
        base_stability: Base stability value (default 0.7)
        player_aura: Average player aura (or target player's aura)
        global_chaos: Current global chaos level (0-100)
        total_karma: Sum of all karma values for target player

    Returns:
        Effective stability (clamped to 0.1 - 1.0)
    """
    stability = base_stability + (player_aura / 200) - (global_chaos / 100) - (total_karma / 300)

    # Clamp to reasonable bounds
    return max(0.1, min(1.0, stability))
