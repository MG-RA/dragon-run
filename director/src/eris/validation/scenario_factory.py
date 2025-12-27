"""
Scenario factory for generating, validating, and curating synthetic scenarios.

Workflow:
1. LLM generates scenario ideas
2. Validator filters by quality and correctness
3. Ideas are converted to full YAML scenarios
4. Humans curate the results
5. Gold scenarios are stored in /scenarios/
"""

import logging
from pathlib import Path
from typing import Any

import yaml
from langchain_core.language_models import BaseChatModel

from .scenario_generator import (
    FOCUS_CATEGORIES,
    ScenarioIdea,
    generate_scenario_batch,
)
from .scenario_validator import (
    ValidationResult,
    filter_scenario_batch,
    validate_scenario_file,
)

logger = logging.getLogger(__name__)


def idea_to_yaml_dict(idea: ScenarioIdea) -> dict[str, Any]:
    """Convert a ScenarioIdea to a YAML-serializable dictionary.

    Args:
        idea: Validated scenario idea

    Returns:
        Dictionary ready to be serialized as YAML
    """
    # Convert key events to scenario events
    # This is a simplified conversion - real events would need more detail
    events = []

    for event_desc in idea.key_events:
        # Parse event description to determine type
        desc_lower = event_desc.lower()

        # Attempt to infer event type from description
        if "advancement" in desc_lower or "mines" in desc_lower or "crafts" in desc_lower:
            # Try to extract advancement name
            if "mine_stone" in desc_lower or "pickaxe" in desc_lower:
                events.append(
                    {
                        "type": "advancement",
                        "player": _extract_player_name(event_desc, idea.party),
                        "advancement": "minecraft:story/mine_stone",
                    }
                )
            elif "iron" in desc_lower and "smelt" in desc_lower:
                events.append(
                    {
                        "type": "advancement",
                        "player": _extract_player_name(event_desc, idea.party),
                        "advancement": "minecraft:story/smelt_iron",
                    }
                )
            elif "nether" in desc_lower and "enter" in desc_lower:
                events.append(
                    {
                        "type": "advancement",
                        "player": _extract_player_name(event_desc, idea.party),
                        "advancement": "minecraft:story/enter_the_nether",
                    }
                )
            elif "blaze" in desc_lower and ("rod" in desc_lower or "obtain" in desc_lower):
                events.append(
                    {
                        "type": "advancement",
                        "player": _extract_player_name(event_desc, idea.party),
                        "advancement": "minecraft:nether/obtain_blaze_rod",
                    }
                )
            elif "end" in desc_lower and "enter" in desc_lower:
                events.append(
                    {
                        "type": "advancement",
                        "player": _extract_player_name(event_desc, idea.party),
                        "advancement": "minecraft:story/enter_the_end",
                    }
                )

        if "dragon" in desc_lower and ("kill" in desc_lower or "killed" in desc_lower or "defeat" in desc_lower or "dies" in desc_lower):
            events.append(
                {
                    "type": "dragon_kill",
                    "player": _extract_player_name(event_desc, idea.party),
                }
            )

        elif "damage" in desc_lower or "hurt" in desc_lower or "hit" in desc_lower:
            # Damage event
            damage_amount = _extract_damage_amount(event_desc)
            source = _extract_damage_source(event_desc)
            events.append(
                {
                    "type": "damage",
                    "player": _extract_player_name(event_desc, idea.party),
                    "source": source,
                    "amount": damage_amount,
                }
            )

        elif "chat" in desc_lower or "says" in desc_lower or "message" in desc_lower:
            # Chat event
            events.append(
                {
                    "type": "chat",
                    "player": _extract_player_name(event_desc, idea.party),
                    "message": event_desc.split(":")[-1].strip().strip('"').strip("'"),
                }
            )

        elif "death" in desc_lower or "dies" in desc_lower or "killed" in desc_lower:
            # Death event
            events.append(
                {
                    "type": "death",
                    "player": _extract_player_name(event_desc, idea.party),
                    "cause": _extract_damage_source(event_desc),
                }
            )

        else:
            # Generic chat event as placeholder
            events.append(
                {
                    "type": "chat",
                    "player": _extract_player_name(event_desc, idea.party),
                    "message": event_desc,
                }
            )

    # Build metadata
    metadata = {
        "name": idea.name,
        "description": idea.description,
        "difficulty": idea.difficulty,
        "focus_areas": idea.focus_areas,
        "expected_outcome": idea.expected_outcome,
        "tags": _generate_tags(idea),
    }

    # Build full scenario dict
    scenario_dict = {
        "metadata": metadata,
        "party": idea.party,
        "events": events,
    }

    return scenario_dict


def _extract_player_name(event_desc: str, party: str) -> str:
    """Extract player name from event description."""
    # Common player names in scenarios
    common_names = ["Alice", "Bob", "Eve", "Charlie", "Diana", "Solo", "Player"]

    for name in common_names:
        if name in event_desc:
            return name

    # Default based on party
    if party == "solo_hardcore":
        return "Solo"
    elif party in ["duo_rush", "speed_trio"]:
        return "Alice"  # Default to first player
    else:
        return "Player"


def _extract_damage_amount(event_desc: str) -> int:
    """Extract damage amount from event description."""
    import re

    # Look for patterns like "8 damage", "takes 10", "12 damage"
    match = re.search(r"(\d+)\s*(damage|hp|health)", event_desc.lower())
    if match:
        return min(20, max(1, int(match.group(1))))

    # Default
    return 6


def _extract_damage_source(event_desc: str) -> str:
    """Extract damage source from event description."""
    desc_lower = event_desc.lower()

    sources = {
        "blaze": "blaze",
        "skeleton": "skeleton",
        "zombie": "zombie",
        "fall": "fall",
        "lava": "lava",
        "fire": "fire",
        "enderman": "enderman",
        "dragon": "dragon",
        "void": "void",
        "explosion": "explosion",
    }

    for keyword, source in sources.items():
        if keyword in desc_lower:
            return source

    return "unknown"


def _generate_tags(idea: ScenarioIdea) -> list[str]:
    """Generate tags for scenario categorization."""
    tags = []

    # Add difficulty
    tags.append(idea.difficulty)

    # Add party type
    tags.append(idea.party)

    # Add focus areas
    tags.extend(idea.focus_areas)

    # Add outcome
    tags.append(idea.expected_outcome)

    # Add phase-based tags
    if any(
        word in idea.description.lower()
        for word in ["apocalypse", "fracture", "breaking"]
    ):
        tags.append("high_fracture")

    if any(word in idea.description.lower() for word in ["rescue", "heal", "close call"]):
        tags.append("rescue_critical")

    if "nether" in idea.description.lower():
        tags.append("nether")

    if "end" in idea.description.lower() or "dragon" in idea.description.lower():
        tags.append("end_game")

    return list(set(tags))  # Deduplicate


def save_scenario_to_file(
    scenario_dict: dict[str, Any],
    output_dir: Path | str,
    filename: str | None = None,
) -> Path:
    """Save a scenario dictionary to a YAML file.

    Args:
        scenario_dict: Scenario data as dictionary
        output_dir: Directory to save scenario in
        filename: Optional filename (defaults to sanitized scenario name)

    Returns:
        Path to saved file
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate filename from scenario name if not provided
    if not filename:
        name = scenario_dict.get("metadata", {}).get("name", "scenario")
        # Sanitize filename
        filename = (
            name.lower()
            .replace(" ", "_")
            .replace("-", "_")
            .replace("'", "")
            .replace('"', "")
        )
        filename = "".join(c for c in filename if c.isalnum() or c == "_")
        filename = f"{filename}.yaml"

    filepath = output_dir / filename

    # Save YAML
    with open(filepath, "w", encoding="utf-8") as f:
        yaml.dump(scenario_dict, f, default_flow_style=False, sort_keys=False)

    logger.info(f"Saved scenario to {filepath}")
    return filepath


class ScenarioFactory:
    """Factory for generating and curating scenarios."""

    def __init__(
        self,
        llm: BaseChatModel,
        scenarios_dir: Path | str = "scenarios",
        min_quality: float = 0.6,
    ):
        """Initialize scenario factory.

        Args:
            llm: LangChain chat model for generation
            scenarios_dir: Directory to store generated scenarios
            min_quality: Minimum quality score for acceptance (0.0-1.0)
        """
        self.llm = llm
        self.scenarios_dir = Path(scenarios_dir)
        self.min_quality = min_quality

        # Ensure scenarios directory exists
        self.scenarios_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Initialized ScenarioFactory (scenarios_dir={self.scenarios_dir})")

    async def generate_and_filter(
        self,
        count: int = 10,
        focus: str | None = None,
        difficulty: str | None = None,
    ) -> tuple[list[ScenarioIdea], list[tuple[ScenarioIdea, ValidationResult]]]:
        """Generate scenarios and filter by quality.

        Args:
            count: Number of scenarios to generate
            focus: Optional focus area
            difficulty: Optional difficulty level

        Returns:
            Tuple of (accepted_ideas, rejected_ideas_with_reasons)
        """
        logger.info(
            f"Generating {count} scenarios (focus={focus}, difficulty={difficulty})"
        )

        # Generate ideas
        ideas = await generate_scenario_batch(
            self.llm, count=count, focus=focus, difficulty=difficulty
        )

        # Filter by quality
        accepted, rejected = filter_scenario_batch(
            ideas, min_quality=self.min_quality, max_results=None
        )

        logger.info(
            f"Generated and filtered: {len(accepted)} accepted, {len(rejected)} rejected"
        )

        return accepted, rejected

    def convert_to_yaml(self, idea: ScenarioIdea) -> dict[str, Any]:
        """Convert a scenario idea to YAML-serializable dictionary.

        Args:
            idea: Scenario idea to convert

        Returns:
            Scenario dictionary
        """
        return idea_to_yaml_dict(idea)

    def save_scenario(
        self, idea: ScenarioIdea, filename: str | None = None
    ) -> Path:
        """Convert idea to YAML and save to scenarios directory.

        Args:
            idea: Scenario idea to save
            filename: Optional filename

        Returns:
            Path to saved file
        """
        scenario_dict = self.convert_to_yaml(idea)
        return save_scenario_to_file(self.scenarios_dir, scenario_dict, filename)

    async def generate_library(
        self,
        total_scenarios: int = 50,
        categories: list[str] | None = None,
    ) -> dict[str, list[Path]]:
        """Generate a library of scenarios across multiple categories.

        Args:
            total_scenarios: Total number of scenarios to generate
            categories: Optional list of focus categories (uses all if None)

        Returns:
            Dictionary mapping category -> list of saved scenario paths
        """
        if categories is None:
            categories = FOCUS_CATEGORIES

        scenarios_per_category = max(1, total_scenarios // len(categories))

        logger.info(
            f"Generating scenario library: {total_scenarios} total across {len(categories)} categories"
        )

        results = {}

        for category in categories:
            logger.info(f"Generating {scenarios_per_category} scenarios for '{category}'")

            accepted, rejected = await self.generate_and_filter(
                count=scenarios_per_category * 2,  # Generate 2x, filter to best
                focus=category,
            )

            # Take top scenarios
            top_scenarios = accepted[:scenarios_per_category]

            # Save them
            saved_paths = []
            for idea in top_scenarios:
                try:
                    path = self.save_scenario(idea)
                    saved_paths.append(path)
                except Exception as e:
                    logger.error(f"Failed to save scenario '{idea.name}': {e}")

            results[category] = saved_paths
            logger.info(f"Saved {len(saved_paths)} scenarios for '{category}'")

        total_saved = sum(len(paths) for paths in results.values())
        logger.info(f"Library generation complete: {total_saved} scenarios saved")

        return results

    def list_scenarios(self) -> list[Path]:
        """List all scenarios in the scenarios directory.

        Returns:
            List of scenario file paths
        """
        return sorted(self.scenarios_dir.glob("*.yaml"))

    def validate_all(self) -> dict[str, ValidationResult]:
        """Validate all scenarios in the directory.

        Returns:
            Dictionary mapping filename -> ValidationResult
        """
        scenarios = self.list_scenarios()
        results = {}

        logger.info(f"Validating {len(scenarios)} scenarios")

        for scenario_path in scenarios:
            result = validate_scenario_file(scenario_path)
            results[scenario_path.name] = result

        # Summary
        valid_count = sum(1 for r in results.values() if r.valid)
        avg_quality = (
            sum(r.quality_score for r in results.values()) / len(results)
            if results
            else 0.0
        )

        logger.info(
            f"Validation complete: {valid_count}/{len(scenarios)} valid, avg quality={avg_quality:.2f}"
        )

        return results
