"""Event processing with priority queue and debouncing."""

import asyncio
import heapq
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

from ..graph.state import EventPriority

logger = logging.getLogger(__name__)


@dataclass(order=True)
class PrioritizedEvent:
    """Event with priority for heap queue."""

    priority: int
    timestamp: float
    event: Dict[str, Any] = field(compare=False)


class EventProcessor:
    """
    Manages event queue with priority and debouncing.
    Prevents GPU saturation while ensuring responsive chat.
    """

    def __init__(self, config: dict):
        self.event_queue: list[PrioritizedEvent] = []
        self.chat_buffer: deque = deque(maxlen=50)  # Last 50 messages
        self.last_process_time: dict[str, float] = {}

        # Debounce settings (seconds)
        self.debounce = {
            "state": 15.0,  # Process state every 15s max
            "player_damaged": 5.0,  # Aggregate damage events
            "resource_milestone": 3.0,
            "mob_kills_batch": 0,  # Already batched on Java side
            "advancement_made": 2.0,  # Allow rapid advancements but slight debounce
        }

        # Processing lock
        self._processing = False
        self._lock = asyncio.Lock()

    async def add_event(self, event: dict) -> bool:
        """Add event to queue. Returns True if event was queued."""
        event_type = event.get("eventType", "")
        now = datetime.now().timestamp()

        # Fast path for chat - always queue immediately
        if event_type == "player_chat":
            self._add_to_chat_buffer(event)
            heapq.heappush(
                self.event_queue,
                PrioritizedEvent(
                    priority=EventPriority.HIGH.value, timestamp=now, event=event
                ),
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
        return True

    async def get_next_event(self) -> Optional[dict]:
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
