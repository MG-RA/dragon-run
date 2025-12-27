"""
Tarot archetype system for emergent player behavior.

Players don't spawn with a card - they earn it through actions.
Tarot is not what you are. It's what you're becoming.
"""

from dataclasses import dataclass, field
from enum import Enum


class TarotCard(str, Enum):
    """The nine archetypal lenses through which players see the world."""

    FOOL = "fool"  # Curiosity, reckless momentum
    MAGICIAN = "magician"  # Mastery, mechanics, efficiency
    HERMIT = "hermit"  # Isolation, secrecy, hidden bases
    EMPEROR = "emperor"  # Order, territory, infrastructure
    DEVIL = "devil"  # Control through scarcity, hoarding
    TOWER = "tower"  # Disruption, chaos, destruction
    DEATH = "death"  # Transformation, no fear of loss
    LOVERS = "lovers"  # Attachment, alliance, one person
    STAR = "star"  # Recovery, hope, helping others


# What each card seeks and avoids - used for decision-making
TAROT_TRAITS: dict[TarotCard, dict[str, list[str]]] = {
    TarotCard.FOOL: {
        "seeks": ["unknown", "portals", "rare_items", "danger"],
        "avoids": ["safety", "planning", "waiting"],
        "eris_lever": "Tempt with portals, rumors of treasure",
    },
    TarotCard.MAGICIAN: {
        "seeks": ["exploits", "efficiency", "xp", "optimal_paths"],
        "avoids": ["brute_force", "waste", "suboptimal"],
        "eris_lever": "Break farms, spawn edge cases",
    },
    TarotCard.HERMIT: {
        "seeks": ["hidden_bases", "solitude", "secrecy"],
        "avoids": ["players", "exposure", "crowds"],
        "eris_lever": "Leak coordinates, spawn trackers",
    },
    TarotCard.EMPEROR: {
        "seeks": ["walls", "farms", "infrastructure", "order"],
        "avoids": ["chaos", "disorder", "destruction"],
        "eris_lever": "Siege, scarcity, structural collapse",
    },
    TarotCard.DEVIL: {
        "seeks": ["hoarded_resources", "portals", "control"],
        "avoids": ["sharing", "transparency", "equality"],
        "eris_lever": "Expose hoards, curse loot",
    },
    TarotCard.TOWER: {
        "seeks": ["tnt", "mob_lures", "destruction", "fire"],
        "avoids": ["stability", "building", "preservation"],
        "eris_lever": "Amplify disasters, target creations",
    },
    TarotCard.DEATH: {
        "seeks": ["endgame", "sacrifice", "transformation"],
        "avoids": ["caution", "preservation", "retreat"],
        "eris_lever": "Offer shortcuts, painful rebirths",
    },
    TarotCard.LOVERS: {
        "seeks": ["one_person", "cooperation", "proximity"],
        "avoids": ["separation", "betrayal", "loneliness"],
        "eris_lever": "Separate, endanger the other",
    },
    TarotCard.STAR: {
        "seeks": ["helping_others", "rebuilding", "hope"],
        "avoids": ["abandoning_anyone", "selfishness"],
        "eris_lever": "Strain them, force impossible choices",
    },
}


@dataclass
class TarotProfile:
    """
    A player's evolving tarot identity.

    Weights accumulate through behavior. The highest card becomes
    their current identity - not assigned, but earned.
    """

    weights: dict[TarotCard, float] = field(
        default_factory=lambda: dict.fromkeys(TarotCard, 0.0)
    )

    @property
    def dominant_card(self) -> TarotCard:
        """The card with highest weight is current identity."""
        if not self.weights or all(w == 0.0 for w in self.weights.values()):
            return TarotCard.FOOL  # Default: everyone starts as Fool
        return max(self.weights, key=lambda c: self.weights[c])

    @property
    def identity_strength(self) -> float:
        """
        How strongly they embody their dominant card (0-1).

        Low strength = identity still forming, volatile
        High strength = locked into archetype, predictable
        """
        total = sum(self.weights.values())
        if total == 0:
            return 0.0
        dominant_weight = self.weights[self.dominant_card]
        return dominant_weight / total

    @property
    def secondary_card(self) -> TarotCard | None:
        """The second-strongest card, if significantly present."""
        if len(self.weights) < 2:
            return None
        sorted_cards = sorted(self.weights, key=lambda c: self.weights[c], reverse=True)
        if len(sorted_cards) >= 2 and self.weights[sorted_cards[1]] > 0.1:
            return sorted_cards[1]
        return None

    def drift(self, card: TarotCard, amount: float) -> None:
        """
        Shift weight toward a card based on behavior.

        Other cards decay slightly to prevent total stagnation,
        but the decay is slow enough to allow multi-card identities.
        """
        self.weights[card] = min(1.0, self.weights.get(card, 0.0) + amount)

        # Slight decay on others to keep identity dynamic
        decay = 0.01
        for other in self.weights:
            if other != card:
                self.weights[other] = max(0.0, self.weights[other] - decay)

    def drift_multiple(self, drifts: dict[TarotCard, float]) -> None:
        """Apply multiple drifts at once (e.g., from a complex event)."""
        for card, amount in drifts.items():
            self.drift(card, amount)

    def get_weight(self, card: TarotCard) -> float:
        """Get the current weight for a specific card."""
        return self.weights.get(card, 0.0)

    def to_dict(self) -> dict:
        """Serialize for logging/storage."""
        return {
            "dominant": self.dominant_card.value,
            "strength": round(self.identity_strength, 3),
            "secondary": self.secondary_card.value if self.secondary_card else None,
            "weights": {card.value: round(w, 3) for card, w in self.weights.items() if w > 0},
        }

    @classmethod
    def from_initial_weights(cls, initial: dict[str, float]) -> "TarotProfile":
        """Create a profile with seeded initial weights."""
        profile = cls()
        for card_name, weight in initial.items():
            try:
                card = TarotCard(card_name.lower())
                profile.weights[card] = weight
            except ValueError:
                pass  # Ignore invalid card names
        return profile


# Tarot drift rules based on events
# Maps event type -> list of (condition_fn, card, drift_amount)
TAROT_DRIFT_RULES: dict[str, list[tuple]] = {
    "dimension_change": [
        (lambda e: getattr(e, "to_dimension", "") == "nether", TarotCard.FOOL, 0.15),
        (lambda e: getattr(e, "to_dimension", "") == "the_end", TarotCard.DEATH, 0.2),
    ],
    "inventory": [
        (lambda e: getattr(e, "action", "") == "add" and "blaze_rod" in getattr(e, "item", ""), TarotCard.DEVIL, 0.1),
        (lambda e: getattr(e, "action", "") == "remove", TarotCard.STAR, 0.1),  # Giving away
        (lambda e: getattr(e, "action", "") == "add" and "diamond" in getattr(e, "item", ""), TarotCard.DEVIL, 0.05),
    ],
    "structure_discovered": [
        (lambda _e: True, TarotCard.FOOL, 0.1),
        (lambda _e: True, TarotCard.HERMIT, 0.05),
    ],
    "player_death": [
        (lambda _e: True, TarotCard.DEATH, 0.3),  # Dying = embracing Death
    ],
    "player_damaged": [
        (lambda e: getattr(e, "amount", 0) >= 10, TarotCard.DEATH, 0.1),  # Near death
        (lambda e: getattr(e, "source", "") == "player", TarotCard.TOWER, 0.2),  # PvP chaos
    ],
    "build": [
        (lambda _e: True, TarotCard.EMPEROR, 0.1),
        (lambda e: "farm" in getattr(e, "structure_type", ""), TarotCard.MAGICIAN, 0.15),
    ],
    "player_chat": [
        (lambda e: "help" in getattr(e, "message", "").lower(), TarotCard.STAR, 0.1),
        (lambda e: any(w in getattr(e, "message", "").lower() for w in ["kill", "destroy", "burn"]), TarotCard.TOWER, 0.1),
    ],
}


def get_drift_for_event(event_type: str, event) -> dict[TarotCard, float]:
    """
    Calculate tarot drift from an event.

    Returns a dict of card -> drift amount to apply.
    """
    drifts: dict[TarotCard, float] = {}
    rules = TAROT_DRIFT_RULES.get(event_type, [])

    for condition, card, amount in rules:
        try:
            if condition(event):
                drifts[card] = drifts.get(card, 0.0) + amount
        except Exception:
            pass  # Skip broken conditions

    return drifts
