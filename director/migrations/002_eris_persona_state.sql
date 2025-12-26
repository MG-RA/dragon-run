-- Migration 002: Eris Persona State
-- Adds betrayal debt tracking and prophecy system for v1.1 graph architecture
--
-- Run this after 001_initial_schema.sql

-- Betrayal debt tracking (persists across runs)
-- Each mask type accumulates debt that influences future behavior
CREATE TABLE IF NOT EXISTS eris_betrayal_debt (
    player_uuid VARCHAR(36) NOT NULL,
    mask_type VARCHAR(20) NOT NULL,  -- 'TRICKSTER', 'PROPHET', 'FRIEND', 'CHAOS_BRINGER', 'OBSERVER', 'GAMBLER'
    debt_value INT DEFAULT 0 CHECK (debt_value >= 0 AND debt_value <= 100),
    last_updated TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (player_uuid, mask_type)
);

-- Prophecy state (persists across runs)
-- Tracks prophecies made by Eris and their fulfillment
CREATE TABLE IF NOT EXISTS eris_prophecies (
    id SERIAL PRIMARY KEY,
    player_uuid VARCHAR(36) NOT NULL,
    prophecy_text TEXT NOT NULL,
    prophecy_type VARCHAR(30),  -- 'doom', 'glory', 'betrayal', 'warning', 'blessing'
    run_id INT,  -- Optional: which run the prophecy was made in
    is_fulfilled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    fulfilled_at TIMESTAMP
);

-- Run-level Eris state (for analytics/debugging)
-- Tracks Eris behavior metrics per run
CREATE TABLE IF NOT EXISTS eris_run_state (
    run_id INT PRIMARY KEY,
    peak_chaos INT DEFAULT 0 CHECK (peak_chaos >= 0 AND peak_chaos <= 100),
    total_interventions INT DEFAULT 0,
    protections_used INT DEFAULT 0,
    respawns_used INT DEFAULT 0,
    final_chaos INT DEFAULT 0 CHECK (final_chaos >= 0 AND final_chaos <= 100)
);

-- Player fear history (for analytics - optional, can be disabled)
-- Logs fear level changes for post-game analysis
CREATE TABLE IF NOT EXISTS eris_player_fear_log (
    id SERIAL PRIMARY KEY,
    run_id INT,
    player_uuid VARCHAR(36) NOT NULL,
    fear_value INT CHECK (fear_value >= 0 AND fear_value <= 100),
    event_type VARCHAR(50),  -- What caused the fear change
    recorded_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_betrayal_debt_player ON eris_betrayal_debt(player_uuid);
CREATE INDEX IF NOT EXISTS idx_prophecies_player ON eris_prophecies(player_uuid);
CREATE INDEX IF NOT EXISTS idx_prophecies_unfulfilled ON eris_prophecies(is_fulfilled) WHERE is_fulfilled = FALSE;
CREATE INDEX IF NOT EXISTS idx_fear_log_run ON eris_player_fear_log(run_id);
CREATE INDEX IF NOT EXISTS idx_fear_log_player ON eris_player_fear_log(player_uuid);

-- Comments for documentation
COMMENT ON TABLE eris_betrayal_debt IS 'Tracks debt accumulation per mask type for each player. High debt influences mask behavior.';
COMMENT ON TABLE eris_prophecies IS 'Stores prophecies made by Eris and tracks their fulfillment status.';
COMMENT ON TABLE eris_run_state IS 'Analytics table for Eris behavior metrics per run.';
COMMENT ON TABLE eris_player_fear_log IS 'Optional logging of fear level changes for post-game analysis.';

COMMENT ON COLUMN eris_betrayal_debt.mask_type IS 'One of: TRICKSTER (prank_debt), PROPHET (doom_debt), FRIEND (betrayal_debt), CHAOS_BRINGER (wrath_debt), OBSERVER (silence_debt), GAMBLER (risk_debt)';
COMMENT ON COLUMN eris_prophecies.prophecy_type IS 'Category of prophecy: doom, glory, betrayal, warning, blessing';
