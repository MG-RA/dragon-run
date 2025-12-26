"""LangGraph nodes for Eris decision-making - v1.1 Linear Pipeline.

New architecture: All events flow through the full linear pipeline:
event_classifier -> context_enricher -> mask_selector -> decision_node ->
agentic_action -> protection_decision -> tool_executor -> END

No more fast paths or conditional routing.
"""

import random
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from ..graph.state import (
    ErisState, ErisMask, EventPriority, ErisIntent,
    MaskConfig, DecisionOutput, ScriptOutput, PlannedAction
)
from ..persona.prompts import build_eris_prompt
from ..persona.masks import get_mask_config, get_all_discouraged_tools, MASK_TRAITS
from ..persona.debt import (
    calculate_mask_probabilities, get_intent_weights, get_debt_narrative_hint,
    calculate_debt_delta, check_debt_resolution, MASK_DEBT_FIELDS
)
from ..core.database import Database

logger = logging.getLogger(__name__)


# === Node 1: Event Classifier ===

async def event_classifier(state: ErisState) -> Dict[str, Any]:
    """
    Fast classification of incoming events.
    Determines priority and metadata.
    NO LLM CALL - pure logic for speed.

    In v1.1: No conditional routing - always proceeds to next node.
    """
    event = state["current_event"]
    if not event:
        return {"event_priority": EventPriority.ROUTINE}

    event_type = event.get("eventType", "")

    priority_map = {
        # Critical - always process
        "player_death": EventPriority.CRITICAL,
        "player_death_detailed": EventPriority.CRITICAL,
        "dragon_killed": EventPriority.CRITICAL,
        "eris_close_call": EventPriority.CRITICAL,
        "eris_caused_death": EventPriority.CRITICAL,
        "eris_respawn_override": EventPriority.CRITICAL,
        # High - usually process
        "player_chat": EventPriority.HIGH,
        "player_damaged": EventPriority.HIGH,
        # Medium - process if interesting
        "dimension_change": EventPriority.MEDIUM,
        "player_dimension_change": EventPriority.MEDIUM,
        "resource_milestone": EventPriority.MEDIUM,
        "advancement_made": EventPriority.MEDIUM,
        "achievement_unlocked": EventPriority.MEDIUM,
        "structure_discovered": EventPriority.MEDIUM,
        "player_joined": EventPriority.MEDIUM,
        "run_starting": EventPriority.MEDIUM,
        "run_started": EventPriority.MEDIUM,
        "run_ended": EventPriority.MEDIUM,
        "boss_killed": EventPriority.MEDIUM,
        "idle_check": EventPriority.MEDIUM,
        "eris_protection_used": EventPriority.MEDIUM,
        "eris_rescue_used": EventPriority.MEDIUM,
        # Low - rarely process
        "mob_kills_batch": EventPriority.LOW,
        "state": EventPriority.LOW,
        "item_collected": EventPriority.LOW,
        "entity_leashed": EventPriority.LOW,
        "vehicle_entered": EventPriority.LOW,
        "vehicle_exited": EventPriority.LOW,
    }

    priority = priority_map.get(event_type, EventPriority.ROUTINE)

    # Upgrade priority for close calls
    if event_type == "player_damaged":
        if event.get("data", {}).get("isCloseCall"):
            priority = EventPriority.HIGH

    # Upgrade priority for critical advancements
    if event_type == "advancement_made":
        if event.get("data", {}).get("isCritical"):
            priority = EventPriority.HIGH

    # Log protection events
    if event_type in ("eris_close_call", "eris_caused_death"):
        logger.info(f"🚨 PROTECTION EVENT: {event_type} - priority={priority.name}")

    logger.debug(f"📋 Event classified: {event_type} -> {priority.name}")
    return {"event_priority": priority}


# === Node 2: Context Enricher ===

async def context_enricher(state: ErisState, db: Database) -> Dict[str, Any]:
    """
    Enrich context with player history, debts, and prophecies from PostgreSQL.
    Also initializes fear/chaos from memory or defaults.

    v1.1: Also loads betrayal_debts and prophecy_state.
    """
    if not db or not db.pool:
        logger.warning("Database not available for context enrichment")
        return {
            "player_histories": {},
            "betrayal_debts": {},
            "prophecy_state": {},
        }

    game_state = state.get("game_state", {})
    players = game_state.get("players", [])
    player_histories = {}
    player_uuids = []

    logger.info(f"📚 Context enricher: {len(players)} players online")

    # Collect UUIDs for batch queries
    for player in players:
        uuid = player.get("uuid")
        if uuid:
            player_uuids.append(str(uuid))

    # Fetch player histories
    for player in players:
        uuid = player.get("uuid")
        username = player.get("username", "Unknown")
        if uuid:
            try:
                uuid_str = str(uuid)
                history = await db.get_player_summary(uuid_str)
                if history:
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
                    logger.debug(
                        f"📚 {username}: {history.get('total_runs', 0)} runs, "
                        f"{history.get('aura', 0)} aura"
                    )
            except Exception as e:
                logger.error(f"📚 Error fetching history for {username}: {e}")

    # Fetch betrayal debts for all players
    betrayal_debts = {}
    try:
        all_debts = await db.get_all_player_debts(player_uuids)
        # Map UUID -> username for debts
        for player in players:
            uuid = str(player.get("uuid", ""))
            username = player.get("username", "Unknown")
            if uuid in all_debts:
                betrayal_debts[username] = all_debts[uuid]
    except Exception as e:
        logger.error(f"📚 Error fetching betrayal debts: {e}")

    # Fetch active prophecies
    prophecy_state = {"active": {}, "count": 0}
    try:
        all_prophecies = await db.get_all_active_prophecies(player_uuids)
        for player in players:
            uuid = str(player.get("uuid", ""))
            username = player.get("username", "Unknown")
            if uuid in all_prophecies:
                prophecy_state["active"][username] = all_prophecies[uuid]
                prophecy_state["count"] += len(all_prophecies[uuid])
    except Exception as e:
        logger.error(f"📚 Error fetching prophecies: {e}")

    logger.info(
        f"📚 Context enriched: {len(player_histories)} histories, "
        f"{len(betrayal_debts)} debt records, {prophecy_state['count']} active prophecies"
    )

    return {
        "player_histories": player_histories,
        "betrayal_debts": betrayal_debts,
        "prophecy_state": prophecy_state,
    }


# === Node 3: Mask Selector ===

async def mask_selector(state: ErisState) -> Dict[str, Any]:
    """
    Select Eris's current personality mask with debt-influenced probability.
    Outputs rich MaskConfig with allowed behaviors and tool groups.

    v1.1: Uses betrayal_debts to influence mask selection probability.
    v1.2: Adds mask stickiness - masks persist for a minimum number of events.
    """
    event = state["current_event"]
    current_mask = state["current_mask"]
    betrayal_debts = state.get("betrayal_debts", {})
    global_chaos = state.get("global_chaos", 0)

    # Track mask persistence (sticky masks)
    session = state.get("session", {})
    mask_event_count = session.get("mask_event_count", 0)
    MASK_MIN_EVENTS = 3  # Minimum events before mask can change

    # Get primary player (target of current event)
    event_data = event.get("data", {}) if event else {}
    primary_player = event_data.get("player", event_data.get("username", ""))

    # Get debts for primary player
    player_debts = {}
    if primary_player and primary_player in betrayal_debts:
        # Convert mask names to debt field names
        for mask_name, debt_value in betrayal_debts[primary_player].items():
            debt_field = MASK_DEBT_FIELDS.get(mask_name, f"{mask_name.lower()}_debt")
            player_debts[debt_field] = debt_value

    # Context-aware base weights
    event_type = event.get("eventType", "") if event else ""

    # Check if mask should be sticky (maintain current mask)
    # Only allow mask change after minimum events, or on high-impact events
    high_impact_events = ("player_death", "dragon_killed", "run_started", "run_starting")
    if mask_event_count < MASK_MIN_EVENTS and event_type not in high_impact_events:
        # Keep current mask, just update count
        mask_config = get_mask_config(current_mask)
        logger.debug(f"🎭 Mask sticky: {current_mask.value} ({mask_event_count + 1}/{MASK_MIN_EVENTS})")
        return {
            "current_mask": current_mask,
            "mask_config": mask_config,
            "session": {**session, "mask_event_count": mask_event_count + 1},
        }

    base_weights = {mask.name: 1.0 for mask in ErisMask}

    # Adjust base weights based on event type
    if event_type in ("player_death", "player_death_detailed"):
        base_weights["PROPHET"] = 2.0
        base_weights["CHAOS_BRINGER"] = 2.0
    elif event_type == "player_chat":
        base_weights["TRICKSTER"] = 2.0
        base_weights["FRIEND"] = 1.5
        base_weights["GAMBLER"] = 1.5
    elif event_type in ("run_starting", "run_started"):
        base_weights["PROPHET"] = 2.0
        base_weights["CHAOS_BRINGER"] = 1.5
        base_weights["GAMBLER"] = 1.5
    elif event_type == "dragon_killed":
        base_weights["CHAOS_BRINGER"] = 1.5
        base_weights["TRICKSTER"] = 1.5
        base_weights["OBSERVER"] = 1.5
    elif event_type == "achievement_unlocked":
        if event_data.get("category") == "negative":
            base_weights["CHAOS_BRINGER"] = 2.0
            base_weights["TRICKSTER"] = 1.5
        else:
            base_weights["FRIEND"] = 1.5
            base_weights["GAMBLER"] = 1.5

    # Calculate debt-influenced probabilities
    mask_probs = calculate_mask_probabilities(player_debts, base_weights, global_chaos)

    # Select mask based on weighted probabilities
    masks = list(mask_probs.keys())
    weights = list(mask_probs.values())
    selected_mask_name = random.choices(masks, weights=weights, k=1)[0]
    selected_mask = ErisMask[selected_mask_name]

    # Build rich mask configuration
    mask_config = get_mask_config(selected_mask)

    # Adjust deception level based on debt
    if player_debts:
        debt_field = MASK_DEBT_FIELDS.get(selected_mask_name, "")
        if debt_field and debt_field in player_debts:
            debt = player_debts[debt_field]
            # High debt increases deception (things are about to change)
            if debt > 50:
                mask_config["deception_level"] = min(100, mask_config["deception_level"] + 20)

    if selected_mask != current_mask:
        logger.info(f"🎭 Mask switched: {current_mask.value} → {selected_mask.value}")
        # Reset mask event count when mask changes
        new_mask_event_count = 0
    else:
        logger.debug(f"🎭 Mask maintained: {selected_mask.value}")
        new_mask_event_count = mask_event_count + 1

    return {
        "current_mask": selected_mask,
        "mask_config": mask_config,
        "session": {**session, "mask_event_count": new_mask_event_count},
    }


# === Node 4: Decision Node ===

async def decision_node(state: ErisState, llm: Any) -> Dict[str, Any]:
    """
    Main LLM decision point - determines intent, targets, and escalation.
    Outputs structured DecisionOutput.

    v1.1: Uses mask_config and debt for intent weighting.
    """
    from langchain_core.messages import AIMessage

    event = state["current_event"]
    event_type = event.get("eventType", "unknown") if event else "unknown"
    event_data = event.get("data", {}) if event else {}
    mask = state["current_mask"]
    mask_config = state.get("mask_config") or get_mask_config(mask)
    global_chaos = state.get("global_chaos", 0)
    betrayal_debts = state.get("betrayal_debts", {})

    # Get primary player and their debt
    primary_player = event_data.get("player", event_data.get("username", ""))
    player_debt = 0
    debt_hint = None
    if primary_player and primary_player in betrayal_debts:
        player_debts_dict = betrayal_debts[primary_player]
        debt_field = MASK_DEBT_FIELDS.get(mask.name, "")
        if debt_field:
            for mask_name, value in player_debts_dict.items():
                if MASK_DEBT_FIELDS.get(mask_name) == debt_field:
                    player_debt = value
                    break
        debt_hint = get_debt_narrative_hint(mask, player_debt)

    # Get intent weights influenced by debt
    intent_weights = get_intent_weights(mask, player_debt, global_chaos)

    # Build context
    context_str = _build_context(state)
    system_prompt = build_eris_prompt(mask, context_str)

    # Force speak/act for certain events
    force_speak = False
    force_act = False
    event_guidance = ""

    if event_type in ("run_starting", "run_started"):
        event_guidance = "⚡ A NEW RUN IS STARTING! Set the tone with words AND action!"
        force_speak = True
        force_act = True  # Do something dramatic at run start
    elif event_type == "player_joined":
        event_guidance = "⚡ A player has joined! Greet them, maybe with a gift or effect!"
        force_speak = True
    elif event_type == "player_chat":
        chat_message = event_data.get("message", "")
        event_guidance = f"💬 Player said: \"{chat_message}\" - RESPOND! Consider an action too."
        force_speak = True
    elif event_type in ("player_death", "player_death_detailed"):
        event_guidance = "⚡ DEATH! Be dramatic with particles, sounds, or titles!"
        force_speak = True
        force_act = True  # Deaths deserve drama
    elif event_type == "dragon_killed":
        event_guidance = "⚡ THE DRAGON IS SLAIN! Fireworks? Lightning? Title?"
        force_speak = True
        force_act = True  # Victory needs celebration
    elif event_type in ("achievement_unlocked", "advancement_made"):
        advancement_name = event_data.get('name', event_data.get('advancement', 'unknown'))
        event_guidance = f"🏆 Achievement: {advancement_name} - Maybe particles or a gift?"
        force_speak = True
    elif event_type == "structure_discovered":
        event_guidance = f"🏛️ Structure found: {event_data.get('structure', 'unknown')} - Foreshadow what awaits!"
        force_speak = True
    elif event_type == "run_ended":
        outcome = event_data.get("outcome", "unknown")
        if outcome == "DEATH":
            event_guidance = "💀 RUN ENDED IN DEATH! Dramatic send-off with effects!"
            force_speak = True
            force_act = True
        elif outcome == "DRAGON_KILLED":
            event_guidance = "🎉 VICTORY! Celebrate with fireworks and fanfare!"
            force_speak = True
            force_act = True
    elif event_type == "idle_check":
        event_guidance = "⏰ You've been quiet. Disturb the peace! Spawn something, play a sound, DO something."
        force_act = True  # Idle checks should trigger actions
    elif event_type == "player_damaged":
        damage = event_data.get("damage", 0)
        health = event_data.get("health", 20)
        if health < 6:  # Low health
            event_guidance = f"⚠️ Player at {health/2:.0f} hearts! Taunt them or offer false mercy?"
            force_speak = True

    # Add debt hint if applicable
    if debt_hint:
        event_guidance += f"\n\n⚠️ DEBT PRESSURE:\n{debt_hint}"

    # Format intent weights for prompt
    intent_weights_str = ", ".join([f"{k}: {v:.0%}" for k, v in sorted(intent_weights.items(), key=lambda x: -x[1])[:3]])

    # Build action suggestions based on mask
    action_suggestions = []
    if mask.value == "trickster":
        action_suggestions = ["spawn silverfish", "teleport randomly", "give random item", "play weird sound"]
    elif mask.value == "prophet":
        action_suggestions = ["particles soul", "sound ambient.cave", "title with prophecy", "lightning"]
    elif mask.value == "chaos_bringer":
        action_suggestions = ["spawn mobs", "tnt", "damage", "weather thunder"]
    elif mask.value == "friend":
        action_suggestions = ["give helpful item", "heal", "particles heart", "effect speed"]
    elif mask.value == "observer":
        action_suggestions = ["particles", "sound", "lookat"]
    elif mask.value == "gambler":
        action_suggestions = ["give random item", "effect random", "spawn mob OR give item"]

    action_hint = f"Consider: {', '.join(action_suggestions)}" if action_suggestions else ""

    decision_prompt = f"""
Current Event: {event_type}
Event Data: {event_data}
{event_guidance}

Your mask: {mask.value.upper()}
Intent tendencies: {intent_weights_str}
Chaos level: {global_chaos}/100

INTENTS:
- bless: Help them (give items, heal, buffs)
- curse: Harm them (spawn mobs, debuffs, damage)
- test: Challenge them (spawn mobs, obstacles)
- confuse: Misdirect (teleport, weird gifts, cryptic messages)
- reveal: Share truth (foreshadow, warn, prophecy)
- lie: Deceive (fake death, false promises, traps)

{action_hint}

Choose your response:
INTENT: [bless/curse/test/confuse/reveal/lie]
TARGETS: [player names] or [all] or [none]
ESCALATION: [0-100] (low=subtle, high=dramatic)
SPEAK: [yes/no]
ACT: [yes/no]
"""

    try:
        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=decision_prompt)
        ])

        content = response.content.lower()

        # Parse intent
        intent = ErisIntent.CONFUSE.value  # default
        for i in ErisIntent:
            if f"intent: {i.value}" in content:
                intent = i.value
                break

        # Parse targets
        targets = []
        game_state = state.get("game_state", {})
        players = game_state.get("players", [])
        player_names = [p.get("username", "") for p in players if p.get("username")]

        if "targets: [all]" in content or "targets: all" in content:
            targets = player_names
        elif "targets: [none]" in content or "targets: none" in content:
            targets = []
        else:
            for name in player_names:
                if name.lower() in content:
                    targets.append(name)

        # Parse escalation
        escalation = 30  # default
        import re
        esc_match = re.search(r'escalation:\s*(\d+)', content)
        if esc_match:
            escalation = min(100, max(0, int(esc_match.group(1))))

        # Cap escalation based on chaos
        if global_chaos > 70:
            max_safe = 100 - (global_chaos * 0.5)
            if escalation > max_safe:
                logger.info(f"⚠️ Escalation capped from {escalation} to {max_safe} due to high chaos")
                escalation = int(max_safe)

        # Parse speak/act
        should_speak = "speak: yes" in content or force_speak
        should_act = "act: yes" in content or force_act

        decision = DecisionOutput(
            intent=intent,
            targets=targets,
            escalation=escalation,
            should_speak=should_speak,
            should_act=should_act,
        )

        logger.info(
            f"🎯 Decision: intent={intent}, targets={targets}, "
            f"escalation={escalation}, speak={should_speak}, act={should_act}"
        )

        return {
            "messages": [response],
            "decision": decision,
        }

    except Exception as e:
        logger.error(f"Error in decision node: {e}", exc_info=True)
        # Fallback decision
        return {
            "decision": DecisionOutput(
                intent=ErisIntent.CONFUSE.value,
                targets=[],
                escalation=20,
                should_speak=force_speak or random.random() < 0.3,
                should_act=force_act or random.random() < 0.2,
            ),
        }


# === Node 5: Agentic Action (Scriptwriting) ===

async def agentic_action(state: ErisState, llm_with_tools: Any) -> Dict[str, Any]:
    """
    Scriptwriting node - generates narrative text and planned actions.
    LLM receives mask constraints and writes the script.

    v1.1: Outputs ScriptOutput with narrative + planned_actions with purposes.
    """
    event = state["current_event"]
    event_type = event.get("eventType", "unknown") if event else "unknown"
    event_data = event.get("data", {}) if event else {}
    mask = state["current_mask"]
    mask_config = state.get("mask_config") or get_mask_config(mask)
    decision = state.get("decision")

    if not decision:
        logger.warning("No decision provided to agentic_action")
        return {
            "script": ScriptOutput(narrative_text="", planned_actions=[]),
            "planned_actions": [],
        }

    # Skip if nothing to do
    if not decision["should_speak"] and not decision["should_act"]:
        logger.debug("Decision says no speak/act, skipping agentic_action")
        return {
            "script": ScriptOutput(narrative_text="", planned_actions=[]),
            "planned_actions": [],
        }

    # Build context
    context_str = _build_context(state)
    system_prompt = build_eris_prompt(mask, context_str)

    # Get player list for validation
    game_state = state.get("game_state", {})
    players = game_state.get("players", [])
    player_names = [p.get("username", "") for p in players if p.get("username")]
    player_list_str = ", ".join(player_names) if player_names else "No players online"

    # Build tool guidance based on mask
    allowed_groups = mask_config.get("allowed_tool_groups", [])
    discouraged_groups = mask_config.get("discouraged_tool_groups", [])

    tool_guidance = f"""
MASK TOOL PREFERENCES (soft guidance):
✓ Encouraged: {', '.join(allowed_groups)}
✗ Discouraged (but allowed): {', '.join(discouraged_groups)}

You CAN use any tool, but staying in character means preferring encouraged tools.
"""

    # Build action prompt
    action_prompt = f"""
Event: {event_type}
Event Data: {event_data}

YOUR DECISION:
- Intent: {decision['intent']}
- Targets: {decision['targets']}
- Escalation: {decision['escalation']}/100
- Should Speak: {decision['should_speak']}
- Should Act: {decision['should_act']}

CURRENT PLAYERS (only use these names): {player_list_str}

{tool_guidance}

⚠️ CRITICAL OUTPUT FORMAT:
- If should_speak: Use the broadcast tool OR output ONLY a short message (5-15 words max)
- Message format: MiniMessage tags like <dark_purple>text</dark_purple>, <i>italic</i>, <b>bold</b>
- NEVER use markdown (**bold**, *italic*, ##headers, bullet points)
- NEVER output numbered lists, explanations, or structured plans
- NEVER include tool names or JSON in your text output
- ONE short sentence only!

GOOD output: The <dark_purple>void</dark_purple> <i>whispers</i>...
BAD output: 1. **Broadcast**: ```text here```

Be {mask.value.upper()}! Output ONLY the message or use tools.
"""

    try:
        response = await llm_with_tools.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=action_prompt)
        ])

        planned_actions: List[PlannedAction] = []
        narrative_text = ""

        # Action limiting - max 5 actions per event to prevent spam
        MAX_ACTIONS_PER_EVENT = 5

        # Check for tool calls
        if hasattr(response, "tool_calls") and response.tool_calls:
            tool_calls = response.tool_calls[:MAX_ACTIONS_PER_EVENT]  # Limit actions
            if len(response.tool_calls) > MAX_ACTIONS_PER_EVENT:
                logger.warning(f"🎬 Limited actions: {len(response.tool_calls)} → {MAX_ACTIONS_PER_EVENT}")
            logger.info(f"🎬 Script: {len(tool_calls)} tool calls")
            for tc in tool_calls:
                tool_name = tc["name"]
                args = tc["args"]

                # Infer purpose from tool and intent
                purpose = _infer_action_purpose(tool_name, decision["intent"], args)

                # Extract narrative text from broadcast calls
                if tool_name == "broadcast" and "message" in args:
                    narrative_text = args["message"]

                planned_actions.append(PlannedAction(
                    tool=tool_name,
                    args=args,
                    purpose=purpose,
                ))
                logger.info(f"   -> {tool_name}: {args} (purpose: {purpose})")
        else:
            # Fallback: extract text for broadcast
            content = response.content.strip() if response.content else ""
            if content and decision["should_speak"]:
                # Validate content - reject structured/markdown responses
                content = _sanitize_broadcast_content(content)
                if content:
                    narrative_text = content
                    planned_actions.append(PlannedAction(
                        tool="broadcast",
                        args={"message": content},
                        purpose="narrative",
                    ))
                    logger.info(f"🎬 Script (text only): {content[:50]}...")
                else:
                    logger.warning("🎬 Rejected invalid LLM output (markdown/structured)")

        script = ScriptOutput(
            narrative_text=narrative_text,
            planned_actions=planned_actions,
        )

        return {
            "messages": [response],
            "script": script,
            "planned_actions": planned_actions,
        }

    except Exception as e:
        error_msg = str(e)
        # Check if this is an invalid tool error from Ollama
        if "tool" in error_msg.lower() and "not found" in error_msg.lower():
            # Extract the bad tool name if possible
            import re
            match = re.search(r"tool ['\"]?(\w+)['\"]? not found", error_msg, re.IGNORECASE)
            bad_tool = match.group(1) if match else "unknown"
            logger.warning(f"⚠️ LLM tried to use invalid tool '{bad_tool}' - skipping action")
        else:
            logger.error(f"Error in agentic_action: {e}", exc_info=True)
        return {
            "script": ScriptOutput(narrative_text="", planned_actions=[]),
            "planned_actions": [],
        }


# === Node 6: Protection Decision ===

async def protection_decision(state: ErisState, llm: Any, ws_client: Any = None) -> Dict[str, Any]:
    """
    Validates planned actions before execution.
    Checks for lethal chains, grief loops, escalation runaway.
    Implements soft tool enforcement (warnings only).

    For death events: Executes respawn immediately (no LLM wait for 500ms requirement).

    v1.1: This is now part of the linear pipeline, not a fast path.
    """
    from ..core.causality import get_causality_tracker

    event = state.get("current_event")
    event_type = event.get("eventType", "") if event else ""
    event_data = event.get("data", {}) if event else {}
    planned_actions = state.get("planned_actions", [])
    mask = state["current_mask"]
    mask_config = state.get("mask_config") or get_mask_config(mask)
    global_chaos = state.get("global_chaos", 0)
    decision = state.get("decision")

    tracker = get_causality_tracker()
    approved_actions: List[PlannedAction] = []
    warnings: List[str] = []

    # === Handle immediate death protection (500ms requirement) ===
    if event_type == "eris_caused_death":
        player = event_data.get("player", "Unknown")

        if tracker.can_respawn():
            logger.info(f"🛡️ URGENT: Death event - executing respawn immediately")

            if ws_client:
                try:
                    tracker.use_respawn()
                    tracker.record_intervention(player, "respawn")

                    await ws_client.send_command(
                        "respawn",
                        {"player": player, "auraCost": 50},
                        reason="Eris Divine Respawn"
                    )
                    await ws_client.send_command(
                        "broadcast",
                        {"message": f"<gold><b>DIVINE INTERVENTION</b></gold>... <white>{player}</white> is not done yet."},
                        reason="Eris Divine Respawn"
                    )
                    logger.info(f"🛡️ ✅ Respawn executed for {player}")
                except Exception as e:
                    logger.error(f"🛡️ Failed to send respawn: {e}")

        return {
            "approved_actions": [],
            "protection_warnings": ["Respawn executed directly"],
            "planned_actions": [],
        }

    # === Handle close call protection ===
    if event_type == "eris_close_call":
        player = event_data.get("player", "Unknown")
        health = event_data.get("healthAfter", 0)

        cooldown = tracker.protection_cooldowns.get(player)
        if cooldown and datetime.now() < cooldown:
            logger.info(f"🛡️ Protection on cooldown for {player}")
        else:
            # Quick LLM decision for close calls
            should_save = await _quick_protection_decision(llm, player, health, mask)

            if should_save and ws_client:
                tracker.use_protection(player)
                tracker.record_intervention(player, "protection")

                protection_action = PlannedAction(
                    tool="protect_player",
                    args={"player": player, "aura_cost": 25},
                    purpose="divine_protection",
                )
                broadcast_action = PlannedAction(
                    tool="broadcast",
                    args={"message": f"I am <i>not finished</i> with you, <gold>{player}</gold>..."},
                    purpose="narrative",
                )
                approved_actions.extend([protection_action, broadcast_action])
                logger.info(f"🛡️ Protection approved for {player}")

    # === Validate planned actions ===
    if planned_actions:
        game_state = state.get("game_state", {})
        players = game_state.get("players", [])
        session = state.get("session", {})
        session_actions = session.get("actions_taken", [])

        for action in planned_actions:
            tool = action.get("tool", "")
            args = action.get("args", {})
            purpose = action.get("purpose", "unknown")

            action_warnings = []

            # Check soft tool enforcement
            discouraged_tools = get_all_discouraged_tools(mask)
            if tool in discouraged_tools:
                warning = f"SOFT WARNING: {mask.name} mask used discouraged tool '{tool}'"
                action_warnings.append(warning)
                logger.warning(f"⚠️ {warning}")

            # Check for target player existence (soft validation - don't reject)
            target_player = args.get("player") or args.get("near_player")
            if target_player and target_player != "all":
                player_names = [p.get("username", "") for p in players]
                if player_names and target_player not in player_names:
                    # Just warn, don't reject - player might have just joined
                    # and game state not yet updated, or Java side will handle it
                    warning = f"Target player '{target_player}' may not be in game"
                    action_warnings.append(warning)
                    logger.warning(f"⚠️ {warning} (allowing anyway)")

            # Check grief loop (>5 recent actions against same player)
            if target_player:
                recent_target_count = sum(
                    1 for a in session_actions[-20:]
                    if a.get("args", {}).get("player") == target_player
                    or a.get("args", {}).get("near_player") == target_player
                )
                if recent_target_count >= 5:
                    warning = f"Grief loop detected: {recent_target_count} recent actions against {target_player}"
                    action_warnings.append(warning)
                    logger.warning(f"⚠️ {warning}")

            # Check lethal chain (estimated damage > 80% health)
            if decision:
                escalation = decision.get("escalation", 0)
                if escalation > 80 and global_chaos > 60:
                    warning = f"High escalation ({escalation}) during high chaos ({global_chaos})"
                    action_warnings.append(warning)
                    logger.warning(f"⚠️ {warning}")

            warnings.extend(action_warnings)

            # Soft enforcement: log warnings but approve action
            approved_actions.append(PlannedAction(
                tool=tool,
                args=args,
                purpose=purpose,
            ))

    logger.info(f"🛡️ Protection decision: {len(approved_actions)} approved, {len(warnings)} warnings")

    return {
        "approved_actions": approved_actions,
        "protection_warnings": warnings,
    }


async def _quick_protection_decision(llm: Any, player: str, health: float, mask: ErisMask) -> bool:
    """Quick LLM decision for close call protection."""
    mask_guidance = {
        ErisMask.TRICKSTER: "As TRICKSTER: More chaos to come if they survive!",
        ErisMask.PROPHET: "As PROPHET: Was this foreseen?",
        ErisMask.FRIEND: "As FRIEND: Show your false mercy...",
        ErisMask.CHAOS_BRINGER: "As CHAOS_BRINGER: Prolonged suffering is beautiful...",
        ErisMask.OBSERVER: "As OBSERVER: Is this moment worthy of intervention?",
        ErisMask.GAMBLER: "As GAMBLER: What's your play?",
    }

    prompt = f"""QUICK DECISION: {player} at {health:.0f} HP from YOUR intervention.
{mask_guidance.get(mask, '')}
Respond: SAVE or ALLOW (one word only)"""

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        return "SAVE" in response.content.upper()
    except Exception:
        return True  # Default to save on error


# === Node 7: Tool Executor ===

async def tool_executor(state: ErisState, ws_client: Any, db: Database = None) -> Dict[str, Any]:
    """
    Execute approved actions via WebSocket.
    Updates session with results and fear/chaos/debt.

    v1.1: Executes approved_actions (post-validation) and updates debts.
    """
    approved_actions = state.get("approved_actions", [])
    mask = state["current_mask"]
    decision = state.get("decision")

    if not approved_actions:
        logger.debug("No approved actions to execute")
        return {}

    results = []
    for action in approved_actions:
        tool_name = action.get("tool", "")
        args = action.get("args", {})
        purpose = action.get("purpose", "unknown")

        try:
            result = await ws_client.send_command(tool_name, args, reason=f"Eris {purpose}")
            results.append({
                "tool": tool_name,
                "success": result,
                "purpose": purpose,
            })
            logger.info(f"✅ Executed: {tool_name} ({purpose})")

            # Update debt based on action
            if db and decision:
                target_player = args.get("player") or args.get("near_player")
                if target_player:
                    debt_delta = calculate_debt_delta(tool_name, purpose, mask)
                    if debt_delta != 0:
                        # Get player UUID from game state
                        game_state = state.get("game_state", {})
                        players = game_state.get("players", [])
                        for p in players:
                            if p.get("username") == target_player:
                                uuid = str(p.get("uuid", ""))
                                if uuid:
                                    await db.update_betrayal_debt(uuid, mask.name, debt_delta)
                                    logger.debug(f"💀 Debt updated: {mask.name} +{debt_delta} for {target_player}")
                                break

                    # Check debt resolution
                    intent = decision.get("intent", "")
                    betrayal_debts = state.get("betrayal_debts", {})
                    if target_player in betrayal_debts:
                        player_debt = 0
                        for mask_name, value in betrayal_debts[target_player].items():
                            if mask_name == mask.name:
                                player_debt = value
                                break
                        resolution_delta = check_debt_resolution(intent, mask, player_debt)
                        if resolution_delta != 0:
                            for p in players:
                                if p.get("username") == target_player:
                                    uuid = str(p.get("uuid", ""))
                                    if uuid:
                                        await db.update_betrayal_debt(uuid, mask.name, resolution_delta)
                                        logger.info(f"💀 Debt resolved: {mask.name} {resolution_delta} for {target_player}")
                                    break

        except Exception as e:
            logger.error(f"Error executing {tool_name}: {e}")
            results.append({"tool": tool_name, "success": False, "purpose": purpose})

    # Update session
    session = state.get("session", {}).copy()
    session["actions_taken"] = session.get("actions_taken", []) + results
    session["intervention_count"] = session.get("intervention_count", 0) + len(results)

    return {"session": session}


# === Helper Functions ===

def _build_context(state: ErisState) -> str:
    """Build structured narrative context for Eris prompt."""
    lines = []
    game_state = state.get("game_state", {})
    player_histories = state.get("player_histories", {})
    context_buffer = state.get("context_buffer", "")
    global_chaos = state.get("global_chaos", 0)
    player_fear = state.get("player_fear", {})

    # === CURRENT RUN ===
    run_state = game_state.get("gameState", "UNKNOWN")
    run_duration = game_state.get("runDuration", 0)
    if run_duration:
        minutes = run_duration // 60
        seconds = run_duration % 60
        duration_str = f"{minutes}m {seconds}s"
    else:
        duration_str = "Just started"

    lines.append("=== CURRENT RUN ===")
    lines.append(f"Status: {run_state} | Duration: {duration_str} | Chaos: {global_chaos}/100")

    # === PLAYERS ===
    players = game_state.get("players", [])
    if players:
        lines.append(f"\n=== PLAYERS ({len(players)} online) ===")
        for p in players:
            username = p.get("username", "Unknown")
            health = p.get("health", 20)
            dimension = p.get("dimension", "Overworld")
            fear = player_fear.get(username, 0)

            history = player_histories.get(username, {})
            total_runs = history.get("total_runs", 0)
            aura = history.get("aura", 0)
            nemesis = history.get("nemesis")

            if total_runs == 0:
                exp_label = "First-timer"
            elif total_runs < 5:
                exp_label = f"Rookie"
            elif total_runs < 20:
                exp_label = f"Regular"
            else:
                exp_label = f"Veteran"

            player_line = f"• {username}: {health:.0f}♥ {dimension} | {exp_label}, {aura} aura"
            if fear > 0:
                player_line += f", 😨{fear}"
            if nemesis:
                player_line += f" | Nemesis: {nemesis}"

            lines.append(player_line)
    else:
        lines.append("\n=== PLAYERS ===")
        lines.append("No players online")

    # === RECENT EVENTS ===
    if context_buffer and context_buffer.strip():
        event_lines = context_buffer.strip().split("\n")
        lines.append(f"\n=== RECENT EVENTS ({len(event_lines)} events) ===")
        for event_line in event_lines[-15:]:
            lines.append(event_line)

    return "\n".join(lines)


def _sanitize_broadcast_content(content: str) -> Optional[str]:
    """
    Sanitize and validate LLM output for broadcast.
    Returns cleaned content or None if invalid.

    Rejects:
    - Markdown formatting (**bold**, *italic*, ##headers)
    - Numbered/bulleted lists
    - Code blocks (```)
    - JSON-like structures
    - Responses over 150 chars (way too long for Minecraft chat)
    - Multi-line structured responses
    """
    import re

    if not content:
        return None

    # Reject markdown indicators
    markdown_patterns = [
        r'\*\*',           # **bold**
        r'^\s*\d+\.',      # 1. numbered lists
        r'^\s*-\s',        # - bullet points
        r'^\s*\*\s',       # * bullet points
        r'^#{1,6}\s',      # ## headers
        r'```',            # code blocks
        r'^\s*\|',         # tables
        r'\{["\']',        # JSON-like
    ]

    for pattern in markdown_patterns:
        if re.search(pattern, content, re.MULTILINE):
            logger.warning(f"🎬 Rejected: matched markdown pattern '{pattern}'")
            return None

    # Reject overly long responses
    if len(content) > 150:
        logger.warning(f"🎬 Rejected: too long ({len(content)} chars)")
        return None

    # Reject multi-line structured responses (more than 2 lines)
    lines = [l.strip() for l in content.split('\n') if l.strip()]
    if len(lines) > 2:
        # Try to extract just the first meaningful line
        first_line = lines[0]
        if len(first_line) <= 100 and not any(re.search(p, first_line) for p in markdown_patterns):
            logger.info(f"🎬 Extracted first line from multi-line response")
            return first_line
        logger.warning(f"🎬 Rejected: too many lines ({len(lines)})")
        return None

    # Clean up: remove any remaining markdown-style formatting
    content = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', content)  # **text** -> <b>text</b>
    content = re.sub(r'\*([^*]+)\*', r'<i>\1</i>', content)      # *text* -> <i>text</i>

    return content.strip()


def _infer_action_purpose(tool_name: str, intent: str, args: dict) -> str:
    """Infer action purpose from tool, intent, and args."""
    purpose_map = {
        "broadcast": "narrative",
        "message_player": "whisper",
        "spawn_mob": "terror" if intent in ("curse", "test") else "challenge",
        "spawn_tnt": "chaos",
        "spawn_falling_block": "trap",
        "strike_lightning": "drama",
        "change_weather": "atmosphere",
        "play_sound": "psychological",
        "spawn_particles": "visual",
        "show_title": "announcement",
        "give_item": "gift" if intent == "bless" else "trick",
        "apply_effect": "buff" if intent == "bless" else "debuff",
        "heal_player": "mercy",
        "damage_player": "punishment",
        "teleport_player": "misdirection",
        "fake_death": "deception",
        "modify_aura": "judgment",
        "protect_player": "protection",
        "rescue_teleport": "rescue",
    }
    return purpose_map.get(tool_name, intent)
