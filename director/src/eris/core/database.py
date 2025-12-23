"""Async PostgreSQL client for player history."""

import logging
from typing import Dict, Optional

import asyncpg

logger = logging.getLogger(__name__)


class Database:
    """Async PostgreSQL interface for player history and long-term memory."""

    def __init__(self, config: dict):
        self.config = config
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Create connection pool."""
        try:
            self.pool = await asyncpg.create_pool(
                host=self.config["host"],
                port=self.config["port"],
                database=self.config["database"],
                user=self.config["user"],
                password=self.config["password"],
                min_size=1,
                max_size=5,
            )
            logger.info("✅ Connected to PostgreSQL database")
        except Exception as e:
            logger.error(f"❌ Failed to connect to database: {e}")
            raise

    async def close(self):
        """Close connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("Database connection closed")

    async def get_player_summary(self, uuid: str) -> Dict:
        """Get player's history summary for context."""
        if not self.pool:
            logger.warning("Database not connected")
            return {}

        query = """
        SELECT
            p.username,
            p.aura,
            p.total_runs,
            p.total_deaths,
            p.dragons_killed,
            p.total_playtime_seconds / 3600 as hours_played,
            (SELECT COUNT(*) FROM achievements_earned WHERE uuid = p.uuid) as achievement_count
        FROM players p
        WHERE p.uuid = $1
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query, uuid)
                if row:
                    return dict(row)
                return {}
        except Exception as e:
            logger.error(f"Error fetching player summary: {e}")
            return {}

    async def get_player_nemesis(self, uuid: str) -> Optional[str]:
        """Get what kills this player most often."""
        if not self.pool:
            return None

        query = """
        SELECT death_cause, COUNT(*) as count
        FROM run_participants
        WHERE uuid = $1 AND death_cause IS NOT NULL
        GROUP BY death_cause
        ORDER BY count DESC
        LIMIT 1
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query, uuid)
                return row["death_cause"] if row else None
        except Exception as e:
            logger.error(f"Error fetching player nemesis: {e}")
            return None

    async def get_recent_runs(self, limit: int = 5) -> list:
        """Get recent run history."""
        if not self.pool:
            return []

        query = """
        SELECT
            run_id,
            started_at,
            ended_at,
            duration_seconds,
            outcome,
            peak_players
        FROM run_history
        ORDER BY started_at DESC
        LIMIT $1
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, limit)
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error fetching recent runs: {e}")
            return []
