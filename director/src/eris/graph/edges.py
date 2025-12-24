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

    # If intervening, use agentic action node which can call multiple tools
    if should_intervene:
        return "agentic_action"

    # If just speaking, go to speak node to generate message
    return "speak"


def route_after_agentic(state: ErisState) -> str:
    """Route after agentic action - check if LLM wants to call more tools."""
    messages = state.get("messages", [])
    if not messages:
        return "end"

    # Get the last message
    last_message = messages[-1]

    # Check if the last message has tool calls
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"

    return "end"


def route_after_fast_response(state: ErisState) -> str:
    """Route after fast response - check if LLM made tool calls or has planned actions."""
    messages = state.get("messages", [])

    # Check if the last message has native tool calls
    if messages:
        last_message = messages[-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"

    # Check for fallback planned_actions (when LLM generates text without tools)
    planned_actions = state.get("planned_actions", [])
    if planned_actions:
        return "tool_executor"

    return "end"
