"""
Load and validate synthetic scenarios from YAML files.

Integrates:
- YAML parsing
- Pydantic validation
- Advancement progression validation
- Party preset expansion
"""

import logging
from pathlib import Path
from typing import Any

import yaml

from .advancement_graph import find_missing_prerequisites, is_valid_progression
from .scenario_schema import (
    PARTY_PRESETS,
    PartyPreset,
    Scenario,
)

logger = logging.getLogger(__name__)


class ScenarioValidationError(Exception):
    """Raised when a scenario fails validation."""

    pass


def load_scenario(path: Path | str) -> Scenario:
    """Load and validate a scenario from a YAML file.

    Args:
        path: Path to the scenario YAML file.

    Returns:
        Validated Scenario object with party presets expanded.

    Raises:
        ScenarioValidationError: If validation fails.
        FileNotFoundError: If the file doesn't exist.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Scenario file not found: {path}")

    logger.info(f"Loading scenario from {path}")

    # Load YAML
    with open(path, encoding="utf-8") as f:
        raw_data = yaml.safe_load(f)

    if not raw_data:
        raise ScenarioValidationError("Empty scenario file")

    # Parse with Pydantic
    try:
        scenario = Scenario(**raw_data)
    except Exception as e:
        raise ScenarioValidationError(f"Schema validation failed: {e}") from e

    # Expand party presets
    if isinstance(scenario.party, str):
        try:
            preset = PartyPreset(scenario.party)
            scenario.party = PARTY_PRESETS[preset]
            logger.debug(f"Expanded party preset '{preset}' to {len(scenario.party)} players")
        except ValueError as e:
            raise ScenarioValidationError(
                f"Unknown party preset: {scenario.party}. "
                f"Valid presets: {[p.value for p in PartyPreset]}"
            ) from e

    # Validate advancement progression
    validate_advancement_sequence(scenario)

    # Validate event consistency
    validate_event_consistency(scenario)

    logger.info(
        f"✓ Scenario '{scenario.metadata.name}' validated: "
        f"{len(scenario.party)} players, {len(scenario.events)} events"
    )

    return scenario


def validate_advancement_sequence(scenario: Scenario) -> None:
    """Validate that advancements follow Minecraft's prerequisite graph.

    Args:
        scenario: The scenario to validate.

    Raises:
        ScenarioValidationError: If impossible advancement sequence detected.
    """
    # Group advancements by player
    player_advancements: dict[str, list[str]] = {}

    for event in scenario.events:
        if event.type == "advancement":
            player = event.player
            advancement = event.advancement

            if player not in player_advancements:
                player_advancements[player] = []

            player_advancements[player].append(advancement)

    # Validate each player's progression
    for player, advancements in player_advancements.items():
        if not is_valid_progression(advancements):
            missing = find_missing_prerequisites(advancements)
            errors = [
                f"  - {adv} requires {prereq}" for adv, prereq in missing.items()
            ]
            raise ScenarioValidationError(
                f"Invalid advancement progression for {player}:\n" + "\n".join(errors)
            )


def validate_event_consistency(scenario: Scenario) -> None:
    """Validate event sequence makes sense (basic sanity checks).

    Args:
        scenario: The scenario to validate.

    Raises:
        ScenarioValidationError: If event sequence is inconsistent.
    """
    # Track player deaths
    dead_players: set[str] = set()

    for i, event in enumerate(scenario.events):
        event_player = getattr(event, "player", None)

        # Check if event involves a dead player
        if event_player and event_player in dead_players:
            raise ScenarioValidationError(
                f"Event #{i+1}: {event_player} acts after death at event {event.type}"
            )

        # Mark player as dead
        if event.type == "death":
            dead_players.add(event.player)
            logger.debug(f"Player {event.player} dies at event #{i+1}")

        # Dragon kill should be last event or very near the end
        if event.type == "dragon_kill":
            remaining = len(scenario.events) - i - 1
            if remaining > 3:
                logger.warning(
                    f"Dragon kill at event #{i+1} with {remaining} events remaining"
                )


def load_scenarios_from_directory(directory: Path | str) -> list[Scenario]:
    """Load all scenarios from a directory.

    Args:
        directory: Path to directory containing .yaml/.yml files.

    Returns:
        List of validated scenarios.
    """
    directory = Path(directory)
    if not directory.exists():
        raise FileNotFoundError(f"Scenario directory not found: {directory}")

    scenarios: list[Scenario] = []
    errors: list[tuple[Path, Exception]] = []

    for path in directory.glob("*.yaml"):
        try:
            scenario = load_scenario(path)
            scenarios.append(scenario)
        except Exception as e:
            logger.error(f"Failed to load {path.name}: {e}")
            errors.append((path, e))

    for path in directory.glob("*.yml"):
        try:
            scenario = load_scenario(path)
            scenarios.append(scenario)
        except Exception as e:
            logger.error(f"Failed to load {path.name}: {e}")
            errors.append((path, e))

    logger.info(
        f"Loaded {len(scenarios)} scenarios from {directory} "
        f"({len(errors)} failed)"
    )

    return scenarios


def scenario_to_dict(scenario: Scenario) -> dict[str, Any]:
    """Convert a scenario back to dict for serialization.

    Args:
        scenario: The scenario to convert.

    Returns:
        Dictionary representation suitable for YAML/JSON.
    """
    return scenario.model_dump(mode="json", exclude_none=True)
