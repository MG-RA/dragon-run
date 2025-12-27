"""Synthetic event processor for closed-loop testing.

Replaces WebSocket connection with scenario-driven events.
Converts Scenario events to Eris graph-compatible event dictionaries.
"""

import logging
from typing import Any

from .scenario_schema import (
    AdvancementEvent,
    ChatEvent,
    DamageEvent,
    DeathEvent,
    DimensionChangeEvent,
    DragonKillEvent,
    Event,
    HealthChangeEvent,
    InventoryEvent,
    MobKillEvent,
    Scenario,
    StructureDiscoveryEvent,
)

logger = logging.getLogger(__name__)


class SyntheticEventProcessor:
    """Converts scenario events to Eris-compatible event dictionaries.

    This processor takes events from a Scenario YAML and transforms them
    into the same format that the WebSocket would send, allowing Eris
    to process synthetic scenarios as if they were real gameplay.
    """

    def __init__(self, scenario: Scenario):
        """Initialize with a scenario.

        Args:
            scenario: Loaded and validated Scenario object
        """
        self.scenario = scenario
        self.event_index = 0

    def reset(self) -> None:
        """Reset to beginning of scenario."""
        self.event_index = 0

    def has_more_events(self) -> bool:
        """Check if there are more events to process."""
        return self.event_index < len(self.scenario.events)

    def get_next_event(self) -> dict[str, Any] | None:
        """Get next event in Eris-compatible format.

        Returns:
            Event dict ready for LangGraph processing, or None if no more events
        """
        if not self.has_more_events():
            return None

        event = self.scenario.events[self.event_index]
        self.event_index += 1

        return self._convert_event(event)

    def _convert_event(self, event: Event) -> dict[str, Any]:
        """Convert a Scenario event to Eris event format.

        Args:
            event: Scenario event (AdvancementEvent, DamageEvent, etc.)

        Returns:
            Event dict matching WebSocket format
        """
        event_type = event.type

        # Map scenario event types to Eris event types
        if event_type == "advancement":
            return self._convert_advancement(event)
        elif event_type == "damage":
            return self._convert_damage(event)
        elif event_type == "inventory":
            return self._convert_inventory(event)
        elif event_type == "dimension":
            return self._convert_dimension(event)
        elif event_type == "chat":
            return self._convert_chat(event)
        elif event_type == "death":
            return self._convert_death(event)
        elif event_type == "dragon_kill":
            return self._convert_dragon_kill(event)
        elif event_type == "mob_kill":
            return self._convert_mob_kill(event)
        elif event_type == "structure":
            return self._convert_structure(event)
        elif event_type == "health":
            return self._convert_health(event)
        else:
            logger.warning(f"Unknown event type: {event_type}")
            return {"eventType": "unknown", "data": {}}

    def _convert_advancement(self, event: AdvancementEvent) -> dict[str, Any]:
        """Convert advancement event."""
        return {
            "eventType": "advancement_made",
            "data": {
                "player": event.player,
                "playerUuid": f"synthetic-{event.player}",  # Synthetic UUID
                "advancementKey": event.advancement,
                "isCritical": self._is_critical_advancement(event.advancement),
            }
        }

    def _convert_damage(self, event: DamageEvent) -> dict[str, Any]:
        """Convert damage event."""
        # Estimate final health (we don't track it in DamageEvent schema)
        estimated_final_health = max(0, 20.0 - event.amount)
        return {
            "eventType": "player_damaged",
            "data": {
                "player": event.player,
                "playerUuid": f"synthetic-{event.player}",
                "source": event.source,
                "amount": event.amount,
                "finalHealth": estimated_final_health,
                "isCloseCall": estimated_final_health <= 6.0,
            }
        }

    def _convert_inventory(self, event: InventoryEvent) -> dict[str, Any]:
        """Convert inventory event - map to resource_milestone if significant."""
        # Check if this is a significant milestone item
        milestone_items = {
            "diamond", "blaze_rod", "ender_pearl", "iron_ingot",
            "obsidian", "ender_eye", "netherite_ingot"
        }

        item_name = event.item.lower()
        is_milestone = any(milestone in item_name for milestone in milestone_items)

        if is_milestone and event.action == "add":
            return {
                "eventType": "resource_milestone",
                "data": {
                    "player": event.player,
                    "playerUuid": f"synthetic-{event.player}",
                    "resource": event.item,
                    "count": event.count,
                }
            }
        else:
            # Generic item event (lower priority, may be ignored)
            return {
                "eventType": "item_collected",
                "data": {
                    "player": event.player,
                    "item": event.item,
                    "count": event.count,
                    "operation": event.action,
                }
            }

    def _convert_dimension(self, event: DimensionChangeEvent) -> dict[str, Any]:
        """Convert dimension change event."""
        return {
            "eventType": "dimension_change",
            "data": {
                "player": event.player,
                "playerUuid": f"synthetic-{event.player}",
                "from": event.from_dim,
                "to": event.to_dim,
            }
        }

    def _convert_chat(self, event: ChatEvent) -> dict[str, Any]:
        """Convert chat event."""
        return {
            "eventType": "player_chat",
            "data": {
                "player": event.player,
                "playerUuid": f"synthetic-{event.player}",
                "message": event.message,
            }
        }

    def _convert_death(self, event: DeathEvent) -> dict[str, Any]:
        """Convert death event."""
        return {
            "eventType": "player_death",
            "data": {
                "player": event.player,
                "playerUuid": f"synthetic-{event.player}",
                "cause": event.cause,
            }
        }

    def _convert_dragon_kill(self, event: DragonKillEvent) -> dict[str, Any]:
        """Convert dragon kill event."""
        return {
            "eventType": "dragon_killed",
            "data": {
                "player": event.player,
                "playerUuid": f"synthetic-{event.player}",
            }
        }

    def _convert_mob_kill(self, event: MobKillEvent) -> dict[str, Any]:
        """Convert mob kill event."""
        return {
            "eventType": "mob_kills_batch",
            "data": {
                "player": event.player,
                "playerUuid": f"synthetic-{event.player}",
                "mobType": event.mob_type,
                "count": event.count,
            }
        }

    def _convert_structure(self, event: StructureDiscoveryEvent) -> dict[str, Any]:
        """Convert structure discovery event."""
        return {
            "eventType": "structure_discovered",
            "data": {
                "player": event.player,
                "playerUuid": f"synthetic-{event.player}",
                "structure": event.structure,
            }
        }

    def _convert_health(self, event: HealthChangeEvent) -> dict[str, Any]:
        """Convert health change event.

        If amount > 0, treat as healing (ignore for now, no direct Eris event).
        If amount < 0, treat as damage without source.
        """
        if event.amount < 0:
            return {
                "eventType": "player_damaged",
                "data": {
                    "player": event.player,
                    "playerUuid": f"synthetic-{event.player}",
                    "source": event.source or "unknown",
                    "amount": abs(event.amount),
                    "finalHealth": event.final_health if event.final_health is not None else 20.0,
                    "isCloseCall": (event.final_health or 20.0) <= 6.0,
                }
            }
        else:
            # Healing - no direct event, just log
            logger.debug(f"{event.player} healed {event.amount} HP")
            return {
                "eventType": "player_healed",  # Not a standard Eris event, may be ignored
                "data": {
                    "player": event.player,
                    "amount": event.amount,
                }
            }

    def _is_critical_advancement(self, advancement: str) -> bool:
        """Check if advancement is critical (speedrun-relevant)."""
        critical = {
            "minecraft:story/form_obsidian",
            "minecraft:story/enter_the_nether",
            "minecraft:nether/find_fortress",
            "minecraft:nether/obtain_blaze_rod",
            "minecraft:story/follow_ender_eye",
            "minecraft:story/enter_the_end",
        }
        return advancement in critical
