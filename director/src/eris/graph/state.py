"""Eris State Schema for LangGraph."""

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


class ErisIntent(Enum):
    """Eris's intent for an action."""

    BLESS = "bless"  # Help the player
    CURSE = "curse"  # Harm the player
    TEST = "test"  # Challenge the player
    CONFUSE = "confuse"  # Misdirect or deceive
    REVEAL = "reveal"  # Share truth or prophecy
    LIE = "lie"  # Deceive with false information


# === New TypedDicts for v1.1 ===


class KarmaVector(TypedDict):
    """Fixed 6-field karma vector per player.

    Each field represents narrative pressure that builds toward resolution.
    Maps to masks: betrayal→FRIEND, risk→GAMBLER, irony→TRICKSTER,
    doom→PROPHET, wrath→CHAOS_BRINGER, inevitability→OBSERVER.
    """

    betrayal: int  # FRIEND mask - builds when helping, resolves on betrayal
    risk: int  # GAMBLER mask - builds on safe bets, resolves on high-stakes
    irony: int  # TRICKSTER mask - builds on harmless pranks, resolves on dangerous
    doom: int  # PROPHET mask - builds on unfulfilled prophecies, resolves on reveal
    wrath: int  # CHAOS_BRINGER mask - builds on restraint, resolves on unleashing
    inevitability: int  # OBSERVER mask - builds on silence, resolves on speaking


# Default zero vector for new players
DEFAULT_KARMA: KarmaVector = {
    "betrayal": 0,
    "risk": 0,
    "irony": 0,
    "doom": 0,
    "wrath": 0,
    "inevitability": 0,
}


class PlannedAction(TypedDict):
    """A single planned action with purpose annotation."""

    tool: str  # Tool name (e.g., "spawn_mob", "broadcast")
    args: dict[str, Any]  # Tool arguments
    purpose: str  # Why this action (e.g., "terror", "misdirection")


class MaskConfig(TypedDict):
    """Rich mask configuration from mask_selector."""

    mask: str  # "TRICKSTER", "PROPHET", etc.
    bias: dict[str, float]  # {"challenge": 0.4, "mercy": 0.2, "dramatic": 0.4}
    allowed_behaviors: list[str]  # ["pranks", "misdirection", "baited gifts"]
    allowed_tool_groups: list[str]  # ["teleport", "fake_death", "particles", "sounds"]
    discouraged_tool_groups: list[str]  # ["damage", "mobs_heavy", "tnt"]
    deception_level: int  # 0-100


class DecisionOutput(BaseModel):
    """Structured output from decision_node using Pydantic for LLM structured output."""

    intent: str = Field(description="One of: bless, curse, test, confuse, reveal, lie")
    targets: list[str] = Field(
        default_factory=list, description="Player names to target, or empty list for none"
    )
    escalation: int = Field(
        default=30, ge=0, le=100, description="Escalation level from 0 (subtle) to 100 (dramatic)"
    )
    should_speak: bool = Field(description="Whether Eris should broadcast a message")
    should_act: bool = Field(description="Whether Eris should take game actions (spawn mobs, effects, etc)")


class ScriptOutput(TypedDict):
    """Output from agentic_action (scriptwriting node)."""

    narrative_text: str  # Message to broadcast (if should_speak)
    planned_actions: list[PlannedAction]  # Actions with purposes


class ErisState(TypedDict):
    """Main graph state for the Eris Director agent."""

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

    # === Persona State (v1.1 Enhanced) ===
    current_mask: ErisMask
    mask_config: MaskConfig | None  # Rich mask configuration from mask_selector

    # === Decision & Script Output (v1.1) ===
    decision: DecisionOutput | None  # Structured decision from decision_node
    script: ScriptOutput | None  # Script from agentic_action

    # === Fear & Chaos (v1.1 - in-memory, resets per run) ===
    player_fear: dict[str, int]  # username -> 0-100 fear level
    player_chaos: dict[str, int]  # username -> chaos contribution
    global_chaos: int  # 0-100 global chaos level

    # === Karma (v1.2 - from PostgreSQL, persists) ===
    player_karmas: dict[str, KarmaVector]  # username -> KarmaVector (6 fixed fields)

    # === Fracture & Phase (v1.3 - in-memory, resets per run) ===
    fracture: int  # 0-200+ fracture level (chaos + karma + fear)
    phase: str  # "normal", "rising", "critical", "locked", "apocalypse"
    apocalypse_triggered: bool  # Whether apocalypse event has fired this run

    # === Prophecy State (v1.1 - from PostgreSQL, persists) ===
    prophecy_state: dict[str, Any]  # Active prophecies, tracking

    # === Output (v1.1 Enhanced) ===
    # NOTE: planned_actions now lives inside script.planned_actions (single source of truth)
    # Protection decision reads from script, outputs to approved_actions
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
        # Karma (loaded from DB)
        player_karmas={},
        # Fracture & Phase (in-memory, reset per run)
        fracture=0,
        phase="normal",
        apocalypse_triggered=False,
        # Prophecy (loaded from DB)
        prophecy_state={},
        # Output (planned_actions now lives inside script)
        approved_actions=[],
        protection_warnings=[],
        # Timing
        timestamp=datetime.now().timestamp(),
        # Tracing
        trace_id=None,
    )
