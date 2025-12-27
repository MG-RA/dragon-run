"""Edge utilities for LangGraph - v1.1.

In the v1.1 linear pipeline, conditional routing is removed.
All events traverse the full pipeline:
event_classifier -> context_enricher -> mask_selector -> decision_node ->
agentic_action -> protection_decision -> tool_executor -> END

This file is kept for backward compatibility and potential utility functions.
The routing functions are no longer used but preserved for reference.
"""

import logging

from ..graph.state import ErisState, EventPriority

logger = logging.getLogger(__name__)


# === DEPRECATED: These routing functions are no longer used in v1.1 ===
# Kept for reference and potential rollback if needed.


def route_after_classification(state: ErisState) -> str:
    """
    DEPRECATED in v1.1 - Linear pipeline has no conditional routing.

    Previously routed based on event priority:
    - LOW -> skip
    - protection events -> protection_decision
    - HIGH + chat -> fast_response
    - default -> context_enricher
    """
    logger.warning("route_after_classification called but is deprecated in v1.1")
    return "context_enricher"


def route_after_protection(state: ErisState) -> str:
    """
    DEPRECATED in v1.1 - Linear pipeline continues to tool_executor always.
    """
    logger.warning("route_after_protection called but is deprecated in v1.1")
    return "tool_executor"


def route_after_decision(state: ErisState) -> str:
    """
    DEPRECATED in v1.1 - Linear pipeline continues to agentic_action always.
    """
    logger.warning("route_after_decision called but is deprecated in v1.1")
    return "agentic_action"


def route_after_agentic(state: ErisState) -> str:
    """
    DEPRECATED in v1.1 - Linear pipeline continues to protection_decision always.
    """
    logger.warning("route_after_agentic called but is deprecated in v1.1")
    return "protection_decision"


def route_after_fast_response(state: ErisState) -> str:
    """
    DEPRECATED in v1.1 - fast_response node removed, no more fast paths.
    """
    logger.warning("route_after_fast_response called but is deprecated in v1.1")
    return "end"


# === Utility Functions ===


def should_skip_low_priority(state: ErisState) -> bool:
    """
    Check if an event should be processed at all.
    In v1.1, we still process all events through the pipeline,
    but nodes can check this to short-circuit their logic.
    """
    priority = state.get("event_priority", EventPriority.ROUTINE)
    return priority == EventPriority.LOW


def is_protection_event(state: ErisState) -> bool:
    """Check if the current event is a protection event."""
    event = state.get("current_event")
    if not event:
        return False
    event_type = event.get("eventType", "")
    return event_type in ("eris_close_call", "eris_caused_death")


def is_critical_event(state: ErisState) -> bool:
    """Check if the current event is critical priority."""
    priority = state.get("event_priority", EventPriority.ROUTINE)
    return priority == EventPriority.CRITICAL


def get_event_type(state: ErisState) -> str:
    """Get the event type from state."""
    event = state.get("current_event")
    return event.get("eventType", "") if event else ""
