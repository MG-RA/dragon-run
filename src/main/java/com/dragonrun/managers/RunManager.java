package com.dragonrun.managers;

import com.dragonrun.DragonRunPlugin;
import com.dragonrun.database.Database;
import org.bukkit.Bukkit;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.UUID;

public class RunManager {

    private final DragonRunPlugin plugin;
    private final Database database;

    private int currentRunId = -1;
    private long runStartTime;
    private boolean dragonAlive = true;

    public RunManager(DragonRunPlugin plugin, Database database) {
        this.plugin = plugin;
        this.database = database;
    }

    /**
     * Ensure there's an active run, creating one if needed
     */
    public void ensureActiveRun() {
        // Check for existing incomplete run
        String checkSql = "SELECT run_id, started_at FROM run_history " +
                "WHERE ended_at IS NULL ORDER BY run_id DESC LIMIT 1";

        try (Connection conn = database.getConnection();
             PreparedStatement stmt = conn.prepareStatement(checkSql);
             ResultSet rs = stmt.executeQuery()) {

            if (rs.next()) {
                currentRunId = rs.getInt("run_id");
                runStartTime = rs.getTimestamp("started_at").getTime();
                plugin.getLogger().info("Resuming run #" + currentRunId);
            } else {
                startNewRun();
            }
        } catch (SQLException e) {
            plugin.getLogger().severe("Failed to check run state: " + e.getMessage());
            startNewRun();
        }
    }

    /**
     * Start a fresh run
     */
    public void startNewRun() {
        String sql = "INSERT INTO run_history (started_at) VALUES (NOW()) RETURNING run_id";

        try (Connection conn = database.getConnection();
             PreparedStatement stmt = conn.prepareStatement(sql);
             ResultSet rs = stmt.executeQuery()) {

            if (rs.next()) {
                currentRunId = rs.getInt("run_id");
                runStartTime = System.currentTimeMillis();
                dragonAlive = true;
                plugin.getLogger().info("Started new run #" + currentRunId);
            }
        } catch (SQLException e) {
            plugin.getLogger().severe("Failed to start new run: " + e.getMessage());
        }
    }

    /**
     * End run due to player death
     */
    public void endRunByDeath(UUID deathPlayerUuid) {
        endRun("PLAYER_DEATH", deathPlayerUuid, null);
    }

    /**
     * End run due to dragon kill
     */
    public void endRunByDragonKill(UUID killerUuid) {
        dragonAlive = false;
        endRun("DRAGON_KILLED", null, killerUuid);
    }

    /**
     * End run manually (admin)
     */
    public void endRunManually() {
        endRun("MANUAL_RESET", null, null);
    }

    private void endRun(String outcome, UUID endedByUuid, UUID dragonKillerUuid) {
        int duration = (int) ((System.currentTimeMillis() - runStartTime) / 1000);

        String sql = "UPDATE run_history SET ended_at = NOW(), duration_seconds = ?, " +
                "outcome = ?, ended_by_uuid = ?, dragon_killer_uuid = ?, " +
                "peak_players = ? WHERE run_id = ?";

        try (Connection conn = database.getConnection();
             PreparedStatement stmt = conn.prepareStatement(sql)) {
            stmt.setInt(1, duration);
            stmt.setString(2, outcome);
            stmt.setString(3, endedByUuid != null ? endedByUuid.toString() : null);
            stmt.setString(4, dragonKillerUuid != null ? dragonKillerUuid.toString() : null);
            stmt.setInt(5, Bukkit.getOnlinePlayers().size());
            stmt.setInt(6, currentRunId);
            stmt.executeUpdate();
        } catch (SQLException e) {
            plugin.getLogger().severe("Failed to end run: " + e.getMessage());
        }
    }

    /**
     * Save current run state (called on plugin disable)
     */
    public void saveRunState() {
        if (currentRunId > 0) {
            String sql = "UPDATE run_history SET peak_players = GREATEST(peak_players, ?) " +
                    "WHERE run_id = ?";
            try (Connection conn = database.getConnection();
                 PreparedStatement stmt = conn.prepareStatement(sql)) {
                stmt.setInt(1, Bukkit.getOnlinePlayers().size());
                stmt.setInt(2, currentRunId);
                stmt.executeUpdate();
            } catch (SQLException e) {
                plugin.getLogger().warning("Failed to save run state: " + e.getMessage());
            }
        }
    }

    /**
     * Update peak players count (call periodically)
     */
    public void updatePeakPlayers() {
        if (currentRunId > 0) {
            Bukkit.getAsyncScheduler().runNow(plugin, task -> {
                String sql = "UPDATE run_history SET peak_players = GREATEST(peak_players, ?) " +
                        "WHERE run_id = ?";
                try (Connection conn = database.getConnection();
                     PreparedStatement stmt = conn.prepareStatement(sql)) {
                    stmt.setInt(1, Bukkit.getOnlinePlayers().size());
                    stmt.setInt(2, currentRunId);
                    stmt.executeUpdate();
                } catch (SQLException e) {
                    plugin.getLogger().warning("Failed to update peak players: " + e.getMessage());
                }
            });
        }
    }

    // Getters
    public int getCurrentRunId() {
        return currentRunId;
    }

    public long getRunStartTime() {
        return runStartTime;
    }

    public long getRunDurationSeconds() {
        return (System.currentTimeMillis() - runStartTime) / 1000;
    }

    public boolean isDragonAlive() {
        return dragonAlive;
    }

    public void setDragonAlive(boolean alive) {
        this.dragonAlive = alive;
    }
}
