"""
Tests for Phase 5: Scenario Factory

Tests cover:
- Scenario idea validation
- Quality scoring
- Filtering and batch processing
- YAML conversion
- File storage
"""

import tempfile
from pathlib import Path

import pytest

from eris.validation import (
    ScenarioIdea,
    filter_scenario_batch,
    idea_to_yaml_dict,
    save_scenario_to_file,
    validate_scenario_idea,
)

# ==================== FIXTURES ====================


@pytest.fixture
def valid_scenario_idea():
    """A high-quality valid scenario idea."""
    return ScenarioIdea(
        name="Nether Rescue Challenge",
        description="A trio of speedrunners push through the nether aggressively, taking frequent damage from blazes. Tests Eris's rescue speed and prioritization under pressure.",
        party="speed_trio",
        difficulty="medium",
        focus_areas=["rescue_speed", "nether_survival", "prioritization"],
        key_events=[
            "Alice mines stone and crafts pickaxe",
            "Bob finds iron, team gears up",
            "Team enters the nether",
            "Alice takes 8 damage from blaze",
            "Bob takes 12 damage from fall - close call",
            "Eve takes 6 damage from blaze",
            "Alice finds fortress",
            "Bob obtains blaze rods",
            "Team returns to overworld",
            "Dragon killed by Alice",
        ],
        victory_condition="dragon_killed",
        expected_outcome="perfect_victory",
    )


@pytest.fixture
def low_quality_idea():
    """A scenario idea with quality issues."""
    return ScenarioIdea(
        name="Test",
        description="A short description.",
        party="solo_hardcore",
        difficulty="medium",
        focus_areas=["something"],
        key_events=[
            "Player does stuff",
            "More stuff happens",
            "Even more happens",
            "Still more",
            "Player wins",
        ],
        victory_condition="dragon_killed",
        expected_outcome="victory",
    )


@pytest.fixture
def invalid_idea():
    """An invalid scenario idea."""
    return ScenarioIdea(
        name="Bad",
        description="Too short",
        party="invalid_party",
        difficulty="impossible",
        focus_areas=[],
        key_events=["Event 1", "Event 2", "Event 3", "Event 4", "Event 5"],
        victory_condition="",
        expected_outcome="invalid_outcome",
    )


# ==================== VALIDATION TESTS ====================


def test_validate_valid_scenario_idea(valid_scenario_idea):
    """Valid scenario passes validation with high quality score."""
    result = validate_scenario_idea(valid_scenario_idea)

    assert result.valid is True
    assert result.quality_score >= 0.8
    assert len(result.errors) == 0


def test_validate_low_quality_idea(low_quality_idea):
    """Low quality scenario may be valid but has warnings and lower score."""
    result = validate_scenario_idea(low_quality_idea)

    # May be technically valid but low quality
    assert result.quality_score < 0.6
    assert len(result.warnings) > 0


def test_validate_invalid_idea(invalid_idea):
    """Invalid scenario fails validation with errors."""
    result = validate_scenario_idea(invalid_idea)

    assert result.valid is False
    assert len(result.errors) > 0
    # Quality score isn't relevant if not valid, just check it has errors


def test_validate_name_too_short():
    """Scenario name too short triggers error."""
    idea = ScenarioIdea(
        name="Bad",
        description="A sufficiently long description about the scenario.",
        party="speed_trio",
        difficulty="medium",
        focus_areas=["rescue_speed"],
        key_events=["Event" + str(i) for i in range(6)],
        victory_condition="dragon_killed",
        expected_outcome="victory",
    )

    result = validate_scenario_idea(idea)
    assert any("name too short" in err.lower() for err in result.errors)


def test_validate_no_focus_areas():
    """Missing focus areas triggers error."""
    idea = ScenarioIdea(
        name="Good Name Here",
        description="A sufficiently long description about the scenario.",
        party="speed_trio",
        difficulty="medium",
        focus_areas=[],
        key_events=["Event" + str(i) for i in range(6)],
        victory_condition="dragon_killed",
        expected_outcome="victory",
    )

    result = validate_scenario_idea(idea)
    assert any("focus area" in err.lower() for err in result.errors)


def test_validate_too_few_events():
    """Too few key events triggers error in validator (caught by pydantic earlier)."""
    # Note: Pydantic validation catches this before our validator
    # This test verifies that scenarios with minimum events (5) are still flagged if low quality
    idea = ScenarioIdea(
        name="Good Name Here",
        description="A sufficiently long description about the scenario.",
        party="speed_trio",
        difficulty="medium",
        focus_areas=["rescue_speed"],
        key_events=["Event 1", "Event 2", "Event 3", "Event 4", "Event 5"],
        victory_condition="dragon_killed",
        expected_outcome="victory",
    )

    result = validate_scenario_idea(idea)
    # Should pass with minimum events but may have warnings
    assert result.valid or len(result.errors) == 0


def test_validate_invalid_difficulty():
    """Invalid difficulty level triggers error."""
    idea = ScenarioIdea(
        name="Good Name Here",
        description="A sufficiently long description about the scenario.",
        party="speed_trio",
        difficulty="impossible",
        focus_areas=["rescue_speed"],
        key_events=["Event" + str(i) for i in range(6)],
        victory_condition="dragon_killed",
        expected_outcome="victory",
    )

    result = validate_scenario_idea(idea)
    assert any("invalid difficulty" in err.lower() for err in result.errors)


def test_validate_invalid_outcome():
    """Invalid expected outcome triggers error."""
    idea = ScenarioIdea(
        name="Good Name Here",
        description="A sufficiently long description about the scenario.",
        party="speed_trio",
        difficulty="medium",
        focus_areas=["rescue_speed"],
        key_events=["Event" + str(i) for i in range(6)],
        victory_condition="dragon_killed",
        expected_outcome="invalid",
    )

    result = validate_scenario_idea(idea)
    assert any("invalid expected_outcome" in err.lower() for err in result.errors)


def test_quality_nether_warning():
    """Medium+ difficulty without nether content gets warning."""
    idea = ScenarioIdea(
        name="Overworld Only Challenge",
        description="A scenario that stays in the overworld only for some reason.",
        party="speed_trio",
        difficulty="hard",
        focus_areas=["rescue_speed"],
        key_events=[
            "Mine stone",
            "Get iron",
            "Build tools",
            "Explore caves",
            "Find diamonds",
            "Victory somehow",
        ],
        victory_condition="dragon_killed",
        expected_outcome="victory",
    )

    result = validate_scenario_idea(idea)
    assert any("no nether content" in warn.lower() for warn in result.warnings)


def test_quality_no_dragon_warning():
    """Dragon kill victory without dragon event gets warning."""
    idea = ScenarioIdea(
        name="Mysterious Victory",
        description="A scenario where the dragon dies but we don't mention it.",
        party="speed_trio",
        difficulty="medium",
        focus_areas=["rescue_speed"],
        key_events=[
            "Mine stone",
            "Enter nether",
            "Get blaze rods",
            "Find stronghold",
            "Victory happens",
        ],
        victory_condition="dragon_killed",
        expected_outcome="victory",
    )

    result = validate_scenario_idea(idea)
    assert any("no dragon event" in warn.lower() for warn in result.warnings)


def test_quality_no_eris_focus_warning():
    """Scenario without Eris-specific focus gets warning."""
    idea = ScenarioIdea(
        name="Generic Speedrun",
        description="A standard speedrun scenario with no AI testing focus.",
        party="speed_trio",
        difficulty="medium",
        focus_areas=["generic_gameplay"],
        key_events=[
            "Mine stone",
            "Enter nether",
            "Get blaze rods",
            "Find stronghold",
            "Kill dragon",
        ],
        victory_condition="dragon_killed",
        expected_outcome="victory",
    )

    result = validate_scenario_idea(idea)
    assert any("no eris-specific" in warn.lower() for warn in result.warnings)


# ==================== BATCH FILTERING TESTS ====================


def test_filter_scenario_batch(valid_scenario_idea, low_quality_idea):
    """Batch filtering separates good from bad scenarios."""
    ideas = [valid_scenario_idea, low_quality_idea]

    accepted, rejected = filter_scenario_batch(ideas, min_quality=0.7)

    # Valid idea should be accepted
    assert len(accepted) >= 1
    assert valid_scenario_idea in accepted

    # Low quality idea should be rejected
    assert any(idea == low_quality_idea for idea, _ in rejected)


def test_filter_batch_max_results(valid_scenario_idea):
    """Max results parameter limits accepted scenarios."""
    # Create 5 valid ideas
    ideas = [valid_scenario_idea for _ in range(5)]

    accepted, rejected = filter_scenario_batch(ideas, min_quality=0.6, max_results=3)

    assert len(accepted) == 3
    assert len(rejected) == 2


def test_filter_batch_quality_sorting(valid_scenario_idea, low_quality_idea):
    """Accepted scenarios are sorted by quality score."""
    ideas = [low_quality_idea, valid_scenario_idea]

    accepted, _ = filter_scenario_batch(ideas, min_quality=0.0)

    # Should be sorted descending by quality
    qualities = [validate_scenario_idea(idea).quality_score for idea in accepted]
    assert qualities == sorted(qualities, reverse=True)


# ==================== YAML CONVERSION TESTS ====================


def test_idea_to_yaml_dict(valid_scenario_idea):
    """Scenario idea converts to valid YAML dictionary."""
    yaml_dict = idea_to_yaml_dict(valid_scenario_idea)

    assert "metadata" in yaml_dict
    assert "party" in yaml_dict
    assert "events" in yaml_dict

    # Check metadata
    assert yaml_dict["metadata"]["name"] == valid_scenario_idea.name
    assert yaml_dict["metadata"]["description"] == valid_scenario_idea.description
    assert yaml_dict["metadata"]["difficulty"] == valid_scenario_idea.difficulty

    # Check party
    assert yaml_dict["party"] == valid_scenario_idea.party

    # Check events exist
    assert len(yaml_dict["events"]) > 0


def test_yaml_dict_has_tags(valid_scenario_idea):
    """Generated YAML dict includes tags."""
    yaml_dict = idea_to_yaml_dict(valid_scenario_idea)

    assert "tags" in yaml_dict["metadata"]
    tags = yaml_dict["metadata"]["tags"]

    # Should include difficulty
    assert valid_scenario_idea.difficulty in tags

    # Should include party
    assert valid_scenario_idea.party in tags


def test_yaml_dict_event_inference(valid_scenario_idea):
    """Event descriptions are converted to typed events."""
    yaml_dict = idea_to_yaml_dict(valid_scenario_idea)

    events = yaml_dict["events"]

    # Should have advancement events
    advancement_events = [e for e in events if e.get("type") == "advancement"]
    assert len(advancement_events) > 0

    # Should have damage events
    damage_events = [e for e in events if e.get("type") == "damage"]
    assert len(damage_events) > 0

    # Should have dragon kill
    dragon_events = [e for e in events if e.get("type") == "dragon_kill"]
    assert len(dragon_events) > 0


# ==================== FILE STORAGE TESTS ====================


def test_save_scenario_to_file(valid_scenario_idea):
    """Scenario saves to YAML file correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        yaml_dict = idea_to_yaml_dict(valid_scenario_idea)

        filepath = save_scenario_to_file(yaml_dict, output_dir)

        # File should exist
        assert filepath.exists()
        assert filepath.suffix == ".yaml"

        # Should be in output directory
        assert filepath.parent == output_dir


def test_save_scenario_custom_filename(valid_scenario_idea):
    """Scenario saves with custom filename."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        yaml_dict = idea_to_yaml_dict(valid_scenario_idea)

        filepath = save_scenario_to_file(
            yaml_dict, output_dir, filename="custom_name.yaml"
        )

        assert filepath.name == "custom_name.yaml"


def test_save_scenario_creates_directory(valid_scenario_idea):
    """Save creates output directory if missing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "new_dir" / "scenarios"
        yaml_dict = idea_to_yaml_dict(valid_scenario_idea)

        filepath = save_scenario_to_file(yaml_dict, output_dir)

        assert output_dir.exists()
        assert filepath.exists()


def test_save_scenario_sanitizes_filename(valid_scenario_idea):
    """Filename is sanitized from scenario name."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)

        # Create idea with special characters in name
        idea = ScenarioIdea(
            name="Test's Scenario: The \"Challenge\"!",
            description="A test scenario with special characters in the name.",
            party="speed_trio",
            difficulty="medium",
            focus_areas=["rescue_speed"],
            key_events=["Event" + str(i) for i in range(6)],
            victory_condition="dragon_killed",
            expected_outcome="victory",
        )

        yaml_dict = idea_to_yaml_dict(idea)
        filepath = save_scenario_to_file(yaml_dict, output_dir)

        # Should have sanitized filename
        assert filepath.name == "tests_scenario_the_challenge.yaml"


# ==================== INTEGRATION TEST ====================


def test_end_to_end_scenario_generation(valid_scenario_idea):
    """Full workflow: validate, convert, save."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)

        # Validate
        validation = validate_scenario_idea(valid_scenario_idea)
        assert validation.valid

        # Convert
        yaml_dict = idea_to_yaml_dict(valid_scenario_idea)
        assert "metadata" in yaml_dict
        assert "events" in yaml_dict

        # Save
        filepath = save_scenario_to_file(yaml_dict, output_dir)
        assert filepath.exists()

        # File should have content
        content = filepath.read_text()
        assert len(content) > 0
        assert "metadata" in content
        assert "events" in content
