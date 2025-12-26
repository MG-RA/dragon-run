"""Eris AI Director Application - Main lifecycle management."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from langchain_ollama import ChatOllama

from eris.config import ErisConfig
from eris.core.database import Database
from eris.core.event_processor import EventProcessor
from eris.core.memory import LongTermMemory, ShortTermMemory
from eris.core.websocket import GameStateClient
from eris.graph.builder import create_graph
from eris.graph.state import ErisMask, EventPriority


logger = logging.getLogger("eris")


class AppState(Enum):
    """Application lifecycle states."""
    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass
class GameContext:
    """Current game state tracking."""
    state: dict = field(default_factory=dict)
    last_logged_players: list = field(default_factory=list)
    last_logged_game_state: Optional[str] = None
    last_intervention_time: float = 0.0


@dataclass
class Services:
    """Container for all application services."""
    config: ErisConfig
    database: Database
    llm: ChatOllama
    event_processor: EventProcessor
    short_memory: ShortTermMemory
    long_memory: LongTermMemory
    ws_client: Optional[GameStateClient] = None
    graph: Optional[Any] = None  # LangGraph CompiledGraph

    @property
    def db_available(self) -> bool:
        """Check if database connection is available."""
        return self.database.pool is not None


class ErisApplication:
    """Main application class for Eris AI Director.

    Manages the complete lifecycle: initialization, running, and shutdown.
    Provides clean dependency injection and testability.
    """

    def __init__(self, config: ErisConfig, base_dir: Path):
        """Initialize application with validated configuration.

        Args:
            config: Validated ErisConfig instance.
            base_dir: Base directory for the director module.
        """
        self.config = config
        self.base_dir = base_dir
        self.state = AppState.CREATED
        self.services: Optional[Services] = None
        self.game_context = GameContext()
        self._shutdown_event = asyncio.Event()
        self._tasks: list[asyncio.Task] = []

    async def initialize(self) -> None:
        """Initialize all services and build the processing graph.

        Raises:
            RuntimeError: If initialization fails critically.
        """
        if self.state != AppState.CREATED:
            raise RuntimeError(f"Cannot initialize from state: {self.state}")

        self.state = AppState.STARTING
        logger.info("Initializing Eris AI Director...")

        try:
            # Database
            db = Database(self.config.database.model_dump())
            try:
                await asyncio.wait_for(
                    db.connect(),
                    timeout=self.config.database.connect_timeout
                )
                logger.info(
                    f"Database connected: {self.config.database.host}:"
                    f"{self.config.database.port}/{self.config.database.database}"
                )
            except asyncio.TimeoutError:
                logger.warning("Database connection timed out, continuing without DB")
            except Exception as e:
                logger.warning(f"Database connection failed: {e}")
                logger.warning("Continuing without long-term memory")

            # LLM
            llm = ChatOllama(
                model=self.config.ollama.model,
                base_url=self.config.ollama.host,
                temperature=self.config.ollama.temperature,
                keep_alive=self.config.ollama.keep_alive,
                num_ctx=self.config.ollama.context_window,
                format="",
            )
            logger.info(f"LLM configured: {self.config.ollama.model} @ {self.config.ollama.host}")

            # Event processor with config
            debounce_config = {
                "state": self.config.event_processor.debounce.state,
                "player_damaged": self.config.event_processor.debounce.player_damaged,
                "resource_milestone": self.config.event_processor.debounce.resource_milestone,
            }
            event_processor = EventProcessor(debounce_config)

            # Memory
            short_memory = ShortTermMemory(
                max_tokens=self.config.memory.short_term_max_tokens
            )
            long_memory = LongTermMemory(db)

            # Create services container
            self.services = Services(
                config=self.config,
                database=db,
                llm=llm,
                event_processor=event_processor,
                short_memory=short_memory,
                long_memory=long_memory,
            )

            # WebSocket client (will be fully configured in run())
            self.services.ws_client = GameStateClient(
                self.config.websocket.uri,
                self._on_state_update,
                self._on_event,
            )

            # Build graph
            self.services.graph = create_graph(
                db=db,
                ws_client=self.services.ws_client,
                llm=llm,
            )

            logger.info("All services initialized successfully")

        except Exception as e:
            self.state = AppState.FAILED
            logger.error(f"Initialization failed: {e}", exc_info=True)
            raise RuntimeError(f"Failed to initialize Eris: {e}") from e

    async def run(self) -> None:
        """Run the main event loop until shutdown.

        Handles WebSocket connection, periodic checks, and graceful shutdown.
        """
        if self.state != AppState.STARTING or self.services is None:
            raise RuntimeError(f"Cannot run from state: {self.state}")

        self.state = AppState.RUNNING
        self.game_context.last_intervention_time = asyncio.get_event_loop().time()

        logger.info("Eris AI Director ready!")
        logger.info(f"Connecting to game server at {self.config.websocket.uri}...")

        # Setup signal handlers for graceful shutdown
        self._setup_signal_handlers()

        try:
            # Create concurrent tasks
            ws_task = asyncio.create_task(
                self._run_websocket_with_backoff(),
                name="websocket"
            )
            idle_task = asyncio.create_task(
                self._run_periodic_idle_check(),
                name="idle_check"
            )
            self._tasks = [ws_task, idle_task]

            # Wait for shutdown signal or task failure
            done, pending = await asyncio.wait(
                self._tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Check if a task failed
            for task in done:
                if task.exception():
                    logger.error(f"Task {task.get_name()} failed: {task.exception()}")

        except asyncio.CancelledError:
            logger.info("Application cancelled")
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        """Gracefully shutdown all services."""
        if self.state in (AppState.STOPPING, AppState.STOPPED):
            return

        self.state = AppState.STOPPING
        logger.info("Shutting down Eris AI Director...")

        # Cancel running tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=5.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass

        # Cleanup services
        if self.services:
            if self.services.ws_client:
                self.services.ws_client.stop()

            if self.services.database.pool:
                await self.services.database.close()

        self.state = AppState.STOPPED
        logger.info("Eris AI Director stopped")

    def request_shutdown(self) -> None:
        """Request graceful shutdown (can be called from signal handlers)."""
        self._shutdown_event.set()

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        loop = asyncio.get_running_loop()

        def signal_handler(sig: signal.Signals) -> None:
            logger.info(f"Received signal {sig.name}, requesting shutdown...")
            self.request_shutdown()

        # Only setup on Unix-like systems
        if sys.platform != "win32":
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))
        # On Windows, KeyboardInterrupt will be caught in the except block

    async def _run_websocket_with_backoff(self) -> None:
        """Run WebSocket with exponential backoff on disconnect."""
        delay = self.config.websocket.reconnect_base_delay
        max_delay = self.config.websocket.reconnect_max_delay
        jitter = self.config.websocket.reconnect_jitter

        while not self._shutdown_event.is_set():
            try:
                await self.services.ws_client.connect()
                # Reset delay on successful connection
                delay = self.config.websocket.reconnect_base_delay
            except Exception as e:
                if self._shutdown_event.is_set():
                    break

                logger.warning(f"WebSocket disconnected: {e}")

                # Apply exponential backoff with jitter
                import random
                actual_delay = delay * (1 + random.uniform(-jitter, jitter))
                logger.info(f"Reconnecting in {actual_delay:.1f}s...")
                await asyncio.sleep(actual_delay)

                # Exponential backoff
                delay = min(delay * 2, max_delay)

    async def _run_periodic_idle_check(self) -> None:
        """Periodic check to make Eris proactive when nothing is happening."""
        interval = self.config.eris.idle_check_interval
        min_idle = self.config.eris.min_idle_time

        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(interval)

                if self._shutdown_event.is_set():
                    break

                # Only check during active runs with players
                game_state = self.game_context.state.get("gameState")
                players = self.game_context.state.get("players", [])

                if game_state != "ACTIVE" or len(players) == 0:
                    continue

                # Check if Eris has been quiet for a while
                current_time = asyncio.get_event_loop().time()
                idle_duration = current_time - self.game_context.last_intervention_time

                if idle_duration >= min_idle:
                    logger.info(f"Idle check: {idle_duration:.0f}s since last intervention")

                    idle_event = {
                        "eventType": "idle_check",
                        "data": {
                            "idle_duration": idle_duration,
                            "player_count": len(players),
                        }
                    }

                    await self._on_event(idle_event, is_idle_check=True)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Periodic check error: {e}")

    async def _on_state_update(self, data: dict) -> None:
        """Handle game state updates."""
        self.game_context.state = data

        # Only log when state changes
        players = data.get("players", [])
        player_names = [p.get("username", "?") for p in players]
        game_state = data.get("gameState")

        if (player_names != self.game_context.last_logged_players or
                game_state != self.game_context.last_logged_game_state):
            logger.info(f"State update: {game_state}, {len(players)} players: {player_names}")
            self.game_context.last_logged_players = player_names
            self.game_context.last_logged_game_state = game_state

    async def _on_event(self, data: dict, is_idle_check: bool = False) -> None:
        """Handle game events by processing through the LangGraph."""
        event_type = data.get("eventType", "unknown")

        event_data = {
            "eventType": event_type,
            "data": data.get("data", {})
        }

        logger.info(f"Event: {event_type}")

        # Add to event processor queue
        queued = await self.services.event_processor.add_event(event_data)

        if not queued:
            return

        # Add to short-term memory
        self.services.short_memory.add_event(event_data)

        # Build initial state for graph invocation
        initial_state = {
            "messages": [],
            "current_event": event_data,
            "event_priority": EventPriority.ROUTINE,
            "context_buffer": self.services.short_memory.get_context_string(),
            "game_state": self.game_context.state,
            "player_histories": {},
            "session": {
                "run_id": None,
                "events_this_run": [],
                "actions_taken": [],
                "last_speech_time": 0,
                "intervention_count": 0
            },
            "current_mask": ErisMask.TRICKSTER,
            "mask_stability": self.config.eris.mask_stability,
            "mood": "neutral",
            "should_speak": False,
            "should_intervene": False,
            "intervention_type": None,
            "planned_actions": [],
            "timestamp": 0.0,
        }

        # Invoke the graph with timeout
        try:
            logger.info(f"Processing event: {event_type}")

            result = await asyncio.wait_for(
                self.services.graph.ainvoke(initial_state),
                timeout=self.config.graph.invoke_timeout
            )

            logger.info(f"Graph completed for: {event_type}")

            # Track intervention time if Eris spoke or intervened
            if result.get("should_speak") or result.get("should_intervene"):
                self.game_context.last_intervention_time = asyncio.get_event_loop().time()

        except asyncio.TimeoutError:
            logger.error(f"Graph timeout after {self.config.graph.invoke_timeout}s for: {event_type}")
        except Exception as e:
            logger.error(f"Graph error: {e}", exc_info=True)
