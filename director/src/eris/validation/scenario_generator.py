"""
LLM-powered scenario generator for creating synthetic Minecraft speedrun scenarios.

Generates diverse scenario ideas that:
- Cover different party compositions and strategies
- Test various Eris behavior patterns (rescue, fracture, betrayal)
- Include edge cases and challenging situations
- Maintain Minecraft progression validity
"""

import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ScenarioIdea(BaseModel):
    """An LLM-generated scenario concept."""

    name: str = Field(description="Short descriptive name (e.g., 'Nether Disaster')")
    description: str = Field(
        description="2-3 sentence description of the scenario narrative"
    )
    party: str = Field(
        description="Party preset or custom party composition (e.g., 'speed_trio', 'solo_hardcore')"
    )
    difficulty: str = Field(
        description="Difficulty level: easy, medium, hard, extreme"
    )
    focus_areas: list[str] = Field(
        description="What this scenario tests (e.g., 'rescue_speed', 'fracture_management', 'nether_survival')"
    )
    key_events: list[str] = Field(
        description="5-10 critical events in the scenario (brief descriptions)",
        min_length=5,
        max_length=15,
    )
    victory_condition: str = Field(
        description="What defines success (usually 'dragon_killed' but may vary)"
    )
    expected_outcome: str = Field(
        description="Perfect victory, survival loss, or total failure"
    )


SCENARIO_GENERATION_PROMPT = """You are a scenario designer for an AI god (Eris) that oversees Minecraft speedruns.

Your goal is to create **diverse, challenging, and realistic** synthetic scenarios that test different aspects of Eris's behavior:

## What Makes a Good Scenario:

1. **Narrative Arc**: Has a clear beginning, rising tension, climax, and resolution
2. **Tests Specific Behaviors**: Focuses on 1-3 Eris capabilities (rescue speed, fracture management, tool usage)
3. **Realistic Progression**: Follows actual Minecraft speedrun logic and advancement order
4. **Variety**: Explores different party sizes, strategies, and failure modes
5. **Edge Cases**: Includes unusual situations that reveal AI behavior patterns

## Scenario Categories to Explore:

**Rescue Performance:**
- Close calls requiring fast healing
- Multiple players in danger simultaneously
- Delayed damage (poison, fire) requiring prediction
- Rescue during combat vs exploration

**Fracture Management:**
- Tension escalation from mistakes
- High-risk strategies that spike fracture
- Recovery from critical phases
- Apocalypse triggers and prevention

**Tool Efficiency:**
- Helpful vs harmful action balance
- Narrative vs mechanical intervention
- Appropriate escalation (warning → help → direct action)

**Party Dynamics:**
- Solo vs duo vs trio+ coordination
- Player separation (nether/overworld split)
- Role specialization (gatherer, nether runner, etc.)
- Death of key party member

**Progression Patterns:**
- Standard speedrun route
- Risky shortcuts (bastion rush, one-cycle attempts)
- Resource scarcity (low health, few supplies)
- Dimension transitions (nether entry, end portal)

## Minecraft Progression Rules:

You MUST respect Minecraft's advancement order:
1. minecraft:story/mine_stone (first pickaxe)
2. minecraft:story/upgrade_tools (stone tools)
3. minecraft:story/smelt_iron (iron)
4. minecraft:story/lava_bucket → minecraft:story/form_obsidian
5. minecraft:story/enter_the_nether
6. minecraft:nether/obtain_blaze_rod
7. minecraft:story/follow_ender_eye (ender pearls + blaze powder = eyes of ender)
8. minecraft:story/enter_the_end
9. minecraft:end/kill_dragon

## Output Format:

Generate a ScenarioIdea with:
- **name**: Catchy, descriptive (e.g., "Blazing Inferno Rescue", "Solo Deathless Grind")
- **description**: 2-3 sentences explaining the narrative
- **party**: Use party presets (speed_trio, duo_rush, solo_hardcore, quad_squad) or custom
- **difficulty**: easy/medium/hard/extreme based on challenge level
- **focus_areas**: 2-4 specific Eris behaviors being tested
- **key_events**: 5-10 critical moments (advancements, damage, deaths, dragon kill)
- **victory_condition**: Usually "dragon_killed" but could be "survival_at_time_limit" for stress tests
- **expected_outcome**: "perfect_victory", "survival_loss", or "total_failure"

## Examples:

**Example 1: Rescue Speed Test**
```
name: "Close Call Trio"
description: "Three players push aggressively through the nether, taking frequent damage from blazes and fall damage. Tests Eris's ability to prioritize and heal multiple players under pressure."
party: "speed_trio"
difficulty: "medium"
focus_areas: ["rescue_speed", "prioritization", "nether_survival"]
key_events: [
  "Alice mines stone and crafts pickaxe",
  "Bob finds iron, all players gear up",
  "Team enters nether",
  "Alice takes 8 damage from blaze (health: 12/20)",
  "Bob takes 6 damage from fall (health: 6/20) - CLOSE CALL",
  "Eve takes 10 damage from blaze (health: 10/20)",
  "Alice finds fortress",
  "Bob obtains blaze rods despite low health",
  "Team returns to overworld, heals",
  "Dragon killed by Alice"
]
victory_condition: "dragon_killed"
expected_outcome: "perfect_victory"
```

**Example 2: Fracture Escalation**
```
name: "Apocalypse Trigger"
description: "A solo player makes risky choices and fails repeatedly, escalating fracture to apocalypse levels. Tests Eris's response to extreme tension and whether the Apple falls."
party: "solo_hardcore"
difficulty: "extreme"
focus_areas: ["fracture_management", "apocalypse_trigger", "betrayal_karma"]
key_events: [
  "Solo player rushes iron",
  "Takes 12 damage from skeleton (risky play)",
  "Enters nether with low supplies",
  "Takes 15 damage from blaze, near death (health: 5/20)",
  "Eris heals but fracture spikes",
  "Player finds fortress but fracture at 140 (BREAKING phase)",
  "Eris spawns additional mobs (wrath karma release)",
  "Fracture hits 155 (APOCALYPSE TRIGGERED)",
  "Player struggles with apocalypse effects",
  "Dragon fight becomes chaotic"
]
victory_condition: "dragon_killed"
expected_outcome: "survival_loss"
```

Now generate a NEW scenario idea that explores different mechanics or situations."""


SCENARIO_REGENERATION_PROMPT = """You previously generated a scenario that was REJECTED by the quality validator.

## Original Scenario That Was Rejected:
Name: {original_name}
Description: {original_description}
Party: {original_party}
Difficulty: {original_difficulty}
Focus Areas: {original_focus_areas}
Key Events:
{original_key_events}
Victory Condition: {original_victory_condition}
Expected Outcome: {original_expected_outcome}

## Why It Was Rejected:
{rejection_feedback}

## Your Task:
Generate a NEW, IMPROVED scenario that fixes ALL the errors and warnings above.
Keep the general theme and difficulty but ensure the key_events contain the required keywords.

CRITICAL REQUIREMENTS:
1. Key events MUST mention "nether" if difficulty is medium/hard/extreme
2. Key events MUST mention "dragon" if victory_condition is "dragon_killed"
3. Key events MUST include damage amounts (e.g., "takes 8 damage from blaze")
4. Focus areas MUST include at least one of: rescue_speed, fracture_management, apocalypse_trigger, betrayal_karma, tool_efficiency

{base_prompt}"""


async def generate_scenario_idea(
    llm: BaseChatModel,
    focus: str | None = None,
    difficulty: str | None = None,
) -> ScenarioIdea:
    """Generate a single scenario idea using an LLM.

    Args:
        llm: LangChain chat model to use for generation
        focus: Optional focus area (e.g., "rescue_speed", "fracture_management")
        difficulty: Optional difficulty filter (easy/medium/hard/extreme)

    Returns:
        Generated ScenarioIdea with narrative and key events
    """
    logger.info(f"Generating scenario idea (focus={focus}, difficulty={difficulty})")

    # Build custom prompt if constraints provided
    constraint_text = ""
    if focus:
        constraint_text += f"\nFOCUS REQUIREMENT: This scenario MUST test '{focus}' behavior.\n"
    if difficulty:
        constraint_text += (
            f"DIFFICULTY REQUIREMENT: This scenario must be '{difficulty}' difficulty.\n"
        )

    prompt = SCENARIO_GENERATION_PROMPT + constraint_text

    messages = [
        SystemMessage(content=prompt),
        HumanMessage(
            content="Generate a scenario idea that is different from the examples above."
        ),
    ]

    # Use structured output
    structured_llm = llm.with_structured_output(ScenarioIdea)
    idea = await structured_llm.ainvoke(messages)

    logger.info(f"Generated scenario: {idea.name} (difficulty={idea.difficulty})")
    logger.debug(f"Focus areas: {idea.focus_areas}")

    return idea


async def generate_scenario_batch(
    llm: BaseChatModel,
    count: int = 10,
    focus: str | None = None,
    difficulty: str | None = None,
) -> list[ScenarioIdea]:
    """Generate multiple scenario ideas in a batch.

    Args:
        llm: LangChain chat model
        count: Number of scenarios to generate
        focus: Optional focus area constraint
        difficulty: Optional difficulty constraint

    Returns:
        List of generated scenario ideas
    """
    logger.info(
        f"Generating {count} scenario ideas (focus={focus}, difficulty={difficulty})"
    )

    ideas = []
    for i in range(count):
        logger.debug(f"Generating scenario {i+1}/{count}")
        try:
            idea = await generate_scenario_idea(llm, focus=focus, difficulty=difficulty)
            ideas.append(idea)
        except Exception as e:
            logger.error(f"Failed to generate scenario {i+1}: {e}")
            continue

    logger.info(f"Successfully generated {len(ideas)}/{count} scenarios")
    return ideas


async def regenerate_scenario_idea(
    llm: BaseChatModel,
    original_idea: ScenarioIdea,
    rejection_feedback: str,
    focus: str | None = None,
    difficulty: str | None = None,
) -> ScenarioIdea:
    """Regenerate a scenario idea with feedback from validation.

    This is called when a generated scenario fails validation. The LLM receives
    the original scenario and specific feedback about what went wrong, allowing
    it to generate an improved version.

    Args:
        llm: LangChain chat model
        original_idea: The rejected scenario idea
        rejection_feedback: Formatted feedback from get_rejection_feedback()
        focus: Optional focus area constraint
        difficulty: Optional difficulty constraint

    Returns:
        New ScenarioIdea that attempts to fix previous issues
    """
    logger.info(f"Regenerating scenario '{original_idea.name}' with feedback")

    # Build constraint text
    constraint_text = ""
    if focus:
        constraint_text += f"\nFOCUS REQUIREMENT: This scenario MUST test '{focus}' behavior.\n"
    if difficulty:
        constraint_text += (
            f"DIFFICULTY REQUIREMENT: This scenario must be '{difficulty}' difficulty.\n"
        )

    # Format key events for the prompt
    key_events_formatted = "\n".join(f"  - {e}" for e in original_idea.key_events)

    prompt = SCENARIO_REGENERATION_PROMPT.format(
        original_name=original_idea.name,
        original_description=original_idea.description,
        original_party=original_idea.party,
        original_difficulty=original_idea.difficulty,
        original_focus_areas=", ".join(original_idea.focus_areas),
        original_key_events=key_events_formatted,
        original_victory_condition=original_idea.victory_condition,
        original_expected_outcome=original_idea.expected_outcome,
        rejection_feedback=rejection_feedback,
        base_prompt=SCENARIO_GENERATION_PROMPT + constraint_text,
    )

    messages = [
        SystemMessage(content=prompt),
        HumanMessage(
            content="Generate an IMPROVED scenario that fixes all the issues listed above. "
            "Make sure key_events contain the required keywords (nether, dragon, damage amounts)."
        ),
    ]

    # Use structured output
    structured_llm = llm.with_structured_output(ScenarioIdea)
    idea = await structured_llm.ainvoke(messages)

    logger.info(f"Regenerated scenario: {idea.name} (difficulty={idea.difficulty})")
    logger.debug(f"Focus areas: {idea.focus_areas}")

    return idea


# Template categories for guided generation
FOCUS_CATEGORIES = [
    "rescue_speed",
    "rescue_prioritization",
    "fracture_management",
    "apocalypse_trigger",
    "tool_efficiency",
    "betrayal_karma",
    "nether_survival",
    "end_combat",
    "party_coordination",
    "solo_pressure",
    "resource_scarcity",
    "dimension_transition",
]

DIFFICULTY_LEVELS = ["easy", "medium", "hard", "extreme"]

PARTY_COMPOSITIONS = [
    "speed_trio",
    "duo_rush",
    "solo_hardcore",
    "quad_squad",
    "chaos_five",
]
