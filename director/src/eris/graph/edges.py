"""Edge routing logic for LangGraph."""

from ..graph.state import ErisState, EventPriority


def route_after_classification(state: ErisState) -> str:
    """Route based on event priority."""
    priority = state.get("event_priority", EventPriority.ROUTINE)

    if priority == EventPriority.LOW:
        return "skip"  # Don't process low-priority state updates

    if priority == EventPriority.HIGH:
        event = state.get("current_event")
        if event and event.get("eventType") == "player_chat":
            return "fast_response"  # Fast path for chat

    return "context_enricher"  # Default: enrich context


def route_after_decision(state: ErisState) -> str:
    """Route based on decision outcome."""
    should_speak = state.get("should_speak", False)
    should_intervene = state.get("should_intervene", False)

    if not should_speak and not should_intervene:
        return "silent"

    # If intervening, go directly to tool_executor (decision already set planned_actions)
    if should_intervene:
        return "tool_executor"

    # If just speaking, go to speak node to generate message
    return "speak"
