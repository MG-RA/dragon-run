"""LangGraph builder for Eris state machine."""

import logging
from typing import Optional

from langgraph.graph import StateGraph, END

from .state import ErisState, create_initial_state
from .nodes import (
    event_classifier,
    context_enricher,
    mask_selector,
    decision_node,
    fast_response,
    speak_node,
    tool_executor,
)
from .edges import route_after_classification, route_after_decision

logger = logging.getLogger(__name__)


def create_graph(
    db: Optional[object] = None,
    ws_client: Optional[object] = None,
    llm: Optional[object] = None,
):
    """Build the Eris LangGraph state machine."""

    # Create graph
    graph = StateGraph(ErisState)

    # Define async wrapper functions that properly close over dependencies
    async def _event_classifier(s):
        return await event_classifier(s)

    async def _context_enricher(s):
        return await context_enricher(s, db)

    async def _mask_selector(s):
        return await mask_selector(s)

    async def _decision(s):
        return await decision_node(s, llm)

    async def _fast_response(s):
        return await fast_response(s, llm)

    async def _speak(s):
        return await speak_node(s, llm)

    async def _tool_executor(s):
        return await tool_executor(s, ws_client)

    def _noop(s):
        return s

    # Add all nodes with proper async wrappers
    graph.add_node("event_classifier", _event_classifier)
    graph.add_node("context_enricher", _context_enricher)
    graph.add_node("mask_selector", _mask_selector)
    graph.add_node("decision", _decision)
    graph.add_node("fast_response", _fast_response)
    graph.add_node("speak", _speak)
    graph.add_node("tool_executor", _tool_executor)

    # No-op nodes for routing endpoints
    graph.add_node("skip", _noop)
    graph.add_node("silent", _noop)

    # Entry point
    graph.set_entry_point("event_classifier")

    # Conditional routing after classification
    # Routes to: skip, fast_response, or context_enricher
    graph.add_conditional_edges(
        "event_classifier",
        route_after_classification,
        {
            "skip": "skip",
            "fast_response": "fast_response",
            "context_enricher": "context_enricher",
        }
    )

    # Fast path for chat -> directly to tool executor
    graph.add_edge("fast_response", "tool_executor")

    # Standard path: context -> mask -> decision
    graph.add_edge("context_enricher", "mask_selector")
    graph.add_edge("mask_selector", "decision")

    # Routing after decision
    # Routes to: silent, speak, or tool_executor (for interventions)
    graph.add_conditional_edges(
        "decision",
        route_after_decision,
        {
            "silent": "silent",
            "speak": "speak",
            "tool_executor": "tool_executor",
        }
    )

    # Speak generates message then executes
    graph.add_edge("speak", "tool_executor")

    # Terminal edges
    graph.add_edge("tool_executor", END)
    graph.add_edge("silent", END)
    graph.add_edge("skip", END)

    # Compile
    compiled = graph.compile()
    logger.info("✅ LangGraph compiled successfully")

    return compiled


def create_graph_for_studio():
    """Create graph for LangGraph Studio (without external dependencies)."""
    from .state import ErisState, create_initial_state
    from langgraph.graph import StateGraph, END

    graph = StateGraph(ErisState)

    # Simple nodes for testing
    async def test_classifier(state):
        return {"event_priority": state.get("event_priority")}

    async def test_decision(state):
        return {"should_speak": True, "should_intervene": False}

    graph.add_node("classifier", test_classifier)
    graph.add_node("decision", test_decision)
    graph.add_node("end_node", lambda s: s)

    graph.set_entry_point("classifier")
    graph.add_edge("classifier", "decision")
    graph.add_edge("decision", "end_node")
    graph.add_edge("end_node", END)

    return graph.compile()
