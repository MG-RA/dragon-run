"""Eris State Schema for LangGraph.

v2.0 - Tarot-driven pipeline with relationship matrix.
"""

from datetime import datetime
from enum import Enum
from typing import Annotated, Any

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class ErisMask(Enum):
    """Eris's personality masks - each affects tone and behavior."""

    TRICKSTER = "trickster"  # Playful chaos, pranks
    PROPHET = "prophet"  # Cryptic warnings, foreshadowing
    FRIEND = "friend"  # Helpful, encouraging (but unsettling)
    CHAOS_BRINGER = "chaos"  # Malevolent, threatening
    OBSERVER = "observer"  # Silent watcher, rare comments
    GAMBLER = "gambler"  # Makes deals, offers bargains


class EventPriority(Enum):
    """Event priority levels for processing."""

    CRITICAL = 1  # Death, dragon killed
    HIGH = 2  # Chat, close calls
    MEDIUM = 3  # Milestones, dimension change
    LOW = 4  # Periodic state updates
    ROUTINE = 5  # Proactive checks


# === Tarot-driven TypedDicts (v2.0) ===


class PlayerTarotProfile(TypedDict):
    """Tarot profile for a single player.

    Players don't spawn with a card - they earn it through actions.
    The dominant card is their current identity.
    """

    dominant_card: str  # "fool", "magician", "hermit", etc.
    strength: float  # 0-1, how locked into this archetype
    secondary_card: str | None  # Second-strongest influence
    weights: dict[str, float]  # All 9 card weights


class ErisOpinion(TypedDict):
    """Eris's subjective opinion of a single player.

    This is not objective truth - it's what Eris believes and feels.
    """

    trust: float  # -1 (enemy) to 1 (pet)
    annoyance: float  # 0-1, how irritating
    interest: float  # 0-1, how much Eris watches them
    last_interaction: str | None  # What Eris last did to them
    interaction_count: int  # How many times Eris has acted on them


class PlayerProfile(TypedDict):
    """Complete profile for a player from Eris's perspective."""

    tarot: PlayerTarotProfile
    opinion: ErisOpinion


def create_default_tarot() -> PlayerTarotProfile:
    """Create default tarot profile for a new player."""
    return PlayerTarotProfile(
        dominant_card="fool",  # Everyone starts as Fool
        strength=0.0,
        secondary_card=None,
        weights={},
    )


def create_default_opinion() -> ErisOpinion:
    """Create default opinion for a new player."""
    return ErisOpinion(
        trust=0.0,
        annoyance=0.0,
        interest=0.3,  # Base curiosity
        last_interaction=None,
        interaction_count=0,
    )


def create_default_profile() -> PlayerProfile:
    """Create default player profile."""
    return PlayerProfile(
        tarot=create_default_tarot(),
        opinion=create_default_opinion(),
    )


# === Shared TypedDicts ===


class PlannedAction(TypedDict):
    """A single planned action with purpose annotation."""

    tool: str  # Tool name (e.g., "spawn_mob", "broadcast")
    args: dict[str, Any]  # Tool arguments
    purpose: str  # Why this action (e.g., "terror", "misdirection")


class MaskConfig(TypedDict):
    """Rich mask configuration from select_mask."""

    mask: str  # "TRICKSTER", "PROPHET", etc.
    bias: dict[str, float]  # {"challenge": 0.4, "mercy": 0.2, "dramatic": 0.4}
    allowed_behaviors: list[str]  # ["pranks", "misdirection", "baited gifts"]
    allowed_tool_groups: list[str]  # ["teleport", "fake_death", "particles", "sounds"]
    discouraged_tool_groups: list[str]  # ["damage", "mobs_heavy", "tnt"]
    deception_level: int  # 0-100


class DecisionOutput(BaseModel):
    """Structured output from decide_should_act using Pydantic for LLM structured output.

    v2.0: Now uses Intent enum values (47 options) instead of 6-value ErisIntent.
    """

    intent: str = Field(
        description="Intent from intents.py (e.g., 'tempt', 'test', 'protect', 'grief')"
    )
    targets: list[str] = Field(
        default_factory=list, description="Player names to target, or empty list for all"
    )
    escalation: int = Field(
        default=30, ge=0, le=100, description="Escalation level from 0 (subtle) to 100 (dramatic)"
    )
    should_speak: bool = Field(description="Whether Eris should broadcast a message")
    should_act: bool = Field(
        description="Whether Eris should take game actions (spawn mobs, effects, etc)"
    )
    tarot_reasoning: str | None = Field(
        default=None, description="How the target's tarot influenced this decision"
    )


class ScriptOutput(TypedDict):
    """Output from llm_invoke (narrative generation node)."""

    narrative_text: str  # Message to broadcast (if should_speak)
    planned_actions: list[PlannedAction]  # Actions with purposes


class ErisState(TypedDict):
    """Main graph state for the Eris Director agent.

    v2.0 - Tarot-driven pipeline:
    - Replaced player_karmas with player_profiles (tarot + opinion per player)
    - 7-node pipeline instead of 8
    - Eris knows each player's tarot card explicitly
    """

    # Core LangGraph messages
    messages: Annotated[list[AnyMessage], add_messages]

    # Current event being processed
    current_event: dict[str, Any] | None
    event_priority: EventPriority

    # Game context (compact string for LLM)
    context_buffer: str

    # Structured game state from WebSocket
    game_state: dict[str, Any]

    # Player data from database (long-term memory)
    player_histories: dict[str, dict]

    # Current run session tracking
    session: dict[str, Any]

    # === Persona State ===
    current_mask: ErisMask
    mask_config: MaskConfig | None  # Rich mask configuration from select_mask

    # === Decision & Script Output ===
    decision: DecisionOutput | None  # Structured decision from decide_should_act
    script: ScriptOutput | None  # Script from llm_invoke

    # === Fear & Chaos (in-memory, resets per run) ===
    player_fear: dict[str, int]  # username -> 0-100 fear level
    player_chaos: dict[str, int]  # username -> chaos contribution
    global_chaos: int  # 0-100 global chaos level

    # === Player Profiles (v2.0 - replaces player_karmas) ===
    player_profiles: dict[str, PlayerProfile]  # username -> PlayerProfile (tarot + opinion)

    # === Fracture & Phase (in-memory, resets per run) ===
    fracture: int  # 0-200+ fracture level (chaos + interest + fear)
    phase: str  # "normal", "rising", "critical", "locked", "apocalypse"
    apocalypse_triggered: bool  # Whether apocalypse event has fired this run

    # === Output ===
    approved_actions: list[PlannedAction]  # Post-protection validation
    protection_warnings: list[str]  # Soft enforcement warnings

    # Timing
    timestamp: float

    # Tracing
    trace_id: str | None  # Unique ID for correlating this event through pipeline


def create_initial_state() -> ErisState:
    """Create initial state for the agent."""
    return ErisState(
        messages=[],
        current_event=None,
        event_priority=EventPriority.ROUTINE,
        context_buffer="",
        game_state={},
        player_histories={},
        session={
            "run_id": None,
            "events_this_run": [],
            "actions_taken": [],
            "last_speech_time": 0,
            "intervention_count": 0,
            "mask_event_count": 0,  # For mask stickiness
        },
        # Persona
        current_mask=ErisMask.TRICKSTER,
        mask_config=None,
        # Decision & Script
        decision=None,
        script=None,
        # Fear & Chaos (in-memory, reset per run)
        player_fear={},
        player_chaos={},
        global_chaos=0,
        # Player Profiles (tarot + opinion per player)
        player_profiles={},
        # Fracture & Phase (in-memory, reset per run)
        fracture=0,
        phase="normal",
        apocalypse_triggered=False,
        # Output
        approved_actions=[],
        protection_warnings=[],
        # Timing
        timestamp=datetime.now().timestamp(),
        # Tracing
        trace_id=None,
    )
