"""
Eris's subjective memory and opinions about players.

This is not objective truth - it's what Eris believes and feels.
Trust can be negative (enemy), interest can spike on dramatic events,
annoyance builds when players defy or escape Eris.
"""

from typing import Any

from typing_extensions import TypedDict


class ErisOpinion(TypedDict):
    """Eris's subjective opinion of a single player."""

    trust: float  # -1 (enemy) to 1 (pet) - how much Eris trusts them
    annoyance: float  # 0-1 - how irritating Eris finds them
    interest: float  # 0-1 - how much Eris is watching them
    last_interaction: str | None  # What Eris last did to them
    interaction_count: int  # How many times Eris has acted on them


def create_default_opinion() -> ErisOpinion:
    """Create a neutral opinion for a new player."""
    return ErisOpinion(
        trust=0.0,
        annoyance=0.0,
        interest=0.3,  # Base curiosity about new players
        last_interaction=None,
        interaction_count=0,
    )


# Opinion triggers: event_type -> {field: delta}
# Some events reset opinions entirely (player_death)
OPINION_TRIGGERS: dict[str, dict[str, float | bool]] = {
    # Chat events - player is engaging, slightly annoying
    "player_chat": {"interest": 0.1, "annoyance": 0.05},
    # Player mentions Eris directly - very interesting
    "player_chat_eris": {"interest": 0.2, "annoyance": 0.1},
    # Player damaged - they're learning to fear
    "player_damaged": {"trust": -0.05},
    # Close call - exciting drama
    "eris_close_call": {"interest": 0.15},
    # Player escaped Eris's trap - frustrating
    "eris_trap_escaped": {"annoyance": 0.2, "interest": 0.1},
    # Achievement - skilled player is interesting
    "achievement_unlocked": {"interest": 0.1},
    # Structure discovered - explorer is interesting
    "structure_discovered": {"interest": 0.08},
    # Dimension change - adventurous
    "dimension_change": {"interest": 0.1},
    # Player death - fresh start
    "player_death": {"reset": True},
    # Run started - reset to baseline
    "run_started": {"reset": True},
    # Eris helped player - trust increases (but betrayal looms)
    "eris_helped": {"trust": 0.15, "interest": -0.05},
    # Eris hurt player - trust decreases, interest stable
    "eris_hurt": {"trust": -0.1, "interest": 0.05},
    # Player defied Eris (ignored warning, etc) - annoying
    "player_defied": {"annoyance": 0.15, "interest": 0.1},
    # Player followed Eris's suggestion - good pet
    "player_obeyed": {"trust": 0.1, "annoyance": -0.1},
}


# Tarot cards that inherently interest Eris
INTERESTING_TAROTS = {"death", "tower", "devil"}
INTEREST_BOOST_FOR_TAROT = 0.15


def update_opinion(
    opinion: ErisOpinion,
    event_type: str,
    event_data: dict[str, Any] | None = None,
    player_tarot: str | None = None,
) -> ErisOpinion:
    """
    Update Eris's opinion based on an event.

    Args:
        opinion: Current opinion to update
        event_type: Type of event that occurred
        event_data: Optional event data for context
        player_tarot: Optional player's dominant tarot card

    Returns:
        Updated opinion (mutates and returns same dict)
    """
    triggers = OPINION_TRIGGERS.get(event_type, {})

    # Handle reset events
    if triggers.get("reset"):
        opinion["trust"] = 0.0
        opinion["annoyance"] = 0.0
        opinion["interest"] = 0.3  # Base curiosity
        opinion["last_interaction"] = None
        # Don't reset interaction_count - that persists
        return opinion

    # Apply deltas
    for field, delta in triggers.items():
        if field == "reset":
            continue
        if field in opinion and isinstance(delta, float):
            current = opinion[field]  # type: ignore
            if field == "trust":
                # Trust ranges from -1 to 1
                opinion[field] = max(-1.0, min(1.0, current + delta))  # type: ignore
            else:
                # Other fields range from 0 to 1
                opinion[field] = max(0.0, min(1.0, current + delta))  # type: ignore

    # Boost interest for chaos-seeking tarots
    if player_tarot and player_tarot.lower() in INTERESTING_TAROTS:
        current_interest = opinion["interest"]
        opinion["interest"] = min(1.0, current_interest + INTEREST_BOOST_FOR_TAROT)

    return opinion


def record_interaction(
    opinion: ErisOpinion,
    action_type: str,
) -> ErisOpinion:
    """
    Record that Eris took an action on this player.

    Args:
        opinion: Current opinion to update
        action_type: What Eris did (e.g., "spawn_mob", "broadcast", "heal")

    Returns:
        Updated opinion
    """
    opinion["last_interaction"] = action_type
    opinion["interaction_count"] += 1
    return opinion


def get_opinion_summary(opinion: ErisOpinion) -> str:
    """
    Generate a human-readable summary of Eris's opinion.

    Used for logging and LLM prompts.
    """
    trust = opinion["trust"]
    annoyance = opinion["annoyance"]
    interest = opinion["interest"]

    parts = []

    # Trust description
    if trust > 0.7:
        parts.append("devoted pet")
    elif trust > 0.3:
        parts.append("trusted")
    elif trust > -0.3:
        parts.append("neutral")
    elif trust > -0.7:
        parts.append("distrusted")
    else:
        parts.append("enemy")

    # Interest description
    if interest > 0.7:
        parts.append("fascinating")
    elif interest > 0.4:
        parts.append("interesting")
    elif interest < 0.2:
        parts.append("boring")

    # Annoyance description
    if annoyance > 0.7:
        parts.append("infuriating")
    elif annoyance > 0.4:
        parts.append("annoying")

    return ", ".join(parts) if parts else "unremarkable"


def decay_opinions(opinions: dict[str, ErisOpinion], decay_rate: float = 0.02) -> None:
    """
    Apply slow decay to opinions over time.

    Called periodically to prevent opinions from being permanent.
    Trust decays toward 0, annoyance decays toward 0.
    Interest decays toward 0.3 (base curiosity).

    Args:
        opinions: Dict of username -> ErisOpinion to decay (mutated in place)
        decay_rate: How much to decay per call (default 0.02)
    """
    for opinion in opinions.values():
        # Trust decays toward 0
        if opinion["trust"] > 0:
            opinion["trust"] = max(0.0, opinion["trust"] - decay_rate)
        elif opinion["trust"] < 0:
            opinion["trust"] = min(0.0, opinion["trust"] + decay_rate)

        # Annoyance decays toward 0
        opinion["annoyance"] = max(0.0, opinion["annoyance"] - decay_rate)

        # Interest decays toward baseline (0.3)
        if opinion["interest"] > 0.3:
            opinion["interest"] = max(0.3, opinion["interest"] - decay_rate)
        elif opinion["interest"] < 0.3:
            opinion["interest"] = min(0.3, opinion["interest"] + decay_rate)
