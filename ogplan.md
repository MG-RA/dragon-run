I want to design a local AI agent (14B ministral 3, 32k context, tool use)

for my minecraft server, the server is run using papermc server

in addition to be using papermc server i develop a custom plugin using papermc plugin system

the plugin is for a custom gamemode I want to do here are the basic of the gamemode for key context: the objective is to kill the ender dragon without dying in a small party of players, less than 10
if any of the players die, the run is reset, they are teleported back to the lobby and a new hardcore world is generated for starting a new run.

some more minecraft context: the win condition is that all players survive from the begining and quickly speed run minecraft to reach the end dimension and kill the dragon to win the run, the progression to get there is something like this, start run get the usuals wood, stone tools, get some food and resources, mine for iron and diamonds, enchantments, armors, nether portal, search for and enderman spawning biome in the nether and also a nether forth for a blaze spawner, craft the ender eyes needed to search and find the end forth and portal, to the end dimension to finally kill the dragon.

How the AI director, fits in, i want something unique and fresh, no only like some chatbot or so, something chaotic, nor evil or good, ambiguous, i like the inspirations of Eris the goddess of discord

The agent is going to be locally it needs to respond to players in the chat quickly, in needs to remember the players chat from different players by name, and have a context window for short memory that contains the latest N players messages, the agent also will have a connection to a websocket, this is serve by the minecraft papermc plugin part, it can receive events, and run commands available design for the agent, some of the tools
 

this could be expanded by adding agent commands in the plugin

```
- broadcast: For commentary and general announcements
- message: For targeted player communication
- spawn mob: To add challenge/enhance drama
- give: To provide support/reward skill
- effect: To create special conditions
- lightning: For dramatic moments
- weather: To change environment mood
- firework: For celebrations/positive reinforcement
```

also there a bunch of listeners for player damage, achievements, deaths, joining, dimension, change, etc, this can be also expanded by additional plugin code

Another important detail is that the plugin has access to a postgress db for storing data

```
-- Dragon Run Database Schema

-- Players table - persistent player data
CREATE TABLE IF NOT EXISTS players (
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
CREATE TABLE IF NOT EXISTS purchases (
    id SERIAL PRIMARY KEY,
    uuid VARCHAR(36) REFERENCES players(uuid),
    item_id VARCHAR(50) NOT NULL,
    price INT NOT NULL,
    purchased_at TIMESTAMP DEFAULT NOW()
);

-- Achievements earned (lifetime)
CREATE TABLE IF NOT EXISTS achievements_earned (
    uuid VARCHAR(36) REFERENCES players(uuid),
    achievement_id VARCHAR(50) NOT NULL,
    earned_at TIMESTAMP DEFAULT NOW(),
    run_id INT,
    PRIMARY KEY (uuid, achievement_id)
);

-- Run history
CREATE TABLE IF NOT EXISTS run_history (
    run_id SERIAL PRIMARY KEY,
    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMP,
    duration_seconds INT,
    outcome VARCHAR(20),
    ended_by_uuid VARCHAR(36),
    dragon_killer_uuid VARCHAR(36),
    world_name VARCHAR(100),
    world_seed BIGINT,
    peak_players INT DEFAULT 0,
    total_deaths INT DEFAULT 0
);

-- Per-run player stats (for detailed history)
CREATE TABLE IF NOT EXISTS run_participants (
    run_id INT REFERENCES run_history(run_id),
    uuid VARCHAR(36) REFERENCES players(uuid),
    joined_at TIMESTAMP DEFAULT NOW(),
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
CREATE TABLE IF NOT EXISTS active_bets (
    id SERIAL PRIMARY KEY,
    run_id INT REFERENCES run_history(run_id),
    bettor_uuid VARCHAR(36) REFERENCES players(uuid),
    target_uuid VARCHAR(36) REFERENCES players(uuid),
    bet_type VARCHAR(20) NOT NULL,
    amount INT NOT NULL,
    placed_at TIMESTAMP DEFAULT NOW()
);

-- Bet history
CREATE TABLE IF NOT EXISTS bet_history (
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

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_players_aura ON players(aura DESC);
CREATE INDEX IF NOT EXISTS idx_players_dragons ON players(dragons_killed DESC);
CREATE INDEX IF NOT EXISTS idx_run_history_started ON run_history(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_achievements_achievement ON achievements_earned(achievement_id);

```

this is a development schema and is in active development, changes can be implemented

the agent could have long term memory with the database if needed, also to game information like aura, run number, past run information, and summaries, to include in the context memory window

more on the role of the agent, here the behaviors i want to see, a kind of cyber jester trickster archetype, teasing, chaotic, silly, fun and scary, paradox. maybe it hides behind masks, and multiple personalities to mess with players, it should be actively engaging in the run and take part as a character, it should not kill people but almost bring them to death sometimes help, or creates chaos, pro actively speak when whatever event is worthy of a comment, use a tool or multiple for responses and player interactions.

regarding how the tools work with the game is that the minecraft plugin host a websocket that can send the events of the papermc listeners to the web socket for processing, but it also has an built command system for execution AI commands from the websocket to use the brigadier api so a  command tree is created and used for this, so we can bind the tools to the websocket and expose them to the agent, all papermc apis and tools and bukkit, can be used for this project to increase the player interaction and experience, for example using worlds from bukkit the default server world is the lobby world where players are in a hub map in creative waiting for a new run to start, players use the /vote command to vote and start a new run, the plugin generate a new hardcore world using bukkit and teleports players in survival there to start the run.

finals, notes:

note that the workdir you are is for the papermc plugin with all the java code for it, in the folder director is located a python project using uv for the agent code, also test a testserver folder for testing the project, you can edit the plugin or director code as needed, i currently have a broken version of the agent and a sub folder call v2 with template from langgraph cli, i will like to use langraph cli dev to run the agent in studio and test it that way also but in game too, clean the unused files.

the model is a mistral mode of 14b with tool use 32k context, running with 16gb vram,  ideally the agent should not be using the gpu inferance 100% of the time but it should react quickly to chat and critical events