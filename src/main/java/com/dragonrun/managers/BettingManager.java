package com.dragonrun.managers;

import com.dragonrun.DragonRunPlugin;
import com.dragonrun.database.Database;
import org.bukkit.Bukkit;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

public class BettingManager {

    private final DragonRunPlugin plugin;
    private final Database database;

    // Cache: bettor UUID -> (target UUID -> bet amount)
    private final Map<UUID, Map<UUID, Integer>> activeBets = new ConcurrentHashMap<>();

    public BettingManager(DragonRunPlugin plugin, Database database) {
        this.plugin = plugin;
        this.database = database;
    }

    /**
     * Place a bet on a player
     * @param bettor Who is placing the bet
     * @param target Who they're betting on
     * @param amount How much aura to bet
     * @return true if bet was placed successfully
     */
    public boolean placeBet(UUID bettor, UUID target, int amount) {
        // Validation
        if (bettor.equals(target)) {
            return false; // Can't bet on yourself
        }

        int currentAura = plugin.getAuraManager().getAura(bettor);
        if (currentAura < amount) {
            return false; // Not enough aura
        }

        if (amount <= 0) {
            return false; // Invalid amount
        }

        // Get current bets on this target
        int existingBet = getActiveBet(bettor, target);
        int totalBet = existingBet + amount;

        // Deduct aura from bettor
        plugin.getAuraManager().removeAura(bettor, amount, "Bet on player");

        // Store bet
        activeBets.computeIfAbsent(bettor, k -> new ConcurrentHashMap<>()).put(target, totalBet);

        // Save to database
        int runId = plugin.getRunManager().getCurrentRunId();
        Bukkit.getAsyncScheduler().runNow(plugin, task -> {
            saveBet(bettor, target, amount, runId);
        });

        return true;
    }

    /**
     * Get active bet amount from bettor on target
     */
    public int getActiveBet(UUID bettor, UUID target) {
        Map<UUID, Integer> bets = activeBets.get(bettor);
        return bets != null ? bets.getOrDefault(target, 0) : 0;
    }

    /**
     * Get all active bets placed by a player
     */
    public Map<UUID, Integer> getPlayerBets(UUID bettor) {
        return activeBets.getOrDefault(bettor, new ConcurrentHashMap<>());
    }

    /**
     * Get total amount bet on a target by all players
     */
    public int getTotalBetsOnPlayer(UUID target) {
        return activeBets.values().stream()
                .mapToInt(bets -> bets.getOrDefault(target, 0))
                .sum();
    }

    /**
     * Process payouts when a player dies (all bets on them are lost)
     * OR when the run ends successfully (bets pay out)
     */
    public void processDeath(UUID deceased) {
        // All bets on the deceased player are lost
        activeBets.values().forEach(bets -> bets.remove(deceased));

        // Also clear any bets the deceased had placed
        activeBets.remove(deceased);
    }

    /**
     * Process run completion - pay out all surviving bets
     */
    public void processRunCompletion() {
        // This would be called if the dragon is killed successfully
        // Pay out all remaining bets (2x multiplier as a reward)
        for (Map.Entry<UUID, Map<UUID, Integer>> entry : activeBets.entrySet()) {
            UUID bettor = entry.getKey();
            Map<UUID, Integer> bets = entry.getValue();

            for (Map.Entry<UUID, Integer> bet : bets.entrySet()) {
                UUID target = bet.getKey();
                int amount = bet.getValue();

                // Check if target is still alive (hasn't quit)
                if (Bukkit.getPlayer(target) != null || Bukkit.getOfflinePlayer(target).isOnline()) {
                    // Pay out 2x (return bet + winnings)
                    plugin.getAuraManager().addAura(bettor, amount * 2, "Bet payout");
                }
            }
        }

        clearAllBets();
    }

    /**
     * Clear all bets (called on world reset)
     */
    public void clearAllBets() {
        activeBets.clear();
    }

    /**
     * Load active bets for current run from database
     */
    public void loadActiveBets(int runId) {
        Bukkit.getAsyncScheduler().runNow(plugin, task -> {
            try (Connection conn = database.getConnection()) {
                String sql = "SELECT bettor_uuid, target_uuid, amount FROM active_bets WHERE run_id = ?";
                try (PreparedStatement stmt = conn.prepareStatement(sql)) {
                    stmt.setInt(1, runId);
                    try (ResultSet rs = stmt.executeQuery()) {
                        while (rs.next()) {
                            UUID bettor = UUID.fromString(rs.getString("bettor_uuid"));
                            UUID target = UUID.fromString(rs.getString("target_uuid"));
                            int amount = rs.getInt("amount");

                            activeBets.computeIfAbsent(bettor, k -> new ConcurrentHashMap<>())
                                    .merge(target, amount, Integer::sum);
                        }
                    }
                }
            } catch (SQLException e) {
                plugin.getLogger().warning("Failed to load active bets: " + e.getMessage());
            }
        });
    }

    private void saveBet(UUID bettor, UUID target, int amount, int runId) {
        try (Connection conn = database.getConnection()) {
            // Insert or update active bet
            String sql = """
                    INSERT INTO active_bets (run_id, bettor_uuid, target_uuid, amount)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT (run_id, bettor_uuid, target_uuid)
                    DO UPDATE SET amount = active_bets.amount + EXCLUDED.amount
                    """;

            try (PreparedStatement stmt = conn.prepareStatement(sql)) {
                stmt.setInt(1, runId);
                stmt.setString(2, bettor.toString());
                stmt.setString(3, target.toString());
                stmt.setInt(4, amount);
                stmt.executeUpdate();
            }
        } catch (SQLException e) {
            plugin.getLogger().warning("Failed to save bet: " + e.getMessage());
        }
    }
}
