"""
Tarot integration helpers for the Eris graph.

Connects tarot archetypes to mask selection and provides
drift application utilities.
"""

from typing import Any

from ..core.tarot import TAROT_TRAITS, TarotCard, TarotProfile, get_drift_for_event
from ..graph.state import ErisMask

# Tarot -> Mask affinities
# Each tarot card predisposes Eris toward certain masks when targeting that player
TAROT_MASK_AFFINITY: dict[TarotCard, list[ErisMask]] = {
    # Fool seeks danger - Trickster tempts, Chaos provides
    TarotCard.FOOL: [ErisMask.TRICKSTER, ErisMask.CHAOS_BRINGER],
    # Magician optimizes - Gambler offers deals, Observer analyzes
    TarotCard.MAGICIAN: [ErisMask.GAMBLER, ErisMask.OBSERVER],
    # Hermit hides - Prophet sees them, Observer watches silently
    TarotCard.HERMIT: [ErisMask.PROPHET, ErisMask.OBSERVER],
    # Emperor builds - Friend helps then betrays, Gambler offers bargains
    TarotCard.EMPEROR: [ErisMask.FRIEND, ErisMask.GAMBLER],
    # Devil hoards - Chaos takes, Gambler tempts with more
    TarotCard.DEVIL: [ErisMask.CHAOS_BRINGER, ErisMask.GAMBLER],
    # Tower destroys - Chaos amplifies, Trickster redirects
    TarotCard.TOWER: [ErisMask.CHAOS_BRINGER, ErisMask.TRICKSTER],
    # Death transforms - Prophet foresees, Chaos accelerates
    TarotCard.DEATH: [ErisMask.PROPHET, ErisMask.CHAOS_BRINGER],
    # Lovers attach - Friend exploits bonds, Trickster separates
    TarotCard.LOVERS: [ErisMask.FRIEND, ErisMask.TRICKSTER],
    # Star helps - Friend pretends kinship, Prophet warns of cost
    TarotCard.STAR: [ErisMask.FRIEND, ErisMask.PROPHET],
}


def get_tarot_mask_weights(
    player_profiles: dict[str, dict],
    base_weights: dict[ErisMask, float] | None = None,
    focus_player: str | None = None,
) -> dict[ErisMask, float]:
    """
    Calculate mask weights influenced by player tarot cards.

    Args:
        player_profiles: Dict of username -> PlayerProfile
        base_weights: Starting weights for each mask (default all 1.0)
        focus_player: If set, weight heavily toward this player's tarot affinities

    Returns:
        Dict of ErisMask -> weight (higher = more likely to select)
    """
    if base_weights is None:
        base_weights = dict.fromkeys(ErisMask, 1.0)

    weights = dict(base_weights)

    # Collect all dominant cards in game
    for username, profile in player_profiles.items():
        tarot_data = profile.get("tarot", {})
        dominant_str = tarot_data.get("dominant_card", "fool")

        try:
            dominant = TarotCard(dominant_str.lower())
        except ValueError:
            dominant = TarotCard.FOOL

        # Get affinities for this card
        affinities = TAROT_MASK_AFFINITY.get(dominant, [])

        # Boost weights for affinity masks
        multiplier = 1.5 if username == focus_player else 1.2
        for mask in affinities:
            weights[mask] = weights.get(mask, 1.0) * multiplier

    return weights


def get_lever_for_player(player_profile: dict) -> str:
    """
    Get Eris's lever (manipulation strategy) for a player based on their tarot.

    Args:
        player_profile: PlayerProfile dict

    Returns:
        String describing how Eris should manipulate this player
    """
    tarot_data = player_profile.get("tarot", {})
    dominant_str = tarot_data.get("dominant_card", "fool")

    try:
        dominant = TarotCard(dominant_str.lower())
    except ValueError:
        dominant = TarotCard.FOOL

    traits = TAROT_TRAITS.get(dominant, {})
    return traits.get("eris_lever", "Observe and learn their patterns")


def apply_event_drift(
    player_profiles: dict[str, dict],
    event_type: str,
    event_data: dict[str, Any],
    affected_player: str | None = None,
) -> dict[str, dict]:
    """
    Apply tarot drift to players based on an event.

    Args:
        player_profiles: Dict of username -> PlayerProfile (mutated)
        event_type: Type of event
        event_data: Event payload
        affected_player: If set, only drift this player

    Returns:
        Updated player_profiles
    """

    # Create a simple event object for the drift function
    class EventWrapper:
        def __init__(self, data: dict):
            self._data = data

        def __getattr__(self, name: str) -> Any:
            return self._data.get(name, "")

    event_obj = EventWrapper(event_data)
    drifts = get_drift_for_event(event_type, event_obj)

    if not drifts:
        return player_profiles

    # Apply drift to affected player(s)
    players_to_update = (
        [affected_player] if affected_player else list(player_profiles.keys())
    )

    for username in players_to_update:
        if username not in player_profiles:
            continue

        profile = player_profiles[username]
        tarot_data = profile.get("tarot", {})

        # Reconstruct TarotProfile from stored data
        weights = tarot_data.get("weights", {})
        tarot_profile = TarotProfile()
        for card_str, weight in weights.items():
            try:
                card = TarotCard(card_str.lower())
                tarot_profile.weights[card] = weight
            except ValueError:
                pass

        # Apply drifts
        tarot_profile.drift_multiple(drifts)

        # Store back
        profile["tarot"] = {
            "dominant_card": tarot_profile.dominant_card.value,
            "strength": tarot_profile.identity_strength,
            "secondary_card": (
                tarot_profile.secondary_card.value
                if tarot_profile.secondary_card
                else None
            ),
            "weights": {
                card.value: weight
                for card, weight in tarot_profile.weights.items()
                if weight > 0
            },
        }

    return player_profiles


def describe_tarot_for_prompt(player_profiles: dict[str, dict]) -> str:
    """
    Build a tarot context section for LLM prompts.

    Args:
        player_profiles: Dict of username -> PlayerProfile

    Returns:
        Formatted string for inclusion in system prompt
    """
    if not player_profiles:
        return ""

    lines = ["=== PLAYER ARCHETYPES ==="]

    for username, profile in player_profiles.items():
        tarot_data = profile.get("tarot", {})
        dominant = tarot_data.get("dominant_card", "fool")
        strength = tarot_data.get("strength", 0.0)
        secondary = tarot_data.get("secondary_card")

        # Get traits for this card
        try:
            card = TarotCard(dominant.lower())
            traits = TAROT_TRAITS.get(card, {})
        except ValueError:
            traits = {}

        seeks = traits.get("seeks", [])
        lever = traits.get("eris_lever", "")

        lines.append(f"\n{username} is THE {dominant.upper()}")
        if strength > 0.7:
            lines.append(f"  Identity: LOCKED (strength {strength:.0%})")
        elif strength > 0.4:
            lines.append(f"  Identity: forming (strength {strength:.0%})")
        else:
            lines.append(f"  Identity: uncertain (strength {strength:.0%})")

        if secondary:
            lines.append(f"  Secondary influence: {secondary.upper()}")

        if seeks:
            lines.append(f"  Seeks: {', '.join(seeks[:3])}")
        if lever:
            lines.append(f"  YOUR LEVER: {lever}")

    return "\n".join(lines)


def describe_opinions_for_prompt(player_profiles: dict[str, dict]) -> str:
    """
    Build an opinion context section for LLM prompts.

    Args:
        player_profiles: Dict of username -> PlayerProfile

    Returns:
        Formatted string for inclusion in system prompt
    """
    if not player_profiles:
        return ""

    lines = ["=== YOUR FEELINGS ==="]

    for username, profile in player_profiles.items():
        opinion = profile.get("opinion", {})
        trust = opinion.get("trust", 0.0)
        annoyance = opinion.get("annoyance", 0.0)
        interest = opinion.get("interest", 0.3)

        feelings = []

        # Trust
        if trust > 0.5:
            feelings.append("you favor them")
        elif trust < -0.5:
            feelings.append("you despise them")
        elif trust < -0.2:
            feelings.append("you distrust them")

        # Interest
        if interest > 0.7:
            feelings.append("you are OBSESSED with them")
        elif interest > 0.5:
            feelings.append("you find them fascinating")
        elif interest < 0.2:
            feelings.append("you find them boring")

        # Annoyance
        if annoyance > 0.7:
            feelings.append("they INFURIATE you")
        elif annoyance > 0.4:
            feelings.append("they annoy you")

        if feelings:
            lines.append(f"  {username}: {', '.join(feelings)}")
        else:
            lines.append(f"  {username}: neutral")

    return "\n".join(lines)


# Chaos-seeking tarot cards that increase fracture
CHAOS_TAROTS = {TarotCard.DEATH, TarotCard.TOWER, TarotCard.DEVIL}
CHAOS_TAROT_BONUS = 10


def calculate_tarot_fracture_bonus(player_profiles: dict[str, dict]) -> int:
    """
    Calculate bonus fracture from chaos-seeking tarot cards.

    Args:
        player_profiles: Dict of username -> PlayerProfile

    Returns:
        Bonus to add to fracture calculation
    """
    bonus = 0

    for profile in player_profiles.values():
        tarot_data = profile.get("tarot", {})
        dominant_str = tarot_data.get("dominant_card", "fool")

        try:
            dominant = TarotCard(dominant_str.lower())
            if dominant in CHAOS_TAROTS:
                bonus += CHAOS_TAROT_BONUS
        except ValueError:
            pass

    return bonus


def get_total_interest(player_profiles: dict[str, dict]) -> float:
    """
    Calculate total interest Eris has in all players.

    Used in fracture calculation.
    """
    return sum(
        profile.get("opinion", {}).get("interest", 0.3)
        for profile in player_profiles.values()
    )
