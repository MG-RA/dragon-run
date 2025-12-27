# Phase 2: SyntheticWorld Core - COMPLETE

## Goal
Simulate Minecraft enough to feel real. Create a deterministic world state that evolves based on scenario events and Eris tool calls.

## Deliverable
**World state that evolves deterministically via `apply_event(event)` and `apply_tool_call(tool_call)`.**

---

## What Was Built

### 1. PlayerState ([player_state.py](director/src/eris/validation/player_state.py))

Dataclasses for tracking player and entity state:

**PlayerState Fields:**
- Identity: `name`, `role`
- Health: `health`, `max_health`, `food_level`, `saturation`
- Location: `dimension`, `x`, `y`, `z`
- Status: `alive`, `game_mode`
- Progress: `advancements`, `inventory`
- Stats: `mob_kills`, `damage_taken`, `entered_nether`, `entered_end`
- Eris tracking: `fear`, `aura`

**Computed Properties:**
- `diamond_count`, `ender_pearl_count`, `blaze_rod_count`
- `has_elytra`, `armor_tier`

**Methods:**
- `take_damage(amount)` - Apply damage, returns True if killed
- `heal(amount)` - Heal player
- `add_item(item, count)` / `remove_item(item, count)`
- `change_dimension(dimension)` - Updates tracking flags
- `to_snapshot()` - Java PlayerStateSnapshot format

**Supporting Classes:**
- `SpawnedMob` - Track spawned mobs with `kill()` method
- `ActiveEffect` - Track potion effects with duration
- `Dimension` enum - OVERWORLD, NETHER, THE_END

### 2. WorldDiff ([world_diff.py](director/src/eris/validation/world_diff.py))

Telemetry for tracking state changes:

**StateChange:**
- `field`, `old_value`, `new_value`
- `delta` property for numeric changes

**WorldDiff:**
- `source_type` - "event" or "tool_call"
- `source_name` - e.g., "damage", "spawn_mob"
- `player` - affected player (if any)
- `changes` - list of StateChange
- `caused_death`, `caused_victory`, `triggered_phase_change`

**RunTrace:**
- Collects all WorldDiffs from a scenario execution
- Summary stats: `total_events`, `total_tool_calls`, `deaths`, `victory`, `final_phase`
- `to_dict()` for JSON serialization

### 3. SyntheticWorld ([synthetic_world.py](director/src/eris/validation/synthetic_world.py))

Main simulation class (~500 lines):

**Core State:**
```python
players: Dict[str, PlayerState]
game_state: GameState  # IDLE, ACTIVE, ENDING, ENDED
dragon_alive: bool
dragon_health: float
weather: str
spawned_mobs: List[SpawnedMob]
```

**Tension/Fracture System:**
```python
tension: float      # Builds from events
fracture: float     # tension + fears + chaos
phase: Phase        # NORMAL → RISING → CRITICAL → BREAKING → APOCALYPSE
player_fear: Dict[str, float]
global_chaos: float
```

**Key Methods:**

| Method | Purpose |
|--------|---------|
| `from_scenario(scenario)` | Factory method to create world |
| `apply_event(event)` | Apply any of 10 event types |
| `apply_tool_call(name, args)` | Apply any of 22 Eris tools |
| `to_game_snapshot()` | Generate Java-compatible snapshot |
| `run_scenario(scenario)` | Execute full scenario |

### 4. Event Handlers (10 types)

| Event | State Changes |
|-------|---------------|
| `advancement` | Add to player.advancements |
| `damage` | Reduce health, check death, increase fear |
| `inventory` | Add/remove items |
| `dimension` | Change dimension, set entered_* flags |
| `chat` | Log only |
| `death` | Kill player, end game |
| `dragon_kill` | Kill dragon, mark victory |
| `mob_kill` | Increment mob_kills |
| `structure` | Track discovery |
| `health` | Heal or damage without source |

### 5. Tool Handlers (22 tools)

**State-changing tools:**
- `spawn_mob` - Add to spawned_mobs, increase fear
- `give_item` - Add to inventory
- `damage_player` - Non-lethal damage (capped)
- `heal_player` - Full or partial heal
- `teleport_player` - Dimension swap, fear for isolate
- `apply_effect` - Track active effects
- `modify_aura` - Update reputation
- `change_weather` - Update weather, thunder adds chaos
- `spawn_tnt`, `spawn_falling_block` - Hazard fear

**Protection tools:**
- `protect_player` - Full heal + fear reduction
- `rescue_teleport` - Fear reduction
- `respawn_override` - Resurrect dead player

**Visual/audio tools (no state change):**
- `broadcast`, `message_player`, `strike_lightning`, `launch_firework`
- `play_sound`, `show_title`, `spawn_particles`, `fake_death`

### 6. Tension/Fracture Calculation

```python
# Tension from events
damage: +amount * 0.5
death: +50
dragon_kill: -30
dimension_change: +5 (nether/end)

# Tension from tools
spawn_mob: +count * 2
damage_player: +amount
spawn_tnt: +count * 5
heal_player: -5

# Fracture = tension + sum(fears) + chaos
# Phase thresholds: 50/80/120/150
```

### 7. Test Suite ([test_synthetic_world.py](director/tests/test_synthetic_world.py))

**46 tests covering:**
- Loading from scenarios (8 tests)
- All 10 event types (18 tests)
- Tool calls (7 tests)
- Tension/fracture (4 tests)
- Snapshots (2 tests)
- Full execution (3 tests)
- Real scenario files (3 tests)

**All tests pass:**
```
46 passed in 0.22s
```

---

## Usage Example

```python
from pathlib import Path
from eris.validation import load_scenario, SyntheticWorld

# Load scenario
scenario = load_scenario(Path("scenarios/01_simple_trio.yaml"))

# Create world
world = SyntheticWorld.from_scenario(scenario)

# Run full scenario
trace = world.run_scenario(scenario)

# Check results
print(f"Victory: {trace.victory}")
print(f"Deaths: {trace.deaths}")
print(f"Events: {trace.total_events}")
print(f"Final phase: {trace.final_phase}")

# Or apply events manually
world = SyntheticWorld.from_scenario(scenario)
for event in scenario.events:
    diff = world.apply_event(event)
    print(f"{event.type}: {diff}")

    # Simulate Eris intervention
    if event.type == "damage" and event.amount > 10:
        world.apply_tool_call("heal_player", {"player": event.player, "full": True})

# Get snapshot for Eris
snapshot = world.to_game_snapshot()
```

---

## Files Created

```
director/src/eris/validation/
  ├── player_state.py      (190 lines) - PlayerState, SpawnedMob, ActiveEffect
  ├── world_diff.py        (150 lines) - WorldDiff, StateChange, RunTrace
  ├── synthetic_world.py   (520 lines) - SyntheticWorld
  └── __init__.py          (updated) - Exports

director/tests/
  └── test_synthetic_world.py (400 lines) - 46 tests

PHASE2_COMPLETE.md (this file)
```

**Total:** ~1260 lines of production code + tests

---

## Integration Points

### Exports Available
```python
from eris.validation import (
    # Phase 2: SyntheticWorld
    SyntheticWorld,
    GameState,
    Phase,
    PHASE_THRESHOLDS,
    # Player state
    PlayerState,
    SpawnedMob,
    ActiveEffect,
    Dimension,
    # World diff / telemetry
    WorldDiff,
    StateChange,
    RunTrace,
)
```

### Snapshot Compatibility
`to_game_snapshot()` produces format matching Java WebSocket:
```json
{
  "timestamp": 1234567890000,
  "gameState": "ACTIVE",
  "runId": 1,
  "dragonAlive": true,
  "dragonHealth": 200.0,
  "players": [
    {
      "username": "Alice",
      "health": 20.0,
      "dimension": "overworld",
      "diamondCount": 5,
      ...
    }
  ]
}
```

---

## Next Steps: Phase 3

Phase 2 provides the **deterministic simulation core**.

**Ready for Phase 3:** Create closed-loop Eris harness that:
- Replaces WebSocket with scenario → SyntheticWorld
- Feeds snapshots to LangGraph pipeline
- Captures Eris tool calls
- Applies tool calls back to SyntheticWorld
- Produces full trace with both events AND Eris actions

```
Scenario → EventProcessor → LangGraph → Tool Calls → SyntheticWorld
              ↑                               ↓
              └───────── Snapshot ────────────┘
```

---

## Success Criteria

- [x] SyntheticWorld class implemented
- [x] from_scenario() factory method
- [x] apply_event() for all 10 event types
- [x] apply_tool_call() for 22 tools
- [x] to_game_snapshot() for Eris integration
- [x] Tension/fracture calculation
- [x] Phase transitions (NORMAL → APOCALYPSE)
- [x] WorldDiff telemetry
- [x] RunTrace collection
- [x] 46 tests passing
- [x] Works with real scenario files

**Phase 2 Status: COMPLETE**
