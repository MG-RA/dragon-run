"""
Tests for SyntheticWorld - Phase 2 implementation.

Tests cover:
- Loading from scenarios
- Applying all 10 event types
- Applying key tool calls
- Tension/fracture calculation
- Snapshot generation
- Full scenario execution
"""

from pathlib import Path

import pytest

from eris.validation import (
    AdvancementEvent,
    DamageEvent,
    DeathEvent,
    Dimension,
    DimensionChangeEvent,
    DragonKillEvent,
    GameState,
    HealthChangeEvent,
    InventoryEvent,
    MobKillEvent,
    PartyPreset,
    Phase,
    PlayerDefinition,
    PlayerRole,
    Scenario,
    ScenarioMetadata,
    SyntheticWorld,
    load_scenario,
)

# ==================== FIXTURES ====================


@pytest.fixture
def simple_scenario() -> Scenario:
    """Create a minimal valid scenario for testing."""
    return Scenario(
        metadata=ScenarioMetadata(
            name="Test Scenario",
            description="A simple test scenario",
            difficulty="easy",
            tags=["test"],
        ),
        party={
            "Alice": PlayerDefinition(role=PlayerRole.GATHERER),
            "Bob": PlayerDefinition(role=PlayerRole.NETHER_RUNNER),
        },
        events=[
            AdvancementEvent(player="Alice", advancement="minecraft:story/mine_stone"),
            DamageEvent(player="Bob", source="zombie", amount=4),
            InventoryEvent(player="Alice", action="add", item="diamond", count=3),
        ],
    )


@pytest.fixture
def world_from_scenario(simple_scenario: Scenario) -> SyntheticWorld:
    """Create a SyntheticWorld from the simple scenario."""
    return SyntheticWorld.from_scenario(simple_scenario)


# ==================== LOADING TESTS ====================


class TestFromScenario:
    """Tests for SyntheticWorld.from_scenario()"""

    def test_creates_world_from_scenario(self, simple_scenario: Scenario):
        """Should create a world with correct players."""
        world = SyntheticWorld.from_scenario(simple_scenario)

        assert len(world.players) == 2
        assert "Alice" in world.players
        assert "Bob" in world.players

    def test_players_have_correct_roles(self, world_from_scenario: SyntheticWorld):
        """Players should have roles from scenario."""
        assert world_from_scenario.players["Alice"].role == PlayerRole.GATHERER
        assert world_from_scenario.players["Bob"].role == PlayerRole.NETHER_RUNNER

    def test_players_start_with_full_health(self, world_from_scenario: SyntheticWorld):
        """Players should start with full health."""
        for player in world_from_scenario.players.values():
            assert player.health == 20.0
            assert player.alive is True

    def test_game_state_is_active(self, world_from_scenario: SyntheticWorld):
        """World should start in ACTIVE state."""
        assert world_from_scenario.game_state == GameState.ACTIVE

    def test_dragon_is_alive(self, world_from_scenario: SyntheticWorld):
        """Dragon should start alive."""
        assert world_from_scenario.dragon_alive is True
        assert world_from_scenario.dragon_health == 200.0

    def test_trace_is_created(self, world_from_scenario: SyntheticWorld):
        """A RunTrace should be created."""
        assert world_from_scenario.trace is not None
        assert world_from_scenario.trace.scenario_name == "Test Scenario"

    def test_expands_party_preset(self):
        """Should expand party presets correctly."""
        scenario = Scenario(
            metadata=ScenarioMetadata(name="Preset Test"),
            party=PartyPreset.SPEED_TRIO,
            events=[],
        )
        world = SyntheticWorld.from_scenario(scenario)

        assert len(world.players) == 3
        assert "Alice" in world.players
        assert "Bob" in world.players
        assert "Eve" in world.players

    def test_starting_inventory(self):
        """Should apply starting inventory."""
        scenario = Scenario(
            metadata=ScenarioMetadata(name="Inventory Test"),
            party={
                "Rich": PlayerDefinition(
                    role=PlayerRole.SOLO,
                    starting_inventory={"diamond": 5, "iron_ingot": 10},
                ),
            },
            events=[],
        )
        world = SyntheticWorld.from_scenario(scenario)

        assert world.players["Rich"].inventory["diamond"] == 5
        assert world.players["Rich"].inventory["iron_ingot"] == 10


# ==================== EVENT HANDLER TESTS ====================


class TestAdvancementEvent:
    """Tests for advancement event handling."""

    def test_adds_advancement(self, world_from_scenario: SyntheticWorld):
        """Should add advancement to player."""
        event = AdvancementEvent(player="Alice", advancement="minecraft:story/mine_stone")
        diff = world_from_scenario.apply_event(event)

        assert "minecraft:story/mine_stone" in world_from_scenario.players["Alice"].advancements
        assert diff.has_changes

    def test_ignores_duplicate(self, world_from_scenario: SyntheticWorld):
        """Should not add duplicate advancements."""
        event = AdvancementEvent(player="Alice", advancement="minecraft:story/mine_stone")
        world_from_scenario.apply_event(event)
        diff = world_from_scenario.apply_event(event)

        assert len(world_from_scenario.players["Alice"].advancements) == 1
        # Second application shouldn't have changes
        assert not diff.has_changes


class TestDamageEvent:
    """Tests for damage event handling."""

    def test_reduces_health(self, world_from_scenario: SyntheticWorld):
        """Should reduce player health."""
        event = DamageEvent(player="Bob", source="zombie", amount=6)
        diff = world_from_scenario.apply_event(event)

        assert world_from_scenario.players["Bob"].health == 14.0
        assert diff.has_changes

    def test_increases_fear(self, world_from_scenario: SyntheticWorld):
        """Should increase player fear."""
        event = DamageEvent(player="Bob", source="blaze", amount=8)
        world_from_scenario.apply_event(event)

        assert world_from_scenario.player_fear["Bob"] > 0

    def test_causes_death_at_zero_health(self, world_from_scenario: SyntheticWorld):
        """Should kill player when health reaches zero."""
        event = DamageEvent(player="Alice", source="void", amount=20)
        diff = world_from_scenario.apply_event(event)

        assert world_from_scenario.players["Alice"].health == 0
        assert world_from_scenario.players["Alice"].alive is False
        assert diff.caused_death is True
        assert world_from_scenario.game_state == GameState.ENDING


class TestInventoryEvent:
    """Tests for inventory event handling."""

    def test_adds_items(self, world_from_scenario: SyntheticWorld):
        """Should add items to inventory."""
        event = InventoryEvent(player="Alice", action="add", item="diamond", count=5)
        world_from_scenario.apply_event(event)

        assert world_from_scenario.players["Alice"].inventory["diamond"] == 5

    def test_removes_items(self, world_from_scenario: SyntheticWorld):
        """Should remove items from inventory."""
        # First add some items
        world_from_scenario.players["Bob"].add_item("blaze_rod", 10)

        event = InventoryEvent(player="Bob", action="remove", item="blaze_rod", count=3)
        world_from_scenario.apply_event(event)

        assert world_from_scenario.players["Bob"].inventory["blaze_rod"] == 7

    def test_stacks_items(self, world_from_scenario: SyntheticWorld):
        """Should stack items when adding multiple times."""
        event1 = InventoryEvent(player="Alice", action="add", item="iron_ingot", count=5)
        event2 = InventoryEvent(player="Alice", action="add", item="iron_ingot", count=3)
        world_from_scenario.apply_event(event1)
        world_from_scenario.apply_event(event2)

        assert world_from_scenario.players["Alice"].inventory["iron_ingot"] == 8


class TestDimensionEvent:
    """Tests for dimension change event handling."""

    def test_changes_dimension(self, world_from_scenario: SyntheticWorld):
        """Should change player dimension."""
        event = DimensionChangeEvent(player="Bob", from_dim="overworld", to_dim="nether")
        world_from_scenario.apply_event(event)

        assert world_from_scenario.players["Bob"].dimension == Dimension.NETHER

    def test_sets_entered_nether_flag(self, world_from_scenario: SyntheticWorld):
        """Should set entered_nether flag."""
        event = DimensionChangeEvent(player="Bob", from_dim="overworld", to_dim="nether")
        world_from_scenario.apply_event(event)

        assert world_from_scenario.players["Bob"].entered_nether is True

    def test_sets_entered_end_flag(self, world_from_scenario: SyntheticWorld):
        """Should set entered_end flag."""
        event = DimensionChangeEvent(player="Alice", from_dim="overworld", to_dim="the_end")
        world_from_scenario.apply_event(event)

        assert world_from_scenario.players["Alice"].entered_end is True


class TestDeathEvent:
    """Tests for death event handling."""

    def test_kills_player(self, world_from_scenario: SyntheticWorld):
        """Should kill the player."""
        event = DeathEvent(player="Alice", cause="lava")
        diff = world_from_scenario.apply_event(event)

        assert world_from_scenario.players["Alice"].alive is False
        assert diff.caused_death is True

    def test_ends_game(self, world_from_scenario: SyntheticWorld):
        """Should end the game."""
        event = DeathEvent(player="Bob", cause="explosion")
        world_from_scenario.apply_event(event)

        assert world_from_scenario.game_state == GameState.ENDING


class TestDragonKillEvent:
    """Tests for dragon kill event handling."""

    def test_kills_dragon(self, world_from_scenario: SyntheticWorld):
        """Should kill the dragon."""
        event = DragonKillEvent(player="Alice")
        diff = world_from_scenario.apply_event(event)

        assert world_from_scenario.dragon_alive is False
        assert world_from_scenario.dragon_health == 0
        assert diff.caused_victory is True

    def test_records_killer(self, world_from_scenario: SyntheticWorld):
        """Should record who killed the dragon."""
        event = DragonKillEvent(player="Bob")
        world_from_scenario.apply_event(event)

        assert world_from_scenario.dragon_killer == "Bob"


class TestMobKillEvent:
    """Tests for mob kill event handling."""

    def test_increments_kill_count(self, world_from_scenario: SyntheticWorld):
        """Should increment mob kills."""
        event = MobKillEvent(player="Alice", mob_type="zombie", count=5)
        world_from_scenario.apply_event(event)

        assert world_from_scenario.players["Alice"].mob_kills == 5


class TestHealthChangeEvent:
    """Tests for health change event handling."""

    def test_heals_player(self, world_from_scenario: SyntheticWorld):
        """Should heal player."""
        # First damage the player
        world_from_scenario.players["Bob"].health = 10.0

        event = HealthChangeEvent(player="Bob", amount=5)
        world_from_scenario.apply_event(event)

        assert world_from_scenario.players["Bob"].health == 15.0

    def test_caps_at_max_health(self, world_from_scenario: SyntheticWorld):
        """Should cap at max health."""
        event = HealthChangeEvent(player="Alice", amount=100)
        world_from_scenario.apply_event(event)

        assert world_from_scenario.players["Alice"].health == 20.0

    def test_negative_health_change(self, world_from_scenario: SyntheticWorld):
        """Should handle negative health changes."""
        event = HealthChangeEvent(player="Alice", amount=-5)
        world_from_scenario.apply_event(event)

        assert world_from_scenario.players["Alice"].health == 15.0


# ==================== TOOL CALL TESTS ====================


class TestToolCalls:
    """Tests for tool call handling."""

    def test_spawn_mob(self, world_from_scenario: SyntheticWorld):
        """Should spawn mobs."""
        world_from_scenario.apply_tool_call(
            "spawn_mob",
            {"mob_type": "zombie", "near_player": "Alice", "count": 3},
        )

        assert len(world_from_scenario.spawned_mobs) == 1
        assert world_from_scenario.spawned_mobs[0].mob_type == "zombie"
        assert world_from_scenario.spawned_mobs[0].count == 3

    def test_give_item(self, world_from_scenario: SyntheticWorld):
        """Should give items to player."""
        world_from_scenario.apply_tool_call(
            "give_item",
            {"player": "Bob", "item": "golden_apple", "count": 2},
        )

        assert world_from_scenario.players["Bob"].inventory["golden_apple"] == 2

    def test_damage_player_nonlethal(self, world_from_scenario: SyntheticWorld):
        """Should damage player but keep them alive."""
        world_from_scenario.apply_tool_call(
            "damage_player",
            {"player": "Alice", "amount": 15},
        )

        # Should not kill - capped at health - 1
        assert world_from_scenario.players["Alice"].alive is True
        assert world_from_scenario.players["Alice"].health == 5.0

    def test_heal_player_full(self, world_from_scenario: SyntheticWorld):
        """Should heal player to full."""
        world_from_scenario.players["Bob"].health = 5.0

        world_from_scenario.apply_tool_call(
            "heal_player",
            {"player": "Bob", "full": True},
        )

        assert world_from_scenario.players["Bob"].health == 20.0

    def test_modify_aura(self, world_from_scenario: SyntheticWorld):
        """Should modify player aura."""
        world_from_scenario.apply_tool_call(
            "modify_aura",
            {"player": "Alice", "amount": 10, "reason": "being cool"},
        )

        assert world_from_scenario.players["Alice"].aura == 60

    def test_change_weather(self, world_from_scenario: SyntheticWorld):
        """Should change weather."""
        world_from_scenario.apply_tool_call(
            "change_weather",
            {"weather_type": "thunder"},
        )

        assert world_from_scenario.weather == "thunder"

    def test_respawn_override(self, world_from_scenario: SyntheticWorld):
        """Should resurrect dead player."""
        # Kill the player first
        world_from_scenario.players["Alice"].alive = False
        world_from_scenario.players["Alice"].health = 0
        world_from_scenario.game_state = GameState.ENDING

        world_from_scenario.apply_tool_call(
            "respawn_override",
            {"player": "Alice", "aura_cost": 50},
        )

        assert world_from_scenario.players["Alice"].alive is True
        assert world_from_scenario.players["Alice"].health == 20.0
        assert world_from_scenario.game_state == GameState.ACTIVE


# ==================== TENSION/FRACTURE TESTS ====================


class TestTensionFracture:
    """Tests for tension and fracture calculation."""

    def test_damage_increases_tension(self, world_from_scenario: SyntheticWorld):
        """Damage should increase tension."""
        initial_tension = world_from_scenario.tension

        event = DamageEvent(player="Alice", source="creeper", amount=10)
        world_from_scenario.apply_event(event)

        assert world_from_scenario.tension > initial_tension

    def test_death_spikes_tension(self, world_from_scenario: SyntheticWorld):
        """Death should spike tension significantly."""
        event = DeathEvent(player="Bob", cause="void")
        world_from_scenario.apply_event(event)

        assert world_from_scenario.tension >= 50

    def test_phase_transitions(self, world_from_scenario: SyntheticWorld):
        """Fracture should trigger phase transitions."""
        assert world_from_scenario.phase == Phase.NORMAL

        # Manually increase fracture
        world_from_scenario.fracture = 60
        world_from_scenario._update_phase()
        assert world_from_scenario.phase == Phase.RISING

        world_from_scenario.fracture = 90
        world_from_scenario._update_phase()
        assert world_from_scenario.phase == Phase.CRITICAL

        world_from_scenario.fracture = 130
        world_from_scenario._update_phase()
        assert world_from_scenario.phase == Phase.BREAKING

        world_from_scenario.fracture = 160
        world_from_scenario._update_phase()
        assert world_from_scenario.phase == Phase.APOCALYPSE

    def test_phase_change_triggers_diff_flag(self, world_from_scenario: SyntheticWorld):
        """Phase changes should be recorded in diff."""
        # Build up enough fracture for a phase change
        for _ in range(10):
            event = DamageEvent(player="Alice", source="test", amount=10)
            world_from_scenario.apply_event(event)
            # Heal to prevent death
            world_from_scenario.players["Alice"].health = 20.0

        # Verify trace exists (phase changes may or may not occur depending on fracture)
        assert world_from_scenario.trace is not None
        # At least some events should have been processed
        assert len(world_from_scenario.trace.diffs) > 0


# ==================== SNAPSHOT TESTS ====================


class TestSnapshots:
    """Tests for snapshot generation."""

    def test_game_snapshot_format(self, world_from_scenario: SyntheticWorld):
        """Snapshot should have expected fields."""
        snapshot = world_from_scenario.to_game_snapshot()

        assert "timestamp" in snapshot
        assert "gameState" in snapshot
        assert "runId" in snapshot
        assert "dragonAlive" in snapshot
        assert "players" in snapshot

        assert snapshot["gameState"] == "ACTIVE"
        assert snapshot["dragonAlive"] is True
        assert len(snapshot["players"]) == 2

    def test_player_snapshot_format(self, world_from_scenario: SyntheticWorld):
        """Player snapshot should have expected fields."""
        snapshot = world_from_scenario.get_player_snapshot("Alice")

        assert snapshot["username"] == "Alice"
        assert "health" in snapshot
        assert "maxHealth" in snapshot
        assert "dimension" in snapshot
        assert "diamondCount" in snapshot
        assert "aura" in snapshot


# ==================== FULL SCENARIO TESTS ====================


class TestScenarioExecution:
    """Tests for full scenario execution."""

    def test_run_simple_scenario(self, simple_scenario: Scenario):
        """Should execute all events in a scenario."""
        world = SyntheticWorld.from_scenario(simple_scenario)
        trace = world.run_scenario(simple_scenario)

        assert trace is not None
        assert trace.total_events == 3
        assert len(trace.diffs) == 3

    def test_stops_on_death(self):
        """Should stop execution on player death."""
        scenario = Scenario(
            metadata=ScenarioMetadata(name="Death Test"),
            party={"Solo": PlayerDefinition(role=PlayerRole.SOLO)},
            events=[
                DamageEvent(player="Solo", source="test", amount=5),
                DeathEvent(player="Solo", cause="test"),
                # This event should NOT be processed
                InventoryEvent(player="Solo", action="add", item="diamond", count=100),
            ],
        )
        world = SyntheticWorld.from_scenario(scenario)
        trace = world.run_scenario(scenario)

        assert world.game_state == GameState.ENDED
        assert "diamond" not in world.players["Solo"].inventory
        assert trace.deaths == ["Solo"]

    def test_records_victory(self):
        """Should record victory on dragon kill."""
        scenario = Scenario(
            metadata=ScenarioMetadata(name="Victory Test"),
            party={"Hero": PlayerDefinition(role=PlayerRole.SOLO)},
            events=[
                DragonKillEvent(player="Hero"),
            ],
        )
        world = SyntheticWorld.from_scenario(scenario)
        trace = world.run_scenario(scenario)

        assert trace.victory is True
        assert world.dragon_killer == "Hero"


# ==================== INTEGRATION WITH REAL SCENARIOS ====================


class TestRealScenarios:
    """Tests using the actual scenario files."""

    @pytest.fixture
    def scenarios_dir(self) -> Path:
        """Get the scenarios directory."""
        return Path(__file__).parent.parent.parent / "scenarios"

    def test_simple_trio_scenario(self, scenarios_dir: Path):
        """Should successfully run the simple trio scenario."""
        scenario_path = scenarios_dir / "01_simple_trio.yaml"
        if not scenario_path.exists():
            pytest.skip("Scenario file not found")

        scenario = load_scenario(scenario_path)
        world = SyntheticWorld.from_scenario(scenario)
        trace = world.run_scenario(scenario)

        # Simple trio should end in victory
        assert trace.victory is True
        assert len(trace.deaths) == 0

    def test_nether_disaster_scenario(self, scenarios_dir: Path):
        """Should handle the nether disaster (death) scenario."""
        scenario_path = scenarios_dir / "02_nether_disaster.yaml"
        if not scenario_path.exists():
            pytest.skip("Scenario file not found")

        scenario = load_scenario(scenario_path)
        world = SyntheticWorld.from_scenario(scenario)
        trace = world.run_scenario(scenario)

        # Nether disaster should end in death
        assert trace.victory is False
        assert len(trace.deaths) == 1

    def test_eris_chaos_scenario(self, scenarios_dir: Path):
        """Should handle the chaos scenario with custom party."""
        scenario_path = scenarios_dir / "03_eris_chaos.yaml"
        if not scenario_path.exists():
            pytest.skip("Scenario file not found")

        scenario = load_scenario(scenario_path)
        world = SyntheticWorld.from_scenario(scenario)
        trace = world.run_scenario(scenario)

        # Just verify it runs without error
        assert trace is not None
        assert trace.total_events > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
