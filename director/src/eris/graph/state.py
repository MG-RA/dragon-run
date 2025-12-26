"""Eris State Schema for LangGraph."""

from typing import Annotated, Any, Dict, List, Optional
from datetime import datetime
from enum import Enum

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class ErisMask(Enum):
    """Eris's personality masks - each affects tone and behavior."""

    TRICKSTER = "trickster"      # Playful chaos, pranks
    PROPHET = "prophet"          # Cryptic warnings, foreshadowing
    FRIEND = "friend"            # Helpful, encouraging (but unsettling)
    CHAOS_BRINGER = "chaos"      # Malevolent, threatening
    OBSERVER = "observer"        # Silent watcher, rare comments
    GAMBLER = "gambler"          # Makes deals, offers bargains


class EventPriority(Enum):
    """Event priority levels for processing."""

    CRITICAL = 1   # Death, dragon killed
    HIGH = 2       # Chat, close calls
    MEDIUM = 3     # Milestones, dimension change
    LOW = 4        # Periodic state updates
    ROUTINE = 5    # Proactive checks


class ErisIntent(Enum):
    """Eris's intent for an action."""

    BLESS = "bless"        # Help the player
    CURSE = "curse"        # Harm the player
    TEST = "test"          # Challenge the player
    CONFUSE = "confuse"    # Misdirect or deceive
    REVEAL = "reveal"      # Share truth or prophecy
    LIE = "lie"            # Deceive with false information


# === New TypedDicts for v1.1 ===

class PlannedAction(TypedDict):
    """A single planned action with purpose annotation."""

    tool: str                     # Tool name (e.g., "spawn_mob", "broadcast")
    args: Dict[str, Any]          # Tool arguments
    purpose: str                  # Why this action (e.g., "terror", "misdirection")


class MaskConfig(TypedDict):
    """Rich mask configuration from mask_selector."""

    mask: str                          # "TRICKSTER", "PROPHET", etc.
    bias: Dict[str, float]             # {"challenge": 0.4, "mercy": 0.2, "dramatic": 0.4}
    allowed_behaviors: List[str]       # ["pranks", "misdirection", "baited gifts"]
    allowed_tool_groups: List[str]     # ["teleport", "fake_death", "particles", "sounds"]
    discouraged_tool_groups: List[str] # ["damage", "mobs_heavy", "tnt"]
    deception_level: int               # 0-100


class DecisionOutput(TypedDict):
    """Structured output from decision_node."""

    intent: str                   # One of ErisIntent values
    targets: List[str]            # Player names to target
    escalation: int               # 0-100 escalation level
    should_speak: bool            # Whether to broadcast a message
    should_act: bool              # Whether to take game actions


class ScriptOutput(TypedDict):
    """Output from agentic_action (scriptwriting node)."""

    narrative_text: str                    # Message to broadcast (if should_speak)
    planned_actions: List[PlannedAction]   # Actions with purposes


class ErisState(TypedDict):
    """Main graph state for the Eris Director agent."""

    # Core LangGraph messages
    messages: Annotated[List[AnyMessage], add_messages]

    # Current event being processed
    current_event: Optional[Dict[str, Any]]
    event_priority: EventPriority

    # Game context (compact string for LLM)
    context_buffer: str

    # Structured game state from WebSocket
    game_state: Dict[str, Any]

    # Player data from database (long-term memory)
    player_histories: Dict[str, Dict]

    # Current run session tracking
    session: Dict[str, Any]

    # === Persona State (v1.1 Enhanced) ===
    current_mask: ErisMask
    mask_config: Optional[MaskConfig]      # Rich mask configuration from mask_selector

    # === Decision & Script Output (v1.1) ===
    decision: Optional[DecisionOutput]     # Structured decision from decision_node
    script: Optional[ScriptOutput]         # Script from agentic_action

    # === Fear & Chaos (v1.1 - in-memory, resets per run) ===
    player_fear: Dict[str, int]            # username -> 0-100 fear level
    player_chaos: Dict[str, int]           # username -> chaos contribution
    global_chaos: int                      # 0-100 global chaos level

    # === Karma (v1.2 - from PostgreSQL, persists) ===
    player_karmas: Dict[str, Dict[str, int]]  # username -> {mask_type -> karma value}

    # === Fracture & Phase (v1.3 - in-memory, resets per run) ===
    fracture: int                          # 0-200+ fracture level (chaos + karma + fear)
    phase: str                             # "normal", "rising", "critical", "locked", "apocalypse"
    apocalypse_triggered: bool             # Whether apocalypse event has fired this run

    # === Prophecy State (v1.1 - from PostgreSQL, persists) ===
    prophecy_state: Dict[str, Any]         # Active prophecies, tracking

    # === Output (v1.1 Enhanced) ===
    planned_actions: List[PlannedAction]   # Now includes purpose field
    approved_actions: List[PlannedAction]  # Post-protection validation
    protection_warnings: List[str]         # Soft enforcement warnings

    # Timing
    timestamp: float


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
            "intervention_count": 0
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
        # Output
        planned_actions=[],
        approved_actions=[],
        protection_warnings=[],
        # Timing
        timestamp=datetime.now().timestamp()
    )
