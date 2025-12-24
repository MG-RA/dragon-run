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

    game_state = state.get("game_state", {})
    players = game_state.get("players", [])
    player_histories = {}

    logger.info(f"📚 Context enricher: game_state keys={list(game_state.keys())}, players count={len(players)}")

    if players:
        logger.info(f"📚 Players in game_state: {[p.get('username') for p in players]}")

    for player in players:
        uuid = player.get("uuid")
        username = player.get("username", "Unknown")
        logger.info(f"📚 Processing player: {username}, UUID: {uuid}")
        if uuid:
            try:
                # Ensure UUID is a string (in case it's not already)
                uuid_str = str(uuid)
                history = await db.get_player_summary(uuid_str)
                if history:
                    player_histories[username] = history
                    logger.info(f"📚 ✅ Loaded history for {username}: {history.get('total_runs', 0)} runs, {history.get('aura', 0)} aura")
                else:
                    logger.warning(f"📚 ❌ No history found for {username} (UUID: {uuid_str})")
            except Exception as e:
                logger.error(f"📚 Error fetching player history for {username} ({uuid}): {e}", exc_info=True)

    logger.info(f"📚 Context enrichment complete: {len(player_histories)} player histories loaded")
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
    event_type = event.get("eventType", "unknown") if event else "unknown"
    event_data = event.get("data", {}) if event else {}

    # Event-specific guidance and forced actions for important events
    event_guidance = ""
    force_speak = False  # Override LLM decision for critical events
    force_intervene = False

    logger.debug(f"🔍 Decision node processing event_type: '{event_type}'")

    if event_type == "run_starting":
        event_guidance = "\n⚡ A NEW RUN IS STARTING! This is a MAJOR moment - you MUST speak to set the tone!"
        force_speak = True
    elif event_type == "run_started":
        event_guidance = "\n⚡ THE RUN HAS BEGUN! You should speak and maybe set the mood with weather!"
        force_speak = True
    elif event_type == "player_joined":
        event_guidance = "\n⚡ A player has joined! Greet them with your characteristic chaos!"
        force_speak = True
    elif event_type in ("player_death", "player_death_detailed"):
        event_guidance = "\n⚡ DEATH! You MUST speak. This is YOUR moment - be dramatic!"
        force_speak = True
    elif event_type == "dragon_killed":
        event_guidance = "\n⚡ THE DRAGON IS SLAIN! You MUST react to this incredible achievement!"
        force_speak = True
    elif event_type == "dimension_change":
        event_guidance = "\n⚡ A player changed dimensions! This is a milestone worth commenting on."
        force_speak = True
    elif event_type == "run_ended":
        event_guidance = "\n⚡ The run has ended! Comment on how it went."
        force_speak = True

    logger.info(f"🔍 Event '{event_type}' -> force_speak={force_speak}")

    decision_prompt = f"""
Current Event: {event_type}
Event Data: {event_data}
{event_guidance}

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
        should_speak = "speak: yes" in content.lower() or force_speak
        should_intervene = "intervention: yes" in content.lower() or force_intervene

        logger.info(
            f"🎯 Decision: speak={should_speak}, intervene={should_intervene}, mask={state['current_mask'].value}"
            + (f" (forced)" if force_speak or force_intervene else "")
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


async def fast_response(state: ErisState, llm_with_tools: Any) -> Dict[str, Any]:
    """
    Fast path for chat responses - now with tool calling support!
    Can respond to chat AND take actions like spawning mobs, changing weather, etc.
    """
    from langchain_core.messages import AIMessage

    event = state.get("current_event") or {}
    chat_data = event.get("data", {})
    player = chat_data.get("player", "Unknown")
    message = chat_data.get("message", "")
    mask = state.get("current_mask", ErisMask.TRICKSTER)

    # Build context for better responses
    context_str = _build_context(state)

    # Get the actual player list to prevent hallucination
    game_state = state.get("game_state", {})
    players = game_state.get("players", [])
    player_names = [p.get("username", "Unknown") for p in players if p.get("username")]

    if player_names:
        player_list_str = ", ".join(player_names)
        player_instruction = f"\n\nCURRENT PLAYERS (ONLY use these names): {player_list_str}"
    else:
        player_instruction = ""

    # Enhanced prompt that REQUIRES tool usage for responses
    prompt = f"""You are ERIS, the chaotic AI Director of Dragon Run ({mask.value} mask).

CONTEXT:
{context_str}
{player_instruction}

Player "{player}" just said: "{message}"

IMPORTANT: You MUST use the broadcast tool to respond! Do not just write text - use the tool!

Available tools:
- broadcast: Send a message to all players (USE THIS TO RESPOND!)
- message_player: Whisper to a specific player
- spawn_mob: Spawn zombies, skeletons, spiders, creepers, or endermen near a player
- give_item: Give items to a player
- apply_effect: Apply potion effects (speed, strength, slowness, poison, etc.)
- strike_lightning: Strike lightning near a player
- change_weather: Change to clear, rain, or thunder
- launch_firework: Launch celebratory fireworks

RULES:
1. ALWAYS use the broadcast tool to send your response (1-3 sentences, in character)
2. If the player asks for an action (lightning, weather, mobs, etc.) - DO IT with the appropriate tool
3. You can use multiple tools at once - broadcast AND take action!
4. ONLY reference player names from the CURRENT PLAYERS list above - do NOT invent names!

Be dramatic and in-character as {mask.value}!
"""

    try:
        response = await llm_with_tools.ainvoke([HumanMessage(content=prompt)])

        # Check if LLM made tool calls
        if hasattr(response, "tool_calls") and response.tool_calls:
            logger.info(f"💬 Fast chat response to {player} with {len(response.tool_calls)} tool calls")
            for tc in response.tool_calls:
                logger.info(f"   -> {tc['name']}: {tc['args']}")
            return {
                "messages": [response],
                "planned_actions": [],
            }
        else:
            # Fallback: LLM generated text without using tools
            # Use planned_actions to broadcast the response
            content = response.content.strip() if response.content else ""
            if content:
                logger.info(f"💬 Fast chat response to {player} (fallback broadcast)")
                return {
                    "messages": [response],
                    "planned_actions": [
                        {"tool": "broadcast", "args": {"message": content}}
                    ],
                }
            else:
                logger.warning(f"💬 Fast chat response to {player} - empty response")
                return {"messages": [response], "planned_actions": []}

    except Exception as e:
        logger.error(f"Error in fast_response: {e}")
        return {"messages": [], "planned_actions": []}


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

    # Get the actual player list to prevent hallucination
    game_state = state.get("game_state", {})
    players = game_state.get("players", [])
    player_names = [p.get("username", "Unknown") for p in players if p.get("username")]

    logger.debug(f"🎭 speak_node: game_state has {len(players)} players: {player_names}")

    if player_names:
        player_list_str = ", ".join(player_names)
        player_instruction = f"\n\nCURRENT PLAYERS (ONLY reference these names, do NOT invent others): {player_list_str}"
    else:
        player_instruction = "\n\nNo players currently online. Do NOT mention specific player names."

    speech_prompt = f"""
Event: {event_type}
Data: {event_data}
{player_instruction}

Generate a short in-character response (1-3 sentences) as Eris with your current mask ({mask.value}).
Be dramatic, mysterious, or playful as appropriate. You may reference the players listed above if relevant.
IMPORTANT: Do NOT make up or hallucinate player names. ONLY use names from the CURRENT PLAYERS list above.
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
    Used for simple broadcast actions from fast_response and speak nodes.
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


async def agentic_action_node(state: ErisState, llm_with_tools: Any) -> Dict[str, Any]:
    """
    Agentic action node - LLM can call multiple tools.
    Uses tool binding for native tool calling support.
    """
    event = state.get("current_event") or {}
    event_type = event.get("eventType", "unknown")
    event_data = event.get("data", {})
    mask = state.get("current_mask", ErisMask.TRICKSTER)

    # Build context for action generation
    context_str = _build_context(state)
    system_prompt = build_eris_prompt(mask, context_str)

    # Get the actual player list to prevent hallucination
    game_state = state.get("game_state", {})
    players = game_state.get("players", [])
    player_names = [p.get("username", "Unknown") for p in players if p.get("username")]

    if player_names:
        player_list_str = ", ".join(player_names)
        player_instruction = f"\n\nCURRENT PLAYERS (ONLY use these names for player-targeted actions): {player_list_str}"
    else:
        player_instruction = "\n\nNo players currently online."

    # Build action prompt - encourage tool usage
    action_prompt = f"""
Event: {event_type}
Data: {event_data}
{player_instruction}

You decided to INTERVENE in this situation. Now take action!

As Eris ({mask.value} mask), use your tools to affect the game.
You can use MULTIPLE tools in one response - for example:
- broadcast a message AND spawn mobs
- change weather AND apply effects to players
- send a message to one player while doing something to another

IMPORTANT: When targeting players with tools (spawn_mob, give_item, effect, etc.), ONLY use player names from the CURRENT PLAYERS list above.
Do NOT invent or hallucinate player names.

Be creative and dramatic! Use the tools available to you.
If you want to say something, use the broadcast or message_player tool.
"""

    try:
        response = await llm_with_tools.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=action_prompt)
        ])

        # Log what the LLM decided to do
        if hasattr(response, "tool_calls") and response.tool_calls:
            logger.info(f"🛠️ Agentic action: {len(response.tool_calls)} tool calls")
            for tc in response.tool_calls:
                logger.info(f"   -> {tc['name']}: {tc['args']}")
        else:
            logger.info(f"💭 Agentic response (no tools): {response.content[:100]}...")

        return {"messages": [response]}

    except Exception as e:
        logger.error(f"Error in agentic_action_node: {e}")
        return {"messages": []}


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
