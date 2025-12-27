"""
SyntheticWorld - Deterministic Minecraft simulation for testing Eris.

Simulates Minecraft state evolution based on scenario events and Eris tool calls.
Mirrors GameSnapshot and PlayerStateSnapshot from the Java plugin.
"""

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
    MobKillEvent,
    PartyPreset,
    PlayerDefinition,
    Scenario,
    StructureDiscoveryEvent,
)
from .tarot import TarotCard, TarotProfile, get_drift_for_event
from .world_diff import RunTrace, WorldDiff


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
