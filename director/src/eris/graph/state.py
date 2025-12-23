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

    # Eris persona state
    current_mask: ErisMask
    mask_stability: float  # How likely to keep current mask (0-1)
    mood: str  # Affects response tone

    # Decision tracking
    should_speak: bool
    should_intervene: bool
    intervention_type: Optional[str]

    # Output
    planned_actions: List[Dict[str, Any]]

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
        current_mask=ErisMask.TRICKSTER,
        mask_stability=0.7,
        mood="neutral",
        should_speak=False,
        should_intervene=False,
        intervention_type=None,
        planned_actions=[],
        timestamp=datetime.now().timestamp()
    )
