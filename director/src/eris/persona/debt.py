"""Betrayal debt system for Eris masks.

Each mask accumulates debt based on its actions. When debt exceeds thresholds,
it influences mask selection probability and intent weights, creating:
- Delayed punishments
- Sudden betrayals
- Narrative arcs
"""

from typing import Dict, List, Optional
import random
import logging

from ..graph.state import ErisMask, ErisIntent
from .masks import MASK_DEBT_FIELDS, MASK_TRAITS

logger = logging.getLogger("eris.debt")


# === Debt Configuration ===

DEBT_THRESHOLD = 50  # When debt becomes influential
DEBT_MAX = 100       # Maximum debt value
DEBT_BOOST_FACTOR = 0.5  # Max 50% boost at threshold

# How much debt increases per action type
DEBT_ACCUMULATION = {
    # FRIEND accumulates betrayal_debt when being helpful
    "betrayal_debt": {
        "heal_player": 8,
        "protect_player": 10,
        "give_item": 5,
        "apply_effect_positive": 6,
    },
    # GAMBLER accumulates risk_debt when playing safe
    "risk_debt": {
        "safe_gamble": 10,  # When gamble has low stakes
        "refused_bet": 15,  # When player declines and Eris doesn't punish
    },
    # TRICKSTER accumulates prank_debt with harmless pranks
    "prank_debt": {
        "fake_death": 5,
        "teleport_player": 3,
        "harmless_scare": 4,
    },
    # PROPHET accumulates doom_debt with unfulfilled prophecies
    "doom_debt": {
        "prophecy_made": 15,
        "prophecy_unfulfilled": 10,  # Per minute prophecy remains unfulfilled
    },
    # CHAOS_BRINGER accumulates wrath_debt when restrained
    "wrath_debt": {
        "restrained_action": 10,  # When chaos is high but Eris backs off
        "mercy_shown": 15,
    },
    # OBSERVER accumulates silence_debt while watching
    "silence_debt": {
        "silent_observation": 2,  # Per event observed without action
        "withheld_judgment": 5,
    },
}

# How debt resets when resolved
DEBT_RESOLUTION = {
    "betrayal_debt": {
        "triggered_by": ["curse", "test"],  # FRIEND betrays
        "reset_amount": 40,  # How much to reduce after betrayal
    },
    "risk_debt": {
        "triggered_by": ["test"],  # GAMBLER forces high-stakes
        "reset_amount": 35,
    },
    "prank_debt": {
        "triggered_by": ["test", "confuse"],  # TRICKSTER does dangerous prank
        "reset_amount": 30,
    },
    "doom_debt": {
        "triggered_by": ["reveal"],  # PROPHET fulfills prophecy
        "reset_amount": 50,
    },
    "wrath_debt": {
        "triggered_by": ["curse"],  # CHAOS_BRINGER unleashes
        "reset_amount": 45,
    },
    "silence_debt": {
        "triggered_by": ["reveal", "curse"],  # OBSERVER finally speaks/acts
        "reset_amount": 40,
    },
}


def calculate_mask_probabilities(
    player_debts: Dict[str, int],
    base_weights: Optional[Dict[str, float]] = None,
    global_chaos: int = 0,
) -> Dict[str, float]:
    """
    Calculate mask selection probabilities influenced by debt.

    Debt increases probability of selecting that mask (pressure to resolve debt).
    High chaos also influences mask selection (favors CHAOS_BRINGER, TRICKSTER).

    Args:
        player_debts: Dict mapping debt field names to values (e.g., {"betrayal_debt": 45})
        base_weights: Optional base weights for each mask. Defaults to equal weights.
        global_chaos: Current global chaos level (0-100)

    Returns:
        Dict mapping mask names to selection probabilities (normalized to sum to 1.0)
    """
    if base_weights is None:
        base_weights = {mask.name: 1.0 for mask in ErisMask}

    adjusted = {}
    for mask in ErisMask:
        mask_name = mask.name
        base = base_weights.get(mask_name, 1.0)

        # Get this mask's debt field and current debt
        debt_field = MASK_DEBT_FIELDS.get(mask_name, "generic_debt")
        debt = player_debts.get(debt_field, 0)

        # Debt influence: higher debt = higher selection probability
        debt_multiplier = 1 + min(debt / DEBT_THRESHOLD, 1) * DEBT_BOOST_FACTOR

        # Chaos influence: high chaos favors CHAOS_BRINGER, TRICKSTER
        chaos_multiplier = 1.0
        if global_chaos > 60:
            if mask_name == "CHAOS_BRINGER":
                chaos_multiplier = 1.3
            elif mask_name == "TRICKSTER":
                chaos_multiplier = 1.2
            elif mask_name in ["FRIEND", "OBSERVER"]:
                chaos_multiplier = 0.7  # Less likely when chaos is high

        adjusted[mask_name] = base * debt_multiplier * chaos_multiplier

    # Normalize to probabilities
    total = sum(adjusted.values())
    if total == 0:
        return {mask.name: 1.0 / len(ErisMask) for mask in ErisMask}

    return {k: v / total for k, v in adjusted.items()}


def get_intent_weights(
    mask: ErisMask,
    player_debt: int,
    global_chaos: int = 0,
) -> Dict[str, float]:
    """
    Get intent selection weights for a mask, influenced by debt.

    When debt is high, the mask is more likely to select intents that resolve the debt.

    Args:
        mask: Current active mask
        player_debt: Debt value for this mask's debt field
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

    # Debt influence on intent
    if player_debt >= DEBT_THRESHOLD:
        debt_field = MASK_DEBT_FIELDS.get(mask.name, "generic_debt")
        resolution = DEBT_RESOLUTION.get(debt_field, {})
        resolution_intents = resolution.get("triggered_by", [])

        # Boost intents that resolve debt
        debt_boost = 0.3 * min(player_debt / DEBT_MAX, 1.0)
        for intent in resolution_intents:
            if intent in base_weights:
                base_weights[intent] += debt_boost

    # Chaos influence: high chaos reduces BLESS, increases CURSE/TEST
    if global_chaos > 70:
        base_weights[ErisIntent.BLESS.value] *= 0.5
        base_weights[ErisIntent.CURSE.value] *= 1.4
        base_weights[ErisIntent.TEST.value] *= 1.3

    # Normalize
    total = sum(base_weights.values())
    return {k: v / total for k, v in base_weights.items()}


def select_intent_weighted(weights: Dict[str, float]) -> str:
    """Select an intent based on weighted probabilities."""
    intents = list(weights.keys())
    probs = list(weights.values())
    return random.choices(intents, weights=probs, k=1)[0]


def calculate_debt_delta(
    action_tool: str,
    action_purpose: str,
    mask: ErisMask,
) -> int:
    """
    Calculate how much debt to add for an action.

    Args:
        action_tool: The tool used (e.g., "heal_player")
        action_purpose: The purpose annotation (e.g., "mercy", "terror")
        mask: The mask performing the action

    Returns:
        Debt delta (positive = increase, negative = resolution)
    """
    debt_field = MASK_DEBT_FIELDS.get(mask.name, "generic_debt")
    accumulation = DEBT_ACCUMULATION.get(debt_field, {})

    # Check for specific tool accumulation
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

    return 0  # No debt change


def check_debt_resolution(
    intent: str,
    mask: ErisMask,
    current_debt: int,
) -> int:
    """
    Check if an intent resolves debt and calculate the reduction.

    Args:
        intent: The intent being executed
        mask: Current mask
        current_debt: Current debt value

    Returns:
        Amount to reduce debt by (negative delta)
    """
    debt_field = MASK_DEBT_FIELDS.get(mask.name, "generic_debt")
    resolution = DEBT_RESOLUTION.get(debt_field, {})

    if intent in resolution.get("triggered_by", []):
        if current_debt >= DEBT_THRESHOLD:
            reduction = resolution.get("reset_amount", 30)
            logger.info(
                f"Debt resolution triggered! {mask.name} {debt_field}: "
                f"{current_debt} -> {max(0, current_debt - reduction)}"
            )
            return -reduction

    return 0


def get_debt_narrative_hint(mask: ErisMask, debt: int) -> Optional[str]:
    """
    Get a narrative hint based on debt level for LLM prompts.

    Returns None if debt is below threshold.
    """
    if debt < DEBT_THRESHOLD:
        return None

    debt_field = MASK_DEBT_FIELDS.get(mask.name, "generic_debt")
    pressure = min(debt / DEBT_MAX, 1.0)

    hints = {
        "betrayal_debt": (
            f"You have been too kind. The debt weighs on you (pressure: {pressure:.0%}). "
            "The time for betrayal approaches..."
        ),
        "risk_debt": (
            f"You have played too safe. Fortune demands balance (pressure: {pressure:.0%}). "
            "Force a high-stakes gamble..."
        ),
        "prank_debt": (
            f"Your pranks have been too harmless (pressure: {pressure:.0%}). "
            "Time for a prank with real consequences..."
        ),
        "doom_debt": (
            f"Your prophecies remain unfulfilled (pressure: {pressure:.0%}). "
            "The threads demand resolution. Make doom manifest..."
        ),
        "wrath_debt": (
            f"You have held back too long (pressure: {pressure:.0%}). "
            "The wrath must be unleashed. NO MERCY."
        ),
        "silence_debt": (
            f"You have watched in silence long enough (pressure: {pressure:.0%}). "
            "Speak. Judge. Act. Your words carry weight now..."
        ),
    }

    return hints.get(debt_field)
