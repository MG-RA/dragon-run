import psycopg2
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)

class DatabaseTools:
    """Tools for querying the PostgreSQL database (long-term memory)."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config['database']
        self.conn = None

    def connect(self):
        """Connect to the database."""
        try:
            self.conn = psycopg2.connect(
                host=self.config['host'],
                port=self.config['port'],
                dbname=self.config['name'],
                user=self.config['user'],
                password=self.config['password']
            )
            logger.info("Connected to database")
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            self.conn = None

    def query_player_stats(self, player_name: str) -> Optional[Dict]:
        """Query historical player stats."""
        if not self.conn:
            return None

        try:
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    SELECT player_name, player_uuid, total_aura, created_at
                    FROM player_data
                    WHERE LOWER(player_name) = LOWER(%s)
                """, (player_name,))

                row = cursor.fetchone()
                if row:
                    return {
                        'name': row[0],
                        'uuid': row[1],
                        'totalAura': row[2],
                        'createdAt': row[3].isoformat() if row[3] else None
                    }
        except Exception as e:
            logger.error(f"Error querying player stats: {e}")

        return None

    def query_run_history(self, limit: int = 10) -> List[Dict]:
        """Get recent run history."""
        if not self.conn:
            return []

        try:
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    SELECT run_id, world_name, outcome, duration, started_at, ended_at
                    FROM run_history
                    ORDER BY started_at DESC
                    LIMIT %s
                """, (limit,))

                rows = cursor.fetchall()
                return [
                    {
                        'runId': row[0],
                        'worldName': row[1],
                        'outcome': row[2],
                        'duration': row[3],
                        'startedAt': row[4].isoformat() if row[4] else None,
                        'endedAt': row[5].isoformat() if row[5] else None
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.error(f"Error querying run history: {e}")

        return []

    def query_aura_leaderboard(self, limit: int = 10) -> List[Dict]:
        """Get top aura players."""
        if not self.conn:
            return []

        try:
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    SELECT player_name, total_aura
                    FROM player_data
                    ORDER BY total_aura DESC
                    LIMIT %s
                """, (limit,))

                rows = cursor.fetchall()
                return [
                    {
                        'player': row[0],
                        'aura': row[1]
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.error(f"Error querying leaderboard: {e}")

        return []

    def query_achievements(self, player_name: Optional[str] = None) -> List[Dict]:
        """Get achievement data, optionally filtered by player."""
        if not self.conn:
            return []

        try:
            with self.conn.cursor() as cursor:
                if player_name:
                    cursor.execute("""
                        SELECT player_uuid, achievement_id, unlocked_at
                        FROM achievements
                        WHERE player_uuid IN (
                            SELECT player_uuid FROM player_data WHERE LOWER(player_name) = LOWER(%s)
                        )
                        ORDER BY unlocked_at DESC
                        LIMIT 20
                    """, (player_name,))
                else:
                    cursor.execute("""
                        SELECT player_uuid, achievement_id, unlocked_at
                        FROM achievements
                        ORDER BY unlocked_at DESC
                        LIMIT 50
                    """)

                rows = cursor.fetchall()
                return [
                    {
                        'playerUuid': str(row[0]),
                        'achievementId': row[1],
                        'unlockedAt': row[2].isoformat() if row[2] else None
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.error(f"Error querying achievements: {e}")

        return []

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")
