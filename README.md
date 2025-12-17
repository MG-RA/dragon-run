# Dragon Run

A hardcore roguelike PaperMC plugin where **any player death resets the entire world**.

## Features

- **Hardcore Roguelike**: If ANY player dies, the world resets for everyone
- **Persistent Aura Economy**: Players gain and lose "aura" (currency) that persists across resets
- **Achievements System**: 40+ achievements with positive and negative rewards
- **Betting System**: Bet aura on other players' survival
- **Live Stats**: Track player locations, health, and stats in real-time
- **Death Roasts**: Custom death messages that roast the player who died
- **Discord Integration**: Live run stats and notifications (coming soon)
- **REST API**: WebSocket endpoints for external dashboards (coming soon)

## Commands

- `/aura [player]` - Check aura balance
- `/stats` - View dashboard with run info and player stats
- `/achievements` - View your achievements
- `/bet <player> <amount>` - Bet aura on a player's survival
- `/bet` - View your active bets
- `/live` - See all player locations and live stats

## Installation

1. Install PostgreSQL and create a database named `dragonrun`
2. Download the latest `DragonRun.jar` from releases
3. Place in your Paper server's `plugins/` folder
4. Configure `plugins/DragonRun/config.yml` with your database credentials
5. Restart your server

## Configuration

Edit `plugins/DragonRun/config.yml`:

```yaml
database:
  host: localhost
  port: 5432
  database: dragonrun
  username: postgres
  password: your_password

game:
  reset-delay-seconds: 10
  starting-aura: 100
```

## Tech Stack

- **Paper API** 1.21
- **PostgreSQL** with HikariCP
- **Adventure API** for rich text formatting
- **Brigadier** for command system
- **Gradle** 8.12 build system

## Development

```bash
# Build the plugin
./gradlew shadowJar

# Output: build/libs/dragon-run-plugin-1.0.0-SNAPSHOT.jar
```

## How It Works

1. Players join the server and start with 100 aura
2. When ANY player dies:
   - They lose aura based on death type (20-50 aura)
   - A roast message is broadcast to all players
   - All bets on the deceased are lost
   - A 10-second countdown begins
   - The world resets and server restarts
3. Achievements award/remove aura permanently
4. Aura persists across all resets in the database

## License

MIT License - See LICENSE file for details

## Credits

Created with Claude Code by Anthropic
