"""LangGraph builder for Eris state machine - v1.1 Linear Pipeline.

New architecture: All events flow through a single linear pipeline:
event_classifier -> context_enricher -> mask_selector -> decision_node ->
agentic_action -> protection_decision -> tool_executor -> END

No conditional routing, no fast paths, no forks.
One artery of reality.
"""

import logging
from typing import Optional

from langgraph.graph import StateGraph, END, START

from .state import ErisState, create_initial_state
from .nodes import (
    event_classifier,
    context_enricher,
    mask_selector,
    decision_node,
    agentic_action,
    protection_decision,
    tool_executor,
)
from ..tools.game_tools import create_game_tools

logger = logging.getLogger(__name__)


def create_graph(
    db: Optional[object] = None,
    ws_client: Optional[object] = None,
    llm: Optional[object] = None,
):
    """
    Build the Eris LangGraph state machine - v1.1 Linear Pipeline.

    All events traverse the full 7-node pipeline:
    1. event_classifier - Assign priority (no LLM)
    2. context_enricher - Load player histories, debts, prophecies (no LLM)
    3. mask_selector - Select personality with debt influence (no LLM)
    4. decision_node - Determine intent, targets, escalation (LLM)
    5. agentic_action - Generate narrative and planned actions (LLM with tools)
    6. protection_decision - Validate actions, handle death protection (partial LLM)
    7. tool_executor - Execute approved actions via WebSocket (no LLM)

    No conditional edges. No fast paths. Linear flow only.
    """

    # Create game tools bound to websocket client
    tools = create_game_tools(ws_client) if ws_client else []

    # Bind tools to LLM for agentic behavior
    llm_with_tools = llm.bind_tools(tools) if llm and tools else llm

    # Create graph
    graph = StateGraph(ErisState)

    # === Define async wrapper functions that close over dependencies ===

    async def _event_classifier(s: ErisState):
        return await event_classifier(s)

    async def _context_enricher(s: ErisState):
        return await context_enricher(s, db)

    async def _mask_selector(s: ErisState):
        return await mask_selector(s)

    async def _decision_node(s: ErisState):
        return await decision_node(s, llm)

    async def _agentic_action(s: ErisState):
        return await agentic_action(s, llm_with_tools)

    async def _protection_decision(s: ErisState):
        return await protection_decision(s, llm, ws_client)

    async def _tool_executor(s: ErisState):
        return await tool_executor(s, ws_client, db)

    # === Add all 7 nodes ===
    graph.add_node("event_classifier", _event_classifier)
    graph.add_node("context_enricher", _context_enricher)
    graph.add_node("mask_selector", _mask_selector)
    graph.add_node("decision_node", _decision_node)
    graph.add_node("agentic_action", _agentic_action)
    graph.add_node("protection_decision", _protection_decision)
    graph.add_node("tool_executor", _tool_executor)

    # === Linear pipeline - no conditional edges ===
    graph.add_edge(START, "event_classifier")
    graph.add_edge("event_classifier", "context_enricher")
    graph.add_edge("context_enricher", "mask_selector")
    graph.add_edge("mask_selector", "decision_node")
    graph.add_edge("decision_node", "agentic_action")
    graph.add_edge("agentic_action", "protection_decision")
    graph.add_edge("protection_decision", "tool_executor")
    graph.add_edge("tool_executor", END)

    # Compile
    compiled = graph.compile()
    logger.info("✅ LangGraph v1.1 compiled successfully (linear pipeline)")

    return compiled


def create_graph_for_studio():
    """Create graph for LangGraph Studio (without external dependencies)."""
    from .state import ErisState, create_initial_state

    graph = StateGraph(ErisState)

    # Simple nodes for testing
    async def test_classifier(state):
        return {"event_priority": state.get("event_priority")}

    async def test_enricher(state):
        return {"player_histories": {}}

    async def test_mask(state):
        from .state import ErisMask
        return {"current_mask": ErisMask.TRICKSTER}

    async def test_decision(state):
        return {
            "decision": {
                "intent": "confuse",
                "targets": [],
                "escalation": 30,
                "should_speak": True,
                "should_act": False,
            }
        }

    async def test_action(state):
        return {"planned_actions": [], "script": {"narrative_text": "", "planned_actions": []}}

    async def test_protection(state):
        return {"approved_actions": [], "protection_warnings": []}

    async def test_executor(state):
        return {"session": state.get("session", {})}

    graph.add_node("event_classifier", test_classifier)
    graph.add_node("context_enricher", test_enricher)
    graph.add_node("mask_selector", test_mask)
    graph.add_node("decision_node", test_decision)
    graph.add_node("agentic_action", test_action)
    graph.add_node("protection_decision", test_protection)
    graph.add_node("tool_executor", test_executor)

    graph.add_edge(START, "event_classifier")
    graph.add_edge("event_classifier", "context_enricher")
    graph.add_edge("context_enricher", "mask_selector")
    graph.add_edge("mask_selector", "decision_node")
    graph.add_edge("decision_node", "agentic_action")
    graph.add_edge("agentic_action", "protection_decision")
    graph.add_edge("protection_decision", "tool_executor")
    graph.add_edge("tool_executor", END)

    return graph.compile()
