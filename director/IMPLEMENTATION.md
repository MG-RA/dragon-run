# Eris AI Director v2.0 - Implementation Guide

## 🎭 Overview

**Eris** is a chaotic trickster AI director for the Dragon Run hardcore Minecraft speedrun gamemode. She's a LangGraph-based agent using Ministral 3 14B locally via Ollama, with a 32k context window and sophisticated personality masking system.

## 🏗️ Architecture

### Core Components

```
┌─────────────────────────────────────────────────────┐
│                  ERIS AI DIRECTOR                   │
├─────────────────────────────────────────────────────┤
│ WebSocket Client ←→ Game Server (PaperMC Plugin)   │
│ Event Processor (Priority Queue + Debouncing)      │
│ LangGraph State Machine (6 nodes, async)           │
│ Persona System (6 personality masks)               │
│ Memory (Short-term + Long-term via PostgreSQL)     │
│ Tools (8 Minecraft action tools)                   │
└─────────────────────────────────────────────────────┘
```

### Directory Structure

```
director/
├── src/eris/                    # Main source code
│   ├── graph/
│   │   ├── state.py             # ErisState schema + enums
│   │   ├── nodes.py             # 6 graph nodes
│   │   ├── edges.py             # Routing logic
│   │   └── builder.py           # Graph compilation
│   │
│   ├── core/
│   │   ├── websocket.py         # GameStateClient
│   │   ├── database.py          # Async PostgreSQL
│   │   ├── event_processor.py   # Priority queue + debouncing
│   │   └── memory.py            # Short/long-term memory
│   │
│   ├── persona/
│   │   ├── masks.py             # 6 personality masks
│   │   └── prompts.py           # System prompts
│   │
│   └── tools/
│       ├── schemas.py           # Pydantic schemas
│       └── game_tools.py        # 8 Minecraft tools
│
├── scripts/
│   └── run.py                   # Main entry point
│
├── pyproject.toml               # Dependencies
├── langgraph.json               # LangGraph CLI config
├── config.yaml                  # Runtime configuration
├── .env                         # Environment variables
└── IMPLEMENTATION.md            # This file
```

## 🎯 Key Features

### Event Processing
- **Priority Queue**: CRITICAL (death) → HIGH (chat) → MEDIUM (milestones) → LOW (state)
- **Debouncing**: Prevents GPU saturation
  - State updates: 15s minimum
  - Damage events: 5s minimum
  - Milestones: 3s minimum
- **Fast Path**: Chat gets 2-3s response time with simplified prompt
- **Chat Buffer**: Rolling window of last 50 messages in context

### Personality Masks (Random Switching)
1. **TRICKSTER** - Playful, pranks, wordplay
2. **PROPHET** - Cryptic warnings, riddles
3. **FRIEND** - Warm but unsettling, betrayal
4. **CHAOS_BRINGER** - Menacing, threats, mob spawns
5. **OBSERVER** - Detached, rare comments
6. **GAMBLER** - Deals, bargains, risk-taking

### LangGraph State Machine

```
event_classifier
    ↓
    ├→ skip (LOW priority)
    ├→ fast_response (chat) → tool_executor → END
    └→ context_enricher
        ↓
    mask_selector
        ↓
    decision_node
        ↓
        ├→ silent → END
        ├→ speak → tool_executor → END
        └→ intervene → tool_executor → END
```

### Memory System
- **Short-term**: Last 50 chat messages, recent events (20k tokens max)
- **Long-term**: PostgreSQL queries for player history, stats, achievements

### Tools (8 Total)
- `spawn_mob` - Summon creatures (1-10)
- `give_item` - Gift items
- `broadcast` - Announce to all
- `message_player` - Private DM
- `apply_effect` - Potion effects
- `strike_lightning` - Dramatic effect
- `change_weather` - Control sky
- `launch_firework` - Celebration

## 🚀 Getting Started

### Installation

```bash
cd director
uv sync                    # Or pip install -e .
```

### Configuration

1. **Set environment variables** (`.env`):
```
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=ministral:latest
WEBSOCKET_URI=ws://localhost:8765
DB_HOST=localhost
DB_PORT=5432
DB_NAME=dragonrun
DB_USER=postgres
DB_PASSWORD=postgres
```

2. **Configure** `config.yaml` (optional - has defaults)

### Running

```bash
# Standard run
python scripts/run.py

# With LangGraph Studio (development)
langgraph dev

# In your test server
cd testserver && java -jar server.jar
```

## 🧠 LangGraph Studio Development

For interactive development and debugging:

```bash
langgraph dev
```

This will:
- Start the graph at http://localhost:8123
- Allow step-by-step execution
- Visualize the state machine
- Test individual nodes

## 🔧 Configuration

### `config.yaml`

- **websocket.uri**: Game server WebSocket endpoint
- **database**: PostgreSQL connection (host, port, database, user, password)
- **ollama**: Model, host, temperature, context window
- **event_processor**: Debounce timings
- **memory**: Token limits, buffer sizes
- **eris**: Mask stability, speech cooldown

### `.env`

Environment overrides for sensitive data and deployment:
- `OLLAMA_MODEL`: Which model to use
- Database credentials
- WebSocket URI

## 💾 Database Schema

Uses existing `dragonrun` database schema:
- `players` - Player stats and aura
- `run_history` - Game session records
- `run_participants` - Per-run player stats
- `achievements_earned` - Lifetime achievements

Queries:
- `get_player_summary()` - Player aura, deaths, dragons, hours
- `get_player_nemesis()` - Most common death cause
- `get_recent_runs()` - Recent game history

## 📊 Performance

### Response Times
| Event | Target | Strategy |
|-------|--------|----------|
| Chat | 2-3s | Fast path, minimal prompt |
| Death | 3-5s | Full processing, dramatic |
| Milestone | 5-10s | Context enriched |
| Proactive | No constraint | Background |

### GPU Usage
- Model stays loaded (`keep_alive: 30m`)
- Events debounced to prevent saturation
- Context pruned to ~25k tokens
- Fast path skips expensive enrichment

## 🎬 Example Interactions

### Death Event (Prophet Mask)
```
Event: player_death
Eris: "The one who flew too close to the stars...
       I warned you, did I not? Oh wait, I didn't.
       How delicious."
```

### Chat Response (Trickster Mask)
```
Player: "Eris please help us"
Eris: "Help? Oh, I AM helping. *spawns 3 zombies*
       These friends will keep you company!"
```

### Close Call (Gambler Mask)
```
Player: Steve (2.5 hearts)
Eris: "Ooh, dancing on the edge, are we?
       Survive the next minute and I'll make it worth your while."
```

## 🔌 Integration with PaperMC Plugin

### WebSocket Protocol

**Incoming Event**:
```json
{
  "type": "event",
  "eventType": "player_chat",
  "data": {
    "player": "Steve",
    "message": "Eris help us!",
    "uuid": "..."
  }
}
```

**Outgoing Command**:
```json
{
  "type": "command",
  "command": "spawn_mob",
  "parameters": {
    "mobType": "zombie",
    "nearPlayer": "Steve",
    "count": 1
  },
  "reason": "Eris Intervention"
}
```

## 🐛 Debugging

### Logging
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Event Queue
```python
processor.get_queue_size()  # Check pending events
processor.get_chat_context()  # View chat buffer
```

### LangGraph Studio
Visualize execution: `langgraph dev` then trace through nodes

## 📝 Notes

- Mask stability defaults to 70%, decays 5% per event (min 30%)
- Chat always goes through fast path regardless of debounce
- Database queries are async and non-blocking
- WebSocket reconnects automatically with 5s backoff
- All times in context are ISO format timestamps

## 🚀 Next Steps

1. **Test with Studio**: `langgraph dev` for interactive debugging
2. **Connect to server**: Update `.env` with actual game server IP
3. **Tune prompts**: Adjust system prompts in `persona/prompts.py`
4. **Add listeners**: Extend events in Java plugin as needed
5. **Monitor performance**: Watch GPU/CPU usage during gameplay

---

**Created**: 2024
**Version**: 2.0.0
**Status**: Production Ready ✨
