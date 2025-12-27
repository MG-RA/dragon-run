"""LangGraph builder for Eris state machine - v1.3 Linear Pipeline with Fracture.

New architecture: All events flow through a single linear pipeline:
event_classifier -> context_enricher -> fracture_check -> mask_selector -> decision_node ->
agentic_action -> protection_decision -> tool_executor -> END

v1.3: Added fracture_check node for phase transitions and apocalypse triggering.
No conditional routing, no fast paths, no forks.
One artery of reality.
"""

import logging
from typing import Optional, Dict, Any

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
    trigger_apocalypse,
)
from ..tools.game_tools import create_game_tools
from ..core.tension import get_fracture_tracker
from ..persona.karma import calculate_total_karma

logger = logging.getLogger(__name__)


def create_graph(
    db: Optional[object] = None,
    ws_client: Optional[object] = None,
    llm: Optional[object] = None,
):
    """
    Build the Eris LangGraph state machine - v1.3 Linear Pipeline with Fracture.

    All events traverse the full 8-node pipeline:
    1. event_classifier - Assign priority (no LLM)
    2. context_enricher - Load player histories, karmas, prophecies (no LLM)
    3. fracture_check - Calculate fracture, check apocalypse, update phase (no LLM)
    4. mask_selector - Select personality with karma/fracture influence (no LLM)
    5. decision_node - Determine intent, targets, escalation (LLM)
    6. agentic_action - Generate narrative and planned actions (LLM with tools)
    7. protection_decision - Validate actions, handle death protection (partial LLM)
    8. tool_executor - Execute approved actions via WebSocket (no LLM)

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

    async def _fracture_check(s: ErisState) -> Dict[str, Any]:
        """
        Calculate fracture level and check for phase transitions/apocalypse.
        This node updates fracture, phase, and may trigger apocalypse.
        """
        fracture_tracker = get_fracture_tracker()

        # Update total karma from state
        player_karmas = s.get("player_karmas", {})
        total_karma = 0
        for player_data in player_karmas.values():
            total_karma += sum(player_data.values())
        fracture_tracker.update_total_karma(total_karma)

        # Check for phase transition
        new_phase = fracture_tracker.check_phase_transition()
        if new_phase:
            logger.info(f"🔥 Phase transition detected: {new_phase}")

        # Check if apocalypse should trigger
        if fracture_tracker.should_trigger_apocalypse():
            logger.warning("🍎 APOCALYPSE THRESHOLD REACHED - Triggering apocalypse!")
            apocalypse_result = await trigger_apocalypse(s, ws_client)
            fracture_tracker.mark_apocalypse_triggered()
            return {
                **fracture_tracker.get_state_for_graph(),
                **apocalypse_result,
            }

        # Return updated fracture state
        return fracture_tracker.get_state_for_graph()

    async def _mask_selector(s: ErisState):
        return await mask_selector(s)

    async def _decision_node(s: ErisState):
        return await decision_node(s, llm)

    async def _agentic_action(s: ErisState):
        return await agentic_action(s, llm_with_tools)

    async def _protection_decision(s: ErisState):
        return await protection_decision(s, llm, ws_client)

    async def _tool_executor(s: ErisState):
        return await tool_executor(s, ws_client, db, llm, tools)

    # === Add all 8 nodes ===
    graph.add_node("event_classifier", _event_classifier)
    graph.add_node("context_enricher", _context_enricher)
    graph.add_node("fracture_check", _fracture_check)
    graph.add_node("mask_selector", _mask_selector)
    graph.add_node("decision_node", _decision_node)
    graph.add_node("agentic_action", _agentic_action)
    graph.add_node("protection_decision", _protection_decision)
    graph.add_node("tool_executor", _tool_executor)

    # === Linear pipeline - no conditional edges ===
    graph.add_edge(START, "event_classifier")
    graph.add_edge("event_classifier", "context_enricher")
    graph.add_edge("context_enricher", "fracture_check")
    graph.add_edge("fracture_check", "mask_selector")
    graph.add_edge("mask_selector", "decision_node")
    graph.add_edge("decision_node", "agentic_action")
    graph.add_edge("agentic_action", "protection_decision")
    graph.add_edge("protection_decision", "tool_executor")
    graph.add_edge("tool_executor", END)

    # Compile
    compiled = graph.compile()
    logger.info("✅ LangGraph v1.3 compiled successfully (linear pipeline with fracture)")

    return compiled


def create_graph_for_studio():
    """Create graph for LangGraph Studio (without external dependencies)."""
    from .state import ErisState, create_initial_state

    graph = StateGraph(ErisState)

    # Simple nodes for testing
    async def test_classifier(state):
        return {"event_priority": state.get("event_priority")}

    async def test_enricher(state):
        return {"player_histories": {}, "player_karmas": {}}

    async def test_fracture(state):
        return {"fracture": 0, "phase": "normal", "apocalypse_triggered": False}

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
    graph.add_node("fracture_check", test_fracture)
    graph.add_node("mask_selector", test_mask)
    graph.add_node("decision_node", test_decision)
    graph.add_node("agentic_action", test_action)
    graph.add_node("protection_decision", test_protection)
    graph.add_node("tool_executor", test_executor)

    graph.add_edge(START, "event_classifier")
    graph.add_edge("event_classifier", "context_enricher")
    graph.add_edge("context_enricher", "fracture_check")
    graph.add_edge("fracture_check", "mask_selector")
    graph.add_edge("mask_selector", "decision_node")
    graph.add_edge("decision_node", "agentic_action")
    graph.add_edge("agentic_action", "protection_decision")
    graph.add_edge("protection_decision", "tool_executor")
    graph.add_edge("tool_executor", END)

    return graph.compile()
