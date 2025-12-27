"""LangGraph builder for Eris state machine - v2.0 Tarot-Driven Pipeline.

7-node linear pipeline:
update_player_state -> update_tarot -> update_eris_opinions -> select_mask ->
decide_should_act -> llm_invoke -> tool_execute -> END

v2.0: Replaces karma with tarot archetypes.
No conditional routing, no fast paths, no forks.
One artery of reality.
"""

import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

from ..tools.game_tools import create_game_tools
from .nodes import (
    decide_should_act,
    fracture_check,
    llm_invoke,
    select_mask,
    tool_execute,
    update_eris_opinions,
    update_player_state,
    update_tarot,
)
from .state import ErisState

logger = logging.getLogger(__name__)


def create_graph(
    db: object | None = None,
    ws_client: object | None = None,
    llm: object | None = None,
):
    """
    Build the Eris LangGraph state machine - v2.0 Tarot-Driven Pipeline.

    All events traverse the full 7-node pipeline:
    1. update_player_state - Load player data, init profiles (no LLM)
    2. update_tarot - Apply tarot drift based on event (no LLM)
    3. update_eris_opinions - Update trust/annoyance/interest (no LLM)
    4. select_mask - Select personality with tarot/fracture influence (no LLM)
    5. decide_should_act - Determine intent, targets, escalation (LLM)
    6. llm_invoke - Generate narrative and planned actions (LLM with tools)
    7. tool_execute - Validate and execute actions via WebSocket (no LLM)

    Fracture check is integrated into update_eris_opinions.
    No conditional edges. No fast paths. Linear flow only.
    """

    # Create game tools bound to websocket client
    tools = create_game_tools(ws_client) if ws_client else []

    # Create graph
    graph = StateGraph(ErisState)

    # === Define async wrapper functions that close over dependencies ===

    async def _update_player_state(s: ErisState) -> dict[str, Any]:
        return await update_player_state(s, db)

    async def _update_tarot(s: ErisState) -> dict[str, Any]:
        return await update_tarot(s)

    async def _update_eris_opinions(s: ErisState) -> dict[str, Any]:
        return await update_eris_opinions(s)

    async def _fracture_check(s: ErisState) -> dict[str, Any]:
        """
        Calculate fracture level and check for phase transitions/apocalypse.
        Uses tarot-based fracture calculation (interest + chaos cards).
        """
        return await fracture_check(s, ws_client)

    async def _select_mask(s: ErisState) -> dict[str, Any]:
        return await select_mask(s)

    async def _decide_should_act(s: ErisState) -> dict[str, Any]:
        return await decide_should_act(s, llm)

    async def _llm_invoke(s: ErisState) -> dict[str, Any]:
        return await llm_invoke(s, llm, tools)

    async def _tool_execute(s: ErisState) -> dict[str, Any]:
        return await tool_execute(s, ws_client, db, llm, tools)

    # === Add all 7 nodes + fracture check ===
    graph.add_node("update_player_state", _update_player_state)
    graph.add_node("update_tarot", _update_tarot)
    graph.add_node("update_eris_opinions", _update_eris_opinions)
    graph.add_node("fracture_check", _fracture_check)
    graph.add_node("select_mask", _select_mask)
    graph.add_node("decide_should_act", _decide_should_act)
    graph.add_node("llm_invoke", _llm_invoke)
    graph.add_node("tool_execute", _tool_execute)

    # === Linear pipeline ===
    graph.add_edge(START, "update_player_state")
    graph.add_edge("update_player_state", "update_tarot")
    graph.add_edge("update_tarot", "update_eris_opinions")
    graph.add_edge("update_eris_opinions", "fracture_check")
    graph.add_edge("fracture_check", "select_mask")
    graph.add_edge("select_mask", "decide_should_act")
    graph.add_edge("decide_should_act", "llm_invoke")
    graph.add_edge("llm_invoke", "tool_execute")
    graph.add_edge("tool_execute", END)

    # Compile
    compiled = graph.compile()
    logger.info("LangGraph v2.0 compiled successfully (tarot-driven pipeline)")

    return compiled


def create_graph_for_studio():
    """Create graph for LangGraph Studio (without external dependencies)."""
    from .state import ErisMask, ErisState, create_default_profile

    graph = StateGraph(ErisState)

    # Simple nodes for testing
    async def test_update_player_state(state):
        return {
            "event_priority": state.get("event_priority"),
            "player_profiles": {"TestPlayer": create_default_profile()},
            "player_histories": {},
        }

    async def test_update_tarot(state):
        return {"player_profiles": state.get("player_profiles", {})}

    async def test_update_opinions(state):
        return {"player_profiles": state.get("player_profiles", {})}

    async def test_fracture(state):
        return {"fracture": 0, "phase": "normal", "apocalypse_triggered": False}

    async def test_mask(state):
        return {"current_mask": ErisMask.TRICKSTER}

    async def test_decision(state):
        return {
            "decision": {
                "intent": "confuse",
                "targets": [],
                "escalation": 30,
                "should_speak": True,
                "should_act": False,
                "tarot_reasoning": None,
            }
        }

    async def test_llm_invoke(state):
        return {"script": {"narrative_text": "", "planned_actions": []}}

    async def test_tool_execute(state):
        return {
            "approved_actions": [],
            "protection_warnings": [],
            "session": state.get("session", {}),
        }

    graph.add_node("update_player_state", test_update_player_state)
    graph.add_node("update_tarot", test_update_tarot)
    graph.add_node("update_eris_opinions", test_update_opinions)
    graph.add_node("fracture_check", test_fracture)
    graph.add_node("select_mask", test_mask)
    graph.add_node("decide_should_act", test_decision)
    graph.add_node("llm_invoke", test_llm_invoke)
    graph.add_node("tool_execute", test_tool_execute)

    graph.add_edge(START, "update_player_state")
    graph.add_edge("update_player_state", "update_tarot")
    graph.add_edge("update_tarot", "update_eris_opinions")
    graph.add_edge("update_eris_opinions", "fracture_check")
    graph.add_edge("fracture_check", "select_mask")
    graph.add_edge("select_mask", "decide_should_act")
    graph.add_edge("decide_should_act", "llm_invoke")
    graph.add_edge("llm_invoke", "tool_execute")
    graph.add_edge("tool_execute", END)

    return graph.compile()
