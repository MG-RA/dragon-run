-- Migration: Add world_name and world_seed columns to run_history
-- This is needed for Director's Cut multi-world support

ALTER TABLE run_history
ADD COLUMN IF NOT EXISTS world_name VARCHAR(100);

ALTER TABLE run_history
ADD COLUMN IF NOT EXISTS world_seed BIGINT;
