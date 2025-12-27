"""Validation module for Minecraft progression sequences and synthetic scenarios."""

from .advancement_graph import (
    ADVANCEMENT_GRAPH,
    PREREQUISITES,
    find_missing_prerequisites,
    get_prerequisites,
    is_valid_progression,
)
from .player_state import (
    ActiveEffect,
    Dimension,
    PlayerState,
    SpawnedMob,
)
from .scenario_loader import (
    ScenarioValidationError,
    load_scenario,
    load_scenarios_from_directory,
    scenario_to_dict,
)
from .scenario_schema import (
    PARTY_PRESETS,
    AdvancementEvent,
    ChatEvent,
    DamageEvent,
    DeathEvent,
    DimensionChangeEvent,
    DragonKillEvent,
    Event,
    HealthChangeEvent,
    InventoryEvent,
    MobKillEvent,
    PartyPreset,
    PlayerDefinition,
    PlayerRole,
    Scenario,
    ScenarioMetadata,
    StructureDiscoveryEvent,
)
from .synthetic_world import (
    GameState,
    Phase,
    PHASE_THRESHOLDS,
    SyntheticWorld,
)
from .world_diff import (
    RunTrace,
    StateChange,
    WorldDiff,
)
from .synthetic_event_processor import SyntheticEventProcessor
from .synthetic_client import SyntheticGameStateClient
from .scenario_runner import (
    ScenarioRunner,
    ScenarioRunResult,
    run_scenario_batch,
)

__all__ = [
    # Advancement validation (Phase 0)
    "ADVANCEMENT_GRAPH",
    "PREREQUISITES",
    "find_missing_prerequisites",
    "get_prerequisites",
    "is_valid_progression",
    # Scenario loading (Phase 1)
    "load_scenario",
    "load_scenarios_from_directory",
    "scenario_to_dict",
    "ScenarioValidationError",
    # Scenario schema
    "Scenario",
    "ScenarioMetadata",
    "PlayerDefinition",
    "PlayerRole",
    "PartyPreset",
    "PARTY_PRESETS",
    # Event types
    "Event",
    "AdvancementEvent",
    "DamageEvent",
    "InventoryEvent",
    "DimensionChangeEvent",
    "ChatEvent",
    "DeathEvent",
    "DragonKillEvent",
    "MobKillEvent",
    "StructureDiscoveryEvent",
    "HealthChangeEvent",
    # Phase 2: SyntheticWorld
    "SyntheticWorld",
    "GameState",
    "Phase",
    "PHASE_THRESHOLDS",
    # Player state
    "PlayerState",
    "SpawnedMob",
    "ActiveEffect",
    "Dimension",
    # World diff / telemetry
    "WorldDiff",
    "StateChange",
    "RunTrace",
    # Phase 3: Closed-loop harness
    "SyntheticEventProcessor",
    "SyntheticGameStateClient",
    "ScenarioRunner",
    "ScenarioRunResult",
    "run_scenario_batch",
]
