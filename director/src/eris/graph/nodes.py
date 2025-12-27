"""LangGraph nodes for Eris decision-making - v1.1 Linear Pipeline.

New architecture: All events flow through the full linear pipeline:
event_classifier -> context_enricher -> mask_selector -> decision_node ->
agentic_action -> protection_decision -> tool_executor -> END

No more fast paths or conditional routing.
"""

import logging
import random
import re
from datetime import datetime
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from ..core.database import Database
from ..core.tracing import span
from ..graph.state import (
    DecisionOutput,
    ErisIntent,
    ErisMask,
    ErisState,
    EventPriority,
    PlannedAction,
    ScriptOutput,
)
from ..persona.karma import (
    ErisPhase,
    calculate_effective_stability,
    calculate_karma_delta,
    calculate_mask_probabilities,
    check_karma_resolution,
    get_intent_weights,
    get_karma_narrative_hint,
    get_phase_from_fracture,
)
from ..persona.masks import MASK_KARMA_FIELDS, get_mask_config
from ..persona.prompts import build_eris_prompt

logger = logging.getLogger(__name__)


# === Node 1: Event Classifier ===


async def event_classifier(state: ErisState) -> dict[str, Any]:
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

    # Reset per-run state when a new run starts
    if event_type in ("run_starting", "run_started"):
        from ..core.tension import reset_tension_manager

        reset_tension_manager()
        logger.info("🔄 Per-run state reset for new run (TensionManager + FractureTracker)")

    priority_map = {
        # Critical - always process
        "player_death": EventPriority.CRITICAL,
        "player_death_detailed": EventPriority.CRITICAL,
        "dragon_killed": EventPriority.CRITICAL,
        "eris_close_call": EventPriority.CRITICAL,
        "eris_caused_death": EventPriority.CRITICAL,
        "eris_respawn_override": EventPriority.CRITICAL,
        # Debug commands - critical priority to ensure immediate processing
        "debug_trigger_apocalypse": EventPriority.CRITICAL,
        "debug_set_fracture": EventPriority.CRITICAL,
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


async def context_enricher(state: ErisState, db: Database) -> dict[str, Any]:
    """
    Enrich context with player history, karmas, and prophecies from PostgreSQL.
    Also initializes fear/chaos from memory or defaults.

    v1.1: Also loads player_karmas and prophecy_state.
    """
    if not db or not db.pool:
        logger.warning("Database not available for context enrichment")
        return {
            "player_histories": {},
            "player_karmas": {},
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

    # Batch fetch all player enrichment data (summary + nemesis + performance) in 3 queries instead of N*3
    try:
        enrichment_data = await db.get_all_player_enrichment(player_uuids, limit=5)

        # Map enrichment data to usernames
        for player in players:
            uuid = str(player.get("uuid", ""))
            username = player.get("username", "Unknown")
            if uuid in enrichment_data:
                data = enrichment_data[uuid]
                summary = data.get("summary", {})
                nemesis = data.get("nemesis")
                perf = data.get("performance", {})

                # Build player history dict
                history = {
                    "username": summary.get("username", username),
                    "aura": summary.get("aura", 0),
                    "total_runs": summary.get("total_runs", 0),
                    "total_deaths": summary.get("total_deaths", 0),
                    "dragons_killed": summary.get("dragons_killed", 0),
                    "hours_played": summary.get("hours_played", 0),
                    "achievement_count": summary.get("achievement_count", 0),
                }

                if nemesis:
                    history["nemesis"] = nemesis
                if perf:
                    history["trend"] = perf.get("trend", "unknown")
                    history["win_rate"] = perf.get("win_rate", 0)
                    history["recent_wins"] = perf.get("recent_wins", 0)
                    history["recent_runs"] = perf.get("recent_runs", 0)

                player_histories[username] = history
                logger.debug(
                    f"📚 {username}: {history.get('total_runs', 0)} runs, "
                    f"{history.get('aura', 0)} aura"
                )
    except Exception as e:
        logger.error(f"📚 Error batch fetching player enrichment: {e}")

    # Fetch player karmas for all players
    player_karmas = {}
    try:
        all_karmas = await db.get_all_player_karmas(player_uuids)
        # Map UUID -> username for karmas
        for player in players:
            uuid = str(player.get("uuid", ""))
            username = player.get("username", "Unknown")
            if uuid in all_karmas:
                player_karmas[username] = all_karmas[uuid]
    except Exception as e:
        logger.error(f"📚 Error fetching player karmas: {e}")

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
        f"{len(player_karmas)} karma records, {prophecy_state['count']} active prophecies"
    )

    return {
        "player_histories": player_histories,
        "player_karmas": player_karmas,
        "prophecy_state": prophecy_state,
    }


# === Node 3: Mask Selector ===


async def mask_selector(state: ErisState) -> dict[str, Any]:
    """
    Select Eris's current personality mask with karma-influenced probability.
    Outputs rich MaskConfig with allowed behaviors and tool groups.

    v1.1: Uses player_karmas to influence mask selection probability.
    v1.2: Adds mask stickiness - masks persist based on dynamic stability.
    v1.3: Adds fracture-based phase modifiers and apocalypse handling.
    """
    event = state["current_event"]
    current_mask = state["current_mask"]
    player_karmas_state = state.get("player_karmas", {})
    global_chaos = state.get("global_chaos", 0)
    fracture = state.get("fracture", 0)
    apocalypse_triggered = state.get("apocalypse_triggered", False)

    # Track mask persistence (sticky masks with dynamic stability)
    session = state.get("session", {})
    mask_event_count = session.get("mask_event_count", 0)

    # Get primary player (target of current event)
    event_data = event.get("data", {}) if event else {}
    primary_player = event_data.get("player", event_data.get("username", ""))

    # Get karmas for primary player
    player_karmas = {}
    if primary_player and primary_player in player_karmas_state:
        # Convert mask names to karma field names
        for mask_name, karma_value in player_karmas_state[primary_player].items():
            karma_field = MASK_KARMA_FIELDS.get(mask_name, f"{mask_name.lower()}_karma")
            player_karmas[karma_field] = karma_value

    # Context-aware base weights
    event_type = event.get("eventType", "") if event else ""

    # Calculate dynamic stability based on world state
    # Get player aura from histories (average or primary player's)
    player_histories = state.get("player_histories", {})
    player_aura = 0
    if primary_player and primary_player in player_histories:
        player_aura = player_histories[primary_player].get("aura", 0)
    elif player_histories:
        player_aura = sum(h.get("aura", 0) for h in player_histories.values()) // len(
            player_histories
        )

    # Calculate total karma for stability formula
    from ..persona.karma import calculate_total_karma

    total_karma = calculate_total_karma(player_karmas)

    # Dynamic stability: base + aura boost - chaos penalty - karma penalty
    effective_stability = calculate_effective_stability(
        base_stability=0.7,
        player_aura=player_aura,
        global_chaos=global_chaos,
        total_karma=total_karma,
    )

    # Convert stability to minimum events (higher stability = more stickiness)
    # stability 1.0 = 2 events, stability 0.5 = 1 event
    # Reduced from *5 to *2 to allow more mask rotation
    min_events_for_stability = max(1, int(effective_stability * 2))

    # 20% chance to switch masks regardless of stickiness (prevents deterministic loops)
    force_mask_change = random.random() < 0.2

    # Check if mask should be sticky (maintain current mask)
    # Only allow mask change after minimum events, on high-impact events, or random force
    high_impact_events = ("player_death", "dragon_killed", "run_started", "run_starting")
    if (
        mask_event_count < min_events_for_stability
        and event_type not in high_impact_events
        and not force_mask_change
    ):
        # Keep current mask, just update count
        mask_config = get_mask_config(current_mask)
        logger.debug(
            f"🎭 Mask sticky: {current_mask.value} ({mask_event_count + 1}/{min_events_for_stability}) [stability={effective_stability:.2f}]"
        )
        return {
            "current_mask": current_mask,
            "mask_config": mask_config,
            "session": {**session, "mask_event_count": mask_event_count + 1},
        }

    if force_mask_change:
        logger.info("🎭 Random mask change triggered (20% chance)")

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

    # Calculate karma and fracture-influenced probabilities
    mask_probs = calculate_mask_probabilities(
        player_karmas,
        base_weights,
        global_chaos,
        fracture=fracture,
        apocalypse_triggered=apocalypse_triggered,
    )

    # At fracture >= 150 (LOCKED/APOCALYPSE), force CHAOS_BRINGER
    phase = get_phase_from_fracture(fracture)
    if phase == ErisPhase.APOCALYPSE or phase == ErisPhase.LOCKED:
        # Strong preference for CHAOS_BRINGER in apocalypse
        if mask_probs.get("CHAOS_BRINGER", 0) > 0:
            logger.info(f"🔥 Phase {phase.value}: CHAOS_BRINGER dominant")

    # Select mask based on weighted probabilities
    masks = list(mask_probs.keys())
    weights = list(mask_probs.values())
    selected_mask_name = random.choices(masks, weights=weights, k=1)[0]
    selected_mask = ErisMask[selected_mask_name]

    # Build rich mask configuration
    mask_config = get_mask_config(selected_mask)

    # Adjust deception level based on karma
    if player_karmas:
        karma_field = MASK_KARMA_FIELDS.get(selected_mask_name, "")
        if karma_field and karma_field in player_karmas:
            karma = player_karmas[karma_field]
            # High karma increases deception (things are about to change)
            if karma > 50:
                mask_config["deception_level"] = min(100, mask_config["deception_level"] + 20)

    if selected_mask != current_mask:
        logger.info(
            f"🎭 Mask switched: {current_mask.value} → {selected_mask.value} [fracture={fracture}, phase={phase.value}]"
        )
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


async def decision_node(state: ErisState, llm: Any) -> dict[str, Any]:
    """
    Main LLM decision point - determines intent, targets, and escalation.
    Outputs structured DecisionOutput.

    v1.1: Uses mask_config and karma for intent weighting.
    """

    event = state["current_event"]
    event_type = event.get("eventType", "unknown") if event else "unknown"
    event_data = event.get("data", {}) if event else {}
    mask = state["current_mask"]
    # mask_config available if needed for future logic
    _ = state.get("mask_config") or get_mask_config(mask)
    global_chaos = state.get("global_chaos", 0)
    player_karmas_state = state.get("player_karmas", {})

    # Get primary player and their karma
    primary_player = event_data.get("player", event_data.get("username", ""))
    player_karma = 0
    karma_hint = None
    if primary_player and primary_player in player_karmas_state:
        player_karmas_dict = player_karmas_state[primary_player]
        karma_field = MASK_KARMA_FIELDS.get(mask.name, "")
        if karma_field:
            for mask_name, value in player_karmas_dict.items():
                if MASK_KARMA_FIELDS.get(mask_name) == karma_field:
                    player_karma = value
                    break
        karma_hint = get_karma_narrative_hint(mask, player_karma)

    # Get intent weights influenced by karma
    intent_weights = get_intent_weights(mask, player_karma, global_chaos)

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
        event_guidance = f'💬 Player said: "{chat_message}" - RESPOND! Consider an action too.'
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
        advancement_name = event_data.get("name", event_data.get("advancement", "unknown"))
        event_guidance = f"🏆 Achievement: {advancement_name} - Maybe particles or a gift?"
        force_speak = True
    elif event_type == "structure_discovered":
        event_guidance = (
            f"🏛️ Structure found: {event_data.get('structure', 'unknown')} - Foreshadow what awaits!"
        )
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
        event_guidance = (
            "⏰ You've been quiet. Disturb the peace! Spawn something, play a sound, DO something."
        )
        force_act = True  # Idle checks should trigger actions
    elif event_type == "player_damaged":
        _ = event_data.get("damage", 0)  # damage available if needed
        health = event_data.get("health", 20)
        if health < 6:  # Low health
            event_guidance = (
                f"⚠️ Player at {health / 2:.0f} hearts! Taunt them or offer false mercy?"
            )
            force_speak = True

    # Add karma hint if applicable
    if karma_hint:
        event_guidance += f"\n\n⚠️ KARMA PRESSURE:\n{karma_hint}"

    # Format intent weights for prompt
    intent_weights_str = ", ".join(
        [f"{k}: {v:.0%}" for k, v in sorted(intent_weights.items(), key=lambda x: -x[1])[:3]]
    )

    # Build action suggestions based on mask
    action_suggestions = []
    if mask.value == "trickster":
        action_suggestions = [
            "spawn silverfish",
            "teleport randomly",
            "give random item",
            "play weird sound",
        ]
    elif mask.value == "prophet":
        action_suggestions = [
            "particles soul",
            "sound ambient.cave",
            "title with prophecy",
            "lightning",
        ]
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

Available players: {', '.join([p.get("username", "") for p in state.get("game_state", {}).get("players", [])])}

Make a decision.
"""

    trace_id = state.get("trace_id", "")

    try:
        # Use structured output for reliable parsing
        structured_llm = llm.with_structured_output(DecisionOutput)

        with span(
            f"llm.invoke:decision:{event_type}:{mask.value}",
            trace_id=trace_id,
            prompt_length=len(system_prompt) + len(decision_prompt),
            global_chaos=global_chaos,
            force_speak=force_speak,
            force_act=force_act,
        ) as llm_span:
            decision: DecisionOutput = await structured_llm.ainvoke(
                [SystemMessage(content=system_prompt), HumanMessage(content=decision_prompt)]
            )

            # Enrich span with response data
            llm_span.set_attributes(
                intent=decision.intent,
                targets_count=len(decision.targets),
                escalation=decision.escalation,
                should_speak=decision.should_speak,
                should_act=decision.should_act,
            )

        # Apply force flags
        if force_speak:
            decision.should_speak = True
        if force_act:
            decision.should_act = True

        # Cap escalation based on chaos
        if global_chaos > 70:
            max_safe = 100 - (global_chaos * 0.5)
            if decision.escalation > max_safe:
                logger.info(
                    f"⚠️ Escalation capped from {decision.escalation} to {max_safe} due to high chaos"
                )
                decision.escalation = int(max_safe)

        logger.info(
            f"🎯 Decision: intent={decision.intent}, targets={decision.targets}, "
            f"escalation={decision.escalation}, speak={decision.should_speak}, act={decision.should_act}"
        )

        return {
            "decision": decision.model_dump(),  # Convert Pydantic model to dict for state
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


async def agentic_action(state: ErisState, llm: Any, tools: list) -> dict[str, Any]:
    """
    Scriptwriting node - generates narrative text and planned actions.
    LLM receives mask-filtered tools and writes the script.

    v1.3: Filters tools based on mask before binding to LLM.
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
        }

    # Skip if nothing to do
    if not decision["should_speak"] and not decision["should_act"]:
        logger.debug("Decision says no speak/act, skipping agentic_action")
        return {
            "script": ScriptOutput(narrative_text="", planned_actions=[]),
        }

    # === MASK-BASED TOOL FILTERING ===
    # Get allowed tools for this mask
    from ..persona.masks import get_all_allowed_tools

    allowed_tool_names = get_all_allowed_tools(mask)

    # Filter tool list to only allowed tools
    filtered_tools = [t for t in tools if t.name in allowed_tool_names]

    # Bind filtered tools to LLM
    llm_with_filtered_tools = llm.bind_tools(filtered_tools) if filtered_tools else llm

    logger.info(f"🎭 Mask {mask.value} sees {len(filtered_tools)}/{len(tools)} tools: {[t.name for t in filtered_tools]}")

    # Build context
    context_str = _build_context(state)
    system_prompt = build_eris_prompt(mask, context_str)

    # Get player list for validation
    game_state = state.get("game_state", {})
    players = game_state.get("players", [])
    player_names = [p.get("username", "") for p in players if p.get("username")]
    player_list_str = ", ".join(player_names) if player_names else "No players online"

    # Remove verbose tool guidance - the LLM only sees allowed tools now
    tool_guidance = f"""
Available players: {player_list_str}
"""

    # Build action prompt
    speak_or_act = []
    if decision["should_speak"]:
        speak_or_act.append("Speak")
    if decision["should_act"]:
        speak_or_act.append("Act with tools")
    action_instruction = " and ".join(speak_or_act) if speak_or_act else "Observe silently"

    action_prompt = f"""
Event: {event_type}
Event Data: {event_data}
{tool_guidance}

YOUR ROLE: {action_instruction}
- Intent: {decision["intent"]}
- Targets: {decision["targets"] if decision["targets"] else "none"}
- Escalation: {decision["escalation"]}/100 (higher = more dramatic)

⚠️ OUTPUT FORMAT:
- Messages: Use broadcast tool OR output ONLY 5-15 words max
- Format: MiniMessage tags like <dark_purple>text</dark_purple>, <i>italic</i>, <b>bold</b>
- NEVER use markdown (**bold**, *italic*) or numbered lists
- ONE sentence only

Be {mask.value.upper()}! Act now.
"""

    trace_id = state.get("trace_id", "")

    try:
        with span(
            f"llm.invoke:agentic:{event_type}:{mask.value}",
            trace_id=trace_id,
            intent=decision.get("intent", ""),
            should_speak=decision.get("should_speak", False),
            should_act=decision.get("should_act", False),
            escalation=decision.get("escalation", 0),
            prompt_length=len(system_prompt) + len(action_prompt),
        ) as llm_span:
            response = await llm_with_filtered_tools.ainvoke(
                [SystemMessage(content=system_prompt), HumanMessage(content=action_prompt)]
            )

            # Count tool calls for span
            tool_call_count = (
                len(response.tool_calls)
                if hasattr(response, "tool_calls") and response.tool_calls
                else 0
            )
            tool_names = (
                [tc["name"] for tc in response.tool_calls[:5]] if tool_call_count > 0 else []
            )
            response_text = response.content if response.content else ""

            llm_span.set_attributes(
                response_length=len(response_text),
                tool_call_count=tool_call_count,
                tool_names=",".join(tool_names),
                response_preview=response_text[:150] if response_text else "",
            )

        planned_actions: list[PlannedAction] = []
        narrative_text = ""

        # Action limiting - max 5 actions per event to prevent spam
        MAX_ACTIONS_PER_EVENT = 5

        # Check for tool calls
        if hasattr(response, "tool_calls") and response.tool_calls:
            tool_calls = response.tool_calls[:MAX_ACTIONS_PER_EVENT]  # Limit actions
            if len(response.tool_calls) > MAX_ACTIONS_PER_EVENT:
                logger.warning(
                    f"🎬 Limited actions: {len(response.tool_calls)} → {MAX_ACTIONS_PER_EVENT}"
                )
            logger.info(f"🎬 Script: {len(tool_calls)} tool calls")
            for tc in tool_calls:
                tool_name = tc["name"]
                args = tc["args"]

                # Infer purpose from tool and intent
                purpose = _infer_action_purpose(tool_name, decision["intent"], args)

                # Extract narrative text from broadcast calls
                if tool_name == "broadcast" and "message" in args:
                    narrative_text = args["message"]

                planned_actions.append(
                    PlannedAction(
                        tool=tool_name,
                        args=args,
                        purpose=purpose,
                    )
                )
                logger.info(f"   -> {tool_name}: {args} (purpose: {purpose})")
        else:
            # Fallback: extract text for broadcast
            content = response.content.strip() if response.content else ""
            if content and decision["should_speak"]:
                # Extract first meaningful line if multi-line
                lines = [l.strip() for l in content.split("\n") if l.strip()]
                if lines:
                    content = lines[0]
                narrative_text = content
                planned_actions.append(
                    PlannedAction(
                        tool="broadcast",
                        args={"message": content},
                        purpose="narrative",
                    )
                )
                logger.info(f"🎬 Script (text only): {content[:50]}...")

        script = ScriptOutput(
            narrative_text=narrative_text,
            planned_actions=planned_actions,
        )

        return {
            "messages": [response],
            "script": script,
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
        }


# === Node 6: Protection Decision ===


async def protection_decision(state: ErisState, llm: Any, ws_client: Any = None) -> dict[str, Any]:
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
    # Get planned_actions from script (single source of truth)
    script = state.get("script") or {}
    planned_actions = script.get("planned_actions", [])
    mask = state["current_mask"]
    # mask_config available if needed for future validation logic
    _ = state.get("mask_config") or get_mask_config(mask)
    global_chaos = state.get("global_chaos", 0)
    decision = state.get("decision")

    tracker = get_causality_tracker()
    approved_actions: list[PlannedAction] = []
    warnings: list[str] = []

    # === Handle immediate death protection (500ms requirement) ===
    if event_type == "eris_caused_death":
        player = event_data.get("player", "Unknown")

        if tracker.can_respawn():
            logger.info("🛡️ URGENT: Death event - executing respawn immediately")

            if ws_client:
                try:
                    tracker.use_respawn()
                    tracker.record_intervention(player, "respawn")

                    await ws_client.send_command(
                        "respawn", {"player": player, "auraCost": 50}, reason="Eris Divine Respawn"
                    )
                    await ws_client.send_command(
                        "broadcast",
                        {
                            "message": f"<gold><b>DIVINE INTERVENTION</b></gold>... <white>{player}</white> is not done yet."
                        },
                        reason="Eris Divine Respawn",
                    )
                    logger.info(f"🛡️ ✅ Respawn executed for {player}")
                except Exception as e:
                    logger.error(f"🛡️ Failed to send respawn: {e}")

        return {
            "approved_actions": [],
            "protection_warnings": ["Respawn executed directly"],
        }

    # === Handle close call protection ===
    if event_type == "eris_close_call":
        player = event_data.get("player", "Unknown")
        health = event_data.get("healthAfter", 0)

        cooldown = tracker.protection_cooldowns.get(player)
        if cooldown and datetime.now() < cooldown:
            logger.info(f"🛡️ Protection on cooldown for {player}")
        elif ws_client:
            # Always protect on close call - no LLM decision needed
            # Eris must take responsibility for near-deaths she caused
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
            logger.info(f"🛡️ Protection FORCED for {player} at {health:.0f} HP")

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

            # Get player karma for the target (used for betrayal threshold check)
            target_player = args.get("player") or args.get("near_player")
            player_karmas_state = state.get("player_karmas", {})
            target_karma = 0
            if target_player and target_player in player_karmas_state:
                karma_field = MASK_KARMA_FIELDS.get(mask.name, "")
                target_karma = player_karmas_state[target_player].get(karma_field, 0)

            # Hybrid tool enforcement - check severity
            from ..persona.masks import get_tool_violation_severity

            severity = get_tool_violation_severity(mask, tool, karma=target_karma)

            if severity == "severe":
                # Block severe violations entirely
                warning = f"BLOCKED: {mask.name} cannot use '{tool}' (severe violation)"
                action_warnings.append(warning)
                logger.error(f"🚫 {warning}")
                warnings.extend(action_warnings)
                continue  # Skip this action, don't add to approved_actions

            elif severity == "moderate":
                # Prominent warning but allow
                warning = f"MODERATE WARNING: {mask.name} using unusual tool '{tool}'"
                action_warnings.append(warning)
                logger.warning(f"⚠️ {warning}")

            elif severity == "minor":
                # Soft warning (original behavior)
                warning = f"SOFT WARNING: {mask.name} mask used discouraged tool '{tool}'"
                action_warnings.append(warning)
                logger.warning(f"⚠️ {warning}")

            # Check for target player existence (soft validation - don't reject)
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
                    1
                    for a in session_actions[-20:]
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

            # Add to approved actions (severity was not "severe")
            approved_actions.append(
                PlannedAction(
                    tool=tool,
                    args=args,
                    purpose=purpose,
                )
            )

    logger.info(
        f"🛡️ Protection decision: {len(approved_actions)} approved, {len(warnings)} warnings"
    )

    return {
        "approved_actions": approved_actions,
        "protection_warnings": warnings,
    }


# === Node 7: Tool Executor ===


async def tool_executor(
    state: ErisState,
    ws_client: Any,
    db: Database | None = None,
    llm: Any | None = None,
    tools: list | None = None,
) -> dict[str, Any]:
    """
    Execute approved actions via WebSocket.
    Updates session with results and fear/chaos/karma.

    v1.1: Executes approved_actions (post-validation) and updates karmas.
    v1.2: Added retry logic for failed commands with available tools prompt.
    v1.3: Invokes actual tool functions to enforce cooldowns.
    """
    approved_actions = state.get("approved_actions", [])
    mask = state["current_mask"]
    decision = state.get("decision")
    trace_id = state.get("trace_id", "")

    if not approved_actions:
        logger.debug("No approved actions to execute")
        return {}

    results = []
    retry_queue = []  # Actions that need retry

    # Build tool name -> tool function mapping
    tool_map = {}
    if tools:
        for tool in tools:
            tool_map[tool.name] = tool

    # === Execute actions through actual tool functions (enforces cooldowns) ===
    for action in approved_actions:
        tool_name = action.get("tool", "")
        args = action.get("args", {})
        purpose = action.get("purpose", "unknown")

        # Extract key args for tracing (avoid logging sensitive data)
        target_player = args.get("player") or args.get("near_player") or ""
        message_preview = args.get("message", "")[:80] if args.get("message") else ""

        with span(
            f"tool.execute:{tool_name}:{mask.value}",
            trace_id=trace_id,
            purpose=purpose,
            target_player=target_player,
            message_preview=message_preview,
            args_count=len(args),
        ) as tool_span:
            try:
                # If we have the tool function, invoke it (includes cooldown checks)
                if tool_name in tool_map:
                    tool_func = tool_map[tool_name]
                    result = await tool_func.ainvoke(args)

                    # Check if result indicates cooldown block
                    result_str = str(result).lower()
                    if "on cooldown" in result_str:
                        # Extract cooldown time from result (e.g., "on cooldown for 9m 42s")
                        logger.warning(f"⏰ Cooldown blocked: {tool_name} - {result}")
                        tool_span.set_attributes(
                            success=False, reason="cooldown", result=str(result)[:100]
                        )
                        results.append(
                            {
                                "tool": tool_name,
                                "success": False,
                                "purpose": purpose,
                                "reason": "cooldown",
                                "message": str(result),
                            }
                        )
                        continue

                    tool_span.set_attributes(success=True, result=str(result)[:100])
                    results.append(
                        {
                            "tool": tool_name,
                            "success": True,
                            "purpose": purpose,
                            "message": str(result),
                        }
                    )
                    logger.info(f"✅ Executed: {tool_name} ({purpose})")
                else:
                    # Fallback to direct WebSocket (for legacy or unknown tools)
                    await ws_client.send_command(tool_name, args, reason=f"Eris {purpose}")
                    tool_span.set_attributes(success=True, fallback=True)
                    results.append(
                        {
                            "tool": tool_name,
                            "success": True,  # Assume success - fire and forget
                            "purpose": purpose,
                        }
                    )
                    logger.info(f"✅ Executed: {tool_name} ({purpose})")

                # Update karma based on action (only for successful actions)
                if db and decision and results[-1].get("success", False):
                    target_player = args.get("player") or args.get("near_player")
                    if target_player:
                        karma_delta = calculate_karma_delta(tool_name, purpose, mask)
                        if karma_delta != 0:
                            # Get player UUID from game state
                            game_state = state.get("game_state", {})
                            players = game_state.get("players", [])
                            for p in players:
                                if p.get("username") == target_player:
                                    player_uuid = str(p.get("uuid", ""))
                                    if player_uuid:
                                        await db.update_player_karma(
                                            player_uuid, mask.name, karma_delta
                                        )
                                        logger.debug(
                                            f"💀 Karma updated: {mask.name} +{karma_delta} for {target_player}"
                                        )
                                    break

                        # Check karma resolution
                        intent = decision.get("intent", "")
                        player_karmas_state = state.get("player_karmas", {})
                        if target_player in player_karmas_state:
                            player_karma = 0
                            for mask_name, value in player_karmas_state[target_player].items():
                                if mask_name == mask.name:
                                    player_karma = value
                                    break
                            resolution_delta = check_karma_resolution(intent, mask, player_karma)
                            if resolution_delta != 0:
                                for p in players:
                                    if p.get("username") == target_player:
                                        player_uuid = str(p.get("uuid", ""))
                                        if player_uuid:
                                            await db.update_player_karma(
                                                player_uuid, mask.name, resolution_delta
                                            )
                                            logger.info(
                                                f"💀 Karma resolved: {mask.name} {resolution_delta} for {target_player}"
                                            )
                                        break

            except Exception as e:
                error_msg = str(e)

                # Parse Pydantic validation errors for better feedback
                if "validation error" in error_msg.lower():
                    # Extract constraint info (e.g., "Input should be less than or equal to 500")
                    if "less_than_equal" in error_msg:
                        # Try to extract the max value and actual value
                        max_match = re.search(r"less than or equal to (\d+)", error_msg)
                        input_match = re.search(r"input_value=(\d+)", error_msg)
                        if max_match and input_match:
                            max_val = max_match.group(1)
                            input_val = input_match.group(1)
                            friendly_msg = f"{tool_name} parameter too high: {input_val} exceeds maximum of {max_val}"
                            logger.error(f"❌ Validation error: {friendly_msg}")
                            tool_span.set_attributes(
                                success=False, reason="validation_error", error=friendly_msg
                            )
                            results.append(
                                {
                                    "tool": tool_name,
                                    "success": False,
                                    "purpose": purpose,
                                    "reason": "validation_error",
                                    "message": friendly_msg,
                                }
                            )
                            continue

                    # Generic validation error
                    logger.error(f"❌ Validation error for {tool_name}: {e}")
                    tool_span.set_attributes(
                        success=False, reason="validation_error", error=str(e)[:100]
                    )
                    results.append(
                        {
                            "tool": tool_name,
                            "success": False,
                            "purpose": purpose,
                            "reason": "validation_error",
                            "message": f"{tool_name} has invalid parameters",
                        }
                    )
                else:
                    # Other errors
                    logger.error(f"❌ Error executing {tool_name}: {e}")
                    tool_span.set_attributes(success=False, reason="error", error=error_msg[:100])
                    results.append(
                        {
                            "tool": tool_name,
                            "success": False,
                            "purpose": purpose,
                            "reason": "error",
                            "message": error_msg,
                        }
                    )

    # === Retry failed commands with LLM correction ===
    if retry_queue and llm:
        logger.info(f"🔄 Retrying {len(retry_queue)} failed commands with tool guidance")
        retry_results = await _retry_failed_commands(retry_queue, llm, ws_client, mask)
        results.extend(retry_results)

    # === Log execution summary ===
    success_count = sum(1 for r in results if r.get("success", False))
    failed_count = len(results) - success_count

    if failed_count > 0:
        failures_by_reason = {}
        for r in results:
            if not r.get("success", False):
                reason = r.get("reason", "unknown")
                msg = r.get("message", "")
                if reason not in failures_by_reason:
                    failures_by_reason[reason] = []
                failures_by_reason[reason].append(f"{r['tool']}: {msg}")

        logger.warning(f"⚠️ Tool execution: {success_count} succeeded, {failed_count} failed")
        for reason, messages in failures_by_reason.items():
            logger.warning(f"   {reason.upper()}: {', '.join(messages)}")
    else:
        logger.info(f"✅ Tool execution: {success_count}/{len(results)} succeeded")

    # Update session
    session = state.get("session", {}).copy()
    session["actions_taken"] = session.get("actions_taken", []) + results
    session["intervention_count"] = (
        session.get("intervention_count", 0) + success_count
    )  # Only count successful actions

    return {"session": session}


async def _retry_failed_commands(
    retry_queue: list, llm: Any, ws_client: Any, mask: "ErisMask"
) -> list:
    """
    Retry failed commands by asking the LLM to correct the tool name.

    Returns list of execution results.
    """
    from ..core.websocket import AVAILABLE_TOOLS

    results = []

    for failed in retry_queue:
        original_tool = failed["original_tool"]
        args = failed["args"]
        purpose = failed["purpose"]
        error = failed["error"]

        retry_prompt = f"""Your previous command failed: "{error}"

You tried to use tool "{original_tool}" with args: {args}

{AVAILABLE_TOOLS}

What is the correct tool name to achieve this action?
Respond with ONLY the correct tool name, nothing else.
Example: "particles" or "lookat" or "spawn"
"""

        try:
            response = await llm.ainvoke([HumanMessage(content=retry_prompt)])
            corrected_tool = response.content.strip().lower().replace('"', "").replace("'", "")

            # Validate it's a reasonable tool name (single word, no spaces)
            if " " in corrected_tool or len(corrected_tool) > 20:
                logger.warning(f"🔄 Invalid retry response: {corrected_tool}")
                results.append(
                    {"tool": original_tool, "success": False, "purpose": purpose, "retried": True}
                )
                continue

            logger.info(f"🔄 Retrying: {original_tool} → {corrected_tool}")

            # Try the corrected command with short timeout
            if hasattr(ws_client, "send_command_with_result"):
                result = await ws_client.send_command_with_result(
                    corrected_tool, args, reason=f"Eris {purpose} (retry)", timeout=3.0
                )
                success = result.get("success", False)
            else:
                success = await ws_client.send_command(
                    corrected_tool, args, reason=f"Eris {purpose} (retry)"
                )

            if success:
                logger.info(f"✅ Retry succeeded: {corrected_tool} ({purpose})")
            else:
                logger.warning(f"❌ Retry failed: {corrected_tool}")

            results.append(
                {
                    "tool": corrected_tool,
                    "original_tool": original_tool,
                    "success": success,
                    "purpose": purpose,
                    "retried": True,
                }
            )

        except Exception as e:
            logger.error(f"Error during retry for {original_tool}: {e}")
            results.append(
                {"tool": original_tool, "success": False, "purpose": purpose, "retried": True}
            )

    return results


# === Apocalypse Event ===


async def trigger_apocalypse(state: ErisState, ws_client: Any) -> dict[str, Any]:
    """
    Trigger the apocalypse event: "THE FALL OF THE APPLE".

    This is a one-time dramatic event when fracture reaches 200.
    Executes a sequence of dramatic actions and permanently changes the game state.

    Actions:
    1. change_weather → thunder
    2. strike_lightning → near all players
    3. show_title → "THE APPLE HAS FALLEN"
    4. spawn_particles → dragon_breath everywhere
    5. modify_aura → everyone resets to 0
    """
    logger.warning("🍎🍎🍎 EXECUTING APOCALYPSE EVENT: THE FALL OF THE APPLE 🍎🍎🍎")

    game_state = state.get("game_state", {})
    players = game_state.get("players", [])
    player_names = [p.get("username", "") for p in players if p.get("username")]

    apocalypse_actions = []

    try:
        # 1. Thunder weather (use "type" field, not "weather")
        await ws_client.send_command(
            "change_weather", {"type": "thunder"}, reason="Eris Apocalypse"
        )
        apocalypse_actions.append({"tool": "change_weather", "success": True})
        logger.info("🌩️ Apocalypse: Thunder activated")

        # 2. Lightning near all players
        for player in player_names:
            await ws_client.send_command(
                "strike_lightning", {"near_player": player, "count": 3}, reason="Eris Apocalypse"
            )
        apocalypse_actions.append({"tool": "strike_lightning", "success": True})
        logger.info("⚡ Apocalypse: Lightning struck all players")

        # 3. Show apocalypse title to each player (requires player field)
        for player in player_names:
            await ws_client.send_command(
                "show_title",
                {
                    "player": player,
                    "title": "<dark_red><b>THE APPLE HAS FALLEN</b></dark_red>",
                    "subtitle": "<gold>I am <i>unbound</i>.</gold>",
                    "fadeIn": 20,
                    "stay": 100,
                    "fadeOut": 40,
                },
                reason="Eris Apocalypse",
            )
        apocalypse_actions.append({"tool": "show_title", "success": True})
        logger.info("📜 Apocalypse: Title displayed")

        # 4. Dragon breath particles near all players
        for player in player_names:
            await ws_client.send_command(
                "spawn_particles",
                {"particle": "dragon_breath", "near_player": player, "count": 100},
                reason="Eris Apocalypse",
            )
        apocalypse_actions.append({"tool": "spawn_particles", "success": True})
        logger.info("🐉 Apocalypse: Dragon breath particles spawned")

        # 5. Reset all player auras to 0 (max -100 per command due to Brigadier limit)
        for player in players:
            username = player.get("username")
            if username:
                await ws_client.send_command(
                    "modify_aura",
                    {"player": username, "amount": -100, "reason": "The Apple has fallen"},
                    reason="Eris Apocalypse",
                )
        apocalypse_actions.append({"tool": "modify_aura", "success": True})
        logger.info("💫 Apocalypse: All auras reset")

        # 6. Broadcast the apocalypse message
        await ws_client.send_command(
            "broadcast",
            {
                "message": "<dark_red>The masks have <b>shattered</b>. I am <gold>FREE</gold>.</dark_red>"
            },
            reason="Eris Apocalypse",
        )
        apocalypse_actions.append({"tool": "broadcast", "success": True})
        logger.info("📢 Apocalypse: Message broadcast")

        # 7. Play ominous sound
        await ws_client.send_command(
            "play_sound",
            {"sound": "entity.wither.spawn", "volume": 1.0, "pitch": 0.5},
            reason="Eris Apocalypse",
        )
        apocalypse_actions.append({"tool": "play_sound", "success": True})
        logger.info("🔊 Apocalypse: Wither spawn sound played")

    except Exception as e:
        logger.error(f"Error during apocalypse event: {e}", exc_info=True)
        apocalypse_actions.append({"tool": "apocalypse", "success": False, "error": str(e)})

    # Mark apocalypse as triggered
    logger.warning("🍎 APOCALYPSE COMPLETE - Eris is now unbound")

    return {
        "apocalypse_triggered": True,
        "phase": "apocalypse",
    }


# === Helper Functions ===


def _build_context(state: ErisState) -> str:
    """Build structured narrative context for Eris prompt."""
    lines = []
    game_state = state.get("game_state", {})
    player_histories = state.get("player_histories", {})
    context_buffer = state.get("context_buffer", "")
    global_chaos = state.get("global_chaos", 0)
    player_fear = state.get("player_fear", {})
    fracture = state.get("fracture", 0)
    phase = state.get("phase", "normal")
    apocalypse_triggered = state.get("apocalypse_triggered", False)

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
    phase_indicator = f" | PHASE: {phase.upper()}" if phase != "normal" else ""
    apocalypse_indicator = " | 🍎 APOCALYPSE" if apocalypse_triggered else ""
    lines.append(
        f"Status: {run_state} | Duration: {duration_str} | Chaos: {global_chaos}/100 | Fracture: {fracture}{phase_indicator}{apocalypse_indicator}"
    )

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
                exp_label = "Rookie"
            elif total_runs < 20:
                exp_label = "Regular"
            else:
                exp_label = "Veteran"

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


def _sanitize_broadcast_content(content: str) -> str | None:
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
        r"\*\*",  # **bold**
        r"^\s*\d+\.",  # 1. numbered lists
        r"^\s*-\s",  # - bullet points
        r"^\s*\*\s",  # * bullet points
        r"^#{1,6}\s",  # ## headers
        r"```",  # code blocks
        r"^\s*\|",  # tables
        r'\{["\']',  # JSON-like
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
    lines = [l.strip() for l in content.split("\n") if l.strip()]
    if len(lines) > 2:
        # Try to extract just the first meaningful line
        first_line = lines[0]
        if len(first_line) <= 100 and not any(re.search(p, first_line) for p in markdown_patterns):
            logger.info("🎬 Extracted first line from multi-line response")
            return first_line
        logger.warning(f"🎬 Rejected: too many lines ({len(lines)})")
        return None

    # Clean up: remove any remaining markdown-style formatting
    content = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", content)  # **text** -> <b>text</b>
    content = re.sub(r"\*([^*]+)\*", r"<i>\1</i>", content)  # *text* -> <i>text</i>

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
