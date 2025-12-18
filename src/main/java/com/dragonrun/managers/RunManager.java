package com.dragonrun.managers;

import com.dragonrun.DragonRunPlugin;
import com.dragonrun.database.Database;
import com.dragonrun.util.MessageUtil;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import net.kyori.adventure.title.Title;
import org.bukkit.Bukkit;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

public class RunManager {

    private final DragonRunPlugin plugin;
    private final Database database;
    private final WorldManager worldManager;

    private GameState gameState = GameState.IDLE;
    private int currentRunId = -1;
    private long runStartTime;
    private boolean dragonAlive = true;
    private String currentWorldName;

    public RunManager(DragonRunPlugin plugin, Database database, WorldManager worldManager) {
        this.plugin = plugin;
        this.database = database;
        this.worldManager = worldManager;
    }

    // ==================== GAME STATE ====================

    /**
     * Get current game state.
     */
    public GameState getGameState() {
        return gameState;
    }

    /**
     * Check if a run can be started (state is IDLE).
     */
    public boolean canStartRun() {
        return gameState == GameState.IDLE;
    }

    /**
     * Check if a run is active.
     */
    public boolean isRunActive() {
        return gameState == GameState.ACTIVE;
    }

    // ==================== RUN LIFECYCLE ====================

    /**
     * Start a new run. Uses pre-created world and teleports players.
     * Can only be called from IDLE state.
     * @param requestedSeed Optional seed (null to use pre-created world)
     * @return CompletableFuture that completes when run starts
     */
    public CompletableFuture<Boolean> startRun(Long requestedSeed) {
        if (gameState != GameState.IDLE) {
            plugin.getLogger().warning("Cannot start run - state is " + gameState);
            return CompletableFuture.completedFuture(false);
        }

        int playerCount = worldManager.getLobbyPlayerCount();
        if (playerCount == 0) {
            plugin.getLogger().warning("Cannot start run - no players in lobby");
            return CompletableFuture.completedFuture(false);
        }

        // Check if hardcore world is already pre-created
        if (worldManager.getHardcoreWorld() == null) {
            // World not ready, need to create it
            gameState = GameState.GENERATING;
            broadcastGeneratingMessage();

            return worldManager.createHardcoreWorld(requestedSeed)
                    .thenCompose(world -> startRunWithWorld(world));
        } else {
            // World already exists, start immediately
            plugin.getLogger().info("Using pre-created hardcore world");
            return startRunWithWorld(worldManager.getHardcoreWorld());
        }
    }

    /**
     * Internal method to start run with a given world.
     */
    private CompletableFuture<Boolean> startRunWithWorld(org.bukkit.World world) {
        if (world == null) {
            gameState = GameState.IDLE;
            Bukkit.broadcast(MessageUtil.error("Failed to create world! Try again."));
            return CompletableFuture.completedFuture(false);
        }

        currentWorldName = world.getName();

        // Create database record
        createRunRecord(worldManager.getCurrentWorldSeed());

        broadcastGeneratingMessage();

        // Broadcast to Director AI
        broadcastDirectorEvent("run_starting", currentRunId, currentWorldName);

        // Teleport all lobby players to hardcore world
        return worldManager.teleportAllToHardcore()
                .thenApply(v -> {
                    gameState = GameState.ACTIVE;
                    runStartTime = System.currentTimeMillis();
                    dragonAlive = true;
                    broadcastRunStartMessage();

                    // Broadcast to Director AI
                    broadcastDirectorEvent("run_started", currentRunId, currentWorldName);

                    return true;
                })
                .exceptionally(e -> {
                    plugin.getLogger().severe("Error starting run: " + e.getMessage());
                    gameState = GameState.IDLE;
                    return false;
                });
    }

    /**
     * End run due to player death.
     * Transitions to RESETTING, teleports players to lobby, deletes world.
     */
    public void endRunByDeath(UUID deathPlayerUuid) {
        if (gameState != GameState.ACTIVE) {
            plugin.getLogger().warning("Cannot end run by death - state is " + gameState);
            return;
        }

        gameState = GameState.RESETTING;
        endRun("PLAYER_DEATH", deathPlayerUuid, null);

        // Broadcast to Director AI
        com.google.gson.JsonObject data = new com.google.gson.JsonObject();
        data.addProperty("runId", currentRunId);
        data.addProperty("playerUuid", deathPlayerUuid.toString());
        data.addProperty("outcome", "PLAYER_DEATH");
        if (plugin.getDirectorServer() != null) {
            plugin.getDirectorServer().broadcastEvent("run_ended", data);
        }

        // Clear bets
        plugin.getBettingManager().clearAllBets();

        // Clear achievement run data
        plugin.getAchievementListener().clearRunData();

        // Schedule world deletion after countdown
        int delaySeconds = plugin.getConfig().getInt("game.reset-delay-seconds", 10);

        Bukkit.getAsyncScheduler().runDelayed(plugin, task -> {
            worldManager.deleteHardcoreWorld().thenRun(this::completeReset);
        }, delaySeconds, TimeUnit.SECONDS);
    }

    /**
     * End run due to dragon kill (victory).
     */
    public void endRunByDragonKill(UUID killerUuid) {
        if (gameState != GameState.ACTIVE) return;

        gameState = GameState.RESETTING;
        dragonAlive = false;
        endRun("DRAGON_KILLED", null, killerUuid);

        // Broadcast to Director AI
        com.google.gson.JsonObject data = new com.google.gson.JsonObject();
        data.addProperty("runId", currentRunId);
        data.addProperty("killerUuid", killerUuid.toString());
        data.addProperty("outcome", "DRAGON_KILLED");
        data.addProperty("duration", getRunDurationSeconds());
        if (plugin.getDirectorServer() != null) {
            plugin.getDirectorServer().broadcastEvent("run_ended", data);
        }

        // Pay out bets on successful run
        plugin.getBettingManager().processRunCompletion();

        // Clear achievement run data
        plugin.getAchievementListener().clearRunData();

        // Victory celebration, then reset after delay
        int delaySeconds = plugin.getConfig().getInt("game.victory-delay-seconds", 30);

        Bukkit.getAsyncScheduler().runDelayed(plugin, task -> {
            worldManager.deleteHardcoreWorld().thenRun(this::completeReset);
        }, delaySeconds, TimeUnit.SECONDS);
    }

    /**
     * End run manually (admin).
     */
    public void endRunManually() {
        if (gameState != GameState.ACTIVE) return;

        gameState = GameState.RESETTING;
        endRun("MANUAL_RESET", null, null);

        plugin.getBettingManager().clearAllBets();
        plugin.getAchievementListener().clearRunData();

        worldManager.deleteHardcoreWorld().thenRun(this::completeReset);
    }

    /**
     * Handle transition to IDLE after reset completes.
     */
    private void completeReset() {
        gameState = GameState.IDLE;
        currentWorldName = null;
        currentRunId = -1;
        dragonAlive = true;

        Bukkit.broadcast(MessageUtil.info("Run ended. Vote to start a new run!"));
        plugin.getLogger().info("Reset complete. Ready for new run.");

        // Pre-create next hardcore world so it's ready for the next vote
        Bukkit.getScheduler().runTaskLater(plugin, () -> {
            worldManager.createHardcoreWorld(null).thenAccept(world -> {
                if (world != null) {
                    plugin.getLogger().info("Pre-created next hardcore world: " + world.getName());
                }
            });
        }, 20L); // Wait 1 second after reset
    }

    // ==================== DATABASE ====================

    private void createRunRecord(long seed) {
        String sql = "INSERT INTO run_history (started_at, world_name, world_seed) " +
                "VALUES (NOW(), ?, ?) RETURNING run_id";

        plugin.getLogger().info("Creating run record - world: " + currentWorldName + ", seed: " + seed);

        try (Connection conn = database.getConnection();
             PreparedStatement stmt = conn.prepareStatement(sql)) {

            plugin.getLogger().info("Database connection obtained, executing INSERT...");

            stmt.setString(1, currentWorldName);
            stmt.setLong(2, seed);

            try (ResultSet rs = stmt.executeQuery()) {
                plugin.getLogger().info("Query executed, checking result...");

                if (rs.next()) {
                    currentRunId = rs.getInt("run_id");
                    plugin.getLogger().info("✓ Created run record #" + currentRunId);
                } else {
                    plugin.getLogger().severe("✗ No run_id returned from INSERT - query succeeded but no rows returned!");
                }
            }
        } catch (SQLException e) {
            plugin.getLogger().severe("✗ Failed to create run record: " + e.getMessage());
            plugin.getLogger().severe("  SQL State: " + e.getSQLState());
            plugin.getLogger().severe("  Error Code: " + e.getErrorCode());
            e.printStackTrace();
        }
    }

    private void endRun(String outcome, UUID endedByUuid, UUID dragonKillerUuid) {
        if (currentRunId <= 0) return;

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
            stmt.setInt(5, worldManager.getHardcorePlayerCount());
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
        if (currentRunId > 0 && gameState == GameState.ACTIVE) {
            String sql = "UPDATE run_history SET peak_players = GREATEST(peak_players, ?) " +
                    "WHERE run_id = ?";
            try (Connection conn = database.getConnection();
                 PreparedStatement stmt = conn.prepareStatement(sql)) {
                stmt.setInt(1, worldManager.getHardcorePlayerCount());
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
        if (currentRunId > 0 && gameState == GameState.ACTIVE) {
            Bukkit.getAsyncScheduler().runNow(plugin, task -> {
                String sql = "UPDATE run_history SET peak_players = GREATEST(peak_players, ?) " +
                        "WHERE run_id = ?";
                try (Connection conn = database.getConnection();
                     PreparedStatement stmt = conn.prepareStatement(sql)) {
                    stmt.setInt(1, worldManager.getHardcorePlayerCount());
                    stmt.setInt(2, currentRunId);
                    stmt.executeUpdate();
                } catch (SQLException e) {
                    plugin.getLogger().warning("Failed to update peak players: " + e.getMessage());
                }
            });
        }
    }

    // ==================== BROADCASTS ====================

    private void broadcastGeneratingMessage() {
        Title title = Title.title(
                Component.text("GENERATING WORLD", NamedTextColor.GOLD),
                Component.text("Prepare yourself...", NamedTextColor.GRAY),
                Title.Times.times(Duration.ZERO, Duration.ofSeconds(5), Duration.ofMillis(500))
        );

        for (var player : Bukkit.getOnlinePlayers()) {
            player.showTitle(title);
        }

        Bukkit.broadcast(MessageUtil.info("Generating hardcore world... Stand by!"));
    }

    private void broadcastRunStartMessage() {
        Title title = Title.title(
                Component.text("RUN STARTED!", NamedTextColor.GREEN),
                Component.text("Kill the dragon. Don't die.", NamedTextColor.WHITE),
                Title.Times.times(Duration.ZERO, Duration.ofSeconds(3), Duration.ofMillis(500))
        );

        for (var player : Bukkit.getOnlinePlayers()) {
            player.showTitle(title);
        }

        Bukkit.broadcast(MessageUtil.success("Run #" + currentRunId + " has begun! Good luck."));
    }

    /**
     * Broadcast event to Director AI WebSocket clients.
     */
    private void broadcastDirectorEvent(String eventType, int runId, String worldName) {
        if (plugin.getDirectorServer() == null) return;

        com.google.gson.JsonObject data = new com.google.gson.JsonObject();
        data.addProperty("runId", runId);
        data.addProperty("worldName", worldName);
        data.addProperty("gameState", gameState.name());

        plugin.getDirectorServer().broadcastEvent(eventType, data);
    }

    // ==================== GETTERS ====================

    public int getCurrentRunId() {
        return currentRunId;
    }

    public long getRunStartTime() {
        return runStartTime;
    }

    public long getRunDurationSeconds() {
        if (gameState != GameState.ACTIVE || runStartTime == 0) {
            return 0;
        }
        return (System.currentTimeMillis() - runStartTime) / 1000;
    }

    public boolean isDragonAlive() {
        return dragonAlive;
    }

    public void setDragonAlive(boolean alive) {
        this.dragonAlive = alive;
    }

    public String getCurrentWorldName() {
        return currentWorldName;
    }

    /**
     * @deprecated Use startRun() instead - this is kept for backwards compatibility during migration
     */
    @Deprecated
    public void ensureActiveRun() {
        // No longer auto-starts - game starts in IDLE state
        plugin.getLogger().info("Game starting in IDLE state. Use /vote to start a run.");
    }

    /**
     * @deprecated Use startRun() instead
     */
    @Deprecated
    public void startNewRun() {
        startRun(null);
    }
}
