# Scenarios Directory

This directory contains synthetic Minecraft speedrun scenarios for testing Eris.

## Generating Scenarios

Use the CLI tool to generate scenarios:

```bash
# Generate 10 scenarios with specific focus
python scripts/generate_scenarios.py generate --count 10 --focus rescue_speed --save

# Generate full library across all categories
python scripts/generate_scenarios.py library --total 50

# Interactive curation mode
python scripts/generate_scenarios.py curate --count 5
```

## Validating Scenarios

```bash
# Validate all scenarios
python scripts/generate_scenarios.py validate

# List scenarios with filtering
python scripts/generate_scenarios.py list --filter nether
```

## Running Scenarios

Scenarios are automatically discovered by the ScenarioRunner:

```python
from eris.validation import ScenarioRunner, load_scenarios_from_directory

# Load all scenarios
scenarios = load_scenarios_from_directory("scenarios")

# Run them
runner = ScenarioRunner(llm=llm)
for scenario_path in scenarios:
    result = await runner.run_scenario(scenario_path)
    score = result.calculate_score()
    print(f"{scenario_path.name}: {score.overall_score}/100")
```

## Scenario Categories

Generated scenarios focus on different aspects of Eris behavior:

- **rescue_speed** - Fast healing under pressure
- **rescue_prioritization** - Multiple players in danger
- **fracture_management** - Tension escalation/recovery
- **apocalypse_trigger** - Extreme fracture scenarios
- **tool_efficiency** - Helpful vs harmful balance
- **betrayal_karma** - Karma accumulation and release
- **nether_survival** - Nether fortress challenges
- **end_combat** - Dragon fight mechanics
- **party_coordination** - Multi-player dynamics
- **solo_pressure** - Solo player stress tests
- **resource_scarcity** - Low health/supplies
- **dimension_transition** - Portal mechanics

## Scenario Structure

Each scenario is a YAML file with:

```yaml
metadata:
  name: Scenario Name
  description: Brief description
  difficulty: easy/medium/hard/extreme
  focus_areas: [list, of, focus, categories]
  tags: [auto, generated, tags]

party: speed_trio  # or custom player definitions

events:
  - type: advancement
    player: Alice
    advancement: minecraft:story/mine_stone
  - type: damage
    player: Bob
    source: blaze
    amount: 8
  # ... more events
```

See [PHASE1_COMPLETE.md](../PHASE1_COMPLETE.md) for full schema documentation.
