# Dragon Run AI Director

An AI-powered director system that provides real-time commentary and strategic interventions for the Dragon Run hardcore Minecraft roguelike.

## Features

- **Real-time Commentary**: Dramatic narration of key game events (deaths, achievements, milestones)
- **Strategic Interventions**: Helps struggling players or adds challenges when appropriate
- **Memory System**:
  - Short-term: 32k token context window with recent events and state
  - Long-term: PostgreSQL database queries for historical player data
- **Batched Updates**: State updates every 5 seconds, events sent immediately
- **Chat Monitoring**: Can read and respond to player chat messages
- **Tool-based Architecture**: Uses Brigadier command tree for type-safe game interactions

## Setup

1. **Install Python dependencies** (using uv):
```bash
cd director
uv sync
```

2. **Install and run Ollama**:
```bash
# Install Ollama from https://ollama.ai
ollama pull ministral-3:14b
```

3. **Configure** the director in `config.yaml`:
- WebSocket URI (default: ws://localhost:8765)
- Ollama settings
- Database credentials
- Commentary and intervention preferences

4. **Enable director** in the Minecraft plugin config (`config.yml`):
```yaml
director:
  enabled: true
  port: 8765
  broadcast-interval: 100  # 5 seconds
  monitor-chat: true
```

## Usage

Run the director (using uv):
```bash
cd director
uv run python main_new.py
```

The director will:
1. Connect to the Minecraft server via WebSocket
2. Monitor game state and events
3. Provide commentary on key moments
4. Strategically intervene to enhance gameplay

## Configuration

### Commentary Settings
```yaml
commentary:
  enabled: true
  cooldown_seconds: 30
  style: "dramatic_announcer"  # or "sports_announcer", "dungeon_master"
  triggers:
    player_death: true
    dimension_change: true
    near_death: true
    milestone: true
    dragon_phase: true
    player_chat: false
```

### Intervention Settings
```yaml
intervention:
  enabled: true
  rate: 0.3  # 30% chance when conditions are met
  cooldown_seconds: 300  # 5 minutes
  types:
    mercy: true        # Help struggling players
    challenge: true    # Add difficulty for progressing players
    dramatic: true     # Create cinematic moments
```

## Architecture

### Java Plugin Side
- **DirectorWebSocketServer**: Broadcasts enhanced game state every 5 seconds
- **PlayerStateSnapshot**: Detailed player data (health, inventory, position, stats)
- **DirectorCommands**: Brigadier command tree for director actions
- **DirectorCommandExecutor**: Executes commands from director
- **DirectorChatListener**: Forwards chat messages to director

### Python Director Side
- **main_new.py**: Main event loop and AI orchestration
- **websocket_client.py**: WebSocket communication with server
- **state_manager.py**: Short-term memory (current state + recent events)
- **database_tools.py**: Long-term memory (historical queries)
- **commentary_engine.py**: Decides when/what to narrate
- **intervention_engine.py**: Strategic gameplay interventions

## Available Director Commands

The director can execute these commands via the Brigadier API:

```
/director broadcast <message>                          - Send message to all players
/director message <player> <message>                   - Send message to specific player
/director spawn mob <type> near <player> [count]       - Spawn mobs near player
/director give <player> <item> [count]                 - Give items to player
/director effect <player> <effect> [duration] [amp]    - Apply potion effect
/director lightning near <player>                      - Strike lightning near player
/director weather <clear|rain|thunder>                 - Change weather
```

## Database Schema

The director can query historical data:
- `player_data` - Player stats and aura
- `run_history` - Past run outcomes
- `achievements` - Achievement unlocks

## Development

### Testing the Director

1. Start the Minecraft server with director enabled
2. Start the Python director: `uv run python main_new.py`
3. Join the server and start a run
4. Observe commentary and interventions in chat

### Debugging

Enable debug logging:
```python
logging.basicConfig(level=logging.DEBUG)
```

### Adding New Commands

1. Add Brigadier command in `DirectorCommands.java`
2. Add case in `DirectorCommandExecutor.buildBrigadierCommand()`
3. Add Python method in `DragonRunDirector` class
4. Use via `await self.ws_client.send_command()`

## Safety Features

- Rate limiting: Max 10 commands per minute
- Cooldowns: 30s for commentary, 5min for interventions
- Validation: All commands validated before execution
- Logging: All interventions logged for review

## Future Enhancements

- [ ] Web dashboard for monitoring director activity
- [ ] Machine learning for adaptive difficulty
- [ ] Voice output for commentary
- [ ] Player preference system
- [ ] Achievement-based director personalities
