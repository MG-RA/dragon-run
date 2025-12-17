package com.dragonrun.managers;

import com.dragonrun.DragonRunPlugin;
import com.dragonrun.database.Database;
import com.dragonrun.util.MessageUtil;
import net.kyori.adventure.text.Component;
import org.bukkit.Bukkit;
import org.bukkit.entity.Player;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;

public class AuraManager {

    private final DragonRunPlugin plugin;
    private final Database database;

    // In-memory cache for current session
    private final Map<UUID, Integer> auraCache = new ConcurrentHashMap<>();

    // Aura thresholds for broadcasts
    private static final int BROADCAST_GAIN_THRESHOLD = 100;
    private static final int BROADCAST_LOSS_THRESHOLD = -50;

    public AuraManager(DragonRunPlugin plugin, Database database) {
        this.plugin = plugin;
        this.database = database;
    }

    /**
     * Get player's current aura (from cache or database)
     */
    public int getAura(UUID uuid) {
        return auraCache.computeIfAbsent(uuid, this::loadAuraFromDatabase);
    }

    private int loadAuraFromDatabase(UUID uuid) {
        String sql = "SELECT aura FROM players WHERE uuid = ?";
        try (Connection conn = database.getConnection();
             PreparedStatement stmt = conn.prepareStatement(sql)) {
            stmt.setString(1, uuid.toString());
            try (ResultSet rs = stmt.executeQuery()) {
                if (rs.next()) {
                    return rs.getInt("aura");
                }
            }
        } catch (SQLException e) {
            plugin.getLogger().warning("Failed to load aura for " + uuid + ": " + e.getMessage());
        }
        return plugin.getConfig().getInt("game.starting-aura", 100);
    }

    /**
     * Add aura to player with reason tracking
     */
    public void addAura(UUID uuid, int amount, String reason) {
        if (amount == 0) return;

        int newAura = auraCache.merge(uuid, amount, Integer::sum);

        // Persist to database asynchronously
        Bukkit.getAsyncScheduler().runNow(plugin, task -> persistAura(uuid, newAura));

        // Notify player
        Player player = Bukkit.getPlayer(uuid);
        if (player != null) {
            player.sendMessage(MessageUtil.auraChange(amount, reason));
        }

        // Broadcast significant changes
        if (amount >= BROADCAST_GAIN_THRESHOLD) {
            broadcastAuraGain(uuid, amount, reason);
        } else if (amount <= BROADCAST_LOSS_THRESHOLD) {
            broadcastAuraLoss(uuid, Math.abs(amount), reason);
        }
    }

    /**
     * Remove aura (delegates to addAura with negative amount)
     */
    public void removeAura(UUID uuid, int amount, String reason) {
        addAura(uuid, -amount, reason);
    }

    private void persistAura(UUID uuid, int aura) {
        String sql = "UPDATE players SET aura = ?, last_seen = NOW() WHERE uuid = ?";
        try (Connection conn = database.getConnection();
             PreparedStatement stmt = conn.prepareStatement(sql)) {
            stmt.setInt(1, aura);
            stmt.setString(2, uuid.toString());
            stmt.executeUpdate();
        } catch (SQLException e) {
            plugin.getLogger().warning("Failed to persist aura: " + e.getMessage());
        }
    }

    private void broadcastAuraGain(UUID uuid, int amount, String reason) {
        String playerName = Bukkit.getOfflinePlayer(uuid).getName();
        if (playerName == null) playerName = "Unknown";
        Component message = MessageUtil.auraBroadcastGain(playerName, amount, reason);
        Bukkit.broadcast(message);
    }

    private void broadcastAuraLoss(UUID uuid, int amount, String reason) {
        String playerName = Bukkit.getOfflinePlayer(uuid).getName();
        if (playerName == null) playerName = "Unknown";
        Component message = MessageUtil.auraBroadcastLoss(playerName, amount, reason);
        Bukkit.broadcast(message);
    }

    /**
     * Load aura for player on join, creating record if needed
     */
    public void loadPlayer(Player player) {
        UUID uuid = player.getUniqueId();

        Bukkit.getAsyncScheduler().runNow(plugin, task -> {
            String sql = "INSERT INTO players (uuid, username, aura) VALUES (?, ?, ?) " +
                    "ON CONFLICT (uuid) DO UPDATE SET username = ?, last_seen = NOW()";
            try (Connection conn = database.getConnection();
                 PreparedStatement stmt = conn.prepareStatement(sql)) {
                int startingAura = plugin.getConfig().getInt("game.starting-aura", 100);
                stmt.setString(1, uuid.toString());
                stmt.setString(2, player.getName());
                stmt.setInt(3, startingAura);
                stmt.setString(4, player.getName());
                stmt.executeUpdate();
            } catch (SQLException e) {
                plugin.getLogger().warning("Failed to load player: " + e.getMessage());
            }

            // Load into cache
            auraCache.put(uuid, loadAuraFromDatabase(uuid));
        });
    }

    /**
     * Clear cache entry when player leaves
     */
    public void unloadPlayer(UUID uuid) {
        auraCache.remove(uuid);
    }

    /**
     * Increment player's total runs count
     */
    public void incrementRunCount(UUID uuid) {
        Bukkit.getAsyncScheduler().runNow(plugin, task -> {
            String sql = "UPDATE players SET total_runs = total_runs + 1 WHERE uuid = ?";
            try (Connection conn = database.getConnection();
                 PreparedStatement stmt = conn.prepareStatement(sql)) {
                stmt.setString(1, uuid.toString());
                stmt.executeUpdate();
            } catch (SQLException e) {
                plugin.getLogger().warning("Failed to increment run count: " + e.getMessage());
            }
        });
    }

    /**
     * Increment player's death count
     */
    public void incrementDeathCount(UUID uuid) {
        Bukkit.getAsyncScheduler().runNow(plugin, task -> {
            String sql = "UPDATE players SET total_deaths = total_deaths + 1 WHERE uuid = ?";
            try (Connection conn = database.getConnection();
                 PreparedStatement stmt = conn.prepareStatement(sql)) {
                stmt.setString(1, uuid.toString());
                stmt.executeUpdate();
            } catch (SQLException e) {
                plugin.getLogger().warning("Failed to increment death count: " + e.getMessage());
            }
        });
    }

    /**
     * Increment player's dragon kill count
     */
    public void incrementDragonKills(UUID uuid) {
        Bukkit.getAsyncScheduler().runNow(plugin, task -> {
            String sql = "UPDATE players SET dragons_killed = dragons_killed + 1 WHERE uuid = ?";
            try (Connection conn = database.getConnection();
                 PreparedStatement stmt = conn.prepareStatement(sql)) {
                stmt.setString(1, uuid.toString());
                stmt.executeUpdate();
            } catch (SQLException e) {
                plugin.getLogger().warning("Failed to increment dragon kills: " + e.getMessage());
            }
        });
    }
}
