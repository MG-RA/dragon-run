"""Scenario runner for closed-loop Eris testing.

Orchestrates: Scenario → EventProcessor → LangGraph → Tool Calls → SyntheticWorld
Produces full trace with both events and Eris interventions.
"""

import asyncio
import logging
import random
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import ErisConfig
from ..core.database import Database
from ..core.memory import LongTermMemory, ShortTermMemory
from ..core.tracing import generate_trace_id
from ..graph.builder import create_graph
from ..graph.state import ErisMask, EventPriority, create_initial_state
from .intent_compiler import IntentCompiler
from .intents import IntentResult
from .player_memory import PlayerMemory
from .scenario_loader import load_scenario
from .scenario_schema import Scenario
from .scoring import ScenarioScore, score_run
from .synthetic_client import SyntheticGameStateClient
from .synthetic_event_processor import SyntheticEventProcessor
from .synthetic_world import GameState, SyntheticWorld
from .tarot_brains import DecisionContext, TarotBrain
from .world_diff import RunTrace

logger = logging.getLogger(__name__)


@dataclass
class ScenarioRunResult:
    """Result of running a scenario through Eris."""

    scenario_name: str
    run_id: str
    victory: bool
    deaths: int
    total_events: int
    total_tool_calls: int
    eris_interventions: int  # Times Eris spoke or acted
    final_phase: str
    final_fracture: int
    world_trace: RunTrace  # From SyntheticWorld
    eris_actions: list[dict[str, Any]]  # All tool calls from Eris
    graph_outputs: list[dict[str, Any]]  # LangGraph results per event
    duration_seconds: float
    success: bool
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON export."""
        return {
            "scenario_name": self.scenario_name,
            "run_id": self.run_id,
            "victory": self.victory,
            "deaths": self.deaths,
            "total_events": self.total_events,
            "total_tool_calls": self.total_tool_calls,
            "eris_interventions": self.eris_interventions,
            "final_phase": self.final_phase,
            "final_fracture": self.final_fracture,
            "world_trace": self.world_trace.to_dict(),
            "eris_actions": self.eris_actions,
            "graph_outputs": self.graph_outputs,
            "duration_seconds": self.duration_seconds,
            "success": self.success,
            "error": self.error,
        }

    def calculate_score(self) -> ScenarioScore:
        """Calculate Phase 4 score for this run.

        Returns:
            ScenarioScore with all metrics calculated
        """
        return score_run(self.world_trace, self.duration_seconds, self.run_id)


class ScenarioRunner:
    """Runs scenarios through the complete Eris pipeline.

    This is the Phase 3 deliverable: a closed-loop harness that:
    1. Loads a scenario
    2. Creates SyntheticWorld from scenario
    3. Feeds scenario events to LangGraph
    4. Captures Eris tool calls
    5. Applies tool calls to SyntheticWorld
    6. Produces complete trace with telemetry
    """

    def __init__(
        self,
        llm: Any,
        db: Database | None = None,
        config: ErisConfig | None = None,
    ):
        """Initialize scenario runner.

        Args:
            llm: LangChain LLM instance
            db: Database instance (optional, for player history)
            config: Eris configuration (optional)
        """
        self.llm = llm
        self.db = db
        self.config = config

        # Memory systems
        self.short_memory = ShortTermMemory(max_tokens=4000)
        self.long_memory = LongTermMemory(db) if db else None

    async def run_scenario(
        self,
        scenario: Scenario | Path | str,
        run_id: str | None = None,
    ) -> ScenarioRunResult:
        """Run a scenario through the complete Eris pipeline.

        Args:
            scenario: Scenario object or path to scenario YAML
            run_id: Optional run ID (generated if not provided)

        Returns:
            ScenarioRunResult with complete telemetry
        """
        start_time = datetime.now()

        # Load scenario if path provided
        if isinstance(scenario, (Path, str)):
            scenario = load_scenario(Path(scenario))

        run_id = run_id or str(uuid.uuid4())[:8]

        logger.info(f"[SCENARIO] Starting run: {scenario.metadata.name} (run_id={run_id})")

        try:
            # Create synthetic world from scenario
            world = SyntheticWorld.from_scenario(scenario)
            world.game_state = GameState.ACTIVE

            # Create synthetic client
            client = SyntheticGameStateClient(world)

            # Create event processor
            event_processor = SyntheticEventProcessor(scenario)

            # Create LangGraph
            graph = create_graph(db=self.db, ws_client=client, llm=self.llm)

            # Reset memory
            self.short_memory = ShortTermMemory(max_tokens=4000)

            # Track results
            graph_outputs = []
            eris_actions = []
            intervention_count = 0

            # Process each event
            while event_processor.has_more_events():
                event_dict = event_processor.get_next_event()
                if not event_dict:
                    break

                event_type = event_dict.get("eventType", "unknown")
                trace_id = generate_trace_id()

                logger.info(f"[SCENARIO] Event {event_processor.event_index}: {event_type} [trace:{trace_id}]")

                # First, apply event to world (if it's a scenario event, not Eris action)
                # This ensures world state is updated before Eris sees it
                try:
                    # Convert event back to scenario event format for world application
                    # (SyntheticWorld.apply_event expects Event objects)
                    scenario_event = scenario.events[event_processor.event_index - 1]
                    world_diff = world.apply_event(scenario_event)
                    logger.debug(f"[SCENARIO] Applied event to world: {len(world_diff.changes)} changes")
                except Exception as e:
                    logger.error(f"[SCENARIO] Error applying event to world: {e}")

                # Add to short-term memory
                self.short_memory.add_event(event_dict)

                # Build game state snapshot for Eris
                game_snapshot = world.to_game_snapshot()

                # Build initial state for graph
                initial_state = create_initial_state()
                initial_state.update({
                    "current_event": event_dict,
                    "event_priority": EventPriority.MEDIUM,
                    "context_buffer": self.short_memory.get_context_string(),
                    "game_state": game_snapshot,
                    "player_histories": {},
                    "player_profiles": {},  # v2.0: replaces player_karmas
                    "session": {
                        "run_id": run_id,
                        "events_this_run": graph_outputs,
                        "actions_taken": eris_actions,
                        "last_speech_time": 0,
                        "intervention_count": intervention_count,
                    },
                    "timestamp": datetime.now().timestamp(),
                    "trace_id": trace_id,
                })

                # Invoke graph
                try:
                    result = await asyncio.wait_for(
                        graph.ainvoke(initial_state),
                        timeout=30.0,
                    )

                    # Extract results
                    decision = result.get("decision") or {}
                    script = result.get("script") or {}
                    approved_actions = result.get("approved_actions") or []

                    # Count interventions
                    if decision.get("should_speak") or decision.get("should_act"):
                        intervention_count += 1

                    # Record graph output
                    graph_output = {
                        "event_index": event_processor.event_index - 1,
                        "event_type": event_type,
                        "trace_id": trace_id,
                        "mask": result.get("current_mask", ErisMask.TRICKSTER).value,
                        "phase": result.get("phase", "normal"),
                        "fracture": result.get("fracture", 0),
                        "decision": {
                            "intent": decision.get("intent", ""),
                            "targets": decision.get("targets", []),
                            "escalation": decision.get("escalation", 0),
                            "should_speak": decision.get("should_speak", False),
                            "should_act": decision.get("should_act", False),
                        },
                        "narrative": script.get("narrative_text", ""),
                        "planned_actions": script.get("planned_actions", []),
                        "approved_actions": approved_actions,
                    }

                    graph_outputs.append(graph_output)

                    logger.info(
                        f"[SCENARIO] Eris responded: mask={graph_output['mask']}, "
                        f"speak={decision.get('should_speak')}, "
                        f"act={decision.get('should_act')}, "
                        f"actions={len(approved_actions)}"
                    )

                except TimeoutError:
                    logger.error(f"[SCENARIO] Graph timeout for event: {event_type} [trace:{trace_id}]")
                except Exception as e:
                    logger.error(f"[SCENARIO] Graph error for event: {event_type} [trace:{trace_id}]: {e}", exc_info=True)

                # Check if run ended (death or victory)
                if world.game_state in (GameState.ENDED, GameState.ENDING):
                    logger.info(f"[SCENARIO] Run ended: {world.game_state.value}")
                    break

            # Collect results
            tool_calls = client.get_tool_calls()
            eris_actions = [
                {
                    "command": tc["command"],
                    "args": tc["args"],
                    "timestamp": tc["timestamp"],
                    "success": tc["success"],
                    "changes": len(tc["diff"].changes) if tc.get("diff") else 0,
                }
                for tc in tool_calls
            ]

            # Get world trace
            world_trace = world.get_trace()

            # Build result
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            result = ScenarioRunResult(
                scenario_name=scenario.metadata.name,
                run_id=run_id,
                victory=world_trace.victory,
                deaths=world_trace.deaths,
                total_events=world_trace.total_events,
                total_tool_calls=len(tool_calls),
                eris_interventions=intervention_count,
                final_phase=world_trace.final_phase,
                final_fracture=world.fracture,
                world_trace=world_trace,
                eris_actions=eris_actions,
                graph_outputs=graph_outputs,
                duration_seconds=duration,
                success=True,
            )

            logger.info(
                f"[SCENARIO] Run complete: victory={result.victory}, "
                f"deaths={result.deaths}, "
                f"events={result.total_events}, "
                f"tool_calls={result.total_tool_calls}, "
                f"interventions={result.eris_interventions}, "
                f"duration={duration:.2f}s"
            )

            return result

        except Exception as e:
            logger.error(f"[SCENARIO] Run failed: {e}", exc_info=True)
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            return ScenarioRunResult(
                scenario_name=scenario.metadata.name if isinstance(scenario, Scenario) else "unknown",
                run_id=run_id,
                victory=False,
                deaths=0,
                total_events=0,
                total_tool_calls=0,
                eris_interventions=0,
                final_phase="unknown",
                final_fracture=0,
                world_trace=RunTrace(scenario_name="unknown"),  # Empty trace
                eris_actions=[],
                graph_outputs=[],
                duration_seconds=duration,
                success=False,
                error=str(e),
            )


async def run_scenario_batch(
    scenarios: list[Path],
    llm: Any,
    db: Database | None = None,
) -> list[ScenarioRunResult]:
    """Run multiple scenarios in sequence.

    Args:
        scenarios: List of paths to scenario YAML files
        llm: LangChain LLM instance
        db: Database instance (optional)

    Returns:
        List of ScenarioRunResult objects
    """
    runner = ScenarioRunner(llm=llm, db=db)
    results = []

    for scenario_path in scenarios:
        logger.info(f"[BATCH] Running scenario: {scenario_path.name}")
        result = await runner.run_scenario(scenario_path)
        results.append(result)

    return results


# ==================== EMERGENT SCENARIO RUNNER (PHASE 6) ====================


@dataclass
class EmergentRunResult(ScenarioRunResult):
    """Extended result for emergent scenarios with tarot data."""

    tarot_summary: dict[str, dict] | None = None  # Final tarot profiles
    tarot_history: list[dict] | None = None  # Tarot evolution over time
    ticks_executed: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON export."""
        base = super().to_dict()
        base["tarot_summary"] = self.tarot_summary
        base["tarot_history"] = self.tarot_history
        base["ticks_executed"] = self.ticks_executed
        return base


class EmergentScenarioRunner:
    """
    Runs emergent scenarios where tarot-driven player brains generate events.

    Instead of replaying pre-scripted events, this runner:
    1. Creates player brains with tarot profiles
    2. Each tick, brains decide what to do based on their tarot identity
    3. Decisions are compiled into events
    4. Events are applied to the world AND fed to Eris
    5. Eris responds, and the cycle continues

    This creates truly emergent narratives where behavior arises from
    psychological archetypes rather than scripts.
    """

    def __init__(
        self,
        llm: Any,
        db: Database | None = None,
        config: ErisConfig | None = None,
    ):
        self.llm = llm
        self.db = db
        self.config = config
        self.short_memory = ShortTermMemory(max_tokens=4000)
        self.long_memory = LongTermMemory(db) if db else None

    async def run_scenario(
        self,
        scenario: Scenario | Path | str,
        run_id: str | None = None,
    ) -> EmergentRunResult:
        """
        Run an emergent scenario where player behavior emerges from tarot.

        Args:
            scenario: Scenario with mode=EMERGENT
            run_id: Optional run ID

        Returns:
            EmergentRunResult with tarot evolution data
        """
        start_time = datetime.now()

        # Load scenario if path provided
        if isinstance(scenario, (Path, str)):
            scenario = load_scenario(Path(scenario))

        run_id = run_id or str(uuid.uuid4())[:8]
        seed = scenario.metadata.seed or 42
        rng = random.Random(seed)

        logger.info(
            f"[EMERGENT] Starting run: {scenario.metadata.name} "
            f"(run_id={run_id}, seed={seed}, max_ticks={scenario.max_ticks})"
        )

        try:
            # Create world from scenario
            world = SyntheticWorld.from_scenario(scenario)
            world.game_state = GameState.ACTIVE

            # Initialize tarot profiles from scenario
            if scenario.initial_tarot:
                world.initialize_tarot(scenario.initial_tarot)

            # Create player brains
            player_brains: dict[str, TarotBrain] = {}
            for player_name in world.players:
                brain = TarotBrain(rng=random.Random(rng.randint(0, 2**32)))
                brain.memory = PlayerMemory()
                # Copy initial tarot profile to brain
                if player_name in world.player_tarot:
                    brain.tarot = world.player_tarot[player_name]
                player_brains[player_name] = brain

            # Create synthetic client and graph
            client = SyntheticGameStateClient(world)
            graph = create_graph(db=self.db, ws_client=client, llm=self.llm)

            # Intent compiler
            compiler = IntentCompiler(rng=rng)

            # Reset memory
            self.short_memory = ShortTermMemory(max_tokens=4000)

            # Tracking
            graph_outputs = []
            eris_actions = []
            intervention_count = 0
            tarot_history = []
            ticks_executed = 0

            # Main simulation loop - TWO-PHASE TICKING
            # Phase 1: All players decide (collect intents)
            # Phase 2: All intents compiled into events
            # Phase 3: All events applied simultaneously
            #
            # This prevents turn-order bias where first player becomes god.
            # Real chaos requires delayed causality.
            for tick in range(scenario.max_ticks):
                ticks_executed = tick + 1

                # Record tarot state periodically
                if tick % 50 == 0:
                    tarot_history.append({
                        "tick": tick,
                        "profiles": world.get_tarot_summary(),
                    })

                # ==================== PHASE 1: ALL PLAYERS DECIDE ====================
                # Collect all intents before applying any - no turn order bias
                tick_intents: list[tuple[str, TarotBrain, IntentResult]] = []

                for player_name, brain in player_brains.items():
                    player = world.players.get(player_name)
                    if not player or not player.alive:
                        continue

                    # Build decision context (snapshot of current state)
                    context = DecisionContext(
                        player_state=player,
                        world_state=world.to_game_snapshot(),
                        nearby_players=[
                            p for p in world.players.values()
                            if p.name != player_name and p.alive
                        ],
                        recent_events=world.event_history[-10:],
                        eris_recent_actions=world.tool_history[-5:],
                        discovered_structures=world.discovered_structures.get(player_name, set()),
                        is_low_health=player.health <= 6,
                        is_under_attack=len(world.spawned_mobs) > 0,
                    )

                    # Brain decides based on tarot
                    intent_result = brain.decide(context)
                    tick_intents.append((player_name, brain, intent_result))

                # ==================== PHASE 2: COMPILE ALL INTENTS ====================
                # Convert intents to events - still no world mutation
                tick_events: list[tuple[str, TarotBrain, list]] = []

                for player_name, brain, intent_result in tick_intents:
                    player = world.players.get(player_name)
                    if not player:
                        continue

                    events = compiler.compile(
                        intent_result,
                        player,
                        brain.tarot,
                        world,
                    )
                    tick_events.append((player_name, brain, events))

                # ==================== PHASE 3: APPLY ALL EVENTS ====================
                # Now apply everything - simultaneous causality
                all_events_this_tick = []

                for player_name, brain, events in tick_events:
                    for event in events:
                        # Apply to world
                        world.apply_event(event)
                        all_events_this_tick.append(event)

                        # Sync brain's tarot with world's tarot
                        if player_name in world.player_tarot:
                            brain.tarot = world.player_tarot[player_name]

                        # Convert to Eris event format
                        event_dict = self._event_to_dict(event, world)
                        self.short_memory.add_event(event_dict)

                # ==================== PHASE 4: ERIS OBSERVES ====================
                # Feed aggregated events to Eris (batch per tick, not per event)
                # This reduces LLM calls dramatically
                if all_events_this_tick:
                    # Pick the most significant event for Eris to respond to
                    primary_event = self._select_primary_event(all_events_this_tick)
                    event_dict = self._event_to_dict(primary_event, world)

                    trace_id = generate_trace_id()
                    game_snapshot = world.to_game_snapshot()

                    initial_state = create_initial_state()
                    initial_state.update({
                        "current_event": event_dict,
                        "event_priority": EventPriority.MEDIUM,
                        "context_buffer": self.short_memory.get_context_string(),
                        "game_state": game_snapshot,
                        "player_histories": {},
                        "player_profiles": {},  # v2.0: replaces player_karmas
                        "session": {
                            "run_id": run_id,
                            "events_this_run": graph_outputs,
                            "actions_taken": eris_actions,
                            "last_speech_time": 0,
                            "intervention_count": intervention_count,
                        },
                        "timestamp": datetime.now().timestamp(),
                        "trace_id": trace_id,
                    })

                    # Invoke graph (with timeout)
                    try:
                        result = await asyncio.wait_for(
                            graph.ainvoke(initial_state),
                            timeout=30.0,
                        )

                        decision = result.get("decision") or {}
                        if decision.get("should_speak") or decision.get("should_act"):
                            intervention_count += 1

                        # Get the brain for the primary event's player
                        primary_player = getattr(primary_event, "player", None)
                        primary_brain = player_brains.get(primary_player) if primary_player else None

                        graph_outputs.append({
                            "tick": tick,
                            "event_type": primary_event.type,
                            "trace_id": trace_id,
                            "mask": result.get("current_mask", ErisMask.TRICKSTER).value,
                            "player_tarot": primary_brain.tarot.dominant_card.value if primary_brain else "unknown",
                            "events_this_tick": len(all_events_this_tick),
                        })

                    except TimeoutError:
                        logger.warning(f"[EMERGENT] Graph timeout at tick {tick}")
                    except Exception as e:
                        logger.warning(f"[EMERGENT] Graph error at tick {tick}: {e}")

                # Check end conditions
                if world.is_run_ended():
                    logger.info(f"[EMERGENT] Run ended at tick {tick}")
                    break

                # Check target phase reached
                if self._target_phase_reached(world, scenario.target_phase):
                    logger.info(f"[EMERGENT] Target phase {scenario.target_phase} reached at tick {tick}")
                    break

            # Final tarot snapshot
            tarot_history.append({
                "tick": ticks_executed,
                "profiles": world.get_tarot_summary(),
            })

            # Collect results
            tool_calls = client.get_tool_calls()
            eris_actions = [
                {
                    "command": tc["command"],
                    "args": tc["args"],
                    "timestamp": tc["timestamp"],
                    "success": tc["success"],
                }
                for tc in tool_calls
            ]

            world_trace = world.get_trace()
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            result = EmergentRunResult(
                scenario_name=scenario.metadata.name,
                run_id=run_id,
                victory=world_trace.victory if world_trace else not world.dragon_alive,
                deaths=world_trace.deaths if world_trace else len(world.get_dead_players()),
                total_events=world_trace.total_events if world_trace else len(world.event_history),
                total_tool_calls=len(tool_calls),
                eris_interventions=intervention_count,
                final_phase=world_trace.final_phase if world_trace else world.phase.value,
                final_fracture=int(world.fracture),
                world_trace=world_trace or RunTrace(scenario_name=scenario.metadata.name),
                eris_actions=eris_actions,
                graph_outputs=graph_outputs,
                duration_seconds=duration,
                success=True,
                tarot_summary=world.get_tarot_summary(),
                tarot_history=tarot_history,
                ticks_executed=ticks_executed,
            )

            logger.info(
                f"[EMERGENT] Run complete: victory={result.victory}, "
                f"ticks={ticks_executed}, "
                f"events={result.total_events}, "
                f"interventions={result.eris_interventions}"
            )

            return result

        except Exception as e:
            logger.error(f"[EMERGENT] Run failed: {e}", exc_info=True)
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            return EmergentRunResult(
                scenario_name=scenario.metadata.name if isinstance(scenario, Scenario) else "unknown",
                run_id=run_id or "unknown",
                victory=False,
                deaths=0,
                total_events=0,
                total_tool_calls=0,
                eris_interventions=0,
                final_phase="unknown",
                final_fracture=0,
                world_trace=RunTrace(scenario_name="unknown"),
                eris_actions=[],
                graph_outputs=[],
                duration_seconds=duration,
                success=False,
                error=str(e),
                tarot_summary=None,
                tarot_history=None,
                ticks_executed=0,
            )

    def _event_to_dict(self, event: Any, world: SyntheticWorld) -> dict:
        """Convert a scenario Event to Eris-compatible event dict."""
        base = {
            "eventType": event.type,
            "timestamp": int(datetime.now().timestamp() * 1000),
        }

        # Add event-specific fields
        if hasattr(event, "player"):
            base["player"] = event.player
            # Include tarot in event for Eris context
            tarot = world.get_player_dominant_tarot(event.player)
            if tarot:
                base["playerTarot"] = tarot.value

        if hasattr(event, "message"):
            base["message"] = event.message
        if hasattr(event, "amount"):
            base["amount"] = event.amount
        if hasattr(event, "source"):
            base["source"] = event.source
        if hasattr(event, "item"):
            base["item"] = event.item
        if hasattr(event, "count"):
            base["count"] = event.count
        if hasattr(event, "to_dim"):
            base["toDimension"] = event.to_dim
        if hasattr(event, "structure"):
            base["structure"] = event.structure
        if hasattr(event, "advancement"):
            base["advancement"] = event.advancement

        return base

    def _select_primary_event(self, events: list) -> Any:
        """
        Select the most significant event from a tick for Eris to respond to.

        Priority order (highest first):
        1. Death events
        2. Damage events (by amount)
        3. Dimension changes
        4. Structure discoveries
        5. Chat events
        6. Everything else
        """
        if not events:
            return None

        # Priority scoring
        def event_priority(event) -> tuple[int, int]:
            event_type = getattr(event, "type", "")

            if event_type == "player_death":
                return (0, 0)  # Highest priority
            if event_type == "player_damaged":
                amount = getattr(event, "amount", 0)
                return (1, -amount)  # Higher damage = higher priority
            if event_type == "dimension_change":
                return (2, 0)
            if event_type == "structure_discovered":
                return (3, 0)
            if event_type == "player_chat":
                return (4, 0)
            return (5, 0)  # Lowest priority

        return min(events, key=event_priority)

    def _target_phase_reached(self, world: SyntheticWorld, target: str) -> bool:
        """Check if the target game phase has been reached."""
        if target == "dragon":
            return not world.dragon_alive
        elif target == "end":
            return any(p.entered_end for p in world.players.values())
        elif target == "nether":
            return any(p.entered_nether for p in world.players.values())
        elif target == "early":
            # Early = first structure found
            return any(len(s) > 0 for s in world.discovered_structures.values())
        return False


async def run_emergent_scenario(
    scenario: Scenario | Path | str,
    llm: Any,
    db: Database | None = None,
    run_id: str | None = None,
) -> EmergentRunResult:
    """
    Convenience function to run a single emergent scenario.

    Args:
        scenario: Scenario with mode=EMERGENT (or will be set)
        llm: LangChain LLM instance
        db: Database instance (optional)
        run_id: Optional run ID

    Returns:
        EmergentRunResult with tarot evolution data
    """
    runner = EmergentScenarioRunner(llm=llm, db=db)
    return await runner.run_scenario(scenario, run_id=run_id)
