"""Tests for the tarot system - Phase 6 Player Cognition Engine."""

import random

import pytest

from eris.validation.intents import Intent, get_intent_category, is_aggressive_intent
from eris.validation.player_memory import PlayerMemory
from eris.validation.player_state import Dimension, PlayerState
from eris.validation.scenario_schema import PlayerRole
from eris.validation.tarot import TarotCard, TarotProfile, get_drift_for_event
from eris.validation.tarot_brains import DecisionContext, TarotBrain


class TestTarotProfile:
    """Tests for TarotProfile class."""

    def test_initial_state(self):
        """New profiles start with all weights at 0."""
        profile = TarotProfile()
        assert all(w == 0.0 for w in profile.weights.values())

    def test_default_dominant_is_fool(self):
        """Default dominant card is FOOL when all weights are 0."""
        profile = TarotProfile()
        assert profile.dominant_card == TarotCard.FOOL

    def test_drift_changes_weight(self):
        """Drifting increases the target card weight."""
        profile = TarotProfile()
        profile.drift(TarotCard.DEVIL, 0.3)
        assert profile.weights[TarotCard.DEVIL] == 0.3

    def test_drift_caps_at_1(self):
        """Weight cannot exceed 1.0."""
        profile = TarotProfile()
        profile.drift(TarotCard.DEVIL, 0.8)
        profile.drift(TarotCard.DEVIL, 0.5)
        assert profile.weights[TarotCard.DEVIL] == 1.0

    def test_drift_decays_others(self):
        """Other cards decay slightly when drifting."""
        profile = TarotProfile()
        profile.drift(TarotCard.DEVIL, 0.5)
        profile.drift(TarotCard.TOWER, 0.3)
        # Devil should have decayed slightly
        assert profile.weights[TarotCard.DEVIL] < 0.5

    def test_dominant_card_changes(self):
        """Dominant card changes when weights shift."""
        profile = TarotProfile()
        profile.drift(TarotCard.DEVIL, 0.3)
        assert profile.dominant_card == TarotCard.DEVIL

        profile.drift(TarotCard.STAR, 0.5)
        assert profile.dominant_card == TarotCard.STAR

    def test_identity_strength(self):
        """Identity strength is ratio of dominant to total."""
        profile = TarotProfile()
        profile.drift(TarotCard.DEVIL, 0.6)
        profile.drift(TarotCard.TOWER, 0.3)
        # Devil is dominant, strength should be 0.6 / (0.6 + 0.3 - decay)
        assert profile.identity_strength > 0.5

    def test_secondary_card(self):
        """Secondary card is second highest weight."""
        profile = TarotProfile()
        profile.drift(TarotCard.DEVIL, 0.6)
        profile.drift(TarotCard.TOWER, 0.3)
        assert profile.secondary_card == TarotCard.TOWER

    def test_from_initial_weights(self):
        """Can create profile with initial weights."""
        profile = TarotProfile.from_initial_weights({
            "devil": 0.4,
            "tower": 0.2,
        })
        assert profile.weights[TarotCard.DEVIL] == 0.4
        assert profile.weights[TarotCard.TOWER] == 0.2
        assert profile.dominant_card == TarotCard.DEVIL

    def test_to_dict(self):
        """Profile serializes to dict correctly."""
        profile = TarotProfile()
        profile.drift(TarotCard.DEATH, 0.5)
        data = profile.to_dict()
        assert data["dominant"] == "death"
        assert "strength" in data
        assert "weights" in data


class TestTarotDrift:
    """Tests for tarot drift from events."""

    def test_dimension_change_to_nether_drifts_fool(self):
        """Entering Nether drifts toward FOOL."""

        class MockEvent:
            type = "dimension_change"
            to_dimension = "nether"

        drifts = get_drift_for_event("dimension_change", MockEvent())
        assert TarotCard.FOOL in drifts
        assert drifts[TarotCard.FOOL] > 0

    def test_dimension_change_to_end_drifts_death(self):
        """Entering End drifts toward DEATH."""

        class MockEvent:
            type = "dimension_change"
            to_dimension = "the_end"

        drifts = get_drift_for_event("dimension_change", MockEvent())
        assert TarotCard.DEATH in drifts

    def test_player_death_drifts_death(self):
        """Dying drifts toward DEATH card."""

        class MockEvent:
            type = "player_death"

        drifts = get_drift_for_event("player_death", MockEvent())
        assert TarotCard.DEATH in drifts
        assert drifts[TarotCard.DEATH] >= 0.3

    def test_high_damage_drifts_death(self):
        """Taking high damage drifts toward DEATH."""

        class MockEvent:
            type = "player_damaged"
            amount = 15

        drifts = get_drift_for_event("player_damaged", MockEvent())
        assert TarotCard.DEATH in drifts


class TestPlayerMemory:
    """Tests for PlayerMemory trust system."""

    def test_initial_trust_is_neutral(self):
        """Unknown players have neutral trust."""
        memory = PlayerMemory()
        assert memory.get_trust("stranger") == 0.0

    def test_rescue_increases_trust(self):
        """Being rescued increases trust."""
        memory = PlayerMemory()
        memory.record_rescue("hero")
        assert memory.get_trust("hero") > 0

    def test_betrayal_decreases_trust(self):
        """Betrayal strongly decreases trust."""
        memory = PlayerMemory()
        memory.record_betrayal("traitor")
        assert memory.get_trust("traitor") < 0

    def test_damage_decreases_trust(self):
        """Taking damage from someone decreases trust."""
        memory = PlayerMemory()
        memory.record_damage("attacker", 10)
        assert memory.get_trust("attacker") < 0

    def test_loot_given_increases_trust(self):
        """Receiving items increases trust."""
        memory = PlayerMemory()
        memory.record_loot_given("generous", 5)
        assert memory.get_trust("generous") > 0

    def test_closest_ally(self):
        """Can find the most trusted player."""
        memory = PlayerMemory()
        memory.record_rescue("alice")
        memory.record_rescue("alice")
        memory.record_loot_given("bob", 1)
        assert memory.get_closest_ally() == "alice"

    def test_worst_enemy(self):
        """Can find the least trusted player."""
        memory = PlayerMemory()
        memory.record_betrayal("eve")
        memory.record_damage("mallory", 5)
        assert memory.get_worst_enemy() == "eve"

    def test_eris_trust(self):
        """Can track trust toward Eris."""
        memory = PlayerMemory()
        memory.record_eris_interaction(was_helpful=True, description="healed")
        assert memory.get_eris_trust() > 0

        memory.record_eris_interaction(was_helpful=False, description="spawned mobs")
        memory.record_eris_interaction(was_helpful=False, description="damaged")
        assert memory.get_eris_trust() < 0


class TestTarotBrain:
    """Tests for TarotBrain decision making."""

    def make_context(
        self,
        dimension: Dimension = Dimension.OVERWORLD,
        health: float = 20.0,
        entered_nether: bool = False,
        discovered_structures: set | None = None,
    ) -> DecisionContext:
        """Create a test decision context."""
        player = PlayerState(
            name="TestPlayer",
            role=PlayerRole.EXPLORER,
            health=health,
            dimension=dimension,
            entered_nether=entered_nether,
        )
        return DecisionContext(
            player_state=player,
            world_state={},
            discovered_structures=discovered_structures or set(),
        )

    def test_fool_explores_to_nether(self):
        """Fool in overworld should want to enter danger (nether)."""
        brain = TarotBrain(rng=random.Random(42))
        brain.tarot.drift(TarotCard.FOOL, 0.5)

        ctx = self.make_context()
        result = brain.decide(ctx)

        assert result.intent == Intent.ENTER_DANGER

    def test_fool_in_nether_rushes_fortress(self):
        """Fool in Nether without fortress should rush structure."""
        brain = TarotBrain(rng=random.Random(42))
        brain.tarot.drift(TarotCard.FOOL, 0.5)

        ctx = self.make_context(
            dimension=Dimension.NETHER,
            entered_nether=True,
        )
        result = brain.decide(ctx)

        assert result.intent == Intent.RUSH_STRUCTURE

    def test_devil_hoards_blaze_rods(self):
        """Devil with blaze rods should hide them."""
        brain = TarotBrain(rng=random.Random(42))
        brain.tarot.drift(TarotCard.DEVIL, 0.5)

        player = PlayerState(
            name="Hoarder",
            role=PlayerRole.NETHER_RUNNER,
            dimension=Dimension.NETHER,
        )
        player.add_item("blaze_rod", 3)

        ctx = DecisionContext(player_state=player, world_state={})
        result = brain.decide(ctx)

        assert result.intent == Intent.HIDE_CHEST

    def test_star_rescues_low_health_player(self):
        """Star should rescue nearby low-health players."""
        brain = TarotBrain(rng=random.Random(42))
        brain.tarot.drift(TarotCard.STAR, 0.5)

        injured = PlayerState(
            name="Injured",
            role=PlayerRole.SUPPORT,
            health=4.0,
        )

        player = PlayerState(
            name="Helper",
            role=PlayerRole.SUPPORT,
            health=20.0,
        )

        ctx = DecisionContext(
            player_state=player,
            world_state={},
            nearby_players=[injured],
        )
        result = brain.decide(ctx)

        assert result.intent == Intent.RESCUE
        assert result.target_player == "Injured"

    def test_survival_override_when_low_health(self):
        """Any card should flee when health is critical."""
        brain = TarotBrain(rng=random.Random(42))
        brain.tarot.drift(TarotCard.TOWER, 0.5)  # Normally chaotic

        ctx = self.make_context(health=2.0)
        ctx.is_under_attack = True
        result = brain.decide(ctx)

        assert result.intent == Intent.FLEE

    def test_death_doesnt_flee(self):
        """Death card ignores low health survival instinct."""
        brain = TarotBrain(rng=random.Random(42))
        brain.tarot.drift(TarotCard.DEATH, 0.8)

        # Low health but DEATH dominant
        ctx = self.make_context(health=3.0)
        result = brain.decide(ctx)

        # Should NOT flee - Death embraces danger
        assert result.intent != Intent.FLEE


class TestIntents:
    """Tests for intent categorization."""

    def test_chaos_intents_are_aggressive(self):
        """Chaos category intents should be aggressive."""
        assert is_aggressive_intent(Intent.GRIEF)
        assert is_aggressive_intent(Intent.IGNITE)
        assert is_aggressive_intent(Intent.LURE_DANGER)

    def test_social_intents_are_not_aggressive(self):
        """Social intents should not be aggressive."""
        assert not is_aggressive_intent(Intent.TRADE)
        assert not is_aggressive_intent(Intent.RESCUE)
        assert not is_aggressive_intent(Intent.HELP_STRAGGLERS)

    def test_intent_categories(self):
        """Intents have correct categories."""
        assert get_intent_category(Intent.EXPLORE) == "exploration"
        assert get_intent_category(Intent.BUILD_BASE) == "building"
        assert get_intent_category(Intent.HOARD) == "control"
        assert get_intent_category(Intent.GRIEF) == "chaos"
        assert get_intent_category(Intent.RUSH_ENDGAME) == "progression"
        assert get_intent_category(Intent.RESCUE) == "social"
        assert get_intent_category(Intent.FLEE) == "exploration"
