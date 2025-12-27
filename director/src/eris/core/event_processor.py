"""Event processing with priority queue and debouncing."""

import asyncio
import heapq
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..graph.state import EventPriority
from ..validation.advancement_graph import find_missing_prerequisites, is_valid_progression

logger = logging.getLogger(__name__)


@dataclass(order=True)
class PrioritizedEvent:
    """Event with priority for heap queue."""

    priority: int
    timestamp: float
    event: dict[str, Any] = field(compare=False)


class EventProcessor:
    """
    Manages event queue with priority and debouncing.
    Prevents GPU saturation while ensuring responsive chat.
    """

    # Default debounce settings (seconds)
    DEFAULT_DEBOUNCE = {
        "state": 15.0,
        "player_damaged": 5.0,
        "resource_milestone": 3.0,
        "mob_kills_batch": 0,  # Already batched on Java side
        "advancement_made": 2.0,
        "eris_close_call": 10.0,  # Prevent spam from DOT effects (poison/wither)
    }

    def __init__(self, config: dict[str, float] | None = None):
        """Initialize event processor.

        Args:
            config: Optional debounce settings dict. Keys are event types,
                   values are debounce times in seconds. Merges with defaults.
        """
        self.event_queue: list[PrioritizedEvent] = []
        self.chat_buffer: deque = deque(maxlen=50)
        self.last_process_time: dict[str, float] = {}

        # Merge config with defaults
        self.debounce = self.DEFAULT_DEBOUNCE.copy()
        if config:
            self.debounce.update(config)

        # Processing lock
        self._processing = False
        self._lock = asyncio.Lock()

        # Advancement progression tracking per player (player_uuid -> list of advancements)
        self.advancement_history: dict[str, list[str]] = {}

    async def add_event(self, event: dict) -> bool:
        """Add event to queue. Returns True if event was queued."""
        event_type = event.get("eventType", "")
        now = datetime.now().timestamp()

        # Fast path for chat - always queue immediately
        if event_type == "player_chat":
            self._add_to_chat_buffer(event)
            heapq.heappush(
                self.event_queue,
                PrioritizedEvent(priority=EventPriority.HIGH.value, timestamp=now, event=event),
            )
            logger.debug(f"💬 Chat event queued from {event.get('data', {}).get('player')}")
            return True

        # Check debounce for other events
        debounce_time = self.debounce.get(event_type, 0)
        last_time = self.last_process_time.get(event_type, 0)

        if now - last_time < debounce_time:
            logger.debug(f"⏭️  Skipped {event_type} (debounced)")
            return False  # Skip - too soon

        # Assign priority
        priority = self._get_priority(event)

        heapq.heappush(
            self.event_queue,
            PrioritizedEvent(priority=priority.value, timestamp=now, event=event),
        )

        self.last_process_time[event_type] = now
        logger.debug(f"📥 Event queued: {event_type} (priority: {priority.name})")

        # Track advancement progression for validation
        if event_type == "advancement_made":
            self.track_advancement(event)

        return True

    async def get_next_event(self) -> dict | None:
        """Get highest priority event from queue."""
        async with self._lock:
            if not self.event_queue:
                return None
            prioritized = heapq.heappop(self.event_queue)
            return prioritized.event

    def _add_to_chat_buffer(self, event: dict):
        """Add chat event to rolling buffer."""
        self.chat_buffer.append(event)

    def get_chat_context(self) -> str:
        """Get rolling chat buffer as context string."""
        lines = []
        for event in self.chat_buffer:
            data = event.get("data", {})
            player = data.get("player", "Unknown")
            message = data.get("message", "")
            lines.append(f"{player}: {message}")
        return "\n".join(lines)

    def _get_priority(self, event: dict) -> EventPriority:
        """Determine event priority."""
        event_type = event.get("eventType", "")

        priority_map = {
            # Critical - run-ending or major milestone events
            "player_death": EventPriority.CRITICAL,
            "dragon_killed": EventPriority.CRITICAL,
            "boss_killed": EventPriority.CRITICAL,  # Wither, Elder Guardian, Warden
            # Critical - protection system events (need immediate response)
            "eris_caused_death": EventPriority.CRITICAL,  # Player killed by Eris - 500ms to respond!
            "eris_close_call": EventPriority.CRITICAL,  # Player nearly killed by Eris
            # High - player interactions and significant progress
            "player_chat": EventPriority.HIGH,
            "player_damaged": EventPriority.HIGH,
            "structure_discovered": EventPriority.HIGH,  # Stronghold, Fortress, etc.
            # Medium - progression events
            "dimension_change": EventPriority.MEDIUM,
            "player_dimension_change": EventPriority.MEDIUM,
            "resource_milestone": EventPriority.MEDIUM,
            "advancement_made": EventPriority.MEDIUM,  # Vanilla Minecraft advancements
            "achievement_unlocked": EventPriority.MEDIUM,  # DragonRun achievements
            "run_started": EventPriority.MEDIUM,
            "run_ended": EventPriority.MEDIUM,
            "run_starting": EventPriority.MEDIUM,
            "eris_protection_used": EventPriority.MEDIUM,  # Protection was activated
            "eris_respawn_override": EventPriority.MEDIUM,  # Respawn was used
            # Low - batched/aggregate data
            "mob_kills_batch": EventPriority.LOW,  # Aggregated kill data
            "state": EventPriority.LOW,
        }

        priority = priority_map.get(event_type, EventPriority.ROUTINE)

        # Upgrade priority for close calls
        if event_type == "player_damaged":
            if event.get("data", {}).get("isCloseCall"):
                priority = EventPriority.HIGH

        return priority

    def get_queue_size(self) -> int:
        """Get current queue size."""
        return len(self.event_queue)

    def track_advancement(self, event: dict) -> None:
        """Track and validate advancement progression.

        Logs a warning if an advancement is received out of order
        (i.e., without its prerequisite being obtained first).

        Args:
            event: The advancement_made event dict with eventType and data.
        """
        data = event.get("data", {})
        player_uuid = data.get("playerUuid", "unknown")
        advancement = data.get("advancementKey", "")
        player_name = data.get("player", "Unknown")

        if not advancement:
            return

        if player_uuid not in self.advancement_history:
            self.advancement_history[player_uuid] = []

        history = self.advancement_history[player_uuid]
        test_path = [*history, advancement]

        if not is_valid_progression(test_path):
            missing = find_missing_prerequisites(test_path)
            missing_prereq = missing.get(advancement, "unknown")
            logger.warning(
                f"Progression anomaly for {player_name}: "
                f"got '{advancement}' without prerequisite '{missing_prereq}'"
            )

        history.append(advancement)

    def reset_advancement_history(self) -> None:
        """Clear advancement history for all players.

        Should be called when a run ends/resets.
        """
        self.advancement_history.clear()
        logger.debug("Advancement history cleared")
