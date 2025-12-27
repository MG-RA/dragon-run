"""Scenario runner for closed-loop Eris testing.

Orchestrates: Scenario → EventProcessor → LangGraph → Tool Calls → SyntheticWorld
Produces full trace with both events and Eris interventions.
"""

import asyncio
import logging
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
from .scenario_loader import load_scenario
from .scenario_schema import Scenario
from .synthetic_client import SyntheticGameStateClient
from .synthetic_event_processor import SyntheticEventProcessor
from .synthetic_world import GameState, SyntheticWorld
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
                    "player_karmas": {},
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
