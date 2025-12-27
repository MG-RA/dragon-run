"""Validation module for Minecraft progression sequences and synthetic scenarios."""

from .advancement_graph import (
    ADVANCEMENT_GRAPH,
    PREREQUISITES,
    find_missing_prerequisites,
    get_prerequisites,
    is_valid_progression,
)
from .leaderboard import (
    Leaderboard,
    LeaderboardEntry,
    compare_builds,
)
from .player_state import (
    ActiveEffect,
    Dimension,
    PlayerState,
    SpawnedMob,
)
from .scenario_factory import (
    ScenarioFactory,
    idea_to_yaml_dict,
    save_scenario_to_file,
)
from .scenario_generator import (
    DIFFICULTY_LEVELS,
    FOCUS_CATEGORIES,
    PARTY_COMPOSITIONS,
    ScenarioIdea,
    generate_scenario_batch,
    generate_scenario_idea,
)
from .scenario_loader import (
    ScenarioValidationError,
    load_scenario,
    load_scenarios_from_directory,
    scenario_to_dict,
)
from .scenario_runner import (
    EmergentRunResult,
    EmergentScenarioRunner,
    ScenarioRunner,
    ScenarioRunResult,
    run_emergent_scenario,
    run_scenario_batch,
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
    ScenarioMode,
    StructureDiscoveryEvent,
)
from .scenario_validator import (
    ValidationResult,
    filter_scenario_batch,
    validate_scenario_file,
    validate_scenario_idea,
)
from .scoring import (
    FractureMetrics,
    Outcome,
    RescueMetrics,
    ScenarioScore,
    TarotMetrics,
    ToolMetrics,
    analyze_tarot_evolution,
    score_emergent_run,
    score_run,
)
from .synthetic_client import SyntheticGameStateClient
from .synthetic_event_processor import SyntheticEventProcessor
from .synthetic_world import (
    PHASE_THRESHOLDS,
    GameState,
    Phase,
    SyntheticWorld,
)
from .tarot import (
    TAROT_DRIFT_RULES,
    TAROT_TRAITS,
    TarotCard,
    TarotProfile,
    get_drift_for_event,
)
from .tarot_brains import (
    DecisionContext,
    TarotBrain,
    describe_tarot_behavior,
)
from .intents import (
    Intent,
    IntentResult,
    get_intent_category,
    is_aggressive_intent,
    is_cooperative_intent,
    is_risky_intent,
)
from .player_memory import PlayerMemory
from .intent_compiler import IntentCompiler
from .world_diff import (
    RunTrace,
    StateChange,
    WorldDiff,
)

__all__ = [
    # Advancement validation (Phase 0)
    "ADVANCEMENT_GRAPH",
    "DIFFICULTY_LEVELS",
    "FOCUS_CATEGORIES",
    "PARTY_COMPOSITIONS",
    "PARTY_PRESETS",
    "PHASE_THRESHOLDS",
    "PREREQUISITES",
    "ActiveEffect",
    "AdvancementEvent",
    "ChatEvent",
    "DamageEvent",
    "DeathEvent",
    "Dimension",
    "DimensionChangeEvent",
    "DragonKillEvent",
    # Event types
    "Event",
    "FractureMetrics",
    "GameState",
    "HealthChangeEvent",
    "InventoryEvent",
    "Leaderboard",
    "LeaderboardEntry",
    "MobKillEvent",
    "Outcome",
    "PartyPreset",
    "Phase",
    "PlayerDefinition",
    "PlayerRole",
    # Player state
    "PlayerState",
    "RescueMetrics",
    "RunTrace",
    # Scenario schema
    "Scenario",
    # Phase 5: Scenario Factory
    "ScenarioFactory",
    "ScenarioIdea",
    "ScenarioMetadata",
    "ScenarioMode",
    "ScenarioRunResult",
    "ScenarioRunner",
    # Phase 4: Scoring & Leaderboards
    "ScenarioScore",
    "ScenarioValidationError",
    "SpawnedMob",
    "StateChange",
    "StructureDiscoveryEvent",
    # Phase 3: Closed-loop harness
    "SyntheticEventProcessor",
    "SyntheticGameStateClient",
    # Phase 2: SyntheticWorld
    "SyntheticWorld",
    "ToolMetrics",
    "ValidationResult",
    # World diff / telemetry
    "WorldDiff",
    "compare_builds",
    "filter_scenario_batch",
    "find_missing_prerequisites",
    "generate_scenario_batch",
    "generate_scenario_idea",
    "get_prerequisites",
    "idea_to_yaml_dict",
    "is_valid_progression",
    # Scenario loading (Phase 1)
    "load_scenario",
    "load_scenarios_from_directory",
    "run_scenario_batch",
    "save_scenario_to_file",
    "scenario_to_dict",
    "score_run",
    "validate_scenario_file",
    "validate_scenario_idea",
    # Phase 6: Player Cognition Engine (Tarot)
    "TAROT_DRIFT_RULES",
    "TAROT_TRAITS",
    "TarotCard",
    "TarotProfile",
    "TarotBrain",
    "TarotMetrics",
    "DecisionContext",
    "Intent",
    "IntentResult",
    "IntentCompiler",
    "PlayerMemory",
    "EmergentRunResult",
    "EmergentScenarioRunner",
    "run_emergent_scenario",
    "score_emergent_run",
    "analyze_tarot_evolution",
    "get_drift_for_event",
    "describe_tarot_behavior",
    "get_intent_category",
    "is_aggressive_intent",
    "is_cooperative_intent",
    "is_risky_intent",
]
