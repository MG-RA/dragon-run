"""Async PostgreSQL client for player history."""

import logging

import asyncpg

from .tracing import span

logger = logging.getLogger(__name__)


class Database:
    """Async PostgreSQL interface for player history and long-term memory."""

    def __init__(self, config: dict):
        self.config = config
        self.pool: asyncpg.Pool | None = None

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

    async def get_player_summary(self, uuid: str) -> dict:
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
        with span("db.query:player_summary", player_uuid=uuid[:8], query_type="player_summary") as db_span:
            try:
                async with self.pool.acquire() as conn:
                    row = await conn.fetchrow(query, uuid)
                    if row:
                        result = dict(row)
                        db_span.set_attributes(
                            found=True,
                            total_runs=result.get("total_runs", 0),
                            aura=result.get("aura", 0),
                        )
                        return result
                    else:
                        db_span.set_attribute("found", False)
                    return {}
            except Exception as e:
                logger.error(f"Error fetching player summary: {e}")
                return {}

    async def get_player_nemesis(self, uuid: str) -> str | None:
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

    async def get_player_recent_performance(self, uuid: str, limit: int = 5) -> dict:
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

    async def get_all_player_enrichment(self, uuids: list, limit: int = 5) -> dict[str, dict]:
        """Batch fetch all enrichment data for multiple players in optimized queries.

        Returns dict[uuid] -> {
            'summary': {...},  # player stats
            'nemesis': str,    # most common death cause
            'performance': {...}  # recent performance trends
        }
        """
        if not self.pool or not uuids:
            return {}

        with span("db.query:player_enrichment", player_count=len(uuids), query_type="batch_enrichment") as db_span:
            try:
                async with self.pool.acquire() as conn:
                    result = {}

                    # Query 1: Batch fetch player summaries
                    summary_query = """
                    SELECT
                        p.uuid,
                        p.username,
                        p.aura,
                        p.total_runs,
                        p.total_deaths,
                        p.dragons_killed,
                        p.total_playtime_seconds / 3600 as hours_played,
                        (SELECT COUNT(*) FROM achievements_earned WHERE uuid = p.uuid) as achievement_count
                    FROM players p
                    WHERE p.uuid = ANY($1)
                    """
                    summary_rows = await conn.fetch(summary_query, uuids)
                    for row in summary_rows:
                        uuid = row["uuid"]
                        result[uuid] = {
                            "summary": dict(row),
                            "nemesis": None,
                            "performance": {}
                        }

                    # Query 2: Batch fetch nemesis (most common death cause per player)
                    nemesis_query = """
                    SELECT DISTINCT ON (uuid)
                        uuid,
                        death_cause
                    FROM (
                        SELECT uuid, death_cause, COUNT(*) as count
                        FROM run_participants
                        WHERE uuid = ANY($1) AND death_cause IS NOT NULL
                        GROUP BY uuid, death_cause
                        ORDER BY uuid, count DESC
                    ) sub
                    """
                    nemesis_rows = await conn.fetch(nemesis_query, uuids)
                    for row in nemesis_rows:
                        uuid = row["uuid"]
                        if uuid in result:
                            result[uuid]["nemesis"] = row["death_cause"]

                    # Query 3: Batch fetch recent performance
                    perf_query = """
                    SELECT
                        rp.uuid,
                        rh.outcome,
                        rp.alive_duration_seconds,
                        rp.mob_kills,
                        rp.entered_nether,
                        rp.entered_end,
                        ROW_NUMBER() OVER (PARTITION BY rp.uuid ORDER BY rh.started_at DESC) as rn
                    FROM run_participants rp
                    JOIN run_history rh ON rp.run_id = rh.run_id
                    WHERE rp.uuid = ANY($1)
                    ORDER BY rp.uuid, rh.started_at DESC
                    """
                    perf_rows = await conn.fetch(perf_query, uuids)

                    # Group performance data by UUID and calculate trends
                    perf_by_uuid = {}
                    for row in perf_rows:
                        uuid = row["uuid"]
                        if row["rn"] <= limit:  # Only keep up to `limit` recent runs
                            if uuid not in perf_by_uuid:
                                perf_by_uuid[uuid] = []
                            perf_by_uuid[uuid].append(row)

                    for uuid, runs in perf_by_uuid.items():
                        if uuid not in result:
                            continue

                        total = len(runs)
                        if total == 0:
                            result[uuid]["performance"] = {}
                            continue

                        wins = sum(1 for r in runs if r["outcome"] == "DRAGON_KILLED")
                        nether_visits = sum(1 for r in runs if r["entered_nether"])
                        end_visits = sum(1 for r in runs if r["entered_end"])
                        avg_survival = sum(r["alive_duration_seconds"] or 0 for r in runs) / total

                        # Determine trend
                        if total >= 3:
                            recent_wins = sum(1 for r in runs[:3] if r["outcome"] == "DRAGON_KILLED")
                            if recent_wins >= 2:
                                trend = "improving"
                            elif recent_wins == 0:
                                trend = "struggling"
                            else:
                                trend = "stable"
                        else:
                            trend = "new"

                        result[uuid]["performance"] = {
                            "recent_runs": total,
                            "recent_wins": wins,
                            "win_rate": wins / total if total > 0 else 0,
                            "avg_survival_seconds": int(avg_survival),
                            "nether_rate": nether_visits / total if total > 0 else 0,
                            "end_rate": end_visits / total if total > 0 else 0,
                            "trend": trend,
                        }

                    db_span.set_attributes(
                        players_enriched=len(result),
                        summaries_fetched=len(summary_rows),
                        nemeses_found=len(nemesis_rows),
                        performance_records=len(perf_rows),
                    )

                    return result

            except Exception as e:
                logger.error(f"Error batch fetching player enrichment: {e}")
                return {}

    async def get_player_personal_bests(self, uuid: str) -> dict:
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

    # === Karma Methods (v1.3 - renamed from betrayal debt) ===
    # Note: Database table is still eris_betrayal_debt for backwards compatibility

    async def get_player_karma(self, uuid: str) -> dict[str, int]:
        """Get all karma values for a player, keyed by mask type."""
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
            logger.error(f"Error fetching player karma: {e}")
            return {}

    async def update_player_karma(self, uuid: str, mask_type: str, delta: int) -> int:
        """
        Update karma for a player/mask combination.

        Returns the new karma value.
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
            logger.error(f"Error updating player karma: {e}")
            return 0

    async def get_all_player_karmas(self, uuids: list) -> dict[str, dict[str, int]]:
        """Get karma values for multiple players at once."""
        if not self.pool or not uuids:
            return {}

        query = """
        SELECT player_uuid, mask_type, debt_value
        FROM eris_betrayal_debt
        WHERE player_uuid = ANY($1)
        """
        with span("db.query:player_karmas", player_count=len(uuids), query_type="batch_karmas") as db_span:
            try:
                async with self.pool.acquire() as conn:
                    rows = await conn.fetch(query, uuids)
                    result: dict[str, dict[str, int]] = {}
                    total_karma_entries = 0
                    for row in rows:
                        player_uuid = row["player_uuid"]
                        if player_uuid not in result:
                            result[player_uuid] = {}
                        result[player_uuid][row["mask_type"]] = row["debt_value"]
                        total_karma_entries += 1
                    db_span.set_attributes(
                        players_with_karma=len(result),
                        total_karma_entries=total_karma_entries,
                    )
                    return result
            except Exception as e:
                logger.error(f"Error fetching all player karmas: {e}")
                return {}

    # Backwards compatibility aliases
    async def get_betrayal_debts(self, uuid: str) -> dict[str, int]:
        """Alias for get_player_karma (backwards compatibility)."""
        return await self.get_player_karma(uuid)

    async def update_betrayal_debt(self, uuid: str, mask_type: str, delta: int) -> int:
        """Alias for update_player_karma (backwards compatibility)."""
        return await self.update_player_karma(uuid, mask_type, delta)

    async def get_all_player_debts(self, uuids: list) -> dict[str, dict[str, int]]:
        """Alias for get_all_player_karmas (backwards compatibility)."""
        return await self.get_all_player_karmas(uuids)

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
        self, uuid: str, text: str, prophecy_type: str, run_id: int | None = None
    ) -> int | None:
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

    async def get_all_active_prophecies(self, uuids: list) -> dict[str, list]:
        """Get active prophecies for multiple players at once."""
        if not self.pool or not uuids:
            return {}

        query = """
        SELECT player_uuid, id, prophecy_text, prophecy_type, created_at
        FROM eris_prophecies
        WHERE player_uuid = ANY($1) AND is_fulfilled = FALSE
        ORDER BY created_at DESC
        """
        with span("db.query:active_prophecies", player_count=len(uuids), query_type="batch_prophecies") as db_span:
            try:
                async with self.pool.acquire() as conn:
                    rows = await conn.fetch(query, uuids)
                    result: dict[str, list] = {}
                    total_prophecies = 0
                    for row in rows:
                        player_uuid = row["player_uuid"]
                        if player_uuid not in result:
                            result[player_uuid] = []
                        result[player_uuid].append(
                            {
                                "id": row["id"],
                                "text": row["prophecy_text"],
                                "type": row["prophecy_type"],
                                "created_at": row["created_at"],
                            }
                        )
                        total_prophecies += 1
                    db_span.set_attributes(
                        players_with_prophecies=len(result),
                        total_prophecies=total_prophecies,
                    )
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
                    query,
                    run_id,
                    peak_chaos,
                    total_interventions,
                    protections_used,
                    respawns_used,
                    final_chaos,
                )
                return True
        except Exception as e:
            logger.error(f"Error saving run Eris state: {e}")
            return False
