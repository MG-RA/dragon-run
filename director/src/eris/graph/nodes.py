"""LangGraph nodes for Eris decision-making."""

import random
import logging
from typing import Any, Dict

from langchain_core.messages import HumanMessage, SystemMessage

from ..graph.state import ErisState, ErisMask, EventPriority
from ..persona.prompts import build_eris_prompt, build_fast_chat_prompt
from ..core.database import Database
from ..core.memory import ShortTermMemory

logger = logging.getLogger(__name__)


async def event_classifier(state: ErisState) -> Dict[str, Any]:
    """
    Fast classification of incoming events.
    Determines priority and whether to process.
    NO LLM CALL - pure logic for speed.
    """
    event = state["current_event"]
    if not event:
        return {"event_priority": EventPriority.ROUTINE}

    event_type = event.get("eventType", "")

    priority_map = {
        "player_death": EventPriority.CRITICAL,
        "dragon_killed": EventPriority.CRITICAL,
        "player_chat": EventPriority.HIGH,
        "player_damaged": EventPriority.HIGH,
        "dimension_change": EventPriority.MEDIUM,
        "resource_milestone": EventPriority.MEDIUM,
        "run_started": EventPriority.MEDIUM,
        "run_ended": EventPriority.MEDIUM,
        "state": EventPriority.LOW,
    }

    priority = priority_map.get(event_type, EventPriority.ROUTINE)

    # Upgrade priority for close calls
    if event_type == "player_damaged":
        if event.get("data", {}).get("isCloseCall"):
            priority = EventPriority.HIGH

    return {"event_priority": priority}


async def context_enricher(state: ErisState, db: Database) -> Dict[str, Any]:
    """
    Enrich context with player history from PostgreSQL.
    Query long-term memory for relevant player data.
    """
    if not db or not db.pool:
        logger.warning("Database not available for context enrichment")
        return {"player_histories": {}}

    players = state["game_state"].get("players", [])
    player_histories = {}

    for player in players:
        uuid = player.get("uuid")
        if uuid:
            try:
                history = await db.get_player_summary(uuid)
                if history:
                    player_histories[player["username"]] = history
            except Exception as e:
                logger.error(f"Error fetching player history for {uuid}: {e}")

    return {"player_histories": player_histories}


async def mask_selector(state: ErisState) -> Dict[str, Any]:
    """
    Select or maintain Eris's current personality mask.
    NO LLM CALL - probabilistic selection based on context.
    """
    import random

    event = state["current_event"]
    current_mask = state["current_mask"]
    mask_stability = state["mask_stability"]

    # Chance to switch masks based on stability
    if random.random() > mask_stability:
        # Context-aware mask selection
        event_type = event.get("eventType", "") if event else ""

        if event_type == "player_death":
            mask = random.choice([ErisMask.PROPHET, ErisMask.CHAOS_BRINGER])
        elif event_type == "player_chat":
            mask = random.choice([ErisMask.TRICKSTER, ErisMask.FRIEND, ErisMask.GAMBLER])
        elif "milestone" in event_type:
            mask = random.choice([ErisMask.TRICKSTER, ErisMask.FRIEND])
        elif event_type == "dragon_killed":
            mask = random.choice(
                [ErisMask.CHAOS_BRINGER, ErisMask.TRICKSTER, ErisMask.OBSERVER]
            )
        else:
            mask = random.choice(list(ErisMask))

        logger.info(f"🎭 Mask switched: {current_mask.value} → {mask.value}")
        return {"current_mask": mask, "mask_stability": 0.7}

    # Decay stability over time
    return {"mask_stability": max(0.3, mask_stability - 0.05)}


async def decision_node(state: ErisState, llm: Any) -> Dict[str, Any]:
    """
    Main LLM decision point - determines what action to take.
    Uses structured output for reliability.
    """
    from langchain_core.messages import AIMessage

    # Build context-aware system prompt
    context_str = _build_context(state)
    system_prompt = build_eris_prompt(state["current_mask"], context_str)

    # Decision prompt
    event = state["current_event"]
    decision_prompt = f"""
Current Event: {event.get('eventType', 'unknown')}
Event Data: {event.get('data', {})}

Analyze this situation and decide:
1. Should you SPEAK? (broadcast to all or message specific player)
2. Should you INTERVENE? (use tools like spawn_mob, give, effect, etc.)
3. What tone should you use? (current mask: {state['current_mask'].value})

Respond with your decision in this format:
SPEAK: [yes/no]
INTERVENTION: [yes/no]
TONE: [your current mask tone]
ACTION: [brief description of what to do]
"""

    try:
        response = await llm.ainvoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=decision_prompt)]
        )

        # Parse response
        content = response.content
        should_speak = "speak: yes" in content.lower()
        should_intervene = "intervention: yes" in content.lower()

        logger.info(
            f"🎯 Decision: speak={should_speak}, intervene={should_intervene}, mask={state['current_mask'].value}"
        )

        return {
            "messages": [response],
            "should_speak": should_speak,
            "should_intervene": should_intervene,
        }
    except Exception as e:
        logger.error(f"Error in decision node: {e}")
        # Fallback: low frequency random response
        return {
            "should_speak": random.random() < 0.2,
            "should_intervene": random.random() < 0.1,
        }


async def fast_response(state: ErisState, llm: Any) -> Dict[str, Any]:
    """
    Fast path for chat responses - prioritizes latency.
    Simpler prompt, immediate response.
    """
    from langchain_core.messages import AIMessage

    event = state.get("current_event") or {}
    chat_data = event.get("data", {})
    player = chat_data.get("player", "Unknown")
    message = chat_data.get("message", "")

    prompt = build_fast_chat_prompt(state["current_mask"], player, message)

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])

        logger.info(f"💬 Fast chat response to {player}")

        return {
            "messages": [response],
            "planned_actions": [
                {"tool": "broadcast", "args": {"message": response.content}}
            ],
        }
    except Exception as e:
        logger.error(f"Error in fast_response: {e}")
        return {"planned_actions": []}


async def speak_node(state: ErisState, llm: Any) -> Dict[str, Any]:
    """
    Generate speech after decision node determines we should speak.
    Creates the actual message content based on the event and mask.
    """
    event = state.get("current_event") or {}
    event_type = event.get("eventType", "unknown")
    event_data = event.get("data", {})
    mask = state.get("current_mask", ErisMask.TRICKSTER)

    # Build context for speech generation
    context_str = _build_context(state)
    system_prompt = build_eris_prompt(mask, context_str)

    speech_prompt = f"""
Event: {event_type}
Data: {event_data}

Generate a short in-character response (1-3 sentences) as Eris with your current mask ({mask.value}).
Be dramatic, mysterious, or playful as appropriate. Reference specific players if relevant.
Do NOT include the [Eris] prefix - it's added automatically.
Just output the message text, nothing else.
"""

    try:
        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=speech_prompt)
        ])

        message = response.content.strip()
        logger.info(f"🎭 Eris speaks ({mask.value}): {message[:50]}...")

        return {
            "messages": [response],
            "planned_actions": [
                {"tool": "broadcast", "args": {"message": message}}
            ],
        }
    except Exception as e:
        logger.error(f"Error in speak_node: {e}")
        return {"planned_actions": []}


async def tool_executor(state: ErisState, ws_client: Any) -> Dict[str, Any]:
    """
    Execute planned actions via WebSocket.
    """
    results = []
    for action in state["planned_actions"]:
        tool_name = action["tool"]
        args = action["args"]

        try:
            result = await ws_client.send_command(tool_name, args, reason="Eris Action")
            results.append(
                {"tool": tool_name, "success": result}
            )
            logger.info(f"✅ Tool executed: {tool_name}")
        except Exception as e:
            logger.error(f"Error executing {tool_name}: {e}")
            results.append({"tool": tool_name, "success": False})

    session = state["session"].copy()
    session["actions_taken"].extend(results)

    return {"session": session}


def _build_context(state: ErisState) -> str:
    """Build narrative context for Eris prompt."""
    lines = []

    # Game state
    game_state = state["game_state"]
    if game_state:
        lines.append(f"Game State: {game_state.get('gameState', 'UNKNOWN')}")
        players = game_state.get("players", [])
        if players:
            lines.append(f"Players Online: {len(players)}")
            for p in players:
                health = p.get("health", 0)
                location = p.get("dimension", "Overworld")
                lines.append(f"  - {p.get('username')}: {health}♥ ({location})")

    # Recent events
    if state["context_buffer"]:
        lines.append(f"\nRecent Events:\n{state['context_buffer']}")

    # Player histories
    if state["player_histories"]:
        lines.append("\nPlayer Stats:")
        for username, history in list(state["player_histories"].items())[:3]:
            aura = history.get("aura", 0)
            dragons = history.get("dragons_killed", 0)
            lines.append(f"  - {username}: {aura} aura, {dragons} dragons killed")

    return "\n".join(lines) if lines else "No context available."
