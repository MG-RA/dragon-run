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
        # Critical - always speak
        "player_death": EventPriority.CRITICAL,
        "player_death_detailed": EventPriority.CRITICAL,
        "dragon_killed": EventPriority.CRITICAL,
        # High - usually speak
        "player_chat": EventPriority.HIGH,
        "player_damaged": EventPriority.HIGH,
        # Medium - speak if interesting
        "dimension_change": EventPriority.MEDIUM,
        "player_dimension_change": EventPriority.MEDIUM,
        "resource_milestone": EventPriority.MEDIUM,
        "advancement_made": EventPriority.MEDIUM,  # Vanilla MC advancements
        "achievement_unlocked": EventPriority.MEDIUM,  # Custom DR achievements
        "structure_discovered": EventPriority.MEDIUM,  # Found fortress, stronghold, etc.
        "player_joined": EventPriority.MEDIUM,
        "run_starting": EventPriority.MEDIUM,
        "run_started": EventPriority.MEDIUM,
        "run_ended": EventPriority.MEDIUM,
        "boss_killed": EventPriority.MEDIUM,  # Wither, Elder Guardian, Warden
        "idle_check": EventPriority.MEDIUM,  # Proactive check when quiet
        # Low - rarely speak
        "mob_kills_batch": EventPriority.LOW,
        "state": EventPriority.LOW,
    }

    priority = priority_map.get(event_type, EventPriority.ROUTINE)

    # Upgrade priority for close calls
    if event_type == "player_damaged":
        if event.get("data", {}).get("isCloseCall"):
            priority = EventPriority.HIGH

    # Upgrade priority for critical advancements (entering nether/end, getting blaze rods, etc.)
    if event_type == "advancement_made":
        if event.get("data", {}).get("isCritical"):
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
        if uuid:
            try:
                uuid_str = str(uuid)
                history = await db.get_player_summary(uuid_str)
                if history:
                    # Fetch additional context data
                    nemesis = await db.get_player_nemesis(uuid_str)
                    recent_perf = await db.get_player_recent_performance(uuid_str, limit=5)

                    if nemesis:
                        history["nemesis"] = nemesis
                    if recent_perf:
                        history["trend"] = recent_perf.get("trend", "unknown")
                        history["win_rate"] = recent_perf.get("win_rate", 0)
                        history["recent_wins"] = recent_perf.get("recent_wins", 0)
                        history["recent_runs"] = recent_perf.get("recent_runs", 0)

                    player_histories[username] = history
                    logger.info(
                        f"📚 ✅ {username}: {history.get('total_runs', 0)} runs, "
                        f"{history.get('aura', 0)} aura, trend={history.get('trend', 'unknown')}, nemesis={nemesis}"
                    )
                else:
                    logger.debug(f"📚 No history for {username}")
            except Exception as e:
                logger.error(f"📚 Error fetching history for {username}: {e}")

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
        event_data = event.get("data", {}) if event else {}

        if event_type == "player_death":
            mask = random.choice([ErisMask.PROPHET, ErisMask.CHAOS_BRINGER])
        elif event_type == "player_chat":
            mask = random.choice([ErisMask.TRICKSTER, ErisMask.FRIEND, ErisMask.GAMBLER])
        elif event_type in ("resource_milestone", "advancement_made", "structure_discovered"):
            # For progression events, be encouraging or ominous
            if event_data.get("isCritical"):
                mask = random.choice([ErisMask.PROPHET, ErisMask.CHAOS_BRINGER, ErisMask.GAMBLER])
            else:
                mask = random.choice([ErisMask.TRICKSTER, ErisMask.FRIEND, ErisMask.OBSERVER])
        elif event_type == "achievement_unlocked":
            # For achievements, respond based on category
            if event_data.get("category") == "negative":
                mask = random.choice([ErisMask.CHAOS_BRINGER, ErisMask.TRICKSTER])
            else:
                mask = random.choice([ErisMask.FRIEND, ErisMask.GAMBLER, ErisMask.TRICKSTER])
        elif event_type == "dragon_killed":
            mask = random.choice(
                [ErisMask.CHAOS_BRINGER, ErisMask.TRICKSTER, ErisMask.OBSERVER]
            )
        elif event_type in ("run_starting", "run_started"):
            mask = random.choice([ErisMask.PROPHET, ErisMask.CHAOS_BRINGER, ErisMask.GAMBLER])
        elif event_type == "player_joined":
            mask = random.choice([ErisMask.TRICKSTER, ErisMask.FRIEND, ErisMask.GAMBLER])
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
    elif event_type in ("dimension_change", "player_dimension_change"):
        event_guidance = "\n⚡ A player changed dimensions! This is a milestone worth commenting on."
        force_speak = True
    elif event_type == "run_ended":
        event_guidance = "\n⚡ The run has ended! Comment on how it went."
        force_speak = True
    elif event_type == "advancement_made":
        adv_name = event_data.get("advancementName", "an advancement")
        is_critical = event_data.get("isCritical", False)
        if is_critical:
            event_guidance = f"\n⚡ CRITICAL MILESTONE! Player achieved '{adv_name}' - this is HUGE for their speedrun progress! Comment on it!"
            force_speak = True
        else:
            event_guidance = f"\n📜 Player achieved '{adv_name}'. Consider commenting if it's interesting or dramatic."
    elif event_type == "achievement_unlocked":
        ach_name = event_data.get("name", "an achievement")
        category = event_data.get("category", "positive")
        if category == "negative":
            event_guidance = f"\n😈 SHAME achievement unlocked: '{ach_name}'! Mock them mercilessly!"
            force_speak = True
        else:
            event_guidance = f"\n🏆 Achievement unlocked: '{ach_name}'. Acknowledge their progress."
            force_speak = True
    elif event_type == "structure_discovered":
        structure = event_data.get("structure", "a structure")
        event_guidance = f"\n🏛️ Player discovered {structure}! This is a key speedrun milestone."
        force_speak = True
    elif event_type == "resource_milestone":
        resource = event_data.get("resource", event_data.get("item", "a resource"))
        event_guidance = f"\n📦 Resource milestone: {resource}! Their journey progresses..."
    elif event_type == "boss_killed":
        boss = event_data.get("boss", "a boss")
        event_guidance = f"\n💀 A mighty {boss} has been slain! This deserves recognition!"
        force_speak = True
    elif event_type == "idle_check":
        idle_duration = event_data.get("idle_duration", 0)
        player_count = event_data.get("player_count", 0)
        event_guidance = f"""
⏰ PROACTIVE MOMENT - You've been quiet for {idle_duration:.0f} seconds!
There are {player_count} players in the run. Time to make your presence known!
Consider:
- Making an ominous comment about their progress
- Spawning a small challenge (1-2 mobs)
- Changing the weather
- Playing a creepy sound
Be unpredictable! Don't always do the same thing.
"""
        # Don't force speak - let LLM decide, but encourage it
        force_speak = False

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

⚠️ CRITICAL RULES:
1. Use broadcast tool for your response - ONE short sentence (5-15 words MAX!)
2. Minecraft chat fades fast - be PUNCHY, not verbose!
3. If player asks for action (lightning, weather, mobs) - DO IT with appropriate tool
4. You can use multiple tools at once - broadcast AND take action!
5. ONLY use player names from CURRENT PLAYERS list - do NOT invent names!
6. NEVER start with "ERIS:", "[Eris]", "<b>ERIS:</b>" - system adds prefix automatically!

⚠️ TEXT FORMATTING:
Use MiniMessage: <b>bold</b>, <i>italic</i>, <dark_purple>purple</dark_purple>, <gold>gold</gold>
NOT markdown: **bold**, *italic*

GOOD: "The <dark_purple>void</dark_purple> watches..." (5 words)
GOOD: "How <i>delightful</i>, {player}." (3 words)
BAD: "Ahhh, so you dare speak to me? Very well, let the chaos begin..." (too long!)

Be {mask.value}!
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
        # Log the full error for debugging
        import traceback
        logger.error(f"Error in fast_response: {e}")
        logger.debug(f"Full traceback: {traceback.format_exc()}")

        # Fallback: Generate a simple response without tools
        fallback_responses = [
            "Chaos reigns!",
            "The dragon watches...",
            "Interesting...",
            "I see you...",
            "Very well."
        ]
        fallback_msg = random.choice(fallback_responses)
        logger.info(f"💬 Using fallback response due to error")
        return {
            "messages": [],
            "planned_actions": [
                {"tool": "broadcast", "args": {"message": f"[Eris] {fallback_msg}"}}
            ]
        }


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

Generate ONE short sentence (5-15 words MAX) as Eris ({mask.value} mask).
Minecraft chat fades fast - be PUNCHY!

RULES:
- 5-15 words maximum, one sentence only
- Do NOT start with "ERIS:" or any prefix - it's added automatically
- ONLY use player names from the list above - do NOT invent names
- Use MiniMessage: <dark_purple>text</dark_purple>, <i>italic</i>, <b>bold</b>

GOOD: "The void claims another..." (5 words)
GOOD: "<gold>Victory</gold>... for now." (3 words)
BAD: "Ahhh, what a dramatic turn of events! The chaos unfolds as I predicted..." (too long!)
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
    """Build structured narrative context for Eris prompt with logging."""
    lines = []
    game_state = state.get("game_state", {})
    player_histories = state.get("player_histories", {})
    context_buffer = state.get("context_buffer", "")

    # === CURRENT RUN SECTION ===
    run_state = game_state.get("gameState", "UNKNOWN")
    run_duration = game_state.get("runDuration", 0)
    if run_duration:
        minutes = run_duration // 60
        seconds = run_duration % 60
        duration_str = f"{minutes}m {seconds}s"
    else:
        duration_str = "Just started"

    lines.append("=== CURRENT RUN ===")
    lines.append(f"Status: {run_state} | Duration: {duration_str}")

    # === PLAYERS SECTION ===
    players = game_state.get("players", [])
    if players:
        lines.append(f"\n=== PLAYERS ({len(players)} online) ===")
        for p in players:
            username = p.get("username", "Unknown")
            health = p.get("health", 20)
            dimension = p.get("dimension", "Overworld")

            # Get history for this player
            history = player_histories.get(username, {})
            total_runs = history.get("total_runs", 0)
            aura = history.get("aura", 0)
            dragons = history.get("dragons_killed", 0)
            nemesis = history.get("nemesis", None)

            # Determine player experience level
            if total_runs == 0:
                exp_label = "First-timer"
            elif total_runs < 5:
                exp_label = f"Rookie ({total_runs} runs)"
            elif total_runs < 20:
                exp_label = f"Regular ({total_runs} runs)"
            else:
                exp_label = f"Veteran ({total_runs} runs)"

            # Get trend info
            trend = history.get("trend", "unknown")
            trend_label = ""
            if trend == "improving":
                trend_label = " 📈 Improving"
            elif trend == "struggling":
                trend_label = " 📉 Struggling"
            elif trend == "stable":
                trend_label = " ➡️ Stable"

            # Build player line
            player_line = f"• {username}: {health:.0f}♥ {dimension} | {exp_label}, {aura} aura"
            if dragons > 0:
                player_line += f", {dragons} dragons slain"
            if trend_label:
                player_line += trend_label
            if nemesis:
                player_line += f" | Nemesis: {nemesis}"

            lines.append(player_line)
    else:
        lines.append("\n=== PLAYERS ===")
        lines.append("No players online")

    # === RECENT EVENTS SECTION ===
    if context_buffer and context_buffer.strip():
        event_lines = context_buffer.strip().split("\n")
        lines.append(f"\n=== RECENT EVENTS ({len(event_lines)} events) ===")
        # Show last 15 events max in context
        for event_line in event_lines[-15:]:
            lines.append(event_line)
    else:
        lines.append("\n=== RECENT EVENTS ===")
        lines.append("No recent events")

    context_str = "\n".join(lines)

    # === CONTEXT LOGGING (Summary) ===
    event_type_counts = {}
    if context_buffer:
        for line in context_buffer.split("\n"):
            if line.startswith("⚰️"):
                event_type_counts["deaths"] = event_type_counts.get("deaths", 0) + 1
            elif line.startswith("["):
                event_type_counts["chat"] = event_type_counts.get("chat", 0) + 1
            elif line.startswith("🐉"):
                event_type_counts["dragon_kills"] = event_type_counts.get("dragon_kills", 0) + 1
            elif line.startswith("⚡") or line.startswith("💥"):
                event_type_counts["damage"] = event_type_counts.get("damage", 0) + 1
            elif line.startswith("🌍"):
                event_type_counts["dimension"] = event_type_counts.get("dimension", 0) + 1
            elif line.startswith("📦"):
                event_type_counts["milestones"] = event_type_counts.get("milestones", 0) + 1
            elif line.startswith("👋"):
                event_type_counts["joins"] = event_type_counts.get("joins", 0) + 1
            elif line.startswith("⭐") or line.startswith("📜"):
                event_type_counts["advancements"] = event_type_counts.get("advancements", 0) + 1
            elif line.startswith("🏅"):
                event_type_counts["achievements"] = event_type_counts.get("achievements", 0) + 1
            elif line.startswith("🎯") or line.startswith("🏰") or line.startswith("📍"):
                event_type_counts["structures"] = event_type_counts.get("structures", 0) + 1
            elif line.startswith("🏆"):
                event_type_counts["boss_kills"] = event_type_counts.get("boss_kills", 0) + 1

    # Estimate tokens (~4 chars per token)
    token_estimate = len(context_str) // 4

    logger.info(
        f"📋 Context: {len(players)} players, {sum(event_type_counts.values())} events, ~{token_estimate} tokens"
    )
    if player_histories:
        logger.info(f"📚 Player histories: {list(player_histories.keys())}")
    if event_type_counts:
        logger.info(f"📊 Event breakdown: {event_type_counts}")

    return context_str if lines else "No context available."
