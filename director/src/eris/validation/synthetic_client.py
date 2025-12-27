"""Synthetic WebSocket client for closed-loop testing.

Replaces GameStateClient with a mock that captures tool calls
and applies them to SyntheticWorld instead of sending to Java.
"""

import logging
import uuid
from typing import Any

from .synthetic_world import SyntheticWorld
from .world_diff import WorldDiff

logger = logging.getLogger(__name__)


class SyntheticGameStateClient:
    """Mock WebSocket client for testing Eris against synthetic scenarios.

    Captures tool calls from Eris and applies them to a SyntheticWorld,
    producing WorldDiffs for telemetry.
    """

    def __init__(self, world: SyntheticWorld):
        """Initialize with a SyntheticWorld.

        Args:
            world: The SyntheticWorld to apply tool calls to
        """
        self.world = world
        self.tool_calls: list[dict[str, Any]] = []
        self.correlation_ids: dict[str, dict[str, Any]] = {}

    async def send_command(self, command: str, args: dict[str, Any]) -> str:
        """Simulate sending a command to the game server.

        Args:
            command: Tool name (e.g., "spawn_mob", "broadcast")
            args: Tool arguments

        Returns:
            Correlation ID for tracking
        """
        correlation_id = str(uuid.uuid4())

        logger.info(f"[SYNTHETIC] Tool call: {command} with args: {args}")

        # Apply tool to synthetic world
        try:
            diff = self.world.apply_tool_call(command, args)

            # Record tool call
            tool_call_record = {
                "correlation_id": correlation_id,
                "command": command,
                "args": args,
                "timestamp": 0.0,  # No time tracking in synthetic world
                "diff": diff,
                "success": True,
            }

            self.tool_calls.append(tool_call_record)
            self.correlation_ids[correlation_id] = tool_call_record

            logger.info(f"[SYNTHETIC] ✓ {command} applied - {len(diff.changes)} state changes")

        except Exception as e:
            logger.error(f"[SYNTHETIC] ✗ {command} failed: {e}")
            tool_call_record = {
                "correlation_id": correlation_id,
                "command": command,
                "args": args,
                "timestamp": 0.0,
                "diff": None,
                "success": False,
                "error": str(e),
            }
            self.tool_calls.append(tool_call_record)
            self.correlation_ids[correlation_id] = tool_call_record

        return correlation_id

    async def connect(self) -> None:
        """Mock connect method (no-op for synthetic client)."""
        logger.info("[SYNTHETIC] Client 'connected' (mock)")

    def stop(self) -> None:
        """Mock stop method (no-op for synthetic client)."""
        logger.info("[SYNTHETIC] Client 'stopped' (mock)")

    def get_tool_calls(self) -> list[dict[str, Any]]:
        """Get all tool calls made during this run.

        Returns:
            List of tool call records with diffs
        """
        return self.tool_calls

    def reset(self) -> None:
        """Reset tool call history."""
        self.tool_calls.clear()
        self.correlation_ids.clear()


# === Tool execution helpers ===


async def execute_tool_on_synthetic_world(
    tool_name: str,
    args: dict[str, Any],
    world: SyntheticWorld,
    client: SyntheticGameStateClient,
) -> WorldDiff | None:
    """Execute a tool call on synthetic world.

    Args:
        tool_name: Name of the tool
        args: Tool arguments
        world: SyntheticWorld instance
        client: SyntheticGameStateClient instance

    Returns:
        WorldDiff from the tool application
    """
    correlation_id = await client.send_command(tool_name, args)
    record = client.correlation_ids.get(correlation_id)

    if record and record.get("success"):
        return record.get("diff")
    else:
        logger.warning(f"Tool {tool_name} failed or not found in correlation map")
        return None
