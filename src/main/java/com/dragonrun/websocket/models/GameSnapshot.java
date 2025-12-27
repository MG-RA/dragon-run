package com.dragonrun.websocket.models;

import com.dragonrun.DragonRunPlugin;
import com.dragonrun.listeners.AchievementListener;
import com.dragonrun.managers.GameState;
import com.google.gson.JsonObject;
import org.bukkit.Bukkit;
import org.bukkit.World;
import org.bukkit.boss.DragonBattle;
import org.bukkit.entity.EnderDragon;
import org.bukkit.entity.Player;

import java.util.ArrayList;
import java.util.List;
import java.util.Queue;

/**
 * Immutable snapshot of entire game state for thread-safe WebSocket broadcasting.
 *
 * This record is captured on the main server thread where Bukkit API access is safe,
 * then serialized and sent on an async thread to avoid blocking the main thread.
 */
public record GameSnapshot(
    long timestamp,
    String gameState,
    int runId,
    long runDuration,
    boolean dragonAlive,
    double dragonHealth,
    String worldName,
    Long worldSeed,
    String weatherState,
    long timeOfDay,
    int lobbyPlayers,
    int hardcorePlayers,
    int totalPlayers,
    Integer voteCount,
    Integer votesRequired,
    List<PlayerStateSnapshot> players,
    List<JsonObject> recentEvents
) {
    /**
     * Capture the complete game state on the main thread.
     * This method MUST be called from the main server thread.
     *
     * @param plugin The DragonRun plugin instance
     * @param recentEventsQueue Queue of recent events to include
     * @return Immutable snapshot of current game state
     */
    public static GameSnapshot capture(DragonRunPlugin plugin, Queue<JsonObject> recentEventsQueue) {
        long timestamp = System.currentTimeMillis();

        // Game state from RunManager
        GameState gameState = plugin.getRunManager().getGameState();
        int runId = plugin.getRunManager().getCurrentRunId();
        long runDuration = plugin.getRunManager().getRunDurationSeconds();
        boolean dragonAlive = plugin.getRunManager().isDragonAlive();

        // Dragon health
        double dragonHealth = getDragonHealth(plugin);

        // World info
        String worldName = plugin.getRunManager().getCurrentWorldName();
        Long worldSeed = null;
        String weatherState = "clear";
        long timeOfDay = 0;

        if (worldName != null) {
            World world = Bukkit.getWorld(worldName);
            if (world != null) {
                worldSeed = world.getSeed();
                weatherState = world.hasStorm() ? (world.isThundering() ? "thunder" : "rain") : "clear";
                timeOfDay = world.getTime();
            }
        }

        // Player counts
        int lobbyPlayers = plugin.getWorldManager().getLobbyPlayerCount();
        int hardcorePlayers = plugin.getWorldManager().getHardcorePlayerCount();
        int totalPlayers = Bukkit.getOnlinePlayers().size();

        // Vote info (only in IDLE state)
        Integer voteCount = null;
        Integer votesRequired = null;
        if (gameState == GameState.IDLE) {
            voteCount = plugin.getVoteManager().getVoteCount();
            votesRequired = plugin.getVoteManager().getRequiredVotes();
        }

        // Capture player snapshots
        List<PlayerStateSnapshot> players = capturePlayerSnapshots(plugin, worldName);

        // Copy recent events (defensive copy)
        List<JsonObject> recentEvents = new ArrayList<>(recentEventsQueue);

        return new GameSnapshot(
            timestamp,
            gameState.name(),
            runId,
            runDuration,
            dragonAlive,
            dragonHealth,
            worldName,
            worldSeed,
            weatherState,
            timeOfDay,
            lobbyPlayers,
            hardcorePlayers,
            totalPlayers,
            voteCount,
            votesRequired,
            players,
            recentEvents
        );
    }

    /**
     * Capture all player snapshots with enriched data.
     */
    private static List<PlayerStateSnapshot> capturePlayerSnapshots(DragonRunPlugin plugin, String worldName) {
        List<PlayerStateSnapshot> snapshots = new ArrayList<>();
        AchievementListener listener = plugin.getAchievementListener();

        for (Player player : Bukkit.getOnlinePlayers()) {
            // Only include players in the run world (if there's an active run)
            if (worldName == null || player.getWorld().getName().equals(worldName)) {
                PlayerStateSnapshot snapshot = new PlayerStateSnapshot(player);

                // Enrich with aura data
                snapshot.setAura(plugin.getAuraManager().getAura(player.getUniqueId()));

                // Enrich with achievement listener stats
                if (listener != null) {
                    snapshot.setMobKills(listener.getRunMobKills(player.getUniqueId()));
                    snapshot.setAliveSeconds(listener.getAliveSeconds(player.getUniqueId()));
                    snapshot.setEnteredNether(listener.hasEnteredNether(player.getUniqueId()));
                    snapshot.setEnteredEnd(listener.hasEnteredEnd(player.getUniqueId()));
                }

                snapshots.add(snapshot);
            }
        }

        return snapshots;
    }

    /**
     * Get current dragon health, or 0 if dragon is dead/not found.
     */
    private static double getDragonHealth(DragonRunPlugin plugin) {
        if (!plugin.getRunManager().isDragonAlive()) {
            return 0.0;
        }

        String worldName = plugin.getRunManager().getCurrentWorldName();
        if (worldName == null) return 0.0;

        World endWorld = Bukkit.getWorld(worldName + "_the_end");
        if (endWorld == null) return 0.0;

        DragonBattle battle = endWorld.getEnderDragonBattle();
        if (battle == null) return 0.0;

        EnderDragon dragon = battle.getEnderDragon();
        if (dragon == null || dragon.isDead()) return 0.0;

        return dragon.getHealth();
    }
}
