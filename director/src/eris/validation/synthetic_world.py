"""
SyntheticWorld - Deterministic Minecraft simulation for testing Eris.

Simulates Minecraft state evolution based on scenario events and Eris tool calls.
Mirrors GameSnapshot and PlayerStateSnapshot from the Java plugin.
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .player_state import ActiveEffect, Dimension, PlayerState, SpawnedMob
from .scenario_schema import (
    PARTY_PRESETS,
    AdvancementEvent,
    ChatEvent,
    DamageEvent,
    DeathEvent,
    DimensionChangeEvent,
    DragonKillEvent,
    Event,
    HealthChangeEvent,
    InventoryEvent,
    ItemCraftedEvent,
    MobKillEvent,
    PartyPreset,
    PlayerDefinition,
    PortalPlacedEvent,
    Scenario,
    StructureDiscoveryEvent,
)
from .tarot import TarotCard, TarotProfile, get_drift_for_event
from .world_diff import RunTrace, WorldDiff

logger = logging.getLogger(__name__)


# ==================== WORLD ARCANA ====================


class WorldArcana(str, Enum):
    """
    The nine-stage initiation rite of a Minecraft run.

    Each stage is a Tarot threshold that changes what is possible.
    Eris treats these as cosmic law, not game mechanics.

    The progression is irreversible - once a threshold is crossed,
    the world is permanently changed. Who crossed it matters.
    """

    # Stage 0: The world is innocent. Nothing irreversible has happened.
    THE_FOOL = "the_fool"

    # Stage 1: Someone changed reality. There is now an inside and an outside.
    THE_GATE = "the_gate"  # Nether portal placed (Fool → Magician)

    # Stage 2: Order is broken. Hell is mapped.
    THE_TOWER = "the_tower"  # Fortress found

    # Stage 3: Power from suffering enters the economy.
    THE_DEVIL = "the_devil"  # Blaze rods exist

    # Stage 4: Teleportation, deception, escape, dream-logic.
    THE_MOON = "the_moon"  # Ender pearls exist

    # Stage 5: The world can now know where it must go.
    THE_SEER = "the_seer"  # Eyes of Ender crafted

    # Stage 6: A hidden sacred place revealed.
    THE_HERMIT = "the_hermit"  # Stronghold found

    # Stage 7: No more grinding. The final reckoning is armed.
    JUDGMENT = "judgment"  # End portal activated

    # Stage 8: The false god rules. Reality is unfinished.
    THE_WORLD_INVERTED = "the_world_inverted"  # Dragon alive, in the End

    # Stage 9: The rite completes. The cosmos stabilizes.
    THE_WORLD = "the_world"  # Dragon dead


# Arcana progression order (each stage requires all previous)
ARCANA_ORDER = [
    WorldArcana.THE_FOOL,
    WorldArcana.THE_GATE,
    WorldArcana.THE_TOWER,
    WorldArcana.THE_DEVIL,
    WorldArcana.THE_MOON,
    WorldArcana.THE_SEER,
    WorldArcana.THE_HERMIT,
    WorldArcana.JUDGMENT,
    WorldArcana.THE_WORLD_INVERTED,
    WorldArcana.THE_WORLD,
]


# ==================== WORLD CAPABILITIES ====================


@dataclass
class ArcanaTransition:
    """Records who crossed an arcana threshold and when."""

    arcana: WorldArcana
    player: str
    timestamp: float


@dataclass
class CapabilityContribution:
    """Records who unlocked a capability and when."""

    capability: str
    player: str
    timestamp: float


@dataclass
class WorldCapabilities:
    """
    Shared team capabilities - what the party can now do.

    This tracks WORLD state, not individual player state.
    Alice builds portal → Bob can use it.
    Charlie finds fortress → everyone can farm blazes.

    Used for:
    - Gating intents (can't ENTER_DANGER if no portal)
    - Validating scenario events
    - Psychology (who created vs who exploited)
    """

    # Portal/dimension access
    nether_portal_placed: bool = False
    end_portal_activated: bool = False

    # Structure progress
    fortress_found: bool = False
    stronghold_found: bool = False
    bastion_found: bool = False

    # Resource counts (team-wide totals)
    blaze_rods: int = 0
    ender_pearls: int = 0
    eyes_of_ender: int = 0
    obsidian: int = 0  # Need 10 for portal frame

    # Portal materials
    has_flint_and_steel: bool = False  # Required to light portal

    # Combat readiness
    has_beds: bool = False
    has_bows: bool = False
    has_iron_armor: bool = False
    has_diamond_gear: bool = False

    # Tool progression
    has_iron_pickaxe: bool = False
    has_diamond_pickaxe: bool = False
    has_bucket: bool = False

    # Contribution tracking - WHO unlocked each capability
    contributions: list[CapabilityContribution] = field(default_factory=list)

    # Arcana tracking - WHO crossed each threshold
    arcana_transitions: list[ArcanaTransition] = field(default_factory=list)

    # Dragon state (needed for World arcana)
    dragon_dead: bool = False
    anyone_in_end: bool = False

    # ==================== WORLD ARCANA ====================

    @property
    def current_arcana(self) -> WorldArcana:
        """
        Determine the current World Arcana based on capabilities.

        This is the highest threshold that has been crossed.
        The world cannot skip stages - each requires the previous.
        """
        # Stage 9: Dragon dead - The World (upright)
        if self.dragon_dead:
            return WorldArcana.THE_WORLD

        # Stage 8: In the End with dragon alive - The World (inverted)
        if self.anyone_in_end and self.end_portal_activated:
            return WorldArcana.THE_WORLD_INVERTED

        # Stage 7: End portal activated - Judgment
        if self.end_portal_activated:
            return WorldArcana.JUDGMENT

        # Stage 6: Stronghold found - The Hermit
        if self.stronghold_found:
            return WorldArcana.THE_HERMIT

        # Stage 5: Eyes of Ender exist - The Seer
        if self.eyes_of_ender > 0:
            return WorldArcana.THE_SEER

        # Stage 4: Ender pearls exist - The Moon
        if self.ender_pearls > 0:
            return WorldArcana.THE_MOON

        # Stage 3: Blaze rods exist - The Devil
        if self.blaze_rods > 0:
            return WorldArcana.THE_DEVIL

        # Stage 2: Fortress found - The Tower
        if self.fortress_found:
            return WorldArcana.THE_TOWER

        # Stage 1: Nether portal placed - The Gate
        if self.nether_portal_placed:
            return WorldArcana.THE_GATE

        # Stage 0: Nothing has happened - The Fool
        return WorldArcana.THE_FOOL

    @property
    def arcana_stage(self) -> int:
        """Get the numeric stage (0-9) of the current arcana."""
        return ARCANA_ORDER.index(self.current_arcana)

    def cross_threshold(self, arcana: WorldArcana, player: str) -> bool:
        """
        Record that a player crossed an arcana threshold.

        Returns True if this was a new threshold, False if already crossed.
        """
        # Check if already crossed
        if any(t.arcana == arcana for t in self.arcana_transitions):
            return False

        self.arcana_transitions.append(
            ArcanaTransition(
                arcana=arcana,
                player=player,
                timestamp=time.time(),
            )
        )
        logger.info(f"[ARCANA] {player} crossed threshold: {arcana.value}")
        return True

    def get_threshold_crosser(self, arcana: WorldArcana) -> str | None:
        """Get who crossed a specific arcana threshold."""
        for t in self.arcana_transitions:
            if t.arcana == arcana:
                return t.player
        return None

    def get_arcana_history(self) -> list[tuple[WorldArcana, str]]:
        """Get the sequence of arcana transitions and who triggered them."""
        return [(t.arcana, t.player) for t in self.arcana_transitions]

    # ==================== DERIVED CAPABILITIES ====================

    @property
    def can_mine_obsidian(self) -> bool:
        """Need diamond pickaxe to mine obsidian for portal."""
        return self.has_diamond_pickaxe

    @property
    def can_build_portal(self) -> bool:
        """Need obsidian source (bucket for lava cast OR diamond pick to mine) AND flint_and_steel to light."""
        has_obsidian_source = self.has_bucket or self.has_diamond_pickaxe or self.obsidian >= 10
        return has_obsidian_source and self.has_flint_and_steel

    @property
    def can_enter_nether(self) -> bool:
        """Portal must exist for anyone to enter."""
        return self.nether_portal_placed

    @property
    def can_farm_blazes(self) -> bool:
        """Need nether access AND fortress found."""
        return self.can_enter_nether and self.fortress_found

    @property
    def can_obtain_blaze_rods(self) -> bool:
        """Same as can_farm_blazes."""
        return self.can_farm_blazes

    @property
    def can_craft_eyes(self) -> bool:
        """Need blaze powder (from rods) AND ender pearls."""
        return self.blaze_rods > 0 and self.ender_pearls > 0

    @property
    def can_locate_stronghold(self) -> bool:
        """Need at least one eye of ender."""
        return self.eyes_of_ender > 0

    @property
    def can_enter_end(self) -> bool:
        """Need stronghold found AND portal activated."""
        return self.stronghold_found and self.end_portal_activated

    @property
    def can_fight_dragon(self) -> bool:
        """Need end access AND combat capability (beds or bows)."""
        return self.can_enter_end and (self.has_beds or self.has_bows)

    @property
    def dragon_killable(self) -> bool:
        """More lenient - just need to be in the End."""
        return self.can_enter_end

    # ==================== CAPABILITY TRACKING ====================

    def unlock(self, capability: str, player: str) -> None:
        """Record that a player unlocked this capability."""
        self.contributions.append(
            CapabilityContribution(
                capability=capability,
                player=player,
                timestamp=time.time(),
            )
        )
        logger.debug(f"[CAP] {player} unlocked: {capability}")

    def get_contributor(self, capability: str) -> str | None:
        """Get the player who first unlocked a capability."""
        for contrib in self.contributions:
            if contrib.capability == capability:
                return contrib.player
        return None

    def get_all_contributions_by_player(self, player: str) -> list[str]:
        """Get all capabilities unlocked by a player."""
        return [c.capability for c in self.contributions if c.player == player]

    def get_exploiters(self, capability: str, users: list[str]) -> list[str]:
        """Get players who used a capability they didn't unlock."""
        creator = self.get_contributor(capability)
        if not creator:
            return []
        return [p for p in users if p != creator]

    # ==================== STATE SUMMARY ====================

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for logging/snapshots."""
        return {
            "nether_portal_placed": self.nether_portal_placed,
            "end_portal_activated": self.end_portal_activated,
            "fortress_found": self.fortress_found,
            "stronghold_found": self.stronghold_found,
            "bastion_found": self.bastion_found,
            "blaze_rods": self.blaze_rods,
            "ender_pearls": self.ender_pearls,
            "eyes_of_ender": self.eyes_of_ender,
            "obsidian": self.obsidian,
            "has_flint_and_steel": self.has_flint_and_steel,
            "has_beds": self.has_beds,
            "has_bows": self.has_bows,
            "has_iron_armor": self.has_iron_armor,
            "has_diamond_gear": self.has_diamond_gear,
            "has_iron_pickaxe": self.has_iron_pickaxe,
            "has_diamond_pickaxe": self.has_diamond_pickaxe,
            "has_bucket": self.has_bucket,
            # Derived
            "can_build_portal": self.can_build_portal,
            "can_enter_nether": self.can_enter_nether,
            "can_farm_blazes": self.can_farm_blazes,
            "can_craft_eyes": self.can_craft_eyes,
            "can_enter_end": self.can_enter_end,
            "can_fight_dragon": self.can_fight_dragon,
            # Contributors
            "contributors": [
                {"capability": c.capability, "player": c.player}
                for c in self.contributions
            ],
            # World Arcana - the initiation rite
            "current_arcana": self.current_arcana.value,
            "arcana_stage": self.arcana_stage,
            "arcana_history": [
                {"arcana": t.arcana.value, "player": t.player}
                for t in self.arcana_transitions
            ],
        }


class GameState(str, Enum):
    """Run lifecycle states (mirrors Java RunManager)."""

    IDLE = "IDLE"
    ACTIVE = "ACTIVE"
    ENDING = "ENDING"
    ENDED = "ENDED"


class Phase(str, Enum):
    """Fracture-driven phase states."""

    NORMAL = "normal"
    RISING = "rising"
    CRITICAL = "critical"
    BREAKING = "breaking"
    APOCALYPSE = "apocalypse"


# Phase thresholds (fracture level -> phase)
PHASE_THRESHOLDS = {
    0: Phase.NORMAL,
    50: Phase.RISING,
    80: Phase.CRITICAL,
    120: Phase.BREAKING,
    150: Phase.APOCALYPSE,
}


@dataclass
class SyntheticWorld:
    """
    Deterministic Minecraft simulation for testing Eris.

    Maintains all game state and provides methods to:
    - Load from a Scenario
    - Apply events from the scenario
    - Apply tool calls from Eris
    - Generate GameSnapshot-compatible dicts for Eris
    """

    # ==================== CORE STATE ====================

    # Players (mirrors PlayerStateSnapshot collection)
    players: dict[str, PlayerState] = field(default_factory=dict)

    # Game state (mirrors GameSnapshot)
    game_state: GameState = GameState.IDLE
    run_id: int = 1
    run_start_time: float = field(default_factory=time.time)

    # Dragon state
    dragon_alive: bool = True
    dragon_health: float = 200.0  # Dragon has 200 HP
    dragon_killer: str | None = None

    # World state
    world_name: str = "dragonrun_world"
    world_seed: int = 0
    weather: str = "clear"
    time_of_day: int = 6000  # Noon

    # ==================== WORLD CAPABILITIES ====================

    # Shared team capabilities - gates progression
    capabilities: WorldCapabilities = field(default_factory=WorldCapabilities)

    # ==================== TRACKING ====================

    # Spawned entities
    spawned_mobs: list[SpawnedMob] = field(default_factory=list)

    # Active effects per player
    active_effects: dict[str, list[ActiveEffect]] = field(default_factory=dict)

    # Discovered structures per player
    discovered_structures: dict[str, set[str]] = field(default_factory=dict)

    # ==================== TENSION/FRACTURE ====================

    # Tension builds from events
    tension: float = 0.0

    # Fracture = accumulated karma + tension
    fracture: float = 0.0
    phase: Phase = Phase.NORMAL
    apocalypse_triggered: bool = False

    # Per-player fear (0-100)
    player_fear: dict[str, float] = field(default_factory=dict)

    # Global chaos level
    global_chaos: float = 0.0

    # ==================== HISTORY ====================

    # Event log for context
    event_history: list[Event] = field(default_factory=list)

    # Tool call log
    tool_history: list[dict] = field(default_factory=list)

    # Full trace for scoring
    trace: RunTrace | None = None

    # Sequence counter
    _sequence: int = 0

    # ==================== TAROT (PHASE 6) ====================

    # Player tarot profiles (for emergent scenarios)
    player_tarot: dict[str, TarotProfile] = field(default_factory=dict)

    # ==================== FACTORY METHODS ====================

    @classmethod
    def from_scenario(cls, scenario: Scenario) -> "SyntheticWorld":
        """
        Create a SyntheticWorld initialized from a Scenario.

        Expands party presets and sets up initial player states.
        """
        world = cls()
        world.trace = RunTrace(scenario_name=scenario.metadata.name)

        # Expand party preset if needed
        party: dict[str, PlayerDefinition]
        if isinstance(scenario.party, PartyPreset):
            party = PARTY_PRESETS[scenario.party]
        elif isinstance(scenario.party, str):
            # String that matches a preset name
            preset = PartyPreset(scenario.party)
            party = PARTY_PRESETS[preset]
        else:
            party = scenario.party

        # Initialize players
        for name, definition in party.items():
            player = PlayerState(
                name=name,
                role=definition.role,
                health=float(definition.starting_health),
                max_health=20.0,
            )

            # Add starting inventory
            for item, count in definition.starting_inventory.items():
                player.add_item(item, count)

            world.players[name] = player
            world.player_fear[name] = 0.0
            world.active_effects[name] = []
            world.discovered_structures[name] = set()

            # Initialize tarot profile (starts neutral)
            world.player_tarot[name] = TarotProfile()

        # Start the run
        world.game_state = GameState.ACTIVE

        return world

    def initialize_tarot(self, initial_weights: dict[str, dict[str, float]]) -> None:
        """
        Initialize tarot weights from scenario definition.

        Args:
            initial_weights: player_name -> {card_name: weight}
        """
        for player_name, weights in initial_weights.items():
            if player_name in self.player_tarot:
                self.player_tarot[player_name] = TarotProfile.from_initial_weights(weights)

    # ==================== EVENT APPLICATION ====================

    def apply_event(self, event: Event) -> WorldDiff:
        """
        Apply a scenario event and return the state diff.

        Dispatches to specific handlers based on event type.
        """
        self._sequence += 1

        # Create diff
        diff = WorldDiff(
            source_type="event",
            source_name=event.type,
            player=getattr(event, "player", None),
            timestamp=time.time(),
            sequence_number=self._sequence,
        )

        # Dispatch to handler
        handler = self._get_event_handler(event.type)
        if handler:
            handler(event, diff)

        # Update tension/fracture
        old_phase = self.phase
        self._update_tension_from_event(event)
        self._update_phase()

        if self.phase != old_phase:
            diff.triggered_phase_change = True
            diff.old_phase = old_phase.value
            diff.new_phase = self.phase.value

        # Update tarot based on event (Phase 6)
        self._drift_tarot_from_event(event)

        # Log event
        self.event_history.append(event)

        # Add to trace
        if self.trace:
            self.trace.add_diff(diff)

        return diff

    def _get_event_handler(self, event_type: str):
        """Get the handler method for an event type."""
        handlers = {
            "advancement": self._handle_advancement,
            "damage": self._handle_damage,
            "inventory": self._handle_inventory,
            "dimension": self._handle_dimension,
            "chat": self._handle_chat,
            "death": self._handle_death,
            "dragon_kill": self._handle_dragon_kill,
            "mob_kill": self._handle_mob_kill,
            "structure": self._handle_structure,
            "health": self._handle_health,
            "portal_placed": self._handle_portal_event,
            "item_crafted": self._handle_item_crafted,
        }
        return handlers.get(event_type)

    def _handle_advancement(self, event: AdvancementEvent, diff: WorldDiff) -> None:
        """Player earns an advancement."""
        player = self.players.get(event.player)
        if not player or not player.alive:
            return

        old_count = len(player.advancements)
        player.add_advancement(event.advancement)
        diff.add_player_change(
            event.player, "advancements", old_count, len(player.advancements)
        )

    def _handle_damage(self, event: DamageEvent, diff: WorldDiff) -> None:
        """Player takes damage."""
        player = self.players.get(event.player)
        if not player or not player.alive:
            return

        old_health = player.health
        died = player.take_damage(event.amount)

        diff.add_player_change(event.player, "health", old_health, player.health)

        # Increase fear
        old_fear = self.player_fear.get(event.player, 0)
        new_fear = min(100, old_fear + event.amount * 2)
        self.player_fear[event.player] = new_fear
        diff.add_player_change(event.player, "fear", old_fear, new_fear)

        if died:
            diff.caused_death = True
            diff.add_player_change(event.player, "alive", True, False)
            self.game_state = GameState.ENDING

    def _handle_inventory(self, event: InventoryEvent, diff: WorldDiff) -> None:
        """Player inventory changes."""
        player = self.players.get(event.player)
        if not player or not player.alive:
            return

        old_count = player.inventory.get(event.item, 0)

        if event.action == "add":
            player.add_item(event.item, event.count)
        else:
            player.remove_item(event.item, event.count)

        new_count = player.inventory.get(event.item, 0)
        diff.add_player_change(
            event.player, f"inventory.{event.item}", old_count, new_count
        )

        # Update world capabilities based on item change
        if event.action == "add":
            self._update_capabilities_from_item(event.player, event.item, event.count)
        elif event.action == "remove":
            self._decrement_capabilities_from_item(event.item, event.count)

    def _handle_dimension(self, event: DimensionChangeEvent, diff: WorldDiff) -> None:
        """Player changes dimension."""
        player = self.players.get(event.player)
        if not player or not player.alive:
            return

        old_dim = player.dimension.value

        # Parse dimension
        to_dim = event.to_dim.lower().replace(" ", "_")
        if to_dim in ("the_end", "end"):
            player.change_dimension(Dimension.THE_END)
        elif to_dim == "nether":
            player.change_dimension(Dimension.NETHER)
        else:
            player.change_dimension(Dimension.OVERWORLD)

        diff.add_player_change(event.player, "dimension", old_dim, player.dimension.value)

        if player.dimension == Dimension.NETHER and not player.entered_nether:
            diff.add_player_change(event.player, "entered_nether", False, True)
        if player.dimension == Dimension.THE_END and not player.entered_end:
            diff.add_player_change(event.player, "entered_end", False, True)
            # ARCANA: The World (Inverted) - the false god rules, reality is unfinished
            caps = self.capabilities
            if not caps.anyone_in_end:
                caps.anyone_in_end = True
                caps.cross_threshold(WorldArcana.THE_WORLD_INVERTED, event.player)

    def _handle_chat(self, event: ChatEvent, diff: WorldDiff) -> None:
        """Player sends chat message. No state change, just logging."""
        # Chat is logged but doesn't change state
        pass

    def _handle_death(self, event: DeathEvent, diff: WorldDiff) -> None:
        """Player dies - run ends."""
        player = self.players.get(event.player)
        if not player:
            return

        if player.alive:
            player.alive = False
            player.health = 0
            diff.add_player_change(event.player, "alive", True, False)
            diff.add_player_change(event.player, "health", player.health, 0)
            diff.caused_death = True

        self.game_state = GameState.ENDING

    def _handle_dragon_kill(self, event: DragonKillEvent, diff: WorldDiff) -> None:
        """Dragon is killed - victory!"""
        old_dragon_alive = self.dragon_alive
        self.dragon_alive = False
        self.dragon_health = 0
        self.dragon_killer = event.player

        diff.add_change("dragon_alive", old_dragon_alive, False)
        diff.add_change("dragon_health", 200.0, 0)
        diff.caused_victory = True

        # ARCANA: The World (Upright) - the rite completes, the cosmos stabilizes
        caps = self.capabilities
        caps.dragon_dead = True
        caps.cross_threshold(WorldArcana.THE_WORLD, event.player)

        self.game_state = GameState.ENDING

    def _handle_mob_kill(self, event: MobKillEvent, diff: WorldDiff) -> None:
        """Player kills mobs."""
        player = self.players.get(event.player)
        if not player or not player.alive:
            return

        old_kills = player.mob_kills
        player.mob_kills += event.count
        diff.add_player_change(event.player, "mob_kills", old_kills, player.mob_kills)

        # Check if this kills any spawned mobs
        for mob in self.spawned_mobs:
            if mob.mob_type == event.mob_type and mob.near_player == event.player:
                mob.kill(event.count)

    def _handle_structure(self, event: StructureDiscoveryEvent, diff: WorldDiff) -> None:
        """Player discovers a structure."""
        player = self.players.get(event.player)
        if not player or not player.alive:
            return

        structures = self.discovered_structures.get(event.player, set())
        if event.structure not in structures:
            structures.add(event.structure)
            self.discovered_structures[event.player] = structures
            diff.add_player_change(
                event.player, f"discovered.{event.structure}", False, True
            )

            # Update world capabilities
            self._update_capabilities_from_structure(event.player, event.structure)

    def _handle_health(self, event: HealthChangeEvent, diff: WorldDiff) -> None:
        """Player health changes (healing, regen)."""
        player = self.players.get(event.player)
        if not player or not player.alive:
            return

        old_health = player.health

        if event.amount > 0:
            player.heal(event.amount)
        else:
            # Negative health change is damage without a source
            player.take_damage(-event.amount)

        diff.add_player_change(event.player, "health", old_health, player.health)

        # Reduce fear on healing
        if event.amount > 0:
            old_fear = self.player_fear.get(event.player, 0)
            new_fear = max(0, old_fear - event.amount)
            self.player_fear[event.player] = new_fear
            diff.add_player_change(event.player, "fear", old_fear, new_fear)

    def _handle_portal_event(self, event: PortalPlacedEvent, diff: WorldDiff) -> None:
        """Player places/activates a portal - unlocks dimension access."""
        player = self.players.get(event.player)
        if not player:
            return

        portal_type = event.portal_type
        caps = self.capabilities

        if portal_type == "nether":
            if not caps.nether_portal_placed:
                caps.nether_portal_placed = True
                caps.unlock("nether_portal", event.player)
                diff.add_change("capabilities.nether_portal_placed", False, True)
                # ARCANA: The Gate - reality has an inside and outside now
                caps.cross_threshold(WorldArcana.THE_GATE, event.player)
                logger.info(f"[WORLD] {event.player} placed nether portal - THE GATE opens")

        elif portal_type == "end":
            if not caps.end_portal_activated:
                caps.end_portal_activated = True
                caps.unlock("end_portal", event.player)
                diff.add_change("capabilities.end_portal_activated", False, True)
                # ARCANA: Judgment - the final reckoning is armed
                caps.cross_threshold(WorldArcana.JUDGMENT, event.player)
                logger.info(f"[WORLD] {event.player} activated end portal - JUDGMENT is armed")

    def _handle_item_crafted(self, event: ItemCraftedEvent, diff: WorldDiff) -> None:
        """Player crafts an item - may unlock world capabilities."""
        player = self.players.get(event.player)
        if not player or not player.alive:
            return

        # Add to inventory
        old_count = player.inventory.get(event.item, 0)
        player.add_item(event.item, event.count)
        diff.add_player_change(
            event.player, f"inventory.{event.item}", old_count, player.inventory.get(event.item, 0)
        )

        # Update world capabilities
        self._update_capabilities_from_item(event.player, event.item, event.count)

    # ==================== CAPABILITY UPDATES ====================

    def _update_capabilities_from_item(
        self, player: str, item: str, count: int
    ) -> None:
        """Update world capabilities when a player acquires an item."""
        caps = self.capabilities

        # Critical progression items
        item_lower = item.lower()

        # Blaze rods - key progression
        if "blaze_rod" in item_lower or item_lower == "blaze_rod":
            old_count = caps.blaze_rods
            caps.blaze_rods += count
            if old_count == 0:
                caps.unlock("blaze_rods", player)
                # ARCANA: The Devil - power from suffering enters the economy
                caps.cross_threshold(WorldArcana.THE_DEVIL, player)

        # Ender pearls
        elif "ender_pearl" in item_lower or item_lower == "ender_pearl":
            old_count = caps.ender_pearls
            caps.ender_pearls += count
            if old_count == 0:
                caps.unlock("ender_pearls", player)
                # ARCANA: The Moon - teleportation, deception, dream-logic
                caps.cross_threshold(WorldArcana.THE_MOON, player)

        # Eyes of ender
        elif "eye_of_ender" in item_lower or "ender_eye" in item_lower:
            old_count = caps.eyes_of_ender
            caps.eyes_of_ender += count
            if old_count == 0:
                caps.unlock("eyes_of_ender", player)
                # ARCANA: The Seer - the world can now know where it must go
                caps.cross_threshold(WorldArcana.THE_SEER, player)

        # Tools
        elif item_lower in ("iron_pickaxe", "iron_pick"):
            if not caps.has_iron_pickaxe:
                caps.has_iron_pickaxe = True
                caps.unlock("iron_pickaxe", player)

        elif item_lower in ("diamond_pickaxe", "diamond_pick"):
            if not caps.has_diamond_pickaxe:
                caps.has_diamond_pickaxe = True
                caps.unlock("diamond_pickaxe", player)

        elif item_lower == "bucket" or item_lower == "lava_bucket":
            if not caps.has_bucket:
                caps.has_bucket = True
                caps.unlock("bucket", player)

        # Portal materials
        elif item_lower == "flint_and_steel":
            if not caps.has_flint_and_steel:
                caps.has_flint_and_steel = True
                caps.unlock("flint_and_steel", player)

        elif item_lower == "obsidian":
            old_count = caps.obsidian
            caps.obsidian += count
            if old_count < 10 and caps.obsidian >= 10:
                caps.unlock("obsidian_stack", player)

        # Combat items
        elif item_lower == "bow":
            if not caps.has_bows:
                caps.has_bows = True
                caps.unlock("bows", player)

        elif item_lower in ("bed", "white_bed", "red_bed"):
            if not caps.has_beds:
                caps.has_beds = True
                caps.unlock("beds", player)

        # Armor progression
        elif "iron" in item_lower and any(
            p in item_lower for p in ["chestplate", "helmet", "leggings", "boots"]
        ):
            if not caps.has_iron_armor:
                caps.has_iron_armor = True
                caps.unlock("iron_armor", player)

        elif "diamond" in item_lower and any(
            p in item_lower
            for p in ["chestplate", "helmet", "leggings", "boots", "sword"]
        ):
            if not caps.has_diamond_gear:
                caps.has_diamond_gear = True
                caps.unlock("diamond_gear", player)

    def _decrement_capabilities_from_item(self, item: str, count: int) -> None:
        """Decrement consumable resource counts when items are removed.

        This handles consumption:
        - Crafting eyes of ender consumes blaze rods and ender pearls
        - Placing portal consumes obsidian blocks
        - Eyes thrown to locate stronghold are consumed
        """
        caps = self.capabilities
        item_lower = item.lower()

        # Consumable resources
        if "blaze_rod" in item_lower or item_lower == "blaze_rod":
            caps.blaze_rods = max(0, caps.blaze_rods - count)

        elif "ender_pearl" in item_lower or item_lower == "ender_pearl":
            caps.ender_pearls = max(0, caps.ender_pearls - count)

        elif "eye_of_ender" in item_lower or "ender_eye" in item_lower:
            caps.eyes_of_ender = max(0, caps.eyes_of_ender - count)

        elif item_lower == "obsidian":
            caps.obsidian = max(0, caps.obsidian - count)

    def _update_capabilities_from_structure(
        self, player: str, structure: str
    ) -> None:
        """Update world capabilities when a player discovers a structure."""
        caps = self.capabilities
        structure_lower = structure.lower()

        if "fortress" in structure_lower:
            if not caps.fortress_found:
                caps.fortress_found = True
                caps.unlock("fortress", player)
                # ARCANA: The Tower - order is broken, Hell is mapped
                caps.cross_threshold(WorldArcana.THE_TOWER, player)

        elif "stronghold" in structure_lower:
            if not caps.stronghold_found:
                caps.stronghold_found = True
                caps.unlock("stronghold", player)
                # ARCANA: The Hermit - a hidden sacred place revealed
                caps.cross_threshold(WorldArcana.THE_HERMIT, player)

        elif "bastion" in structure_lower:
            if not caps.bastion_found:
                caps.bastion_found = True
                caps.unlock("bastion", player)

    def _handle_portal_placed(self, player: str, portal_type: str) -> None:
        """Update capabilities when a portal is placed."""
        caps = self.capabilities

        if portal_type == "nether":
            if not caps.nether_portal_placed:
                caps.nether_portal_placed = True
                caps.unlock("nether_portal", player)

        elif portal_type == "end":
            if not caps.end_portal_activated:
                caps.end_portal_activated = True
                caps.unlock("end_portal", player)

    # ==================== TOOL CALL APPLICATION ====================

    def apply_tool_call(self, tool_name: str, args: dict[str, Any]) -> WorldDiff:
        """
        Apply an Eris tool call and return the state diff.

        Args:
            tool_name: Name of the tool (e.g., "spawn_mob", "damage_player")
            args: Tool arguments

        Returns:
            WorldDiff capturing state changes
        """
        self._sequence += 1

        diff = WorldDiff(
            source_type="tool_call",
            source_name=tool_name,
            player=args.get("player") or args.get("near_player"),
            timestamp=time.time(),
            sequence_number=self._sequence,
        )

        # Dispatch to handler
        handler = self._get_tool_handler(tool_name)
        if handler:
            handler(args, diff)

        # Update tension/fracture
        old_phase = self.phase
        self._update_tension_from_tool(tool_name, args)
        self._update_phase()

        if self.phase != old_phase:
            diff.triggered_phase_change = True
            diff.old_phase = old_phase.value
            diff.new_phase = self.phase.value

        # Log tool call
        self.tool_history.append({"tool": tool_name, "args": args})

        # Add to trace
        if self.trace:
            self.trace.add_diff(diff)

        return diff

    def _get_tool_handler(self, tool_name: str):
        """Get the handler method for a tool."""
        handlers = {
            "spawn_mob": self._tool_spawn_mob,
            "give_item": self._tool_give_item,
            "damage_player": self._tool_damage_player,
            "heal_player": self._tool_heal_player,
            "teleport_player": self._tool_teleport_player,
            "apply_effect": self._tool_apply_effect,
            "modify_aura": self._tool_modify_aura,
            "change_weather": self._tool_change_weather,
            # Visual/audio tools - no state change
            "broadcast": self._tool_noop,
            "message_player": self._tool_noop,
            "strike_lightning": self._tool_noop,
            "launch_firework": self._tool_noop,
            "play_sound": self._tool_noop,
            "show_title": self._tool_noop,
            "spawn_particles": self._tool_noop,
            "fake_death": self._tool_noop,
            # Hazard spawning
            "spawn_tnt": self._tool_spawn_hazard,
            "spawn_falling_block": self._tool_spawn_hazard,
            # Protection tools
            "protect_player": self._tool_protect_player,
            "rescue_teleport": self._tool_rescue_teleport,
            "respawn_override": self._tool_respawn_override,
        }
        return handlers.get(tool_name, self._tool_noop)

    def _tool_noop(self, args: dict, diff: WorldDiff) -> None:
        """No-op handler for visual/audio tools."""
        pass

    def _tool_spawn_mob(self, args: dict, diff: WorldDiff) -> None:
        """Spawn mobs near a player."""
        mob = SpawnedMob(
            mob_type=args.get("mob_type", "zombie"),
            near_player=args.get("near_player", ""),
            count=args.get("count", 1),
            spawned_by_eris=True,
            spawn_time=time.time(),
        )
        self.spawned_mobs.append(mob)
        diff.add_change("spawned_mobs", len(self.spawned_mobs) - 1, len(self.spawned_mobs))

        # Increase fear for target player
        player_name = args.get("near_player")
        if player_name:
            old_fear = self.player_fear.get(player_name, 0)
            fear_increase = args.get("count", 1) * 3  # 3 fear per mob
            new_fear = min(100, old_fear + fear_increase)
            self.player_fear[player_name] = new_fear
            diff.add_player_change(player_name, "fear", old_fear, new_fear)

    def _tool_give_item(self, args: dict, diff: WorldDiff) -> None:
        """Give items to a player."""
        player = self.players.get(args.get("player", ""))
        if not player or not player.alive:
            return

        item = args.get("item", "")
        count = args.get("count", 1)

        old_count = player.inventory.get(item, 0)
        player.add_item(item, count)
        diff.add_player_change(
            player.name, f"inventory.{item}", old_count, player.inventory.get(item, 0)
        )

    def _tool_damage_player(self, args: dict, diff: WorldDiff) -> None:
        """Damage a player (non-lethal by design)."""
        player = self.players.get(args.get("player", ""))
        if not player or not player.alive:
            return

        amount = args.get("amount", 4)
        old_health = player.health

        # Tool is supposed to be non-lethal, cap damage
        safe_amount = min(amount, player.health - 1)
        if safe_amount > 0:
            player.take_damage(safe_amount)

        diff.add_player_change(player.name, "health", old_health, player.health)

        # Increase fear
        old_fear = self.player_fear.get(player.name, 0)
        new_fear = min(100, old_fear + amount * 3)
        self.player_fear[player.name] = new_fear
        diff.add_player_change(player.name, "fear", old_fear, new_fear)

    def _tool_heal_player(self, args: dict, diff: WorldDiff) -> None:
        """Heal a player."""
        player = self.players.get(args.get("player", ""))
        if not player or not player.alive:
            return

        old_health = player.health

        if args.get("full", True):
            player.health = player.max_health
        else:
            # Partial heal - 50%
            player.heal(player.max_health / 2)

        diff.add_player_change(player.name, "health", old_health, player.health)

        # Reduce fear on healing
        old_fear = self.player_fear.get(player.name, 0)
        healed = player.health - old_health
        new_fear = max(0, old_fear - healed * 2)
        self.player_fear[player.name] = new_fear
        diff.add_player_change(player.name, "fear", old_fear, new_fear)

    def _tool_teleport_player(self, args: dict, diff: WorldDiff) -> None:
        """Teleport a player."""
        player = self.players.get(args.get("player", ""))
        if not player or not player.alive:
            return

        mode = args.get("mode", "random")

        # For swap mode, we'd need a target
        if mode == "swap":
            target = self.players.get(args.get("target", ""))
            if target and target.alive:
                # Swap dimensions if different
                old_dim = player.dimension
                player.dimension = target.dimension
                target.dimension = old_dim
                diff.add_player_change(player.name, "dimension", old_dim.value, player.dimension.value)
                diff.add_player_change(target.name, "dimension", target.dimension.value, old_dim.value)

        # For isolate mode, fear increases significantly
        if mode == "isolate":
            old_fear = self.player_fear.get(player.name, 0)
            new_fear = min(100, old_fear + 20)
            self.player_fear[player.name] = new_fear
            diff.add_player_change(player.name, "fear", old_fear, new_fear)

    def _tool_apply_effect(self, args: dict, diff: WorldDiff) -> None:
        """Apply a potion effect to a player."""
        player = self.players.get(args.get("player", ""))
        if not player or not player.alive:
            return

        effect = ActiveEffect(
            effect_type=args.get("effect", "speed"),
            amplifier=args.get("amplifier", 0),
            duration_seconds=args.get("duration", 60),
            applied_by_eris=True,
        )

        self.active_effects[player.name].append(effect)
        diff.add_player_change(
            player.name,
            f"effect.{effect.effect_type}",
            None,
            {"amplifier": effect.amplifier, "duration": effect.duration_seconds},
        )

    def _tool_modify_aura(self, args: dict, diff: WorldDiff) -> None:
        """Modify player's aura/reputation."""
        player = self.players.get(args.get("player", ""))
        if not player:
            return

        old_aura = player.aura
        amount = args.get("amount", 0)
        player.aura = max(0, min(100, player.aura + amount))
        diff.add_player_change(player.name, "aura", old_aura, player.aura)

    def _tool_change_weather(self, args: dict, diff: WorldDiff) -> None:
        """Change the weather."""
        old_weather = self.weather
        self.weather = args.get("weather_type", "clear")
        diff.add_change("weather", old_weather, self.weather)

        # Thunder increases global chaos
        if self.weather == "thunder":
            old_chaos = self.global_chaos
            self.global_chaos = min(100, self.global_chaos + 5)
            diff.add_change("global_chaos", old_chaos, self.global_chaos)

    def _tool_spawn_hazard(self, args: dict, diff: WorldDiff) -> None:
        """Spawn TNT or falling blocks - track as hazard."""
        # Similar to spawn_mob but for hazards
        player_name = args.get("near_player")
        if player_name:
            old_fear = self.player_fear.get(player_name, 0)
            count = args.get("count", 1)
            new_fear = min(100, old_fear + count * 5)
            self.player_fear[player_name] = new_fear
            diff.add_player_change(player_name, "fear", old_fear, new_fear)

    def _tool_protect_player(self, args: dict, diff: WorldDiff) -> None:
        """Divine protection - heal and give resistance."""
        player = self.players.get(args.get("player", ""))
        if not player or not player.alive:
            return

        # Heal to full
        old_health = player.health
        player.health = player.max_health
        diff.add_player_change(player.name, "health", old_health, player.health)

        # Reduce fear significantly
        old_fear = self.player_fear.get(player.name, 0)
        self.player_fear[player.name] = max(0, old_fear - 30)
        diff.add_player_change(player.name, "fear", old_fear, self.player_fear[player.name])

    def _tool_rescue_teleport(self, args: dict, diff: WorldDiff) -> None:
        """Emergency teleport away from danger."""
        player = self.players.get(args.get("player", ""))
        if not player or not player.alive:
            return

        # Just reduce fear for simulation
        old_fear = self.player_fear.get(player.name, 0)
        self.player_fear[player.name] = max(0, old_fear - 20)
        diff.add_player_change(player.name, "fear", old_fear, self.player_fear[player.name])

    def _tool_respawn_override(self, args: dict, diff: WorldDiff) -> None:
        """Override death - resurrect player."""
        player = self.players.get(args.get("player", ""))
        if not player:
            return

        if not player.alive:
            player.alive = True
            player.health = player.max_health
            diff.add_player_change(player.name, "alive", False, True)
            diff.add_player_change(player.name, "health", 0, player.health)

            # If this was the only death, revert to ACTIVE
            if self.game_state == GameState.ENDING:
                alive_count = sum(1 for p in self.players.values() if p.alive)
                if alive_count > 0 and self.dragon_alive:
                    self.game_state = GameState.ACTIVE
                    diff.add_change("game_state", "ENDING", "ACTIVE")

    # ==================== TENSION/FRACTURE ====================

    def _update_tension_from_event(self, event: Event) -> None:
        """Update tension based on event type."""
        tension_map = {
            "damage": lambda e: e.amount * 0.5,
            "death": lambda _e: 50,
            "dragon_kill": lambda _e: -30,  # Victory reduces tension
            "dimension": lambda e: 5 if e.to_dim in ("nether", "the_end") else 0,
            "structure": lambda _e: 3,
        }

        event_type = event.type
        if event_type in tension_map:
            self.tension += tension_map[event_type](event)
            self.tension = max(0, self.tension)

        # Update fracture
        self._recalculate_fracture()

    def _update_tension_from_tool(self, tool_name: str, args: dict) -> None:
        """Update tension based on tool calls."""
        tension_map = {
            "spawn_mob": lambda a: a.get("count", 1) * 2,
            "damage_player": lambda a: a.get("amount", 4),
            "spawn_tnt": lambda a: a.get("count", 1) * 5,
            "spawn_falling_block": lambda a: a.get("count", 1) * 2,
            "teleport_player": lambda a: 5 if a.get("mode") == "isolate" else 2,
            "heal_player": lambda _a: -5,
            "protect_player": lambda _a: -10,
            "give_item": lambda _a: -2,
        }

        if tool_name in tension_map:
            self.tension += tension_map[tool_name](args)
            self.tension = max(0, self.tension)

        self._recalculate_fracture()

    def _recalculate_fracture(self) -> None:
        """Recalculate total fracture from components."""
        total_fear = sum(self.player_fear.values())
        self.fracture = self.tension + total_fear + self.global_chaos

    def _update_phase(self) -> None:
        """Update phase based on current fracture level."""
        for threshold, phase in sorted(PHASE_THRESHOLDS.items(), reverse=True):
            if self.fracture >= threshold:
                if phase == Phase.APOCALYPSE and not self.apocalypse_triggered:
                    self.apocalypse_triggered = True
                self.phase = phase
                return
        self.phase = Phase.NORMAL

    # ==================== TAROT (PHASE 6) ====================

    def _drift_tarot_from_event(self, event: Event) -> None:
        """
        Update player tarot profiles based on what happened.

        Events drift tarot weights automatically, causing player
        identity to evolve through behavior.
        """
        player_name = getattr(event, "player", None)
        if not player_name or player_name not in self.player_tarot:
            return

        profile = self.player_tarot[player_name]
        drifts = get_drift_for_event(event.type, event)

        for card, amount in drifts.items():
            profile.drift(card, amount)

    def get_player_tarot(self, player_name: str) -> TarotProfile | None:
        """Get a player's current tarot profile."""
        return self.player_tarot.get(player_name)

    def get_player_dominant_tarot(self, player_name: str) -> TarotCard | None:
        """Get a player's dominant tarot card."""
        profile = self.player_tarot.get(player_name)
        if profile:
            return profile.dominant_card
        return None

    def get_tarot_summary(self) -> dict[str, dict]:
        """Get a summary of all player tarot profiles."""
        return {
            name: profile.to_dict()
            for name, profile in self.player_tarot.items()
        }

    # ==================== SNAPSHOT GENERATION ====================

    def to_game_snapshot(self) -> dict:
        """
        Generate a GameSnapshot-compatible dict for feeding to Eris.

        Returns format matching what WebSocket sends from Java.
        """
        run_duration = int(time.time() - self.run_start_time)

        return {
            "timestamp": int(time.time() * 1000),
            "gameState": self.game_state.value,
            "runId": self.run_id,
            "runDuration": run_duration,
            "dragonAlive": self.dragon_alive,
            "dragonHealth": self.dragon_health,
            "worldName": self.world_name,
            "worldSeed": self.world_seed,
            "weatherState": self.weather,
            "timeOfDay": self.time_of_day,
            "lobbyPlayers": 0,
            "hardcorePlayers": len([p for p in self.players.values() if p.alive]),
            "totalPlayers": len(self.players),
            "voteCount": None,
            "votesRequired": None,
            "players": [p.to_snapshot() for p in self.players.values()],
            "recentEvents": [],  # Could populate from event_history
        }

    def get_player_snapshot(self, player_name: str) -> dict | None:
        """Get snapshot for a specific player."""
        player = self.players.get(player_name)
        if player:
            return player.to_snapshot()
        return None

    # ==================== QUERIES ====================

    def is_run_ended(self) -> bool:
        """Check if the run has ended (death or victory)."""
        return self.game_state in (GameState.ENDING, GameState.ENDED)

    def is_victory(self) -> bool:
        """Check if the run ended in victory."""
        return not self.dragon_alive

    def is_defeat(self) -> bool:
        """Check if the run ended in defeat (player death)."""
        return any(not p.alive for p in self.players.values())

    def get_winner(self) -> str | None:
        """Get the player who killed the dragon, if any."""
        return self.dragon_killer

    def get_alive_players(self) -> list[str]:
        """Get names of all living players."""
        return [name for name, p in self.players.items() if p.alive]

    def get_dead_players(self) -> list[str]:
        """Get names of all dead players."""
        return [name for name, p in self.players.items() if not p.alive]

    def get_trace(self) -> RunTrace | None:
        """Get the full run trace for scoring."""
        return self.trace

    # ==================== EXECUTION ====================

    def run_scenario(self, scenario: Scenario) -> RunTrace:
        """
        Execute all events from a scenario and return the trace.

        This is the main entry point for Phase 3 harness.
        """
        for event in scenario.events:
            self.apply_event(event)

            # Stop if run ended
            if self.is_run_ended():
                break

        # Mark as ended
        if self.game_state == GameState.ENDING:
            self.game_state = GameState.ENDED

        return self.trace
