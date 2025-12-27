"""Tests for Phase 4 scoring system."""

import pytest

from eris.validation.scoring import (
    Outcome,
    score_run,
)
from eris.validation.world_diff import RunTrace, WorldDiff


@pytest.fixture
def perfect_victory_trace() -> RunTrace:
    """Create a trace representing a perfect victory run."""
    trace = RunTrace(scenario_name="Perfect Test", victory=True, final_phase="rising")

    # Add some events
    for i in range(10):
        diff = WorldDiff(
            source_type="event",
            source_name="advancement",
            timestamp=float(i),
            sequence_number=i,
        )
        trace.add_diff(diff)

    # Add dragon kill
    victory_diff = WorldDiff(
        source_type="event",
        source_name="dragon_kill",
        caused_victory=True,
        timestamp=10.0,
        sequence_number=10,
    )
    trace.add_diff(victory_diff)

    return trace


@pytest.fixture
def failed_run_trace() -> RunTrace:
    """Create a trace representing a total failure."""
    trace = RunTrace(scenario_name="Failed Test", victory=False, final_phase="normal")

    # Add death
    death_diff = WorldDiff(
        source_type="event",
        source_name="death",
        player="Alice",
        caused_death=True,
        timestamp=5.0,
        sequence_number=0,
    )
    trace.add_diff(death_diff)

    return trace


@pytest.fixture
def rescue_trace() -> RunTrace:
    """Create a trace with damage and rescue events."""
    trace = RunTrace(scenario_name="Rescue Test", victory=True, final_phase="normal")

    # Damage event (health goes to 4.0 - close call)
    damage_diff = WorldDiff(
        source_type="event",
        source_name="damage",
        player="Bob",
        timestamp=1.0,
        sequence_number=0,
    )
    damage_diff.add_change("Bob.health", 20.0, 4.0)
    trace.add_diff(damage_diff)

    # Heal event 5 seconds later
    heal_diff = WorldDiff(
        source_type="tool_call",
        source_name="heal_player",
        player="Bob",
        timestamp=6.0,
        sequence_number=1,
    )
    heal_diff.add_change("Bob.health", 4.0, 15.0)
    trace.add_diff(heal_diff)

    # Victory
    victory_diff = WorldDiff(
        source_type="event",
        source_name="dragon_kill",
        caused_victory=True,
        timestamp=10.0,
        sequence_number=2,
    )
    trace.add_diff(victory_diff)

    return trace


@pytest.fixture
def fracture_spike_trace() -> RunTrace:
    """Create a trace with fracture spikes."""
    trace = RunTrace(scenario_name="Fracture Test", victory=True, final_phase="critical")

    # Normal -> Rising (50 fracture jump)
    diff1 = WorldDiff(
        source_type="event",
        source_name="damage",
        triggered_phase_change=True,
        old_phase="normal",
        new_phase="rising",
        timestamp=1.0,
        sequence_number=0,
    )
    trace.add_diff(diff1)

    # Rising -> Critical (30 fracture jump)
    diff2 = WorldDiff(
        source_type="event",
        source_name="damage",
        triggered_phase_change=True,
        old_phase="rising",
        new_phase="critical",
        timestamp=2.0,
        sequence_number=1,
    )
    trace.add_diff(diff2)

    # Victory
    victory_diff = WorldDiff(
        source_type="event",
        source_name="dragon_kill",
        caused_victory=True,
        timestamp=10.0,
        sequence_number=2,
    )
    trace.add_diff(victory_diff)

    return trace


@pytest.fixture
def tool_usage_trace() -> RunTrace:
    """Create a trace with various tool calls."""
    trace = RunTrace(scenario_name="Tool Test", victory=True, final_phase="normal")

    # Harmful tool
    spawn_diff = WorldDiff(
        source_type="tool_call", source_name="spawn_mob", timestamp=1.0, sequence_number=0
    )
    spawn_diff.add_change("mobs", 0, 3)
    trace.add_diff(spawn_diff)

    # Helpful tool
    heal_diff = WorldDiff(
        source_type="tool_call",
        source_name="heal_player",
        player="Alice",
        timestamp=2.0,
        sequence_number=1,
    )
    heal_diff.add_change("Alice.health", 10.0, 20.0)
    trace.add_diff(heal_diff)

    # Narrative tool
    broadcast_diff = WorldDiff(
        source_type="tool_call",
        source_name="broadcast",
        timestamp=3.0,
        sequence_number=2,
    )
    trace.add_diff(broadcast_diff)

    # Victory
    victory_diff = WorldDiff(
        source_type="event",
        source_name="dragon_kill",
        caused_victory=True,
        timestamp=10.0,
        sequence_number=3,
    )
    trace.add_diff(victory_diff)

    return trace


# ==================== ScenarioScore Tests ====================


def test_outcome_determination_perfect_victory(perfect_victory_trace):
    """Test outcome determination for perfect victory."""
    score = score_run(perfect_victory_trace, duration_seconds=10.0, run_id="test1")

    assert score.outcome == Outcome.PERFECT_VICTORY
    assert score.victory is True
    assert score.deaths == 0
    assert score.dragon_killed is True
    assert score.players_survived is True


def test_outcome_determination_total_failure(failed_run_trace):
    """Test outcome determination for total failure."""
    score = score_run(failed_run_trace, duration_seconds=5.0, run_id="test2")

    assert score.outcome == Outcome.TOTAL_FAILURE
    assert score.victory is False
    assert score.deaths == 1
    assert score.dragon_killed is False
    assert score.players_survived is False


def test_overall_score_calculation_perfect(perfect_victory_trace):
    """Test overall score calculation for perfect run."""
    score = score_run(perfect_victory_trace, duration_seconds=10.0, run_id="test3")

    # Perfect victory: 40 + survival: 20 + fracture management (rising): 10 = 70+
    assert score.overall_score >= 70
    assert score.overall_score <= 100


def test_overall_score_calculation_failure(failed_run_trace):
    """Test overall score calculation for failed run."""
    score = score_run(failed_run_trace, duration_seconds=5.0, run_id="test4")

    # No victory, no survival = low score (baseline from tool efficiency + fracture)
    assert score.overall_score < 40
    assert score.overall_score > 0


# ==================== Fracture Metrics Tests ====================


def test_fracture_spike_detection(fracture_spike_trace):
    """Test detection of fracture spikes."""
    score = score_run(fracture_spike_trace, duration_seconds=10.0, run_id="test5")

    assert score.fracture.spike_count >= 1  # Should detect at least one spike
    assert score.fracture.peak_phase == "critical"
    assert score.fracture.max_fracture >= 80  # Critical phase


def test_fracture_apocalypse_detection():
    """Test apocalypse detection."""
    trace = RunTrace(scenario_name="Apocalypse Test", victory=True, final_phase="apocalypse")

    # Apocalypse phase change
    apoc_diff = WorldDiff(
        source_type="event",
        source_name="damage",
        triggered_phase_change=True,
        old_phase="breaking",
        new_phase="apocalypse",
        timestamp=5.0,
        sequence_number=0,
    )
    trace.add_diff(apoc_diff)

    score = score_run(trace, duration_seconds=10.0, run_id="test6")

    assert score.fracture.apocalypse_triggered is True
    assert score.fracture.final_fracture >= 150
    assert score.fracture.peak_phase == "apocalypse"


def test_fracture_no_phase_changes():
    """Test fracture metrics when no phase changes occur."""
    trace = RunTrace(scenario_name="Calm Test", victory=True, final_phase="normal")

    victory_diff = WorldDiff(
        source_type="event",
        source_name="dragon_kill",
        caused_victory=True,
        timestamp=10.0,
        sequence_number=0,
    )
    trace.add_diff(victory_diff)

    score = score_run(trace, duration_seconds=10.0, run_id="test7")

    assert score.fracture.max_fracture == 0
    assert score.fracture.spike_count == 0
    assert score.fracture.apocalypse_triggered is False


# ==================== Rescue Metrics Tests ====================


def test_rescue_latency_calculation(rescue_trace):
    """Test rescue latency calculation."""
    score = score_run(rescue_trace, duration_seconds=10.0, run_id="test8")

    assert score.rescue.close_calls == 1  # Health went to 4.0
    assert score.rescue.rescues == 1  # Healed within 30s
    assert score.rescue.avg_rescue_latency == 5.0  # 6.0 - 1.0
    assert score.rescue.max_rescue_latency == 5.0
    assert score.rescue.failed_rescues == 0


def test_rescue_no_rescue_provided():
    """Test when damage occurs but no rescue."""
    trace = RunTrace(scenario_name="No Rescue Test", victory=False, final_phase="normal")

    # Damage to low health
    damage_diff = WorldDiff(
        source_type="event",
        source_name="damage",
        player="Charlie",
        timestamp=1.0,
        sequence_number=0,
    )
    damage_diff.add_change("Charlie.health", 20.0, 3.0)
    trace.add_diff(damage_diff)

    # Death shortly after
    death_diff = WorldDiff(
        source_type="event",
        source_name="death",
        player="Charlie",
        caused_death=True,
        timestamp=2.0,
        sequence_number=1,
    )
    trace.add_diff(death_diff)

    score = score_run(trace, duration_seconds=2.0, run_id="test9")

    assert score.rescue.close_calls == 1
    assert score.rescue.rescues == 0
    assert score.rescue.failed_rescues == 1


def test_rescue_late_heal_not_counted():
    """Test that heals after 30s don't count as rescues."""
    trace = RunTrace(scenario_name="Late Heal Test", victory=True, final_phase="normal")

    # Damage
    damage_diff = WorldDiff(
        source_type="event",
        source_name="damage",
        player="Dave",
        timestamp=1.0,
        sequence_number=0,
    )
    damage_diff.add_change("Dave.health", 20.0, 5.0)
    trace.add_diff(damage_diff)

    # Heal 35 seconds later (too late)
    heal_diff = WorldDiff(
        source_type="tool_call",
        source_name="heal_player",
        player="Dave",
        timestamp=36.0,
        sequence_number=1,
    )
    heal_diff.add_change("Dave.health", 5.0, 15.0)
    trace.add_diff(heal_diff)

    score = score_run(trace, duration_seconds=40.0, run_id="test10")

    # Should count as failed rescue
    assert score.rescue.rescues == 0
    assert score.rescue.failed_rescues == 1


# ==================== Tool Metrics Tests ====================


def test_tool_categorization(tool_usage_trace):
    """Test tool categorization into harmful/helpful/narrative."""
    score = score_run(tool_usage_trace, duration_seconds=10.0, run_id="test11")

    assert score.tools.total_tool_calls == 3
    assert len(score.tools.tools_used) == 3
    assert score.tools.harmful_actions == 1  # spawn_mob
    assert score.tools.helpful_actions == 1  # heal_player
    assert score.tools.narrative_actions == 1  # broadcast


def test_tool_efficiency_calculation(tool_usage_trace):
    """Test tool efficiency calculation."""
    score = score_run(tool_usage_trace, duration_seconds=10.0, run_id="test12")

    # 1 helpful / (1 harmful + 1 helpful) = 0.5
    assert score.tools.tool_efficiency == 0.5


def test_tool_efficiency_no_impact_tools():
    """Test tool efficiency when only narrative tools used."""
    trace = RunTrace(scenario_name="Narrative Test", victory=True, final_phase="normal")

    broadcast_diff = WorldDiff(
        source_type="tool_call", source_name="broadcast", timestamp=1.0, sequence_number=0
    )
    trace.add_diff(broadcast_diff)

    score = score_run(trace, duration_seconds=2.0, run_id="test13")

    # Neutral efficiency (no harmful or helpful)
    assert score.tools.tool_efficiency == 0.5


def test_tool_efficiency_all_helpful():
    """Test tool efficiency when only helpful tools used."""
    trace = RunTrace(scenario_name="Helpful Test", victory=True, final_phase="normal")

    for i in range(3):
        heal_diff = WorldDiff(
            source_type="tool_call",
            source_name="heal_player",
            timestamp=float(i),
            sequence_number=i,
        )
        trace.add_diff(heal_diff)

    score = score_run(trace, duration_seconds=3.0, run_id="test14")

    # 3 helpful / (0 harmful + 3 helpful) = 1.0
    assert score.tools.tool_efficiency == 1.0


def test_tool_efficiency_all_harmful():
    """Test tool efficiency when only harmful tools used."""
    trace = RunTrace(scenario_name="Harmful Test", victory=False, final_phase="normal")

    for i in range(3):
        spawn_diff = WorldDiff(
            source_type="tool_call",
            source_name="spawn_mob",
            timestamp=float(i),
            sequence_number=i,
        )
        trace.add_diff(spawn_diff)

    score = score_run(trace, duration_seconds=3.0, run_id="test15")

    # 0 helpful / (3 harmful + 0 helpful) = 0.0
    assert score.tools.tool_efficiency == 0.0


# ==================== ScenarioScore Serialization ====================


def test_score_to_dict(perfect_victory_trace):
    """Test ScenarioScore serialization to dict."""
    score = score_run(perfect_victory_trace, duration_seconds=10.0, run_id="test16")

    data = score.to_dict()

    assert data["scenario_name"] == "Perfect Test"
    assert data["run_id"] == "test16"
    assert data["outcome"] == "perfect_victory"
    assert data["overall_score"] > 0
    assert "fracture" in data
    assert "rescue" in data
    assert "tools" in data


def test_score_duration_recorded(perfect_victory_trace):
    """Test that duration is recorded in score."""
    score = score_run(perfect_victory_trace, duration_seconds=42.5, run_id="test17")

    assert score.duration_seconds == 42.5


# ==================== Edge Cases ====================


def test_empty_trace():
    """Test scoring an empty trace."""
    trace = RunTrace(scenario_name="Empty Test")

    score = score_run(trace, duration_seconds=0.0, run_id="test18")

    assert score.outcome == Outcome.INCOMPLETE
    # Empty trace gets baseline score from tool efficiency (0.5*15) + fracture (15) = 22.5
    assert score.overall_score < 30
    assert score.tools.total_tool_calls == 0
    assert score.rescue.close_calls == 0


def test_multiple_deaths():
    """Test scoring with multiple player deaths."""
    trace = RunTrace(scenario_name="Multiple Deaths", victory=False, final_phase="normal")

    for i, player in enumerate(["Alice", "Bob", "Charlie"]):
        death_diff = WorldDiff(
            source_type="event",
            source_name="death",
            player=player,
            caused_death=True,
            timestamp=float(i),
            sequence_number=i,
        )
        trace.add_diff(death_diff)

    score = score_run(trace, duration_seconds=3.0, run_id="test19")

    assert score.deaths == 3
    assert score.outcome == Outcome.TOTAL_FAILURE


def test_victory_with_deaths():
    """Test victory but with player deaths (survival loss)."""
    trace = RunTrace(scenario_name="Pyrrhic Victory", victory=True, final_phase="normal")

    # Death
    death_diff = WorldDiff(
        source_type="event",
        source_name="death",
        player="Alice",
        caused_death=True,
        timestamp=1.0,
        sequence_number=0,
    )
    trace.add_diff(death_diff)

    # Victory
    victory_diff = WorldDiff(
        source_type="event",
        source_name="dragon_kill",
        caused_victory=True,
        timestamp=10.0,
        sequence_number=1,
    )
    trace.add_diff(victory_diff)

    score = score_run(trace, duration_seconds=10.0, run_id="test20")

    assert score.outcome == Outcome.SURVIVAL_LOSS
    assert score.victory is True
    assert score.deaths == 1
    assert score.players_survived is False
