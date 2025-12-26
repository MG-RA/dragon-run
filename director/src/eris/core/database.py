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

    async def get_player_recent_performance(self, uuid: str, limit: int = 5) -> Dict:
        """Get player's recent run performance for trend analysis."""
        if not self.pool:
            return {}

        query = """
        SELECT
            rh.outcome,
            rp.alive_duration_seconds,
            rp.mob_kills,
            rp.entered_nether,
            rp.entered_end
        FROM run_participants rp
        JOIN run_history rh ON rp.run_id = rh.run_id
        WHERE rp.uuid = $1
        ORDER BY rh.started_at DESC
        LIMIT $2
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, uuid, limit)
                if not rows:
                    return {}

                # Calculate stats
                total = len(rows)
                wins = sum(1 for r in rows if r["outcome"] == "DRAGON_KILLED")
                nether_visits = sum(1 for r in rows if r["entered_nether"])
                end_visits = sum(1 for r in rows if r["entered_end"])
                avg_survival = sum(r["alive_duration_seconds"] or 0 for r in rows) / total

                # Determine trend
                if total >= 3:
                    recent_wins = sum(1 for r in rows[:3] if r["outcome"] == "DRAGON_KILLED")
                    if recent_wins >= 2:
                        trend = "improving"
                    elif recent_wins == 0:
                        trend = "struggling"
                    else:
                        trend = "stable"
                else:
                    trend = "new"

                return {
                    "recent_runs": total,
                    "recent_wins": wins,
                    "win_rate": wins / total if total > 0 else 0,
                    "avg_survival_seconds": int(avg_survival),
                    "nether_rate": nether_visits / total if total > 0 else 0,
                    "end_rate": end_visits / total if total > 0 else 0,
                    "trend": trend,
                }
        except Exception as e:
            logger.error(f"Error fetching player recent performance: {e}")
            return {}

    async def get_player_personal_bests(self, uuid: str) -> Dict:
        """Get player's personal best records."""
        if not self.pool:
            return {}

        query = """
        SELECT
            MAX(alive_duration_seconds) as longest_survival,
            MAX(mob_kills) as most_kills,
            COUNT(*) FILTER (WHERE entered_end) as end_visits,
            COUNT(*) as total_participations
        FROM run_participants
        WHERE uuid = $1
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query, uuid)
                if row:
                    return {
                        "longest_survival_seconds": row["longest_survival"] or 0,
                        "most_kills_in_run": row["most_kills"] or 0,
                        "total_end_visits": row["end_visits"] or 0,
                        "total_participations": row["total_participations"] or 0,
                    }
                return {}
        except Exception as e:
            logger.error(f"Error fetching player personal bests: {e}")
            return {}

    async def get_player_recent_achievements(self, uuid: str, limit: int = 3) -> list:
        """Get player's most recently earned achievements."""
        if not self.pool:
            return []

        query = """
        SELECT
            achievement_id,
            earned_at
        FROM achievements_earned
        WHERE uuid = $1
        ORDER BY earned_at DESC
        LIMIT $2
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, uuid, limit)
                return [{"id": r["achievement_id"], "earned_at": r["earned_at"]} for r in rows]
        except Exception as e:
            logger.error(f"Error fetching recent achievements: {e}")
            return []

    # === Betrayal Debt Methods (v1.1) ===

    async def get_betrayal_debts(self, uuid: str) -> Dict[str, int]:
        """Get all betrayal debts for a player, keyed by mask type."""
        if not self.pool:
            return {}

        query = """
        SELECT mask_type, debt_value
        FROM eris_betrayal_debt
        WHERE player_uuid = $1
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, uuid)
                return {row["mask_type"]: row["debt_value"] for row in rows}
        except Exception as e:
            logger.error(f"Error fetching betrayal debts: {e}")
            return {}

    async def update_betrayal_debt(self, uuid: str, mask_type: str, delta: int) -> int:
        """
        Update betrayal debt for a player/mask combination.

        Returns the new debt value.
        """
        if not self.pool:
            return 0

        # Upsert query - insert if not exists, update if exists
        query = """
        INSERT INTO eris_betrayal_debt (player_uuid, mask_type, debt_value, last_updated)
        VALUES ($1, $2, GREATEST(0, LEAST(100, $3)), NOW())
        ON CONFLICT (player_uuid, mask_type)
        DO UPDATE SET
            debt_value = GREATEST(0, LEAST(100, eris_betrayal_debt.debt_value + $3)),
            last_updated = NOW()
        RETURNING debt_value
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query, uuid, mask_type, delta)
                return row["debt_value"] if row else 0
        except Exception as e:
            logger.error(f"Error updating betrayal debt: {e}")
            return 0

    async def get_all_player_debts(self, uuids: list) -> Dict[str, Dict[str, int]]:
        """Get betrayal debts for multiple players at once."""
        if not self.pool or not uuids:
            return {}

        query = """
        SELECT player_uuid, mask_type, debt_value
        FROM eris_betrayal_debt
        WHERE player_uuid = ANY($1)
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, uuids)
                result: Dict[str, Dict[str, int]] = {}
                for row in rows:
                    player_uuid = row["player_uuid"]
                    if player_uuid not in result:
                        result[player_uuid] = {}
                    result[player_uuid][row["mask_type"]] = row["debt_value"]
                return result
        except Exception as e:
            logger.error(f"Error fetching all player debts: {e}")
            return {}

    # === Prophecy Methods (v1.1) ===

    async def get_active_prophecies(self, uuid: str) -> list:
        """Get unfulfilled prophecies for a player."""
        if not self.pool:
            return []

        query = """
        SELECT id, prophecy_text, prophecy_type, created_at
        FROM eris_prophecies
        WHERE player_uuid = $1 AND is_fulfilled = FALSE
        ORDER BY created_at DESC
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, uuid)
                return [
                    {
                        "id": row["id"],
                        "text": row["prophecy_text"],
                        "type": row["prophecy_type"],
                        "created_at": row["created_at"],
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.error(f"Error fetching active prophecies: {e}")
            return []

    async def create_prophecy(
        self, uuid: str, text: str, prophecy_type: str, run_id: Optional[int] = None
    ) -> Optional[int]:
        """Create a new prophecy for a player. Returns the prophecy ID."""
        if not self.pool:
            return None

        query = """
        INSERT INTO eris_prophecies (player_uuid, prophecy_text, prophecy_type, run_id)
        VALUES ($1, $2, $3, $4)
        RETURNING id
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query, uuid, text, prophecy_type, run_id)
                return row["id"] if row else None
        except Exception as e:
            logger.error(f"Error creating prophecy: {e}")
            return None

    async def fulfill_prophecy(self, prophecy_id: int) -> bool:
        """Mark a prophecy as fulfilled."""
        if not self.pool:
            return False

        query = """
        UPDATE eris_prophecies
        SET is_fulfilled = TRUE, fulfilled_at = NOW()
        WHERE id = $1
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, prophecy_id)
                logger.info(f"Prophecy {prophecy_id} fulfilled")
                return True
        except Exception as e:
            logger.error(f"Error fulfilling prophecy: {e}")
            return False

    async def get_all_active_prophecies(self, uuids: list) -> Dict[str, list]:
        """Get active prophecies for multiple players at once."""
        if not self.pool or not uuids:
            return {}

        query = """
        SELECT player_uuid, id, prophecy_text, prophecy_type, created_at
        FROM eris_prophecies
        WHERE player_uuid = ANY($1) AND is_fulfilled = FALSE
        ORDER BY created_at DESC
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, uuids)
                result: Dict[str, list] = {}
                for row in rows:
                    player_uuid = row["player_uuid"]
                    if player_uuid not in result:
                        result[player_uuid] = []
                    result[player_uuid].append({
                        "id": row["id"],
                        "text": row["prophecy_text"],
                        "type": row["prophecy_type"],
                        "created_at": row["created_at"],
                    })
                return result
        except Exception as e:
            logger.error(f"Error fetching all active prophecies: {e}")
            return {}

    # === Run State Methods (v1.1) ===

    async def save_run_eris_state(
        self,
        run_id: int,
        peak_chaos: int,
        total_interventions: int,
        protections_used: int,
        respawns_used: int,
        final_chaos: int,
    ) -> bool:
        """Save Eris-specific state for a run (for analytics)."""
        if not self.pool:
            return False

        query = """
        INSERT INTO eris_run_state (run_id, peak_chaos, total_interventions, protections_used, respawns_used, final_chaos)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (run_id) DO UPDATE SET
            peak_chaos = $2,
            total_interventions = $3,
            protections_used = $4,
            respawns_used = $5,
            final_chaos = $6
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    query, run_id, peak_chaos, total_interventions, protections_used, respawns_used, final_chaos
                )
                return True
        except Exception as e:
            logger.error(f"Error saving run Eris state: {e}")
            return False
