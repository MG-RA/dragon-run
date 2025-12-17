# Dragon Run: Hardcore Minecraft Roguelike

## Project Overview

**Dragon Run** is a hardcore Minecraft server experience where the objective is to kill the Ender Dragon. If any player dies, the entire world resets. The server features a persistent "aura" economy that survives resets, absurd achievements, player betting, and Discord integration.

### Core Concept
- **Objective**: Kill the Ender Dragon to win the run
- **Consequence**: Any player death triggers a full world reset
- **Persistence**: Aura (currency), achievements, and stats persist across resets
- **Social**: Discord bot integration, live stats, betting between players

---

## Architecture

```
┌─────────────────────┐     ┌──────────────────────┐     ┌─────────────────────┐
│  PaperMC Plugin     │────▶│  Stats API Server    │────▶│  Discord Bot        │
│  (Java 21)          │     │  (REST + WebSocket)  │     │  (Python)           │
│                     │◀────│                      │◀────│                     │
└─────────────────────┘     └──────────────────────┘     └─────────────────────┘
         │                           │
         ▼                           ▼
┌─────────────────────┐     ┌──────────────────────┐
│  PaperMC Server     │     │  PostgreSQL          │
│  (1.21.x)           │     │  (Persistent Data)   │
└─────────────────────┘     └──────────────────────┘
         │
         ▼
┌─────────────────────┐
│  Reset Script       │
│  (Bash)             │
└─────────────────────┘
```

---

## Component 1: PaperMC Plugin

### Technology
- **Language**: Java 21 (required for Paper 1.21.x)
- **Server**: PaperMC 1.21.x
- **Build Tool**: Gradle (Kotlin DSL)
- **Dependencies**:
  - Paper API 1.21
  - HikariCP (database connection pooling)
  - Gson (JSON serialization)
  - Java-WebSocket (for real-time events)

### Why PaperMC
- Better performance than vanilla/Spigot (async chunk loading, optimizations)
- Extended API with more events and utilities
- Active development and community
- Adventure API for modern text components
- Native async scheduler support

### Plugin Structure

```
dragon-run-plugin/
├── src/main/java/com/dragonrun/
│   ├── DragonRunPlugin.java          # Main plugin class
│   ├── managers/
│   │   ├── AuraManager.java          # Aura economy system
│   │   ├── AchievementManager.java   # Achievement tracking & granting
│   │   ├── BettingManager.java       # Betting system
│   │   ├── ShopManager.java          # Aura shop
│   │   ├── TitleManager.java         # Player titles
│   │   └── RunManager.java           # Current run state & stats
│   ├── listeners/
│   │   ├── DeathListener.java        # Death events & world reset trigger
│   │   ├── CombatListener.java       # Damage, kills, combat tracking
│   │   ├── ProgressionListener.java  # Dimension changes, dragon events
│   │   ├── MovementListener.java     # Position tracking
│   │   └── MiscListener.java         # Chat, joins, misc events
│   ├── database/
│   │   ├── Database.java             # Database connection & queries
│   │   └── models/
│   │       ├── PlayerData.java       # Persistent player data model
│   │       ├── RunHistory.java       # Run history model
│   │       └── Achievement.java      # Achievement model
│   ├── api/
│   │   ├── WebSocketServer.java      # Real-time event broadcasting
│   │   └── RestApiServer.java        # HTTP API for stats
│   ├── commands/
│   │   ├── AuraCommand.java          # /aura check
│   │   ├── ShopCommand.java          # /shop
│   │   ├── BetCommand.java           # /bet
│   │   ├── StatsCommand.java         # /stats
│   │   └── AchievementsCommand.java  # /achievements
│   └── util/
│       ├── MessageUtil.java          # Formatted messages (Adventure API)
│       └── TimeUtil.java             # Duration formatting
├── src/main/resources/
│   ├── paper-plugin.yml              # Paper plugin descriptor
│   └── config.yml
└── build.gradle.kts
```

### build.gradle.kts

```kotlin
plugins {
    java
    id("io.papermc.paperweight.userdev") version "1.7.1"
    id("com.github.johnrengelman.shadow") version "8.1.1"
}

group = "com.dragonrun"
version = "1.0.0"

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(21))
}

repositories {
    mavenCentral()
    maven("https://repo.papermc.io/repository/maven-public/")
}

dependencies {
    paperweight.paperDevBundle("1.21-R0.1-SNAPSHOT")
    
    implementation("com.zaxxer:HikariCP:5.1.0")
    implementation("org.postgresql:postgresql:42.7.3")
    implementation("com.google.code.gson:gson:2.10.1")
    implementation("org.java-websocket:Java-WebSocket:1.5.6")
}

tasks {
    assemble {
        dependsOn(reobfJar)
    }
    
    shadowJar {
        archiveClassifier.set("")
        relocate("com.zaxxer.hikari", "com.dragonrun.libs.hikari")
        relocate("org.postgresql", "com.dragonrun.libs.postgresql")
    }
    
    processResources {
        val props = mapOf("version" to version)
        inputs.properties(props)
        filteringCharset = "UTF-8"
        filesMatching("paper-plugin.yml") {
            expand(props)
        }
    }
}
```

### paper-plugin.yml

```yaml
name: DragonRun
version: ${version}
main: com.dragonrun.DragonRunPlugin
api-version: "1.21"
description: Hardcore roguelike - kill the dragon or reset the world
author: YourName
website: https://github.com/yourname/dragon-run

load: STARTUP

permissions:
  dragonrun.admin:
    description: Admin commands
    default: op
  dragonrun.aura:
    description: Check aura
    default: true
  dragonrun.shop:
    description: Use shop
    default: true
  dragonrun.bet:
    description: Place bets
    default: true
  dragonrun.stats:
    description: View stats
    default: true
```

### Core Systems

#### Paper-Specific API Usage

The plugin leverages Paper's extended API for better performance and cleaner code:

```java
// Adventure API for text components (no legacy color codes)
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import net.kyori.adventure.text.format.TextDecoration;
import net.kyori.adventure.title.Title;

// Sending styled messages
Component message = Component.text()
    .append(Component.text("✨ +100 aura ", NamedTextColor.LIGHT_PURPLE))
    .append(Component.text("(killed the dragon)", NamedTextColor.GRAY))
    .build();
player.sendMessage(message);

// Titles with Adventure
Title title = Title.title(
    Component.text("ACHIEVEMENT!", NamedTextColor.GOLD, TextDecoration.BOLD),
    Component.text("Blaze It", NamedTextColor.YELLOW),
    Title.Times.times(Duration.ofMillis(500), Duration.ofSeconds(2), Duration.ofMillis(500))
);
player.showTitle(title);

// Action bar
player.sendActionBar(Component.text("Health: ", NamedTextColor.RED)
    .append(Component.text("❤❤❤❤❤", NamedTextColor.DARK_RED)));

// Async scheduling (Paper's async scheduler)
Bukkit.getAsyncScheduler().runAtFixedRate(plugin, task -> {
    broadcastPositions();
}, 0, 500, TimeUnit.MILLISECONDS);

// Entity scheduler (per-entity tick scheduling)
entity.getScheduler().run(plugin, task -> {
    // Runs on entity's tick thread
}, null);

// Async chunk loading
world.getChunkAtAsync(x, z).thenAccept(chunk -> {
    // Process chunk asynchronously
});
```

#### 1. Aura Manager

The aura system is the persistent economy. Aura can go negative.

```java
public class AuraManager {
    
    // Core methods
    int getAura(UUID uuid);
    void addAura(UUID uuid, int amount, String reason);
    void removeAura(UUID uuid, int amount, String reason);
    
    // Aura change triggers announcements:
    // - Gains >= 100 aura: server broadcast
    // - Losses <= -50 aura: server broadcast with roast
    // - Milestone thresholds: title unlocks
    
    // Milestones (positive)
    // 100: "Aura Student"
    // 500: "Aura Haver"
    // 1000: "Aura Merchant"
    // 2500: "Aura Lord"
    // 5000: "Aura Emperor"
    // 10000: "Aura Deity"
    
    // Milestones (negative)
    // -100: "Aura Debt"
    // -500: "Aura Bankrupt"
    // -1000: "Aura Vampire"
    // -2500: "Aura Void"
    // -5000: "Aura Demon"
}
```

#### 2. Achievement Manager

Achievements grant or remove aura. Some are progression-based, others are meme/shame achievements.

```java
public class Achievement {
    String id;
    String name;
    String description;
    int auraReward;        // Can be negative for shame achievements
    boolean repeatable;    // Most are once per lifetime, some per-run
}
```

**Achievement Categories**:

##### Progression (Positive Aura)
| ID | Name | Description | Aura |
|----|------|-------------|------|
| FIRST_BLOOD | First Blood | First mob kill of the run | +10 |
| INTO_THE_NETHER | Went to Brazil | Enter the Nether | +25 |
| INTO_THE_VOID | Cooked or Get Cooked | Enter the End | +50 |
| DRAGON_SLAYER | GGs in Chat | Kill the Ender Dragon | +500 |

##### Combat & Skill (Positive Aura)
| ID | Name | Description | Aura |
|----|------|-------------|------|
| CLUTCH_MASTER | CLUTCH GENE ACTIVATED | Survive at half heart 3 times | +100 |
| BLAZE_HUNTER | Blaze It | Kill 10 blazes | +69 |
| WITHER_SKULL | Skull Emoji | Get a wither skeleton skull | +35 |
| CREEPER_SURVIVOR | Creeper? Aw Man... | Survive a creeper at 1 heart | +75 |
| MLG_WATER | MLG Water Bucket | Save yourself from fall damage with water | +80 |
| PEARL_CLUTCH | Pearls Before Swine | Ender pearl save from death | +90 |

##### Deaths - Shame Achievements (Negative Aura)
| ID | Name | Description | Aura |
|----|------|-------------|------|
| BED_BOOM | Skill Issue | Die to bed explosion in Nether | -15 |
| GRAVEL_DEATH | Real. | Die to gravel | -20 |
| CACTUS_DEATH | Touch Grass (It Hurt) | Die to cactus | -25 |
| BERRY_DEATH | Bro Died to a Bush | Die to sweet berry bush | -50 |
| PUFFERFISH | He Ate the Pufferfish | Die to pufferfish | -30 |
| GOLEM_PUNCH | Fucked Around, Found Out | Die to iron golem you provoked | -40 |
| DROWNED | Can't Swim | Drown | -20 |
| STARVE | Just Eat??? | Starve to death | -50 |
| FALL_DAMAGE | Gravity Check Failed | Die to fall damage | -15 |
| VOID_DEATH | See You in the Backrooms | Fall into void | -30 |
| ZOMBIE_DEATH | It's Literally Walking | Die to regular zombie | -60 |
| SILVERFISH | Bro Lost to a Bug | Die to silverfish | -80 |

##### Meme Achievements (Mixed Aura)
| ID | Name | Description | Aura |
|----|------|-------------|------|
| OHIO | Only in Ohio | Die within 30 seconds of joining | -100 |
| LITERALLY_1984 | Literally 1984 | Get killed by another player | 0 |
| NO_RIZZ | Zero Rizz | Fail villager trade 5 times | -10 |
| SKILL_ISSUE | Massive Skill Issue | Die 3 times in one run | -75 |
| NPC_BEHAVIOR | NPC Behavior | Walk into same lava twice | -100 |
| MAIN_CHARACTER | Main Character Syndrome | Solo kill the dragon | +300 |
| SIDE_CHARACTER | Side Character Energy | Contribute nothing to dragon kill | -50 |
| REAL_ONE | You're a Real One | Give last food to another player | +150 |
| SNAKE | Snake in the Grass | Kill player who trusted you | -200 |
| LOWKEY_GOATED | Lowkey Goated | Get 5 achievements in one run | +100 |
| HIGHKEY_COOKED | Highkey Cooked | Get 5 negative achievements in one run | -150 |
| RATIO | Ratio + L + Fell Off | Die while someone fights dragon | -80 |
| UNDERSTOOD_ASSIGNMENT | Understood the Assignment | Enter End with full diamond+ | +120 |
| SLAY | Slay | Kill 100 mobs in one run | +50 |
| ATE_AND_LEFT_NO_CRUMBS | Ate and Left No Crumbs | Perfect dragon fight, no damage | +500 |
| ITS_GIVING | It's Giving... Nothing | Enter dragon fight with stone tools | -40 |
| DELULU | Delulu is the Solulu | Bet on yourself and win | +200 |
| COPIUM | Maximum Copium | Bet on yourself and lose | -50 |
| NO_CAP | No Cap, Fr Fr | Kill dragon under 20 minutes | +250 |
| BIG_YIKES | Big Yikes | Cause world reset within 5 minutes | -150 |
| CAUGHT_IN_4K | Caught in 4K | Die while typing in chat | -100 |
| EMOTIONAL_DAMAGE | Emotional Damage | Watch someone else kill dragon after you die | -50 |
| FANUM_TAX | Fanum Tax | Steal from another player's chest | +30 |
| GRIDDY | Hit the Griddy | Kill dragon while at 1 heart | +1000 |
| MORBIUS | It's Morbin' Time | Play during 3 AM server time | +69 |

#### 3. Betting Manager

Players can bet aura on outcomes.

```java
public enum BetType {
    WINNER,           // This player kills the dragon
    FIRST_DEATH,      // This player dies first  
    SURVIVES_HOUR,    // This player survives 1 hour
    ENTERS_END_FIRST  // First to enter the End
}

public class Bet {
    UUID bettorId;
    UUID targetPlayerId;
    int amount;
    BetType type;
    long placedAt;
}
```

**Betting Rules**:
- Minimum bet: 10 aura
- One active bet per type per player
- Bets lock when someone enters the End
- Winning bets pay 2x
- Lost bets are lost
- Bets refund if run ends without resolution (server crash, etc.)

#### 4. Shop Manager

Players spend aura on items and perks.

**Starter Items** (given at run start):
| ID | Name | Price | Description | Effect |
|----|------|-------|-------------|--------|
| starter_bread | Poverty Pack | 30 | Some bread | 5 bread |
| starter_drip | Minor Drip | 75 | Stone tools | Stone pick + sword |
| starter_copium | Copium Canister | 100 | Emergency pearl | 1 ender pearl |
| boat | Emergency Boat | 40 | Aquatic escape | 1 oak boat |
| milk | Lactose Tolerance | 25 | Clears effects | 1 milk bucket |

**Meme Items**:
| ID | Name | Price | Description |
|----|------|-------|-------------|
| dirt | Premium Dirt | 1 | Just dirt. Why? |
| sponge | Emotional Support Sponge | 50 | He believes in you |
| cookie | Suspicious Cookie | 15 | Trust me bro |
| totem_of_coping | Totem of Coping | 500 | It's psychological (actually works) |
| rizz_sword | Sword of Rizz | 300 | +10 charisma, +0 damage |
| no_bitches | No Maidens? | 69 | A single rose |
| literally_water | Literally Just Water | 5 | Hydrate or diedrate |
| ohio_pass | Ohio Pass | 200 | Spawn in cursed biome |

**Permanent Perks**:
| ID | Name | Price | Effect |
|----|------|-------|--------|
| double_aura | Aura Multiplier | 2000 | 2x aura gains |
| shame_reduction | Shame Dampener | 1500 | 50% less negative aura |
| bet_insurance | Bet Insurance | 1000 | Refund 50% of lost bets |
| death_announcement | Main Character Death | 800 | Fancy death messages |

**Titles** (purchasable):
| ID | Name | Price | Display |
|----|------|-------|---------|
| title_goat | GOAT | 1000 | §7[§6§lGOAT§7] |
| title_npc | NPC | 100 | §7[§8NPC§7] |
| title_ohio | Ohio Final Boss | 500 | §7[§c§lOhio Final Boss§7] |
| title_ratio | Ratio | 250 | §7[§cRatio§7] |
| title_bussin | Bussin | 300 | §7[§dBussin§7] |

#### 5. Run Manager

Tracks current run state and per-player stats.

```java
public class PlayerRunStats {
    UUID playerId;
    String playerName;
    long joinedAt;
    boolean alive;
    int mobKills;
    int playerKills;
    double damageDealt;
    double damageTaken;
    int blocksPlaced;
    int blocksBroken;
    int clutchCount;           // Times survived at <= 1 heart
    Map<String, Integer> mobKillsByType;
    Set<String> achievementsThisRun;
    List<String> dimensionsVisited;
    boolean enteredNether;
    boolean enteredEnd;
}

public class RunState {
    long startTime;
    int deathCount;            // For spectator deaths (after first real death)
    boolean dragonAlive;
    float dragonHealth;
    UUID firstDeathPlayer;
    UUID dragonKiller;
    String endReason;          // "DRAGON_KILLED", "PLAYER_DEATH", "MANUAL_RESET"
}
```

#### 6. Death System & World Reset

When a player dies:

1. **Announce death with roast** based on death cause
2. **Grant shame achievement** if applicable
3. **Deduct aura** based on death type
4. **Broadcast world reset warning** (10 second countdown)
5. **Write reset trigger file** for external script
6. **Kick all players** with message
7. **Shutdown server**

**Death Roasts by Cause**:
```java
FALL -> [
    "forgot how gravity works",
    "failed the vibe check with the ground",
    "thought they had MLG water (they didn't)"
]
DROWNING -> [
    "forgor they need oxygen 💀",
    "went full NPC in water"
]
LAVA -> [
    "tried to swim in the forbidden orange juice",
    "took 'getting cooked' too literally"
]
ENTITY_EXPLOSION -> [
    "got ratio'd by a creeper",
    "received an explosive L"
]
STARVATION -> [
    "forgor food exists 💀",
    "was too busy to eat. Certified NPC."
]
VOID -> [
    "went to the backrooms",
    "fell into the abyss (real)"
]
```

#### 7. WebSocket Events

The plugin broadcasts these events in real-time:

| Event | Frequency | Data |
|-------|-----------|------|
| `positions` | Every 500ms | All player positions, health, food, dimension |
| `death` | On death | Player, cause, roast, aura lost |
| `achievement` | On unlock | Player, achievement, description, aura change |
| `bet_placed` | On bet | Bettor, target, type, amount |
| `bet_resolved` | On resolution | Winners, losers, payouts |
| `dimension_entry` | On change | Player, dimension |
| `dragon_damage` | On damage | Dragon health percentage |
| `dragon_killed` | On kill | Killer, duration, stats |
| `run_reset` | On reset | Caused by, run stats |
| `chat` | On message | Player, message |
| `player_join` | On join | Player, their aura, titles |
| `player_leave` | On leave | Player |

#### 8. Commands

| Command | Permission | Description |
|---------|------------|-------------|
| `/aura [player]` | dragonrun.aura | Check aura balance |
| `/shop` | dragonrun.shop | Open shop GUI |
| `/buy <item>` | dragonrun.shop | Buy item directly |
| `/bet <player> <type> <amount>` | dragonrun.bet | Place a bet |
| `/bets` | dragonrun.bet | View your active bets |
| `/stats [player]` | dragonrun.stats | View run/lifetime stats |
| `/achievements` | dragonrun.achievements | View achievements |
| `/title <title>` | dragonrun.title | Set display title |
| `/leaderboard <type>` | dragonrun.leaderboard | View leaderboards |

---

## Component 2: Database Schema

### Technology
- PostgreSQL 14+

### Schema

```sql
-- Player persistent data
CREATE TABLE players (
    uuid VARCHAR(36) PRIMARY KEY,
    username VARCHAR(16) NOT NULL,
    aura INT DEFAULT 100,
    total_runs INT DEFAULT 0,
    total_deaths INT DEFAULT 0,
    dragons_killed INT DEFAULT 0,
    total_mobs_killed INT DEFAULT 0,
    total_playtime_seconds BIGINT DEFAULT 0,
    equipped_title VARCHAR(50),
    first_joined TIMESTAMP DEFAULT NOW(),
    last_seen TIMESTAMP DEFAULT NOW()
);

-- Purchased items/perks
CREATE TABLE purchases (
    id SERIAL PRIMARY KEY,
    uuid VARCHAR(36) REFERENCES players(uuid),
    item_id VARCHAR(50) NOT NULL,
    price INT NOT NULL,
    purchased_at TIMESTAMP DEFAULT NOW()
);

-- Achievements earned (lifetime)
CREATE TABLE achievements_earned (
    uuid VARCHAR(36) REFERENCES players(uuid),
    achievement_id VARCHAR(50) NOT NULL,
    earned_at TIMESTAMP DEFAULT NOW(),
    run_id INT,
    PRIMARY KEY (uuid, achievement_id)
);

-- Run history
CREATE TABLE run_history (
    run_id SERIAL PRIMARY KEY,
    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP,
    duration_seconds INT,
    outcome VARCHAR(20), -- 'DRAGON_KILLED', 'PLAYER_DEATH', 'MANUAL_RESET'
    ended_by_uuid VARCHAR(36),
    dragon_killer_uuid VARCHAR(36),
    peak_players INT,
    total_deaths INT DEFAULT 0
);

-- Per-run player stats (for detailed history)
CREATE TABLE run_participants (
    run_id INT REFERENCES run_history(run_id),
    uuid VARCHAR(36) REFERENCES players(uuid),
    joined_at TIMESTAMP,
    alive_duration_seconds INT,
    mob_kills INT DEFAULT 0,
    damage_dealt DOUBLE PRECISION DEFAULT 0,
    damage_taken DOUBLE PRECISION DEFAULT 0,
    entered_nether BOOLEAN DEFAULT FALSE,
    entered_end BOOLEAN DEFAULT FALSE,
    death_cause VARCHAR(50),
    PRIMARY KEY (run_id, uuid)
);

-- Active bets (cleared on run end)
CREATE TABLE active_bets (
    id SERIAL PRIMARY KEY,
    run_id INT REFERENCES run_history(run_id),
    bettor_uuid VARCHAR(36) REFERENCES players(uuid),
    target_uuid VARCHAR(36) REFERENCES players(uuid),
    bet_type VARCHAR(20) NOT NULL,
    amount INT NOT NULL,
    placed_at TIMESTAMP DEFAULT NOW()
);

-- Bet history
CREATE TABLE bet_history (
    id SERIAL PRIMARY KEY,
    run_id INT REFERENCES run_history(run_id),
    bettor_uuid VARCHAR(36) REFERENCES players(uuid),
    target_uuid VARCHAR(36) REFERENCES players(uuid),
    bet_type VARCHAR(20) NOT NULL,
    amount INT NOT NULL,
    won BOOLEAN,
    payout INT,
    resolved_at TIMESTAMP DEFAULT NOW()
);

-- Discord account linking
CREATE TABLE discord_links (
    uuid VARCHAR(36) PRIMARY KEY REFERENCES players(uuid),
    discord_id VARCHAR(20) NOT NULL UNIQUE,
    linked_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_players_aura ON players(aura DESC);
CREATE INDEX idx_players_dragons ON players(dragons_killed DESC);
CREATE INDEX idx_run_history_started ON run_history(started_at DESC);
CREATE INDEX idx_achievements_achievement ON achievements_earned(achievement_id);
```

---

## Component 3: Stats API Server

### Technology
- Python 3.11+ with FastAPI
- Or embedded in Java plugin using Javalin/Spark

### Endpoints

#### REST API

```
GET  /api/health                    - Health check
GET  /api/live                      - Current run status
GET  /api/players                   - List all players
GET  /api/player/{username}         - Player stats
GET  /api/player/{username}/history - Player run history
GET  /api/leaderboard/{type}        - Leaderboards (aura, dragons, deaths, shame)
GET  /api/achievements              - All achievements list
GET  /api/shop                      - Shop items
POST /api/bet                       - Place bet (requires discord link)
GET  /api/bets/active               - Active bets this run
GET  /api/run/current               - Current run details
GET  /api/run/{id}                  - Historical run details
```

#### WebSocket

```
ws://server:8585/events

// Client subscribes by connecting
// Server pushes all events automatically

// Message format:
{
    "event": "death",
    "data": { ... },
    "timestamp": 1699999999999
}
```

---

## Component 4: Discord Bot

### Technology
- Python 3.11+
- discord.py 2.x
- aiohttp for API calls
- websockets for real-time events

### Bot Structure

```
discord-bot/
├── bot.py                 # Main bot entry
├── cogs/
│   ├── stats.py          # Stats commands
│   ├── betting.py        # Betting commands
│   ├── shop.py           # Shop commands
│   ├── live.py           # Live status commands
│   └── events.py         # WebSocket event handler
├── utils/
│   ├── api.py            # API client
│   ├── embeds.py         # Embed builders
│   └── formatters.py     # Aura/time formatting
└── config.py             # Configuration
```

### Commands

| Command | Description |
|---------|-------------|
| `!aura [username]` | Check aura balance |
| `!stats [username]` | Player statistics |
| `!live` | Current run status with player positions |
| `!leaderboard [type]` | Aura, dragons, deaths, shame |
| `!shame` | Hall of shame (lowest aura) |
| `!achievements [username]` | View achievements |
| `!bet <player> <type> <amount>` | Place a bet |
| `!bets` | View your active bets |
| `!shop` | View shop |
| `!buy <item>` | Purchase item (applies next run) |
| `!link <minecraft_username>` | Link Discord to MC account |
| `!history [username]` | Run history |

### Event Announcements

The bot listens to WebSocket events and posts to a configured channel:

**Death Event**:
```
☠️ COOKED ☠️
━━━━━━━━━━━━━━━━━━━━
PlayerName took 'getting cooked' too literally

Aura Lost: -25
New Aura: 847

World resetting... gg go next
```

**Achievement Event**:
```
🏆 Achievement Unlocked!
━━━━━━━━━━━━━━━━━━━━
PlayerName earned Blaze It
"Kill 10 blazes"

Aura: +69
```

**Shame Achievement**:
```
💀 Achievement Unlocked (Derogatory)
━━━━━━━━━━━━━━━━━━━━
PlayerName earned Bro Died to a Bush
"Die to sweet berry bush"

Aura: -50
```

**Dragon Kill**:
```
@everyone
🐉 DRAGON DOWN 🐉
━━━━━━━━━━━━━━━━━━━━
PlayerName KILLED THE ENDER DRAGON

GGs IN CHAT ONLY

Run Duration: 47m 32s
Total Deaths: 0
Aura Gained: +500 ✨

They understood the assignment
```

**Bet Placed**:
```
🎰 Bet Placed
━━━━━━━━━━━━━━━━━━━━
Bettor bet 100 aura that TargetPlayer will: WIN

No cap, good luck fr fr
```

---

## Component 5: Reset Script

### Technology
- Bash script
- Runs as wrapper around server

### Script

```bash
#!/bin/bash
# start-server.sh

WORLD_DIRS="world world_nether world_the_end"
SERVER_JAR="paper-1.21.jar"
JAVA_OPTS="-Xmx6G -Xms2G -XX:+UseG1GC -XX:+ParallelRefProcEnabled -XX:MaxGCPauseMillis=200"

# Paper recommended flags
PAPER_FLAGS="-XX:+UnlockExperimentalVMOptions -XX:+DisableExplicitGC -XX:+AlwaysPreTouch"
PAPER_FLAGS="$PAPER_FLAGS -XX:G1NewSizePercent=30 -XX:G1MaxNewSizePercent=40"
PAPER_FLAGS="$PAPER_FLAGS -XX:G1HeapRegionSize=8M -XX:G1ReservePercent=20"
PAPER_FLAGS="$PAPER_FLAGS -XX:G1MixedGCCountTarget=4 -XX:InitiatingHeapOccupancyPercent=15"
PAPER_FLAGS="$PAPER_FLAGS -XX:G1MixedGCLiveThresholdPercent=90 -XX:G1RSetUpdatingPauseTimePercent=5"
PAPER_FLAGS="$PAPER_FLAGS -XX:SurvivorRatio=32 -XX:+PerfDisableSharedMem -XX:MaxTenuringThreshold=1"
PAPER_FLAGS="$PAPER_FLAGS -Dusing.aikars.flags=https://mcflags.emc.gs -Daikars.new.flags=true"

while true; do
    echo "[DragonRun] Starting PaperMC server..."
    java $JAVA_OPTS $PAPER_FLAGS -jar $SERVER_JAR --nogui
    
    EXIT_CODE=$?
    
    if [ -f "RESET_TRIGGER" ]; then
        echo "[DragonRun] Reset triggered, deleting worlds..."
        
        # Read trigger info
        RESET_INFO=$(cat RESET_TRIGGER)
        echo "[DragonRun] Reset caused by: $RESET_INFO"
        
        # Delete world folders
        for dir in $WORLD_DIRS; do
            if [ -d "$dir" ]; then
                rm -rf "$dir"
                echo "[DragonRun] Deleted $dir"
            fi
        done
        
        # Remove trigger file
        rm RESET_TRIGGER
        
        echo "[DragonRun] World reset complete. Restarting in 5 seconds..."
        sleep 5
    else
        echo "[DragonRun] Server stopped without reset trigger (exit code: $EXIT_CODE)"
        echo "[DragonRun] Restarting in 10 seconds... (Ctrl+C to cancel)"
        sleep 10
    fi
done
```

---

## Component 6: PaperMC Server Setup

### Installation

```bash
# Download latest Paper 1.21
mkdir dragon-run-server && cd dragon-run-server
curl -o paper-1.21.jar https://api.papermc.io/v2/projects/paper/versions/1.21/builds/latest/downloads/paper-1.21-latest.jar

# First run to generate files
java -jar paper-1.21.jar --nogui
# Accept EULA
echo "eula=true" > eula.txt
```

### server.properties

```properties
# Core settings
server-port=25565
max-players=20
motd=§c§lDRAGON RUN §7- §fKill the dragon or die trying
difficulty=hard
hardcore=false  # We handle this ourselves
pvp=true
spawn-protection=0

# Performance (Paper handles most of this)
view-distance=10
simulation-distance=8
network-compression-threshold=256

# Gameplay
allow-flight=false
spawn-monsters=true
spawn-animals=true

# Query for external stats (optional)
enable-query=true
query.port=25565

# RCON (optional, for external management)
enable-rcon=false
rcon.password=changeme
rcon.port=25575
```

### config/paper-global.yml (key settings)

```yaml
chunk-loading:
  autoconfig-send-distance: true
  enable-frustum-priority: false
  global-max-chunk-load-rate: -1.0
  global-max-chunk-send-rate: -1.0
  global-max-concurrent-loads: 500.0
  max-concurrent-sends: 2
  min-load-radius: 2
  player-max-chunk-load-rate: -1.0
  player-max-concurrent-loads: 20.0
  target-player-chunk-send-rate: 100.0

packet-limiter:
  kick-message: '<red>You are sending too many packets!'
  limits:
    all:
      action: KICK
      interval: 7.0
      max-packet-rate: 500.0
    PacketPlayInAutoRecipe:
      action: DROP
      interval: 4.0
      max-packet-rate: 5.0

unsupported-settings:
  allow-permanent-block-break-exploits: false
  allow-piston-duplication: false
  perform-username-validation: true

watchdog:
  early-warning-delay: 10000
  early-warning-every: 5000
```

### config/paper-world-defaults.yml (key settings)

```yaml
entities:
  spawning:
    spawn-limits:
      monster: 70
      creature: 10
      ambient: 15
      water-creature: 5

environment:
  optimize-explosions: true
  treasure-maps:
    enabled: true
    find-already-discovered: false

chunks:
  auto-save-interval: 6000
  delay-chunk-unloads-by: 10s
  entity-per-chunk-save-limit:
    experience_orb: 16
    arrow: 16
    
misc:
  redstone-implementation: ALTERNATE_CURRENT
  fix-climbing-bypassing-cramming-rule: true
  
tick-rates:
  mob-spawner: 1
  behavior:
    villager:
      validatenearbypoi: -1
```

---

## Configuration

### Plugin config.yml

```yaml
# Database
database:
  host: localhost
  port: 5432
  name: dragonrun
  user: dragonrun
  password: changeme

# API Server
api:
  rest-port: 8080
  websocket-port: 8585
  
# Game Settings
game:
  reset-delay-seconds: 10
  starting-aura: 100
  min-bet: 10
  bet-multiplier: 2.0
  
# Position broadcast interval (ticks, 20 = 1 second)
position-broadcast-interval: 10

# Death messages
death-messages:
  enabled: true
  roasts: true
  
# Achievement announcements
achievements:
  broadcast-positive: true
  broadcast-negative: true
  min-broadcast-aura: 50  # Only broadcast if |aura change| >= this
```

### Discord bot config.py

```python
BOT_TOKEN = "your-discord-bot-token"
GUILD_ID = 123456789
ANNOUNCEMENT_CHANNEL_ID = 123456789
API_BASE_URL = "http://your-server:8080/api"
WEBSOCKET_URL = "ws://your-server:8585/events"
```

---

## Development Phases

### Phase 1: Core Plugin (MVP)
1. Set up Gradle project with paperweight-userdev
2. Basic plugin structure with Paper API
3. Database connection and schema setup
4. Death detection and world reset trigger
5. Basic aura system (add/remove/check)
6. Reset script with Aikar's flags
7. Test full reset cycle

### Phase 2: Achievements & Shop
1. Achievement manager with all achievements
2. Achievement detection listeners (use Paper's extended events)
3. Shop system with Adventure API GUI
4. Starter items given on join
5. Permanent perks system
6. Title system with Adventure components

### Phase 3: Betting System
1. Betting manager
2. Bet placement and validation
3. Bet resolution on events
4. Bet history tracking

### Phase 4: API & WebSocket
1. REST API endpoints (embedded Javalin or separate service)
2. WebSocket server for real-time events
3. Position broadcasting (use Paper's async scheduler)
4. Event broadcasting

### Phase 5: Discord Bot
1. Basic bot structure with discord.py
2. Stats commands
3. WebSocket event listener
4. Channel announcements with rich embeds
5. Betting commands
6. Account linking

### Phase 6: Polish
1. Scoreboards with Adventure API
2. Boss bars for dragon health
3. Leaderboards
4. Run history detailed view
5. Sound effects and particles
6. Performance optimization

---

## Testing Checklist

### Plugin
- [ ] Player death triggers world reset
- [ ] Aura persists across resets
- [ ] Achievements grant correctly
- [ ] Negative achievements on specific deaths
- [ ] Shop purchases work
- [ ] Starter items given on run start
- [ ] Bets place and resolve correctly
- [ ] Dragon kill ends run successfully
- [ ] WebSocket events broadcast

### Discord Bot
- [ ] Commands respond correctly
- [ ] Events post to channel
- [ ] Betting works through Discord
- [ ] Account linking works
- [ ] Leaderboards display correctly

### Integration
- [ ] Full run: join → play → die → reset → rejoin
- [ ] Full run: join → play → kill dragon → victory
- [ ] Betting flow: place bet → outcome → payout
- [ ] Stats persist across multiple runs

---

## Future Ideas

- **Shame Cam**: Spectator mode that auto-follows lowest aura player
- **Random Events**: Meteor showers, mob waves, temporary buffs/debuffs
- **Seasons**: Monthly resets of aura leaderboard with rewards
- **Twitch Integration**: Channel point redemptions affect game
- **Live Map**: Web dashboard showing real-time player positions
- **Voice Lines**: TTS announcements for deaths and achievements
- **Bounties**: Players can put aura bounties on other players
- **Guilds/Teams**: Group betting and shared achievements