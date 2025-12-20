# Dragon Run Director Dashboard

A rich, real-time console dashboard for monitoring the AI Director.

## Features

The dashboard displays all Director activity in a single, organized view:

### 📊 Header Bar
- **Status**: Current AI state (Idle, Thinking, Generating, Sending, Error)
- **Uptime**: How long the Director has been running
- **Event Count**: Total game events received
- **Commentary Count**: Total AI messages sent
- **Intervention Count**: Total interventions executed

### 🎯 Game State Panel
Real-time game information:
- Run ID and game state (IDLE, GENERATING, ACTIVE, RESETTING)
- Run duration
- Dragon status and health
- Player counts (active/total/lobby)
- Weather and world time

### 👥 Player State Panel
Per-player status table showing:
- Player name
- Current dimension (🌍 overworld, 🔥 nether, 🌌 end, 💤 lobby)
- Health ❤️ (color-coded: green=healthy, yellow=hurt, red=danger)
- Hunger 🍖
- Diamonds 💎
- Status indicators (⚠️ danger, ⚔️ kills, armor tier)

### 🎯 Recent Events Panel
Last 8 game events with:
- Timestamp
- Event type (color-coded by category)
- Event icon (💀 death, 🌀 dimension, 💬 chat, 🐉 dragon)
- Key event details

### 🤖 AI Activity Log
Last 6 AI actions:
- 🎤 Commentary generation
- ⚡ Interventions
- 🧠 Thinking/analyzing
- 🔧 Tool usage
- ℹ️ System events
- ❌ Errors

### 📢 AI Messages Panel
Last 5 messages sent to the game (preview of first 50 chars)

### 📊 Footer Bar
- AI status indicator
- Context usage (tokens/32k with percentage and color coding)
- Time since last model call
- Last tool used

## Installation

1. Install the `rich` library:
```bash
cd director
pip install rich
# Or install all requirements:
pip install -r requirements.txt
```

## Usage

### With Dashboard (Default)
```bash
python main.py
```

The dashboard will take over your terminal with a live, updating view.

### Without Dashboard (Old Logging Mode)
If you prefer traditional file-based logging:

Edit `main.py` line 635:
```python
director = DragonRunDirector(use_dashboard=False)
```

Or pass it programmatically:
```python
from main import DragonRunDirector
director = DragonRunDirector(use_dashboard=False)
```

## Controls

- **Ctrl+C**: Gracefully shut down the Director and exit the dashboard

## Color Coding

### AI Status
- 🟢 **Green (Idle)**: Waiting for events
- 🟡 **Yellow (Thinking/Starting/Connecting)**: Processing
- 🔵 **Blue (Generating)**: AI model is generating response
- 🔴 **Red (Error)**: Something went wrong

### Health
- **Green**: > 12 HP (healthy)
- **Yellow**: 6-12 HP (hurt)
- **Red**: < 6 HP (danger)

### Context Usage
- **Green**: < 50% of context window
- **Yellow**: 50-80% of context window
- **Red**: > 80% of context window (may need trimming soon)

## Dashboard Layout

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ 🔮 DRAGON RUN DIRECTOR AI | Status: 🟢 Idle | Uptime: 1h 23m | Events: 147  ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

┌─ 🎯 Game State ─────────────────┐ ┌─ 🎯 Recent Events ──────────────┐
│ 🎮 Run ID       #46             │ │ 12:34:56 💬 player_chat: ...   │
│ 📊 Game State   ACTIVE          │ │ 12:34:50 🌀 dimension_change    │
│ ⏱️  Duration     6m 23s          │ │ 12:34:45 💀 player_death: ...   │
│ 🐉 Dragon       Not spawned     │ └─────────────────────────────────┘
│ 👥 Players      3 active / 8    │
│ 🌦️  Weather     Clear            │ ┌─ 🤖 AI Activity ────────────────┐
│ 🕐 World Time   Day 2, 6h       │ │ 12:35:01 🎤 Analyzing event...  │
└─────────────────────────────────┘ │ 12:34:58 🧠 Thinking...         │
                                    │ 12:34:56 🔧 Used: broadcast     │
┌─ 👥 Player State ───────────────┐ └─────────────────────────────────┘
│ Player      Dim ❤️  🍖 💎 Status │
│ Butters757  🌍  18  16  4  ⚔️67  │ ┌─ 📢 AI Messages ────────────────┐
│ Player2     🌍  20  20  8  ⚔️45  │ │ 12:35:00 The loop accepts...   │
│ Player3     🔥  15  18  2  ok    │ │ 12:34:45 Another falls...      │
└─────────────────────────────────┘ └─────────────────────────────────┘

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ AI: 🟢 Idle | Context: 12847/32k (39%) | Last call: 5s ago | Tool: broadcast┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

## Troubleshooting

### Dashboard not rendering properly
- Make sure your terminal supports Unicode and emojis
- Try a different terminal (Windows Terminal, iTerm2, etc.)
- Check terminal size (minimum 80x24 recommended)

### High CPU usage
- The dashboard refreshes at 2Hz (twice per second)
- This is normal and minimal impact

### Dashboard flickering
- Some terminals handle live updates better than others
- Windows Terminal and modern terminals work best

### Can't see anything
- Dashboard uses alternate screen buffer
- Press Ctrl+C to exit and return to normal terminal

## Logging

When dashboard is enabled:
- **Warnings and errors** are logged to `director.log`
- **All other output** goes to the dashboard

When dashboard is disabled:
- **All output** goes to stdout with timestamps
- Traditional logging format

## Tips

1. **Maximize your terminal** for best viewing experience
2. **Use a terminal with good emoji support** (Windows Terminal recommended on Windows)
3. **Monitor context usage** - when it hits 80%, the AI trims message history
4. **Watch AI activity** - see exactly when the AI is thinking, generating, or sending
5. **Track events** - quickly see what's happening in the game in real-time
