#!/usr/bin/env python3
"""Eris AI Director - Main entry point."""

import asyncio
import logging
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Setup paths
BASE_DIR = Path(__file__).parent.parent
SRC_DIR = BASE_DIR / "src"
sys.path.insert(0, str(BASE_DIR))

load_dotenv(BASE_DIR / ".env")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("eris")


async def load_config() -> dict:
    """Load configuration from YAML."""
    config_path = BASE_DIR / "config.yaml"
    if not config_path.exists():
        logger.warning("config.yaml not found, using defaults")
        return {
            "websocket": {"uri": "ws://localhost:8765"},
            "database": {
                "host": os.getenv("DB_HOST", "localhost"),
                "port": int(os.getenv("DB_PORT", 5432)),
                "database": os.getenv("DB_NAME", "dragonrun"),
                "user": os.getenv("DB_USER", "postgres"),
                "password": os.getenv("DB_PASSWORD", "postgres"),
            },
            "ollama": {
                "host": os.getenv("OLLAMA_HOST", "http://localhost:11434"),
                "model": os.getenv("OLLAMA_MODEL", "ministral-3:14b"),
            },
        }

    with open(config_path) as f:
        return yaml.safe_load(f)


async def main():
    """Main entry point for Eris AI Director."""
    logger.info("🎭 Eris AI Director starting...")

    # Load configuration
    config = await load_config()

    # Import after logging is configured
    from eris.core.websocket import GameStateClient
    from eris.core.database import Database
    from eris.core.event_processor import EventProcessor
    from eris.core.memory import ShortTermMemory, LongTermMemory
    from eris.graph.builder import create_graph
    from langchain_ollama import ChatOllama

    # Initialize components
    logger.info("Initializing components...")

    # Database
    db_config = config["database"]
    db = Database(db_config)
    try:
        await db.connect()
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        # Continue without DB for now

    # LLM
    ollama_config = config["ollama"]
    llm = ChatOllama(
        model=ollama_config["model"],
        base_url=ollama_config["host"],
        temperature=0.7,
        keep_alive="30m",
        num_ctx=32768,
        timeout=30.0,
    )

    # Event processor
    event_processor = EventProcessor({})

    # Memory
    short_memory = ShortTermMemory()
    long_memory = LongTermMemory(db)

    # WebSocket client
    ws_uri = config["websocket"]["uri"]

    # Track current game state
    current_game_state = {}

    async def on_state_update(data: dict):
        """Handle game state updates."""
        nonlocal current_game_state
        # State messages have fields at root level (players, gameState, etc.)
        # NOT nested under a "data" key like events are
        current_game_state = data
        # Log player count for debugging
        players = data.get("players", [])
        player_names = [p.get("username", "?") for p in players]
        logger.debug(f"📊 State update: {len(players)} players online: {player_names}")

    async def on_event(data: dict):
        """Handle game events."""
        # eventType is at root level, data contains the payload
        event_type = data.get("eventType", "unknown")

        # Keep the original structure - nodes expect data nested under "data" key
        event_data = {
            "eventType": event_type,
            "data": data.get("data", {})
        }

        logger.info(f"📬 Event: {event_type}")

        # Add to event processor queue
        queued = await event_processor.add_event(event_data)

        if queued:
            # Add to short-term memory
            short_memory.add_event(event_data)

            # Build initial state for graph invocation
            from eris.graph.state import ErisState, EventPriority, ErisMask

            initial_state = {
                "messages": [],
                "current_event": event_data,
                "event_priority": EventPriority.ROUTINE,
                "context_buffer": short_memory.get_context_string(),
                "game_state": current_game_state,
                "player_histories": {},
                "session": {
                    "run_id": None,
                    "events_this_run": [],
                    "actions_taken": [],
                    "last_speech_time": 0,
                    "intervention_count": 0
                },
                "current_mask": ErisMask.TRICKSTER,
                "mask_stability": 0.7,
                "mood": "neutral",
                "should_speak": False,
                "should_intervene": False,
                "intervention_type": None,
                "planned_actions": [],
                "timestamp": 0.0,
            }

            # Invoke the graph
            try:
                logger.info(f"🧠 Processing event: {event_type}")
                result = await graph.ainvoke(initial_state)
                logger.info(f"✅ Graph completed for: {event_type}")
            except Exception as e:
                logger.error(f"❌ Graph error: {e}", exc_info=True)

    ws_client = GameStateClient(ws_uri, on_state_update, on_event)

    # Build graph
    graph = create_graph(db=db, ws_client=ws_client, llm=llm)

    logger.info("🚀 Eris AI Director ready!")
    logger.info(f"📡 Connecting to game server at {ws_uri}...")

    # Run WebSocket connection
    try:
        await ws_client.connect()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        ws_client.stop()
        if db.pool:
            await db.close()


if __name__ == "__main__":
    asyncio.run(main())
