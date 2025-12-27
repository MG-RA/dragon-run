"""
Validator for filtering generated scenarios.

Checks:
1. Schema validity (can it be parsed as a Scenario?)
2. Advancement progression (respects Minecraft rules?)
3. Quality metrics (is it interesting and well-formed?)
4. Duplication (is it too similar to existing scenarios?)
"""

import logging
from pathlib import Path

from .advancement_graph import find_missing_prerequisites, is_valid_progression
from .scenario_generator import ScenarioIdea
from .scenario_loader import load_scenario
from .scenario_schema import (
    PartyPreset,
)

logger = logging.getLogger(__name__)


class ValidationResult:
    """Result of scenario validation."""

    def __init__(
        self,
        valid: bool,
        errors: list[str] | None = None,
        warnings: list[str] | None = None,
        quality_score: float = 0.0,
    ):
        self.valid = valid
        self.errors = errors or []
        self.warnings = warnings or []
        self.quality_score = quality_score  # 0.0-1.0

    def __repr__(self) -> str:
        status = "VALID" if self.valid else "INVALID"
        return f"ValidationResult({status}, quality={self.quality_score:.2f}, errors={len(self.errors)}, warnings={len(self.warnings)})"


def validate_scenario_idea(idea: ScenarioIdea) -> ValidationResult:
    """Validate a generated scenario idea before converting to full scenario.

    Performs lightweight validation on the idea structure without full YAML conversion.

    Args:
        idea: Generated scenario idea to validate

    Returns:
        ValidationResult with errors/warnings/quality score
    """
    errors = []
    warnings = []
    quality_score = 1.0

    # Check name
    if not idea.name or len(idea.name) < 5:
        errors.append("Scenario name too short (minimum 5 characters)")
    if len(idea.name) > 60:
        warnings.append("Scenario name very long (may be truncated in displays)")
        quality_score -= 0.05

    # Check description
    if not idea.description or len(idea.description) < 20:
        errors.append("Scenario description too short (minimum 20 characters)")
    if len(idea.description) > 500:
        warnings.append("Description very long (should be 2-3 sentences)")
        quality_score -= 0.05

    # Check party
    valid_presets = [p.value for p in PartyPreset]
    if idea.party not in valid_presets:
        # Could be custom party, check format
        if not idea.party or len(idea.party) < 3:
            errors.append(
                f"Invalid party: '{idea.party}'. Must be a preset ({valid_presets}) or custom composition"
            )

    # Check difficulty
    if idea.difficulty not in ["easy", "medium", "hard", "extreme"]:
        errors.append(
            f"Invalid difficulty: '{idea.difficulty}'. Must be easy/medium/hard/extreme"
        )

    # Check focus areas
    if not idea.focus_areas or len(idea.focus_areas) < 1:
        errors.append("Must have at least 1 focus area")
    if len(idea.focus_areas) > 5:
        warnings.append("Too many focus areas (2-4 recommended)")
        quality_score -= 0.1

    # Check key events
    if not idea.key_events or len(idea.key_events) < 5:
        errors.append("Must have at least 5 key events")
    if len(idea.key_events) > 20:
        warnings.append("Very long event sequence (5-15 recommended)")
        quality_score -= 0.1

    # Check victory condition
    if not idea.victory_condition:
        errors.append("Must specify victory_condition")

    # Check expected outcome
    valid_outcomes = ["perfect_victory", "victory", "survival_loss", "total_failure"]
    if idea.expected_outcome not in valid_outcomes:
        errors.append(
            f"Invalid expected_outcome: '{idea.expected_outcome}'. Must be one of {valid_outcomes}"
        )

    # Quality checks
    # - Does it mention critical advancements?
    key_events_text = " ".join(idea.key_events).lower()
    has_nether = "nether" in key_events_text
    has_dragon = "dragon" in key_events_text or "end" in key_events_text

    if not has_nether and idea.difficulty in ["medium", "hard", "extreme"]:
        warnings.append("No nether content for medium+ difficulty scenario")
        quality_score -= 0.15

    if not has_dragon and idea.victory_condition == "dragon_killed":
        warnings.append("Victory condition is dragon_killed but no dragon event listed")
        quality_score -= 0.2

    # - Does it have narrative tension?
    has_damage = any(
        word in key_events_text
        for word in ["damage", "hurt", "hit", "blaze", "fall", "lava"]
    )

    if not has_damage and idea.difficulty in ["medium", "hard", "extreme"]:
        warnings.append("No damage events for difficulty level (low tension)")
        quality_score -= 0.1

    # - Check for Eris-specific content
    has_eris_focus = any(
        area
        in [
            "rescue_speed",
            "fracture_management",
            "apocalypse_trigger",
            "betrayal_karma",
            "tool_efficiency",
        ]
        for area in idea.focus_areas
    )

    if not has_eris_focus:
        warnings.append("No Eris-specific focus areas (scenario may not test AI behavior)")
        quality_score -= 0.1

    # Final quality score
    quality_score = max(0.0, min(1.0, quality_score))

    valid = len(errors) == 0

    logger.debug(
        f"Validated scenario idea '{idea.name}': valid={valid}, quality={quality_score:.2f}"
    )

    return ValidationResult(
        valid=valid,
        errors=errors,
        warnings=warnings,
        quality_score=quality_score,
    )


def validate_scenario_file(scenario_path: Path | str) -> ValidationResult:
    """Validate a complete scenario YAML file.

    Performs full validation including:
    - YAML syntax
    - Pydantic schema compliance
    - Advancement progression rules
    - Quality metrics

    Args:
        scenario_path: Path to scenario YAML file

    Returns:
        ValidationResult with errors/warnings/quality score
    """
    errors = []
    warnings = []
    quality_score = 1.0

    scenario_path = Path(scenario_path)

    # Check file exists
    if not scenario_path.exists():
        return ValidationResult(
            valid=False, errors=[f"File not found: {scenario_path}"], quality_score=0.0
        )

    # Try to load scenario
    try:
        scenario = load_scenario(scenario_path)
    except Exception as e:
        return ValidationResult(
            valid=False, errors=[f"Failed to load scenario: {e}"], quality_score=0.0
        )

    # Extract advancement events
    advancement_events = [
        event for event in scenario.events if event.get("type") == "advancement"
    ]
    advancement_sequence = [event["advancement"] for event in advancement_events]

    # Validate progression
    if not is_valid_progression(advancement_sequence):
        missing = find_missing_prerequisites(advancement_sequence)
        if missing:
            for adv, prereq in missing.items():
                errors.append(
                    f"Advancement '{adv}' requires '{prereq}' which appears later or is missing"
                )

    # Quality metrics
    # - Event diversity
    event_types = {event.get("type", "unknown") for event in scenario.events}
    if len(event_types) < 3:
        warnings.append(f"Low event diversity ({len(event_types)} unique types)")
        quality_score -= 0.1

    # - Advancement coverage
    if len(advancement_events) < 3:
        warnings.append(f"Very few advancements ({len(advancement_events)} total)")
        quality_score -= 0.15

    # - Has critical path
    critical_advancements = [
        "minecraft:story/enter_the_nether",
        "minecraft:nether/obtain_blaze_rod",
        "minecraft:story/enter_the_end",
        "minecraft:end/kill_dragon",
    ]
    has_critical = [adv in advancement_sequence for adv in critical_advancements]
    critical_coverage = sum(has_critical) / len(critical_advancements)

    if critical_coverage < 0.5:
        warnings.append(
            f"Missing critical path advancements ({sum(has_critical)}/{len(critical_advancements)})"
        )
        quality_score -= 0.2

    # - Metadata quality
    if scenario.metadata:
        if not scenario.metadata.description or len(scenario.metadata.description) < 20:
            warnings.append("Metadata description is too short")
            quality_score -= 0.05

        if not scenario.metadata.focus_areas or len(scenario.metadata.focus_areas) < 1:
            warnings.append("No focus areas specified in metadata")
            quality_score -= 0.1

    # - Party size vs complexity
    party_size = len(scenario.party) if isinstance(scenario.party, list) else 1
    event_count = len(scenario.events)

    if party_size == 1 and event_count > 50:
        warnings.append("Solo scenario with very high event count (may be tedious)")
        quality_score -= 0.05

    if party_size >= 4 and event_count < 20:
        warnings.append("Large party with few events (underutilized)")
        quality_score -= 0.05

    # Final quality score
    quality_score = max(0.0, min(1.0, quality_score))

    valid = len(errors) == 0

    logger.info(
        f"Validated scenario file '{scenario_path.name}': valid={valid}, quality={quality_score:.2f}"
    )

    return ValidationResult(
        valid=valid,
        errors=errors,
        warnings=warnings,
        quality_score=quality_score,
    )


def filter_scenario_batch(
    ideas: list[ScenarioIdea],
    min_quality: float = 0.6,
    max_results: int | None = None,
) -> tuple[list[ScenarioIdea], list[tuple[ScenarioIdea, ValidationResult]]]:
    """Filter a batch of generated scenarios by quality.

    Args:
        ideas: List of generated scenario ideas
        min_quality: Minimum quality score to pass (0.0-1.0)
        max_results: Maximum number of scenarios to return (best first)

    Returns:
        Tuple of (accepted_scenarios, rejected_scenarios_with_reasons)
    """
    logger.info(
        f"Filtering {len(ideas)} scenarios (min_quality={min_quality}, max={max_results})"
    )

    results = []
    for idea in ideas:
        validation = validate_scenario_idea(idea)
        results.append((idea, validation))

    # Filter valid scenarios
    valid_scenarios = [
        (idea, val) for idea, val in results if val.valid and val.quality_score >= min_quality
    ]

    # Sort by quality score (descending)
    valid_scenarios.sort(key=lambda x: x[1].quality_score, reverse=True)

    # Apply max limit
    if max_results:
        accepted = valid_scenarios[:max_results]
        rejected = valid_scenarios[max_results:] + [
            (idea, val) for idea, val in results if not val.valid or val.quality_score < min_quality
        ]
    else:
        accepted = valid_scenarios
        rejected = [
            (idea, val) for idea, val in results if not val.valid or val.quality_score < min_quality
        ]

    accepted_ideas = [idea for idea, _ in accepted]
    rejected_with_reasons = rejected

    logger.info(
        f"Filter results: {len(accepted_ideas)} accepted, {len(rejected_with_reasons)} rejected"
    )

    if accepted_ideas:
        avg_quality = sum(val.quality_score for _, val in accepted) / len(accepted)
        logger.info(f"Accepted scenarios average quality: {avg_quality:.2f}")

    return accepted_ideas, rejected_with_reasons
