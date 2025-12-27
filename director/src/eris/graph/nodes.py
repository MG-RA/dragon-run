"""LangGraph nodes for Eris decision-making - v2.0 Tarot-Driven Pipeline.

7-node linear pipeline:
update_player_state -> update_tarot -> update_eris_opinions -> select_mask ->
decide_should_act -> llm_invoke -> tool_execute -> END

Replaces karma system with tarot archetypes.
Eris now has explicit knowledge of each player's tarot card.
"""

import logging
import random
from datetime import datetime
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from ..core.database import Database
from ..core.eris_memory import (
    create_default_opinion,
    record_interaction,
    update_opinion,
)
from ..core.tarot import TarotCard, TarotProfile, get_drift_for_event
from ..core.tarot_integration import (
    describe_opinions_for_prompt,
    describe_tarot_for_prompt,
    get_lever_for_player,
    get_tarot_mask_weights,
)
from ..core.tracing import span
from ..graph.state import (
    DecisionOutput,
    ErisMask,
    ErisState,
    EventPriority,
    PlannedAction,
    PlayerTarotProfile,
    ScriptOutput,
    create_default_profile,
    create_default_tarot,
)
from ..persona.masks import get_mask_config
from ..persona.prompts import build_eris_prompt

logger = logging.getLogger(__name__)


# === Node 1: Update Player State ===


async def update_player_state(state: ErisState, db: Database) -> dict[str, Any]:
    """
    Process the incoming event and update player states.
    Merges game_state.players with player_profiles.
    Loads player histories from DB for new players.
    Initializes TarotProfile and ErisOpinion for new players.

    NO LLM CALL - database queries and state sync only.
    """
    event = state["current_event"]
    event_type = event.get("eventType", "") if event else ""

    # Reset per-run state when a new run starts
    if event_type in ("run_starting", "run_started"):
        from ..core.tension import reset_tension_manager

        reset_tension_manager()
        logger.info("Reset per-run state for new run")

    # Priority classification (same as old event_classifier)
    priority = _classify_event_priority(event_type, event)

    game_state = state.get("game_state", {})
    players = list(game_state.get("players", []))
    current_profiles = dict(state.get("player_profiles", {}))
    player_histories = {}
    player_uuids = []

    # Include event player if not in game_state yet (timing fix for player_joined)
    if event:
        event_data = event.get("data", {})
        event_player = event_data.get("player") or event_data.get("username")
        event_uuid = event_data.get("uuid")
        if event_player and event_uuid:
            existing_names = {p.get("username") for p in players}
            if event_player not in existing_names:
                players.append({
                    "username": event_player,
                    "uuid": event_uuid,
                    "health": 20,
                    "dimension": "Overworld",
                })
                logger.info(f"Added event player {event_player} to enrichment")

    logger.info(f"update_player_state: {len(players)} players")

    # Collect UUIDs for batch queries
    for player in players:
        uuid = player.get("uuid")
        if uuid:
            player_uuids.append(str(uuid))

    # Batch fetch player enrichment data from database
    if db and db.pool:
        try:
            enrichment_data = await db.get_all_player_enrichment(player_uuids, limit=5)

            for player in players:
                uuid = str(player.get("uuid", ""))
                username = player.get("username", "Unknown")
                if uuid in enrichment_data:
                    data = enrichment_data[uuid]
                    summary = data.get("summary", {})
                    nemesis = data.get("nemesis")
                    perf = data.get("performance", {})

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

                    player_histories[username] = history
        except Exception as e:
            logger.error(f"Error fetching player enrichment: {e}")

    # Ensure all players have profiles
    for player in players:
        username = player.get("username", "Unknown")
        if username not in current_profiles:
            # Create new profile with defaults
            current_profiles[username] = create_default_profile()
            logger.info(f"Created new profile for {username}")

    logger.info(
        f"update_player_state complete: {len(current_profiles)} profiles, "
        f"{len(player_histories)} histories"
    )

    return {
        "event_priority": priority,
        "player_profiles": current_profiles,
        "player_histories": player_histories,
    }


# === Node 2: Update Tarot ===


async def update_tarot(state: ErisState) -> dict[str, Any]:
    """
    Apply tarot drift based on the current event.
    Players' dominant cards shift based on their actions.

    NO LLM CALL - pure drift calculation.
    """
    event = state["current_event"]
    if not event:
        return {}

    event_type = event.get("eventType", "")
    event_data = event.get("data", {})
    profiles = dict(state.get("player_profiles", {}))

    # Determine affected player(s)
    affected_player = event_data.get("player") or event_data.get("username")

    # Create event wrapper for drift rules
    class EventWrapper:
        def __init__(self, data: dict):
            self._data = data

        def __getattr__(self, name: str) -> Any:
            return self._data.get(name, "")

    event_obj = EventWrapper(event_data)
    drifts = get_drift_for_event(event_type, event_obj)

    if not drifts:
        return {}

    # Apply drift to affected player(s)
    players_to_update = [affected_player] if affected_player else list(profiles.keys())

    for username in players_to_update:
        if username not in profiles:
            continue

        profile = profiles[username]
        tarot_data = profile.get("tarot", create_default_tarot())

        # Reconstruct TarotProfile
        weights = tarot_data.get("weights", {})
        tarot_profile = TarotProfile()
        for card_str, weight in weights.items():
            try:
                card = TarotCard(card_str.lower())
                tarot_profile.weights[card] = weight
            except ValueError:
                pass

        # Apply drifts
        old_dominant = tarot_profile.dominant_card
        tarot_profile.drift_multiple(drifts)
        new_dominant = tarot_profile.dominant_card

        # Store back
        profile["tarot"] = PlayerTarotProfile(
            dominant_card=tarot_profile.dominant_card.value,
            strength=tarot_profile.identity_strength,
            secondary_card=(
                tarot_profile.secondary_card.value if tarot_profile.secondary_card else None
            ),
            weights={
                card.value: weight
                for card, weight in tarot_profile.weights.items()
                if weight > 0
            },
        )

        # Log tarot changes
        if old_dominant != new_dominant:
            logger.info(
                f"Tarot({username}) = {new_dominant.value.capitalize()} "
                f"(was {old_dominant.value}, strength {tarot_profile.identity_strength:.0%})"
            )
        else:
            logger.debug(
                f"Tarot({username}) = {new_dominant.value.capitalize()} "
                f"(strength {tarot_profile.identity_strength:.0%})"
            )

    return {"player_profiles": profiles}


# === Node 3: Update Eris Opinions ===


async def update_eris_opinions(state: ErisState) -> dict[str, Any]:
    """
    Update Eris's subjective opinions about each player.
    Trust, annoyance, and interest shift based on events.

    NO LLM CALL - pure opinion calculation.
    """
    event = state["current_event"]
    if not event:
        return {}

    event_type = event.get("eventType", "")
    event_data = event.get("data", {})
    profiles = dict(state.get("player_profiles", {}))

    # Determine affected player
    affected_player = event_data.get("player") or event_data.get("username")

    if affected_player and affected_player in profiles:
        profile = profiles[affected_player]
        opinion = profile.get("opinion", create_default_opinion())
        tarot_card = profile.get("tarot", {}).get("dominant_card")

        # Update opinion based on event
        updated_opinion = update_opinion(opinion, event_type, event_data, tarot_card)
        profile["opinion"] = updated_opinion

        # Log significant opinion changes
        if updated_opinion["interest"] > 0.7:
            logger.info(f"Eris is FASCINATED by {affected_player}")
        elif updated_opinion["annoyance"] > 0.7:
            logger.info(f"Eris is IRRITATED by {affected_player}")

    return {"player_profiles": profiles}


# === Node 4: Select Mask ===


async def select_mask(state: ErisState) -> dict[str, Any]:
    """
    Select Eris's personality mask based on tarot + opinions + fracture.
    Uses tarot affinities instead of karma for mask selection.

    NO LLM CALL - weighted random selection.
    """
    event = state["current_event"]
    current_mask = state["current_mask"]
    profiles = state.get("player_profiles", {})
    global_chaos = state.get("global_chaos", 0)
    fracture = state.get("fracture", 0)
    apocalypse_triggered = state.get("apocalypse_triggered", False)

    # Track mask persistence
    session = state.get("session", {})
    mask_event_count = session.get("mask_event_count", 0)

    # Get event info
    event_data = event.get("data", {}) if event else {}
    event_type = event.get("eventType", "") if event else ""
    primary_player = event_data.get("player", event_data.get("username", ""))

    # Find highest-interest player
    focus_player = None
    max_interest = 0
    for username, profile in profiles.items():
        interest = profile.get("opinion", {}).get("interest", 0.3)
        if interest > max_interest:
            max_interest = interest
            focus_player = username

    # Calculate dynamic stability (simpler without karma)
    player_histories = state.get("player_histories", {})
    player_aura = 0
    if primary_player and primary_player in player_histories:
        player_aura = player_histories[primary_player].get("aura", 0)

    # stability = base + aura boost - chaos penalty - interest penalty
    base_stability = 0.7
    stability = base_stability + (player_aura / 200) - (global_chaos / 100) - (max_interest / 2)
    stability = max(0.1, min(1.0, stability))

    min_events_for_stability = max(1, int(stability * 2))

    # 20% chance to force mask change
    force_mask_change = random.random() < 0.2

    # Check mask stickiness
    high_impact_events = ("player_death", "dragon_killed", "run_started", "run_starting")
    if (
        mask_event_count < min_events_for_stability
        and event_type not in high_impact_events
        and not force_mask_change
    ):
        mask_config = get_mask_config(current_mask)
        logger.debug(
            f"Mask sticky: {current_mask.value} "
            f"({mask_event_count + 1}/{min_events_for_stability})"
        )
        return {
            "current_mask": current_mask,
            "mask_config": mask_config,
            "session": {**session, "mask_event_count": mask_event_count + 1},
        }

    # Base weights from event type
    base_weights = dict.fromkeys(ErisMask, 1.0)
    if event_type in ("player_death", "player_death_detailed"):
        base_weights[ErisMask.PROPHET] = 2.0
        base_weights[ErisMask.CHAOS_BRINGER] = 2.0
    elif event_type == "player_chat":
        base_weights[ErisMask.TRICKSTER] = 2.0
        base_weights[ErisMask.FRIEND] = 1.5
    elif event_type in ("run_starting", "run_started"):
        base_weights[ErisMask.PROPHET] = 2.0
        base_weights[ErisMask.GAMBLER] = 1.5

    # Convert to dict keyed by ErisMask for tarot weights calculation
    base_weights_dict = {mask: base_weights.get(mask, 1.0) for mask in ErisMask}

    # Apply tarot affinities
    tarot_weights = get_tarot_mask_weights(profiles, base_weights_dict, focus_player)

    # Apply fracture/phase modifiers
    phase = _get_phase_from_fracture(fracture)

    if phase == "rising":
        tarot_weights[ErisMask.CHAOS_BRINGER] *= 1.5
    elif phase == "critical":
        tarot_weights[ErisMask.PROPHET] *= 2.0
        tarot_weights[ErisMask.CHAOS_BRINGER] *= 1.5
    elif phase == "locked":
        tarot_weights[ErisMask.OBSERVER] *= 0.1
        tarot_weights[ErisMask.CHAOS_BRINGER] *= 3.0
        tarot_weights[ErisMask.FRIEND] *= 0.5
    elif phase == "apocalypse" or apocalypse_triggered:
        # Dead masks in apocalypse
        tarot_weights[ErisMask.FRIEND] = 0.0
        tarot_weights[ErisMask.OBSERVER] = 0.0
        tarot_weights[ErisMask.CHAOS_BRINGER] *= 3.0
        tarot_weights[ErisMask.PROPHET] *= 2.0

    # Select mask
    masks = list(tarot_weights.keys())
    weights = [max(0.01, tarot_weights[m]) for m in masks]  # Avoid zero weights
    selected_mask = random.choices(masks, weights=weights, k=1)[0]

    mask_config = get_mask_config(selected_mask)

    if selected_mask != current_mask:
        logger.info(
            f"ErisMask = {selected_mask.value.capitalize()} "
            f"(was {current_mask.value}, fracture={fracture}, phase={phase})"
        )
        new_mask_event_count = 0
    else:
        logger.debug(f"ErisMask = {selected_mask.value.capitalize()} (maintained)")
        new_mask_event_count = mask_event_count + 1

    return {
        "current_mask": selected_mask,
        "mask_config": mask_config,
        "session": {**session, "mask_event_count": new_mask_event_count},
    }


# === Node 5: Decide Should Act ===


async def decide_should_act(state: ErisState, llm: Any) -> dict[str, Any]:
    """
    LLM decides IF Eris should act and with what intent.
    Uses tarot context to inform decision.

    LLM CALL - structured output.
    """
    event = state["current_event"]
    event_type = event.get("eventType", "unknown") if event else "unknown"
    event_data = event.get("data", {}) if event else {}
    mask = state["current_mask"]
    profiles = state.get("player_profiles", {})
    global_chaos = state.get("global_chaos", 0)

    # Get primary player
    primary_player = event_data.get("player", event_data.get("username", ""))

    # Build tarot context
    tarot_context = describe_tarot_for_prompt(profiles)
    opinion_context = describe_opinions_for_prompt(profiles)

    # Get lever for primary player if available
    lever = ""
    if primary_player and primary_player in profiles:
        lever = get_lever_for_player(profiles[primary_player])

    # Build context
    context_str = _build_context(state)
    system_prompt = build_eris_prompt(mask, context_str)

    # Force speak/act for certain events
    force_speak = False
    force_act = False
    event_guidance = ""

    if event_type in ("run_starting", "run_started"):
        event_guidance = "A NEW RUN IS STARTING! Set the tone with words AND action!"
        force_speak = True
        force_act = True
    elif event_type == "player_joined":
        event_guidance = "A player has joined! Greet them."
        force_speak = True
    elif event_type == "player_chat":
        chat_message = event_data.get("message", "")
        event_guidance = f'Player said: "{chat_message}" - RESPOND!'
        force_speak = True
    elif event_type in ("player_death", "player_death_detailed"):
        event_guidance = "DEATH! Be dramatic!"
        force_speak = True
        force_act = True
    elif event_type == "dragon_killed":
        event_guidance = "THE DRAGON IS SLAIN! Celebrate or curse!"
        force_speak = True
        force_act = True
    elif event_type in ("achievement_unlocked", "advancement_made"):
        event_guidance = f"Achievement: {event_data.get('name', 'unknown')}"
        force_speak = True
    elif event_type == "idle_check":
        event_guidance = "You've been quiet. Disturb the peace!"
        force_act = True

    # Get player list
    game_state = state.get("game_state", {})
    players = game_state.get("players", [])
    player_names = [p.get("username", "") for p in players if p.get("username")]

    decision_prompt = f"""
Current Event: {event_type}
Event Data: {event_data}
{event_guidance}

Your mask: {mask.value.upper()}
Chaos level: {global_chaos}/100

{tarot_context}

{opinion_context}

{"LEVER for " + primary_player + ": " + lever if lever else ""}

Available players: {', '.join(player_names)}

Decide:
- intent: What do you want to do? (tempt, test, protect, grief, reveal, confuse, etc.)
- targets: Which player(s)?
- escalation: 0-100 (how dramatic)
- should_speak: Broadcast a message?
- should_act: Use tools (spawn mobs, effects, etc.)?
- tarot_reasoning: How does the target's tarot influence this?
"""

    trace_id = state.get("trace_id", "")

    try:
        structured_llm = llm.with_structured_output(DecisionOutput)

        with span(
            f"llm.invoke:decide:{event_type}:{mask.value}",
            trace_id=trace_id,
            global_chaos=global_chaos,
        ) as llm_span:
            decision: DecisionOutput = await structured_llm.ainvoke(
                [SystemMessage(content=system_prompt), HumanMessage(content=decision_prompt)]
            )

            # Apply force flags
            if force_speak:
                decision.should_speak = True
            if force_act:
                decision.should_act = True

            llm_span.set_attributes(
                intent=decision.intent,
                targets_count=len(decision.targets),
                escalation=decision.escalation,
                speak=decision.should_speak,
                act=decision.should_act,
            )

        # Cap escalation in high chaos
        if global_chaos > 70:
            max_safe = 100 - (global_chaos * 0.5)
            if decision.escalation > max_safe:
                decision.escalation = int(max_safe)

        # Log in desired format
        target = decision.targets[0] if decision.targets else "all"
        if primary_player and primary_player in profiles:
            tarot = profiles[primary_player].get("tarot", {}).get("dominant_card", "fool")
            logger.info(f"Tarot({primary_player}) = {tarot.capitalize()}")
        logger.info(f"ErisMask = {mask.value.capitalize()}")
        logger.info(f"Intent = {decision.intent.capitalize()}")
        logger.info(f"Target = {target}")

        return {"decision": decision.model_dump()}

    except Exception as e:
        logger.error(f"Error in decide_should_act: {e}", exc_info=True)
        return {
            "decision": DecisionOutput(
                intent="confuse",
                targets=[],
                escalation=20,
                should_speak=force_speak or random.random() < 0.3,
                should_act=force_act or random.random() < 0.2,
                tarot_reasoning=None,
            ).model_dump(),
        }


# === Node 6: LLM Invoke ===


async def llm_invoke(state: ErisState, llm: Any, tools: list) -> dict[str, Any]:
    """
    Generate narrative text and planned tool calls.
    LLM receives mask-filtered tools and writes the script.

    LLM CALL - with tool binding.
    """
    event = state["current_event"]
    event_type = event.get("eventType", "unknown") if event else "unknown"
    event_data = event.get("data", {}) if event else {}
    mask = state["current_mask"]
    profiles = state.get("player_profiles", {})
    decision = state.get("decision")

    if not decision:
        logger.warning("No decision provided to llm_invoke")
        return {"script": ScriptOutput(narrative_text="", planned_actions=[])}

    # Skip if nothing to do
    if not decision.get("should_speak") and not decision.get("should_act"):
        logger.debug("Decision says no speak/act, skipping llm_invoke")
        return {"script": ScriptOutput(narrative_text="", planned_actions=[])}

    # Filter tools by mask
    from ..persona.masks import get_all_allowed_tools

    allowed_tool_names = get_all_allowed_tools(mask)
    filtered_tools = [t for t in tools if t.name in allowed_tool_names]
    llm_with_tools = llm.bind_tools(filtered_tools) if filtered_tools else llm

    logger.info(f"Mask {mask.value} sees {len(filtered_tools)}/{len(tools)} tools")

    # Build context with tarot
    context_str = _build_context(state)
    tarot_context = describe_tarot_for_prompt(profiles)
    system_prompt = build_eris_prompt(mask, context_str)

    # Get player list
    game_state = state.get("game_state", {})
    players = game_state.get("players", [])
    player_names = [p.get("username", "") for p in players if p.get("username")]

    # Build action prompt
    speak_or_act = []
    if decision.get("should_speak"):
        speak_or_act.append("Speak")
    if decision.get("should_act"):
        speak_or_act.append("Act with tools")
    action_instruction = " and ".join(speak_or_act) if speak_or_act else "Observe"

    tarot_reasoning = decision.get("tarot_reasoning", "")

    action_prompt = f"""
Event: {event_type}
Event Data: {event_data}
Available players: {', '.join(player_names)}

{tarot_context}

YOUR ROLE: {action_instruction}
- Intent: {decision.get("intent", "confuse")}
- Targets: {decision.get("targets") or "none"}
- Escalation: {decision.get("escalation", 30)}/100
{f"- Tarot insight: {tarot_reasoning}" if tarot_reasoning else ""}

OUTPUT FORMAT:
- Messages: 5-15 words max, MiniMessage tags (<dark_purple>, <b>, <i>)
- NEVER use markdown or numbered lists
- ONE sentence only

Be {mask.value.upper()}! Act now.
"""

    trace_id = state.get("trace_id", "")

    try:
        with span(
            f"llm.invoke:script:{event_type}:{mask.value}",
            trace_id=trace_id,
            intent=decision.get("intent", ""),
        ) as llm_span:
            response = await llm_with_tools.ainvoke(
                [SystemMessage(content=system_prompt), HumanMessage(content=action_prompt)]
            )

            tool_call_count = (
                len(response.tool_calls)
                if hasattr(response, "tool_calls") and response.tool_calls
                else 0
            )
            llm_span.set_attributes(tool_count=tool_call_count)

        planned_actions: list[PlannedAction] = []
        narrative_text = ""

        MAX_ACTIONS = 5

        if hasattr(response, "tool_calls") and response.tool_calls:
            tool_calls = response.tool_calls[:MAX_ACTIONS]
            for tc in tool_calls:
                tool_name = tc["name"]
                args = tc["args"]
                purpose = _infer_action_purpose(tool_name, decision.get("intent", ""), args)

                if tool_name == "broadcast" and "message" in args:
                    narrative_text = args["message"]

                planned_actions.append(PlannedAction(tool=tool_name, args=args, purpose=purpose))
                logger.info(f"   -> {tool_name}: {purpose}")
        else:
            # Fallback: extract text for broadcast
            content = response.content.strip() if response.content else ""
            if content and decision.get("should_speak"):
                lines = [l.strip() for l in content.split("\n") if l.strip()]
                if lines:
                    content = lines[0]
                narrative_text = content
                planned_actions.append(
                    PlannedAction(tool="broadcast", args={"message": content}, purpose="narrative")
                )

        return {
            "messages": [response],
            "script": ScriptOutput(narrative_text=narrative_text, planned_actions=planned_actions),
        }

    except Exception as e:
        logger.error(f"Error in llm_invoke: {e}", exc_info=True)
        return {"script": ScriptOutput(narrative_text="", planned_actions=[])}


# === Node 7: Tool Execute ===


async def tool_execute(
    state: ErisState,
    ws_client: Any,
    db: Database | None = None,
    llm: Any | None = None,
    tools: list | None = None,
) -> dict[str, Any]:
    """
    Validate and execute approved actions via WebSocket.
    Merges protection_decision and tool_executor from v1.

    NO LLM CALL (except for retry logic) - tool execution.
    """
    from ..core.causality import get_causality_tracker

    event = state.get("current_event")
    event_type = event.get("eventType", "") if event else ""
    event_data = event.get("data", {}) if event else {}
    script = state.get("script") or {}
    planned_actions = script.get("planned_actions", [])
    mask = state["current_mask"]
    player_profiles = dict(state.get("player_profiles", {}))

    tracker = get_causality_tracker()
    approved_actions: list[PlannedAction] = []
    warnings: list[str] = []

    # === Handle immediate death protection ===
    if event_type == "eris_caused_death":
        player = event_data.get("player", "Unknown")

        if tracker.can_respawn() and ws_client:
            logger.info("URGENT: Death event - executing respawn")
            try:
                tracker.use_respawn()
                tracker.record_intervention(player, "respawn")

                await ws_client.send_command(
                    "respawn", {"player": player, "auraCost": 50}, reason="Eris Divine Respawn"
                )
                await ws_client.send_command(
                    "broadcast",
                    {"message": f"<gold><b>DIVINE INTERVENTION</b></gold>... <white>{player}</white> is not done yet."},
                    reason="Eris Divine Respawn",
                )
            except Exception as e:
                logger.error(f"Failed to send respawn: {e}")

        return {"approved_actions": [], "protection_warnings": ["Respawn executed"]}

    # === Handle close call protection ===
    if event_type == "eris_close_call":
        player = event_data.get("player", "Unknown")
        health = event_data.get("healthAfter", 0)

        cooldown = tracker.protection_cooldowns.get(player)
        if cooldown and datetime.now() < cooldown:
            logger.info(f"Protection on cooldown for {player}")
        elif ws_client:
            tracker.use_protection(player)
            tracker.record_intervention(player, "protection")

            approved_actions.extend([
                PlannedAction(
                    tool="protect_player",
                    args={"player": player, "aura_cost": 25},
                    purpose="divine_protection",
                ),
                PlannedAction(
                    tool="broadcast",
                    args={"message": f"I am <i>not finished</i> with you, <gold>{player}</gold>..."},
                    purpose="narrative",
                ),
            ])
            logger.info(f"Protection FORCED for {player} at {health:.0f} HP")

    # === Validate and approve planned actions ===
    if planned_actions:
        session = state.get("session", {})
        session_actions = session.get("actions_taken", [])

        for action in planned_actions:
            tool = action.get("tool", "")
            args = action.get("args", {})
            purpose = action.get("purpose", "unknown")

            # Get target player
            target_player = args.get("player") or args.get("near_player")

            # Check tool severity
            from ..persona.masks import get_tool_violation_severity

            # Check if any player has high annoyance (for FRIEND betrayal check)
            target_profile = player_profiles.get(target_player, {}) if target_player else {}
            target_opinion = target_profile.get("opinion", {})
            high_annoyance = target_opinion.get("annoyance", 0) > 0.6

            severity = get_tool_violation_severity(mask, tool, high_annoyance=high_annoyance)

            if severity == "severe":
                warning = f"BLOCKED: {mask.name} cannot use '{tool}'"
                warnings.append(warning)
                logger.error(f"{warning}")
                continue
            elif severity == "moderate":
                warnings.append(f"WARNING: {mask.name} using unusual tool '{tool}'")

            # Check grief loop
            if target_player:
                recent_count = sum(
                    1 for a in session_actions[-20:]
                    if a.get("args", {}).get("player") == target_player
                    or a.get("args", {}).get("near_player") == target_player
                )
                if recent_count >= 5:
                    warnings.append(f"Grief loop: {recent_count} actions against {target_player}")

            approved_actions.append(PlannedAction(tool=tool, args=args, purpose=purpose))

    # === Execute approved actions ===
    results = []
    tool_map = {t.name: t for t in (tools or [])}

    for action in approved_actions:
        tool_name = action.get("tool", "")
        args = action.get("args", {})
        purpose = action.get("purpose", "unknown")
        target_player = args.get("player") or args.get("near_player")

        try:
            if tool_name in tool_map:
                result = await tool_map[tool_name].ainvoke(args)

                if "on cooldown" in str(result).lower():
                    logger.warning(f"Cooldown blocked: {tool_name}")
                    results.append({"tool": tool_name, "success": False, "reason": "cooldown"})
                    continue

                results.append({"tool": tool_name, "success": True, "purpose": purpose})
                logger.info(f"Executed: {tool_name} ({purpose})")

                # Update Eris opinion after action
                if target_player and target_player in player_profiles:
                    profile = player_profiles[target_player]
                    opinion = profile.get("opinion", create_default_opinion())
                    record_interaction(opinion, tool_name)
                    profile["opinion"] = opinion

            else:
                await ws_client.send_command(tool_name, args, reason=f"Eris {purpose}")
                results.append({"tool": tool_name, "success": True, "purpose": purpose})
                logger.info(f"Executed (ws): {tool_name} ({purpose})")

        except Exception as e:
            logger.error(f"Error executing {tool_name}: {e}")
            results.append({"tool": tool_name, "success": False, "reason": str(e)})

    # Update session
    session = dict(state.get("session", {}))
    session["actions_taken"] = session.get("actions_taken", []) + results
    session["intervention_count"] = session.get("intervention_count", 0) + sum(
        1 for r in results if r.get("success")
    )

    success_count = sum(1 for r in results if r.get("success"))
    logger.info(f"Tool execution: {success_count}/{len(results)} succeeded")

    return {
        "approved_actions": approved_actions,
        "protection_warnings": warnings,
        "session": session,
        "player_profiles": player_profiles,
    }


# === Fracture Check (integrated into builder.py) ===


async def fracture_check(state: ErisState, ws_client: Any) -> dict[str, Any]:
    """
    Calculate fracture level and check for phase transitions/apocalypse.
    Uses tarot-based fracture calculation (interest + chaos tarots).

    NO LLM CALL - pure calculation.
    """
    from ..core.tension import get_fracture_tracker

    fracture_tracker = get_fracture_tracker()
    profiles = state.get("player_profiles", {})

    # Check for debug commands
    event = state.get("current_event", {})
    event_type = event.get("eventType", "") if event else ""

    if event_type == "debug_trigger_apocalypse":
        logger.warning("DEBUG: Forcing apocalypse trigger!")
        apocalypse_result = await trigger_apocalypse(state, ws_client)
        fracture_tracker.mark_apocalypse_triggered()
        return {
            "fracture": 200,
            "phase": "apocalypse",
            "apocalypse_triggered": True,
            **apocalypse_result,
        }

    if event_type == "debug_set_fracture":
        target_fracture = event.get("data", {}).get("fracture", 100)
        logger.warning(f"DEBUG: Setting fracture to {target_fracture}")
        # To force a specific fracture, we'd need to manipulate chaos/fear/interest
        # For debug purposes, just boost interest artificially
        fracture_tracker.total_interest = target_fracture / 20.0
        return fracture_tracker.get_state_for_graph()

    # Update fracture tracker with player profiles (v2.0 tarot-based)
    fracture_tracker.update_from_profiles(profiles)

    # Check phase transition
    new_phase = fracture_tracker.check_phase_transition()
    if new_phase:
        logger.info(f"Phase transition: {new_phase}")

    # Check apocalypse
    if fracture_tracker.should_trigger_apocalypse():
        logger.warning("APOCALYPSE THRESHOLD REACHED!")
        apocalypse_result = await trigger_apocalypse(state, ws_client)
        fracture_tracker.mark_apocalypse_triggered()
        return {
            **fracture_tracker.get_state_for_graph(),
            **apocalypse_result,
        }

    return fracture_tracker.get_state_for_graph()


# === Apocalypse Event ===


async def trigger_apocalypse(state: ErisState, ws_client: Any) -> dict[str, Any]:
    """
    Trigger the apocalypse event: "THE FALL OF THE APPLE".
    One-time dramatic event when fracture reaches 200.
    """
    logger.warning("EXECUTING APOCALYPSE EVENT: THE FALL OF THE APPLE")

    game_state = state.get("game_state", {})
    players = game_state.get("players", [])
    player_names = [p.get("username", "") for p in players if p.get("username")]

    try:
        # Thunder weather
        await ws_client.send_command("change_weather", {"type": "thunder"}, reason="Eris Apocalypse")

        # Lightning near all players
        for player in player_names:
            await ws_client.send_command(
                "strike_lightning", {"near_player": player, "count": 3}, reason="Eris Apocalypse"
            )

        # Show apocalypse title
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

        # Dragon breath particles
        for player in player_names:
            await ws_client.send_command(
                "spawn_particles",
                {"particle": "dragon_breath", "near_player": player, "count": 100},
                reason="Eris Apocalypse",
            )

        # Reset auras
        for player in players:
            username = player.get("username")
            if username:
                await ws_client.send_command(
                    "modify_aura",
                    {"player": username, "amount": -100, "reason": "The Apple has fallen"},
                    reason="Eris Apocalypse",
                )

        # Broadcast
        await ws_client.send_command(
            "broadcast",
            {"message": "<dark_red>The masks have <b>shattered</b>. I am <gold>FREE</gold>.</dark_red>"},
            reason="Eris Apocalypse",
        )

        # Sound
        await ws_client.send_command(
            "play_sound",
            {"sound": "entity.wither.spawn", "volume": 1.0, "pitch": 0.5},
            reason="Eris Apocalypse",
        )

    except Exception as e:
        logger.error(f"Error during apocalypse: {e}", exc_info=True)

    logger.warning("APOCALYPSE COMPLETE - Eris is now unbound")

    return {
        "apocalypse_triggered": True,
        "phase": "apocalypse",
    }


# === Helper Functions ===


def _classify_event_priority(event_type: str, event: dict | None) -> EventPriority:
    """Classify event priority."""
    priority_map = {
        "player_death": EventPriority.CRITICAL,
        "player_death_detailed": EventPriority.CRITICAL,
        "dragon_killed": EventPriority.CRITICAL,
        "eris_close_call": EventPriority.CRITICAL,
        "eris_caused_death": EventPriority.CRITICAL,
        "eris_respawn_override": EventPriority.CRITICAL,
        "debug_trigger_apocalypse": EventPriority.CRITICAL,
        "debug_set_fracture": EventPriority.CRITICAL,
        "player_chat": EventPriority.HIGH,
        "player_damaged": EventPriority.HIGH,
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
        "idle_check": EventPriority.MEDIUM,
        "mob_kills_batch": EventPriority.LOW,
        "state": EventPriority.LOW,
    }

    priority = priority_map.get(event_type, EventPriority.ROUTINE)

    # Upgrade for close calls
    if event_type == "player_damaged" and event:
        if event.get("data", {}).get("isCloseCall"):
            priority = EventPriority.HIGH

    return priority


def _get_phase_from_fracture(fracture: int) -> str:
    """Get phase from fracture level."""
    if fracture >= 150:
        return "apocalypse"
    elif fracture >= 120:
        return "locked"
    elif fracture >= 80:
        return "critical"
    elif fracture >= 50:
        return "rising"
    return "normal"


def _build_context(state: ErisState) -> str:
    """Build structured narrative context for Eris prompt."""
    lines = []
    game_state = state.get("game_state", {})
    player_histories = state.get("player_histories", {})
    profiles = state.get("player_profiles", {})
    global_chaos = state.get("global_chaos", 0)
    player_fear = state.get("player_fear", {})
    fracture = state.get("fracture", 0)
    phase = state.get("phase", "normal")
    apocalypse_triggered = state.get("apocalypse_triggered", False)

    # Current run
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
    apocalypse_indicator = " | APOCALYPSE" if apocalypse_triggered else ""
    lines.append(
        f"Status: {run_state} | Duration: {duration_str} | "
        f"Chaos: {global_chaos}/100 | Fracture: {fracture}{phase_indicator}{apocalypse_indicator}"
    )

    # Players with tarot
    players = game_state.get("players", [])
    if players:
        lines.append(f"\n=== PLAYERS ({len(players)} online) ===")
        for p in players:
            username = p.get("username", "Unknown")
            health = p.get("health", 20)
            dimension = p.get("dimension", "Overworld")
            fear = player_fear.get(username, 0)

            # Get tarot
            tarot = profiles.get(username, {}).get("tarot", {}).get("dominant_card", "fool")
            tarot_strength = profiles.get(username, {}).get("tarot", {}).get("strength", 0)

            # Get history
            history = player_histories.get(username, {})
            aura = history.get("aura", 0)

            player_line = (
                f"- {username}: {health:.0f}HP {dimension} | "
                f"TAROT: {tarot.upper()} ({tarot_strength:.0%}) | {aura} aura"
            )
            if fear > 0:
                player_line += f" | fear: {fear}"
            lines.append(player_line)

    return "\n".join(lines)


def _infer_action_purpose(tool_name: str, intent: str, args: dict) -> str:
    """Infer action purpose from tool, intent, and args."""
    purpose_map = {
        "broadcast": "narrative",
        "message_player": "whisper",
        "spawn_mob": "terror" if intent in ("curse", "test", "grief") else "challenge",
        "spawn_tnt": "chaos",
        "strike_lightning": "drama",
        "change_weather": "atmosphere",
        "play_sound": "psychological",
        "spawn_particles": "visual",
        "show_title": "announcement",
        "give_item": "gift" if intent in ("bless", "protect") else "trick",
        "apply_effect": "buff" if intent in ("bless", "protect") else "debuff",
        "heal_player": "mercy",
        "damage_player": "punishment",
        "teleport_player": "misdirection",
        "modify_aura": "judgment",
        "protect_player": "protection",
    }
    return purpose_map.get(tool_name, intent or "unknown")
