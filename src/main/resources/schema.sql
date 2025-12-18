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

-- Discord account linking
CREATE TABLE IF NOT EXISTS discord_links (
    uuid VARCHAR(36) PRIMARY KEY REFERENCES players(uuid),
    discord_id VARCHAR(20) NOT NULL UNIQUE,
    linked_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_players_aura ON players(aura DESC);
CREATE INDEX IF NOT EXISTS idx_players_dragons ON players(dragons_killed DESC);
CREATE INDEX IF NOT EXISTS idx_run_history_started ON run_history(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_achievements_achievement ON achievements_earned(achievement_id);
