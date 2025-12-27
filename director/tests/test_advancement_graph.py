"""Tests for advancement progression validation."""

import pytest

from eris.validation.advancement_graph import (
    ADVANCEMENT_GRAPH,
    PREREQUISITES,
    find_missing_prerequisites,
    get_prerequisites,
    is_valid_progression,
)


class TestAdvancementGraph:
    """Test the advancement DAG structure."""

    def test_graph_not_empty(self):
        """Graph should have entries."""
        assert len(ADVANCEMENT_GRAPH) > 0

    def test_prerequisites_built(self):
        """Prerequisites dict should be auto-built from graph."""
        assert len(PREREQUISITES) > 0

    def test_kill_dragon_has_prerequisite(self):
        """Kill dragon should require enter_the_end."""
        assert PREREQUISITES["minecraft:end/kill_dragon"] == "minecraft:story/enter_the_end"

    def test_enter_nether_has_prerequisite(self):
        """Enter nether should require form_obsidian."""
        assert PREREQUISITES["minecraft:story/enter_the_nether"] == "minecraft:story/form_obsidian"


class TestIsValidProgression:
    """Test the is_valid_progression function."""

    def test_valid_full_speedrun_path(self):
        """Complete valid speedrun progression."""
        path = [
            "minecraft:story/mine_stone",
            "minecraft:story/upgrade_tools",
            "minecraft:story/smelt_iron",
            "minecraft:story/lava_bucket",
            "minecraft:story/form_obsidian",
            "minecraft:story/enter_the_nether",
            "minecraft:nether/obtain_blaze_rod",
            "minecraft:story/follow_ender_eye",
            "minecraft:story/enter_the_end",
            "minecraft:end/kill_dragon",
        ]
        assert is_valid_progression(path)

    def test_valid_with_extra_advancements(self):
        """Valid path with non-tracked advancements mixed in."""
        path = [
            "minecraft:story/mine_stone",
            "minecraft:adventure/kill_a_mob",  # Not in DAG, ignored
            "minecraft:story/upgrade_tools",
            "minecraft:husbandry/breed_an_animal",  # Not in DAG, ignored
            "minecraft:story/smelt_iron",
        ]
        assert is_valid_progression(path)

    def test_valid_partial_path(self):
        """Valid partial progression (not complete run)."""
        path = [
            "minecraft:story/mine_stone",
            "minecraft:story/upgrade_tools",
            "minecraft:story/smelt_iron",
        ]
        assert is_valid_progression(path)

    def test_invalid_skip_to_end(self):
        """Can't enter end without the prerequisite chain."""
        path = [
            "minecraft:story/mine_stone",
            "minecraft:story/enter_the_end",  # Skipped entire nether!
        ]
        assert not is_valid_progression(path)

    def test_invalid_blaze_before_nether(self):
        """Can't get blaze rod before entering nether."""
        path = [
            "minecraft:nether/obtain_blaze_rod",
            "minecraft:story/enter_the_nether",
        ]
        assert not is_valid_progression(path)

    def test_invalid_nether_before_obsidian(self):
        """Can't enter nether without forming obsidian."""
        path = [
            "minecraft:story/mine_stone",
            "minecraft:story/enter_the_nether",  # Missing obsidian!
        ]
        assert not is_valid_progression(path)

    def test_empty_path_is_valid(self):
        """Empty path is valid (nothing to validate)."""
        assert is_valid_progression([])

    def test_single_root_advancement_valid(self):
        """Single root advancement is valid."""
        path = ["minecraft:story/mine_stone"]
        assert is_valid_progression(path)

    def test_untracked_advancements_only(self):
        """Path with only untracked advancements is valid."""
        path = [
            "minecraft:adventure/kill_a_mob",
            "minecraft:husbandry/breed_an_animal",
            "minecraft:adventure/adventuring_time",
        ]
        assert is_valid_progression(path)


class TestGetPrerequisites:
    """Test the get_prerequisites function."""

    def test_kill_dragon_full_chain(self):
        """Kill dragon should have full prerequisite chain."""
        prereqs = get_prerequisites("minecraft:end/kill_dragon")
        assert "minecraft:story/enter_the_end" in prereqs
        assert "minecraft:story/follow_ender_eye" in prereqs
        assert "minecraft:nether/obtain_blaze_rod" in prereqs
        assert "minecraft:story/enter_the_nether" in prereqs
        assert "minecraft:story/form_obsidian" in prereqs
        assert "minecraft:story/mine_stone" in prereqs

    def test_enter_nether_chain(self):
        """Enter nether should have its prerequisite chain."""
        prereqs = get_prerequisites("minecraft:story/enter_the_nether")
        assert "minecraft:story/form_obsidian" in prereqs
        assert "minecraft:story/lava_bucket" in prereqs
        assert "minecraft:story/smelt_iron" in prereqs

    def test_root_advancement_no_prerequisites(self):
        """Root advancement should have no prerequisites."""
        prereqs = get_prerequisites("minecraft:story/mine_stone")
        assert len(prereqs) == 0

    def test_untracked_advancement_no_prerequisites(self):
        """Untracked advancement should have no prerequisites."""
        prereqs = get_prerequisites("minecraft:adventure/kill_a_mob")
        assert len(prereqs) == 0


class TestFindMissingPrerequisites:
    """Test the find_missing_prerequisites function."""

    def test_valid_path_no_missing(self):
        """Valid path should have no missing prerequisites."""
        path = [
            "minecraft:story/mine_stone",
            "minecraft:story/upgrade_tools",
            "minecraft:story/smelt_iron",
        ]
        missing = find_missing_prerequisites(path)
        assert len(missing) == 0

    def test_skip_to_end_identifies_missing(self):
        """Should identify missing prerequisite when skipping to end."""
        path = [
            "minecraft:story/mine_stone",
            "minecraft:story/enter_the_end",
        ]
        missing = find_missing_prerequisites(path)
        assert "minecraft:story/enter_the_end" in missing
        assert missing["minecraft:story/enter_the_end"] == "minecraft:story/follow_ender_eye"

    def test_blaze_before_nether_identifies_missing(self):
        """Should identify nether as missing for blaze rod."""
        path = [
            "minecraft:nether/obtain_blaze_rod",
        ]
        missing = find_missing_prerequisites(path)
        assert "minecraft:nether/obtain_blaze_rod" in missing
        assert missing["minecraft:nether/obtain_blaze_rod"] == "minecraft:story/enter_the_nether"

    def test_multiple_missing(self):
        """Should identify multiple missing prerequisites."""
        path = [
            "minecraft:story/upgrade_tools",  # Missing mine_stone
            "minecraft:story/enter_the_nether",  # Missing form_obsidian
        ]
        missing = find_missing_prerequisites(path)
        assert "minecraft:story/upgrade_tools" in missing
        assert "minecraft:story/enter_the_nether" in missing
