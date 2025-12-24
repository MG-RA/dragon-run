package com.dragonrun.managers;

import com.dragonrun.DragonRunPlugin;
import com.dragonrun.database.Database;
import com.dragonrun.util.MessageUtil;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import net.kyori.adventure.title.Title;
import org.bukkit.Bukkit;
import org.bukkit.Color;
import org.bukkit.FireworkEffect;
import org.bukkit.Location;
import org.bukkit.entity.Firework;
import org.bukkit.entity.Player;
import org.bukkit.inventory.meta.FireworkMeta;

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

    // Track UUIDs of players actively participating in current run
    private final java.util.Set<java.util.UUID> activeParticipants = new java.util.concurrent.ConcurrentHashMap<java.util.UUID, Boolean>().keySet(true);

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

        // Reset per-run trackers
        if (plugin.getResourceMilestoneListener() != null) {
            plugin.getResourceMilestoneListener().resetMilestones();
        }
        if (plugin.getMobKillListener() != null) {
            plugin.getMobKillListener().resetRunData();
        }
        if (plugin.getStructureDiscoveryListener() != null) {
            plugin.getStructureDiscoveryListener().resetRunData();
        }

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

                    // Mark all players in hardcore world as active participants
                    org.bukkit.World hardcoreWorld = worldManager.getHardcoreWorld();
                    if (hardcoreWorld != null) {
                        for (org.bukkit.entity.Player player : hardcoreWorld.getPlayers()) {
                            addActiveParticipant(player.getUniqueId());
                        }
                    }

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
        long duration = getRunDurationSeconds();

        // Get all players who participated (in hardcore world or the end)
        java.util.List<String> victorNames = new java.util.ArrayList<>();
        for (Player p : Bukkit.getOnlinePlayers()) {
            String worldName = p.getWorld().getName();
            // Include players in hardcore world or its nether/end dimensions
            if (currentWorldName != null &&
                (worldName.equals(currentWorldName) ||
                 worldName.equals(currentWorldName + "_nether") ||
                 worldName.equals(currentWorldName + "_the_end"))) {
                victorNames.add(p.getName());
            }
        }

        // Save run to database (killer gets credited as dragon_killer)
        endRun("DRAGON_KILLED", null, killerUuid);

        // Get killer name for the "final blow" credit
        String killerName = Bukkit.getOfflinePlayer(killerUuid).getName();
        if (killerName == null) killerName = "Unknown";

        // Broadcast to Director AI with all victors
        com.google.gson.JsonObject data = new com.google.gson.JsonObject();
        data.addProperty("runId", currentRunId);
        data.addProperty("killerUuid", killerUuid.toString());
        data.addProperty("player", killerName);
        data.addProperty("outcome", "DRAGON_KILLED");
        data.addProperty("duration", duration);
        com.google.gson.JsonArray victorsArray = new com.google.gson.JsonArray();
        for (String name : victorNames) {
            victorsArray.add(name);
        }
        data.add("victors", victorsArray);
        if (plugin.getDirectorServer() != null) {
            plugin.getDirectorServer().broadcastEvent("dragon_killed", data);
        }

        // Victory celebration with all participants!
        celebrateVictory(killerName, victorNames, duration);

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
     * Celebrate a dragon kill victory with titles and fireworks.
     */
    private void celebrateVictory(String killerName, java.util.List<String> allVictors, long durationSeconds) {
        long mins = durationSeconds / 60;
        long secs = durationSeconds % 60;
        String timeStr = String.format("%d:%02d", mins, secs);

        // Build subtitle showing all victors or just the killer
        String subtitle;
        if (allVictors.size() > 1) {
            subtitle = String.join(", ", allVictors) + " defeated the dragon in " + timeStr;
        } else {
            subtitle = killerName + " slew the dragon in " + timeStr;
        }

        // Show victory title to all players
        Title victoryTitle = Title.title(
                Component.text("VICTORY!", NamedTextColor.GOLD),
                Component.text(subtitle, NamedTextColor.GREEN),
                Title.Times.times(Duration.ofMillis(500), Duration.ofSeconds(5), Duration.ofSeconds(2))
        );

        for (Player player : Bukkit.getOnlinePlayers()) {
            player.showTitle(victoryTitle);
        }

        // Broadcast victory message crediting all players
        if (allVictors.size() > 1) {
            Bukkit.broadcast(MessageUtil.success("The Ender Dragon has been slain!"));
            Bukkit.broadcast(MessageUtil.success("Victors: " + String.join(", ", allVictors)));
        } else {
            Bukkit.broadcast(MessageUtil.success("The Ender Dragon has been slain by " + killerName + "!"));
        }
        Bukkit.broadcast(MessageUtil.success("Run #" + currentRunId + " completed in " + timeStr));

        // Spawn fireworks for all players in the hardcore world
        spawnVictoryFireworks();

        // Continue spawning fireworks for a few seconds
        for (int i = 1; i <= 5; i++) {
            Bukkit.getScheduler().runTaskLater(plugin, this::spawnVictoryFireworks, i * 20L);
        }
    }

    /**
     * Spawn celebratory fireworks near all players.
     */
    private void spawnVictoryFireworks() {
        for (Player player : Bukkit.getOnlinePlayers()) {
            // Only for players in any world (lobby will see it too as celebration)
            Location loc = player.getLocation().add(
                    (Math.random() - 0.5) * 10,
                    5,
                    (Math.random() - 0.5) * 10
            );

            Firework fw = player.getWorld().spawn(loc, Firework.class);
            FireworkMeta meta = fw.getFireworkMeta();

            // Random colorful effects
            Color[] colors = {Color.RED, Color.GREEN, Color.BLUE, Color.YELLOW, Color.PURPLE, Color.AQUA, Color.WHITE};
            Color primary = colors[(int) (Math.random() * colors.length)];
            Color fade = colors[(int) (Math.random() * colors.length)];

            FireworkEffect.Type[] types = {FireworkEffect.Type.BALL, FireworkEffect.Type.BALL_LARGE, FireworkEffect.Type.STAR, FireworkEffect.Type.BURST};
            FireworkEffect.Type type = types[(int) (Math.random() * types.length)];

            FireworkEffect effect = FireworkEffect.builder()
                    .with(type)
                    .withColor(primary)
                    .withFade(fade)
                    .trail(Math.random() > 0.5)
                    .flicker(Math.random() > 0.5)
                    .build();

            meta.addEffect(effect);
            meta.setPower(1 + (int) (Math.random() * 2));
            fw.setFireworkMeta(meta);
        }
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

        // Clear active participants when run ends
        clearActiveParticipants();
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
     * Mark a player as actively participating in the current run
     */
    public void addActiveParticipant(UUID uuid) {
        activeParticipants.add(uuid);
    }

    /**
     * Check if a player was actively participating in the current run
     */
    public boolean isActiveParticipant(UUID uuid) {
        return activeParticipants.contains(uuid);
    }

    /**
     * Remove a player from active participants (when they die or leave)
     */
    public void removeActiveParticipant(UUID uuid) {
        activeParticipants.remove(uuid);
    }

    /**
     * Clear all active participants (called when run ends)
     */
    public void clearActiveParticipants() {
        activeParticipants.clear();
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
