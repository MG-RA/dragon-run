"""
Tarot-driven decision brains for emergent player behavior.

Each tarot card defines a psychological gravity well that influences
how a player decides what to do next. These aren't deterministic rules -
they're tendencies that emerge through the tarot identity.
"""

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .intents import Intent, IntentResult
from .player_memory import PlayerMemory
from .player_state import Dimension, PlayerState
from .tarot import TarotCard, TarotProfile

if TYPE_CHECKING:
    pass  # Reserved for future type imports


@dataclass
class DecisionContext:
    """Everything a player brain needs to make a decision."""

    # Own state
    player_state: PlayerState

    # World state
    world_state: dict  # GameSnapshot-compatible dict

    # Other players (for social decisions)
    nearby_players: list[PlayerState] = field(default_factory=list)

    # Recent history
    recent_events: list = field(default_factory=list)
    eris_recent_actions: list[dict] = field(default_factory=list)

    # Knowledge
    discovered_structures: set[str] = field(default_factory=set)

    # Flags
    is_low_health: bool = False
    is_under_attack: bool = False
    party_scattered: bool = False


@dataclass
class TarotBrain:
    """
    A player's decision-making engine driven by tarot identity.

    The brain doesn't follow fixed rules - it has tendencies that
    shift based on the dominant tarot card. As tarot drifts through
    gameplay, behavior changes naturally.

    Intent Persistence:
    -------------------
    Players don't make 2000 strategic decisions in a run - they make ~50.
    Intents persist until disrupted by:
    - HP drops significantly
    - Eris acts on them
    - Teammate dies
    - Goal reached
    - Stress crosses threshold
    """

    rng: random.Random = field(default_factory=random.Random)
    tarot: TarotProfile = field(default_factory=TarotProfile)
    memory: PlayerMemory = field(default_factory=PlayerMemory)

    # Tracks what we're currently focused on
    current_focus: str | None = None
    focus_target: str | None = None

    # Intent persistence - don't recalculate every tick
    current_goal: IntentResult | None = None
    last_health: float = 20.0
    last_stress: float = 0.0
    ticks_on_goal: int = 0

    def decide(self, context: DecisionContext) -> IntentResult:
        """
        Make a decision based on current tarot identity.

        Intent persists until disrupted - players don't change their
        mind every tick. This creates legible behavior instead of jitter.
        """
        # Check if we should reconsider our current goal
        if self.current_goal and not self._should_reconsider(context):
            self.ticks_on_goal += 1
            return self.current_goal

        # Need a new goal - reset counter
        self.ticks_on_goal = 0
        self.current_goal = self._pick_new_goal(context)

        # Update tracking state
        self.last_health = context.player_state.health
        self.last_stress = context.player_state.stress if hasattr(context.player_state, "stress") else 0.0

        return self.current_goal

    def _should_reconsider(self, context: DecisionContext) -> bool:
        """
        Determine if current intent should be abandoned.

        Disruption triggers:
        - HP dropped by 4+ hearts
        - Eris acted on us recently
        - Teammate died
        - Goal reached (intent completed)
        - Stress crossed a threshold (25/50/75)
        - Been on same goal for too long (>30 ticks)
        """
        player = context.player_state

        # HP dropped significantly (4+ hearts = 8+ damage)
        hp_drop = self.last_health - player.health
        if hp_drop >= 8:
            return True

        # Eris acted on us recently
        for action in context.eris_recent_actions[-3:]:
            targets = action.get("targets", [])
            if player.name in targets or "all" in targets:
                return True

        # Teammate died (check recent events for death)
        for event in context.recent_events[-5:]:
            if event.get("eventType") == "player_death":
                return True

        # Goal reached - check if current intent is "complete"
        if self._is_goal_reached(context):
            return True

        # Stress crossed a threshold (if stress tracking exists)
        current_stress = player.stress if hasattr(player, "stress") else 0.0
        if self._stress_crossed_threshold(self.last_stress, current_stress):
            return True

        # Been on same goal too long - stale intent
        # At 500 ticks with 4 players, we want ~30-50 decisions total
        # That's ~8-12 decisions per player, so ~40-60 ticks per decision
        if self.ticks_on_goal > 50:
            return True

        # Survival override - always reconsider if about to die
        if player.health <= 4:
            return True

        return False

    def _is_goal_reached(self, context: DecisionContext) -> bool:
        """Check if current goal has been achieved."""
        if not self.current_goal:
            return False

        player = context.player_state
        intent = self.current_goal.intent

        # Dimension change goals
        if intent == Intent.ENTER_DANGER:
            target = self.current_goal.target_location
            if target == "nether" and player.entered_nether:
                return True
            if target == "the_end" and player.entered_end:
                return True

        # Structure discovery goals
        if intent == Intent.RUSH_STRUCTURE:
            target = self.current_goal.target_location
            if target and target in context.discovered_structures:
                return True

        # Healing goal - healed enough
        if intent == Intent.HEAL and player.health >= 16:
            return True

        # Fleeing goal - no longer under attack and HP stable
        if intent == Intent.FLEE and not context.is_under_attack and player.health >= 10:
            return True

        return False

    def _stress_crossed_threshold(self, old_stress: float, new_stress: float) -> bool:
        """Check if stress crossed a psychological threshold."""
        thresholds = [25, 50, 75]
        for threshold in thresholds:
            if old_stress < threshold <= new_stress:
                return True
            if new_stress < threshold <= old_stress:
                return True
        return False

    def _pick_new_goal(self, context: DecisionContext) -> IntentResult:
        """
        Pick a new goal based on current tarot identity.

        Survival instincts can override tarot tendencies.
        """
        # Survival override - any card will flee from death
        if self._should_flee(context):
            return IntentResult(
                intent=Intent.FLEE,
                urgency=1.0,
                reason=f"{context.player_state.name} fleeing - survival instinct",
            )

        # Healing override - injured players tend to heal
        if self._should_heal(context):
            return IntentResult(
                intent=Intent.HEAL,
                urgency=0.8,
                reason=f"{context.player_state.name} needs to heal",
            )

        # Get the card-specific decision
        card = self.tarot.dominant_card
        handler = CARD_DECISION_MAP.get(card, decide_as_fool)
        return handler(self, context)

    def _should_flee(self, ctx: DecisionContext) -> bool:
        """Check if survival instinct should override."""
        player = ctx.player_state

        # Very low health = flee unless Death card
        if player.health <= 4 and self.tarot.dominant_card != TarotCard.DEATH:
            if ctx.is_under_attack or self.rng.random() < 0.7:
                return True

        # Being attacked with no armor
        if ctx.is_under_attack and player.armor_tier == "none":
            if player.health <= 10:
                return True

        return False

    def _should_heal(self, ctx: DecisionContext) -> bool:
        """Check if healing should be prioritized."""
        player = ctx.player_state

        # Low health and not actively fleeing
        if player.health <= 10 and not ctx.is_under_attack:
            # Star always heals others first, then self
            if self.tarot.dominant_card == TarotCard.STAR:
                # Check if others need healing more
                for other in ctx.nearby_players:
                    if other.health < player.health:
                        return False  # Help them first
            return self.rng.random() < 0.6

        return False


# ==================== CARD-SPECIFIC DECISION FUNCTIONS ====================


def decide_as_fool(brain: TarotBrain, ctx: DecisionContext) -> IntentResult:
    """
    The Fool: Curiosity, reckless momentum.

    Seeks the unknown, portals, rare items.
    Avoids safety, planning, waiting.
    """
    player = ctx.player_state

    # Always chase the unknown - push to next dimension
    if player.dimension == Dimension.OVERWORLD and not player.entered_nether:
        return IntentResult(
            intent=Intent.ENTER_DANGER,
            target_location="nether",
            urgency=0.9,
            reason="The Fool rushes toward the unknown Nether",
        )

    if player.dimension == Dimension.NETHER:
        # Find fortress or push to End
        if "fortress" not in ctx.discovered_structures:
            return IntentResult(
                intent=Intent.RUSH_STRUCTURE,
                target_location="fortress",
                urgency=0.8,
                reason="The Fool seeks the fortress",
            )
        if player.blaze_rod_count >= 6:  # Ready for End
            return IntentResult(
                intent=Intent.ENTER_DANGER,
                target_location="the_end",
                urgency=0.9,
                reason="The Fool has what they need - onward to the End!",
            )

    # Chase rare things
    if brain.rng.random() < 0.3:
        return IntentResult(
            intent=Intent.CHASE_RARE,
            urgency=0.7,
            reason="The Fool spots something shiny",
        )

    # Default: explore
    return IntentResult(
        intent=Intent.EXPLORE,
        urgency=0.5,
        reason="The Fool wanders curiously",
    )


def decide_as_magician(brain: TarotBrain, ctx: DecisionContext) -> IntentResult:
    """
    The Magician: Mastery, mechanics, efficiency.

    Seeks exploits, optimal paths, XP farming.
    Avoids brute force, waste.
    """
    player = ctx.player_state

    # Build farms if we have resources
    if player.dimension == Dimension.OVERWORLD:
        if brain.rng.random() < 0.4 and player.inventory.get("iron_ingot", 0) > 0:
            return IntentResult(
                intent=Intent.BUILD_FARM,
                urgency=0.7,
                reason="The Magician optimizes resource generation",
            )

    # Craft optimal gear
    if player.armor_tier == "none" and player.inventory.get("iron_ingot", 0) >= 24:
        return IntentResult(
            intent=Intent.CRAFT_OPTIMAL,
            urgency=0.8,
            reason="The Magician crafts efficient armor",
        )

    # In nether, find the fastest blaze farm spot
    if player.dimension == Dimension.NETHER and "fortress" in ctx.discovered_structures:
        return IntentResult(
            intent=Intent.BUILD_FARM,
            target_location="blaze_spawner",
            urgency=0.7,
            reason="The Magician sets up blaze farming",
        )

    # Default: explore efficiently
    return IntentResult(
        intent=Intent.SCOUT,
        urgency=0.5,
        reason="The Magician surveys the optimal path",
    )


def decide_as_hermit(brain: TarotBrain, ctx: DecisionContext) -> IntentResult:
    """
    The Hermit: Isolation, secrecy, hidden bases.

    Seeks solitude, hidden spots, secret stashes.
    Avoids players, exposure, crowds.
    """
    player = ctx.player_state

    # If near other players, move away
    if len(ctx.nearby_players) > 0:
        if brain.rng.random() < 0.6:
            return IntentResult(
                intent=Intent.HIDE,
                urgency=0.7,
                reason="The Hermit withdraws from the crowd",
            )

    # Build hidden base
    if brain.rng.random() < 0.3:
        return IntentResult(
            intent=Intent.BUILD_BASE,
            urgency=0.5,
            reason="The Hermit builds a secret shelter",
        )

    # Hide valuable items
    if player.blaze_rod_count > 0 or player.diamond_count > 2:
        if brain.rng.random() < 0.4:
            return IntentResult(
                intent=Intent.HIDE_CHEST,
                urgency=0.6,
                reason="The Hermit hides their treasures",
            )

    # Explore alone
    return IntentResult(
        intent=Intent.SCOUT,
        urgency=0.4,
        reason="The Hermit explores the shadows",
    )


def decide_as_emperor(brain: TarotBrain, ctx: DecisionContext) -> IntentResult:
    """
    The Emperor: Order, territory, infrastructure.

    Seeks walls, farms, control.
    Avoids chaos, disorder.
    """
    # Secure the area - light it up
    if brain.rng.random() < 0.4:
        return IntentResult(
            intent=Intent.LIGHT_AREA,
            urgency=0.6,
            reason="The Emperor establishes order",
        )

    # Build infrastructure
    if brain.rng.random() < 0.35:
        return IntentResult(
            intent=Intent.BUILD_BASE,
            urgency=0.6,
            reason="The Emperor builds their domain",
        )

    # Fortify existing structures
    if brain.rng.random() < 0.25:
        return IntentResult(
            intent=Intent.FORTIFY,
            urgency=0.5,
            reason="The Emperor strengthens defenses",
        )

    # Secure resources for the team
    return IntentResult(
        intent=Intent.SECURE_AREA,
        urgency=0.5,
        reason="The Emperor secures the perimeter",
    )


def decide_as_devil(brain: TarotBrain, ctx: DecisionContext) -> IntentResult:
    """
    The Devil: Control through scarcity.

    Seeks hoarded resources, portal control, leverage.
    Avoids sharing, transparency.
    """
    player = ctx.player_state

    # Hoard blaze rods - critical resource
    if player.blaze_rod_count > 0:
        return IntentResult(
            intent=Intent.HIDE_CHEST,
            urgency=0.8,
            reason="The Devil hoards the precious blaze rods",
        )

    # Control portal access in Nether
    if player.dimension == Dimension.NETHER:
        if brain.rng.random() < 0.5:
            return IntentResult(
                intent=Intent.CONTROL_PORTAL,
                urgency=0.7,
                reason="The Devil guards the only way out",
            )

    # Take resources before others
    if brain.rng.random() < 0.4:
        return IntentResult(
            intent=Intent.HOARD,
            urgency=0.6,
            reason="The Devil claims resources first",
        )

    # Withhold from team
    return IntentResult(
        intent=Intent.WITHHOLD_RESOURCES,
        urgency=0.5,
        reason="The Devil keeps their treasures close",
    )


def decide_as_tower(brain: TarotBrain, ctx: DecisionContext) -> IntentResult:
    """
    The Tower: Disruption, chaos, destruction.

    Seeks fire, explosions, mob lures.
    Avoids stability, preservation.
    """
    # Cause chaos
    roll = brain.rng.random()

    if roll < 0.25:
        return IntentResult(
            intent=Intent.IGNITE,
            urgency=0.7,
            reason="The Tower burns it down",
        )

    if roll < 0.45:
        return IntentResult(
            intent=Intent.LURE_DANGER,
            urgency=0.7,
            reason="The Tower brings destruction",
        )

    if roll < 0.6:
        return IntentResult(
            intent=Intent.TRIGGER_MOBS,
            urgency=0.6,
            reason="The Tower awakens the horde",
        )

    if roll < 0.7:
        return IntentResult(
            intent=Intent.GRIEF,
            urgency=0.6,
            reason="The Tower tears down what others built",
        )

    # Even chaos needs fuel
    return IntentResult(
        intent=Intent.EXPLORE,
        urgency=0.4,
        reason="The Tower seeks new things to destroy",
    )


def decide_as_death(brain: TarotBrain, ctx: DecisionContext) -> IntentResult:
    """
    Death: Transformation, no fear of loss.

    Seeks endgame rush, sacrifice, shortcuts.
    Avoids caution, preservation, retreat.
    """
    player = ctx.player_state

    # Rush the endgame - always push forward
    if player.dimension == Dimension.THE_END:
        return IntentResult(
            intent=Intent.RUSH_ENDGAME,
            urgency=1.0,
            reason="Death faces the dragon",
        )

    if player.dimension == Dimension.NETHER and player.blaze_rod_count >= 4:
        return IntentResult(
            intent=Intent.ENTER_DANGER,
            target_location="the_end",
            urgency=0.9,
            reason="Death pushes toward transformation",
        )

    # Take high-risk shortcuts
    if brain.rng.random() < 0.4:
        return IntentResult(
            intent=Intent.HIGH_RISK,
            urgency=0.8,
            reason="Death takes the dangerous path",
        )

    # Sacrifice for progress
    if len(ctx.nearby_players) > 0 and brain.rng.random() < 0.3:
        return IntentResult(
            intent=Intent.SACRIFICE,
            urgency=0.7,
            reason="Death offers themselves for the team",
        )

    # Push advancement
    return IntentResult(
        intent=Intent.PUSH_ADVANCEMENT,
        urgency=0.6,
        reason="Death marches toward the end",
    )


def decide_as_lovers(brain: TarotBrain, ctx: DecisionContext) -> IntentResult:
    """
    The Lovers: Attachment, alliance, devotion to one.

    Seeks proximity to their chosen person.
    Avoids separation, loneliness.
    """
    # Find closest ally
    ally = brain.memory.get_closest_ally()

    if ally:
        # Follow the ally
        if brain.rng.random() < 0.7:
            return IntentResult(
                intent=Intent.FOLLOW_PLAYER,
                target_player=ally,
                urgency=0.8,
                reason=f"The Lovers stay close to {ally}",
            )

        # Protect the ally
        if brain.rng.random() < 0.4:
            return IntentResult(
                intent=Intent.PROTECT,
                target_player=ally,
                urgency=0.9,
                reason=f"The Lovers protect {ally}",
            )

    # If separated, return
    if ctx.party_scattered:
        return IntentResult(
            intent=Intent.RETURN_TO_PLAYER,
            target_player=ally,
            urgency=0.9,
            reason="The Lovers seek reunion",
        )

    # Default: share space
    return IntentResult(
        intent=Intent.SHARE_SPACE,
        urgency=0.5,
        reason="The Lovers want to be near others",
    )


def decide_as_star(brain: TarotBrain, ctx: DecisionContext) -> IntentResult:
    """
    The Star: Recovery, hope, helping others.

    Seeks to heal, rebuild, protect the weak.
    Avoids abandoning anyone, selfishness.
    """
    player = ctx.player_state

    # Check if anyone needs help
    for other in ctx.nearby_players:
        if other.health <= 10:
            return IntentResult(
                intent=Intent.RESCUE,
                target_player=other.name,
                urgency=0.95,
                reason=f"The Star rushes to save {other.name}",
            )

    # Help stragglers
    for other in ctx.nearby_players:
        if other.armor_tier == "none" or other.food_level < 10:
            return IntentResult(
                intent=Intent.HELP_STRAGGLERS,
                target_player=other.name,
                urgency=0.7,
                reason=f"The Star helps {other.name}",
            )

    # Rebuild after destruction
    if brain.rng.random() < 0.3:
        return IntentResult(
            intent=Intent.REBUILD,
            urgency=0.5,
            reason="The Star restores what was lost",
        )

    # Trade resources to those who need them
    if player.diamond_count > 2 or player.blaze_rod_count > 2:
        return IntentResult(
            intent=Intent.TRADE,
            urgency=0.6,
            reason="The Star shares their abundance",
        )

    # Default: stay with the group
    return IntentResult(
        intent=Intent.SHARE_SPACE,
        urgency=0.4,
        reason="The Star watches over the party",
    )


# ==================== CARD DECISION MAP ====================

CARD_DECISION_MAP: dict = {
    TarotCard.FOOL: decide_as_fool,
    TarotCard.MAGICIAN: decide_as_magician,
    TarotCard.HERMIT: decide_as_hermit,
    TarotCard.EMPEROR: decide_as_emperor,
    TarotCard.DEVIL: decide_as_devil,
    TarotCard.TOWER: decide_as_tower,
    TarotCard.DEATH: decide_as_death,
    TarotCard.LOVERS: decide_as_lovers,
    TarotCard.STAR: decide_as_star,
}


def describe_tarot_behavior(card: TarotCard) -> str:
    """Get a human-readable description of tarot behavior for Eris."""
    descriptions = {
        TarotCard.FOOL: "reckless explorer, chases the unknown",
        TarotCard.MAGICIAN: "efficient optimizer, builds farms and exploits",
        TarotCard.HERMIT: "isolated loner, hides from others",
        TarotCard.EMPEROR: "territorial builder, creates order",
        TarotCard.DEVIL: "resource hoarder, controls access",
        TarotCard.TOWER: "chaotic destroyer, brings ruin",
        TarotCard.DEATH: "fearless rusher, embraces transformation",
        TarotCard.LOVERS: "devoted partner, follows one person",
        TarotCard.STAR: "selfless helper, rescues the weak",
    }
    return descriptions.get(card, "unknown archetype")
