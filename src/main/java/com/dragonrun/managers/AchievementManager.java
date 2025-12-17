package com.dragonrun.managers;

import com.dragonrun.DragonRunPlugin;
import com.dragonrun.database.Database;
import com.dragonrun.util.MessageUtil;
import org.bukkit.Bukkit;
import org.bukkit.entity.Player;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

public class AchievementManager {

    private final DragonRunPlugin plugin;
    private final Database database;

    // Cache of player achievements (UUID -> Set of achievement IDs)
    private final Map<UUID, Set<String>> playerAchievements = new ConcurrentHashMap<>();

    // All achievement definitions
    private final Map<String, Achievement> achievements = new LinkedHashMap<>();

    public AchievementManager(DragonRunPlugin plugin, Database database) {
        this.plugin = plugin;
        this.database = database;
        registerAchievements();
    }

    private void registerAchievements() {
        // === POSITIVE ACHIEVEMENTS ===

        // Progression
        register("first_blood", "First Blood", "Kill your first mob", 10, Category.PROGRESSION);
        register("iron_age", "Iron Age", "Craft a full set of iron armor", 25, Category.PROGRESSION);
        register("diamond_hands", "Diamond Hands", "Obtain a diamond", 50, Category.PROGRESSION);
        register("nether_explorer", "Nether Explorer", "Enter the Nether", 75, Category.PROGRESSION);
        register("blaze_hunter", "Blaze Hunter", "Kill a Blaze", 50, Category.PROGRESSION);
        register("ender_eyes", "Ender Eyes", "Craft an Eye of Ender", 100, Category.PROGRESSION);
        register("the_end", "The End?", "Enter The End dimension", 150, Category.PROGRESSION);
        register("dragon_slayer", "Dragon Slayer", "Kill the Ender Dragon", 1000, Category.PROGRESSION);

        // Combat
        register("monster_hunter", "Monster Hunter", "Kill 50 mobs in one run", 30, Category.COMBAT);
        register("mass_extinction", "Mass Extinction", "Kill 100 mobs in one run", 75, Category.COMBAT);
        register("genocide", "Genocide", "Kill 500 mobs in one run", 200, Category.COMBAT);
        register("wither_killer", "Wither Killer", "Kill the Wither", 500, Category.COMBAT);
        register("zombie_slayer", "Zombie Slayer", "Kill 100 zombies lifetime", 50, Category.COMBAT);
        register("skeleton_sniper", "Skeleton Sniper", "Kill a skeleton from 50+ blocks", 75, Category.COMBAT);
        register("creeper_sweeper", "Creeper Sweeper", "Kill 50 creepers lifetime", 60, Category.COMBAT);

        // Survival
        register("survivor", "Survivor", "Survive for 30 minutes in a run", 50, Category.SURVIVAL);
        register("veteran", "Veteran", "Survive for 1 hour in a run", 100, Category.SURVIVAL);
        register("legend", "Legend", "Survive for 2 hours in a run", 250, Category.SURVIVAL);
        register("iron_stomach", "Iron Stomach", "Eat 100 food items in one run", 25, Category.SURVIVAL);
        register("no_hit", "Untouchable", "Kill the dragon without taking damage", 500, Category.SURVIVAL);

        // Social
        register("team_player", "Team Player", "Play in a run with 5+ players", 25, Category.SOCIAL);
        register("party_time", "Party Time", "Play in a run with 10+ players", 50, Category.SOCIAL);
        register("popular", "Popular", "Be online when 20 players join", 100, Category.SOCIAL);

        // Economy
        register("aura_haver", "Aura Haver", "Reach 500 aura", 50, Category.ECONOMY);
        register("aura_merchant", "Aura Merchant", "Reach 1000 aura", 100, Category.ECONOMY);
        register("aura_lord", "Aura Lord", "Reach 2500 aura", 200, Category.ECONOMY);
        register("aura_emperor", "Aura Emperor", "Reach 5000 aura", 500, Category.ECONOMY);
        register("big_spender", "Big Spender", "Spend 1000 aura in the shop", 50, Category.ECONOMY);

        // Speedrun
        register("speedrunner", "Speedrunner", "Kill the dragon in under 1 hour", 300, Category.SPEEDRUN);
        register("speed_demon", "Speed Demon", "Kill the dragon in under 30 minutes", 750, Category.SPEEDRUN);
        register("world_record", "World Record Pace", "Kill the dragon in under 15 minutes", 2000, Category.SPEEDRUN);

        // === NEGATIVE ACHIEVEMENTS (DEROGATORY) ===

        // Deaths
        register("skill_issue", "Skill Issue", "Die within 1 minute of spawning", -25, Category.SHAME);
        register("first_death", "First Death", "Die for the first time", -10, Category.SHAME);
        register("serial_dier", "Serial Dier", "Die 10 times lifetime", -50, Category.SHAME);
        register("professional_dier", "Professional Dier", "Die 50 times lifetime", -150, Category.SHAME);
        register("lava_swimmer", "Lava Swimmer", "Die in lava 5 times", -75, Category.SHAME);
        register("ground_inspector", "Ground Inspector", "Die from fall damage 10 times", -50, Category.SHAME);
        register("fish_food", "Fish Food", "Drown 5 times", -40, Category.SHAME);
        register("starving_artist", "Starving Artist", "Die from starvation", -100, Category.SHAME);
        register("void_walker", "Void Walker", "Fall into the void 3 times", -60, Category.SHAME);

        // Embarrassing
        register("team_killer", "Team Killer", "Cause a run to end", -50, Category.SHAME);
        register("run_ender", "Run Ender", "End 5 runs by dying", -150, Category.SHAME);
        register("cursed", "Cursed", "End 10 runs by dying", -300, Category.SHAME);
        register("aura_debt", "Aura Debt", "Go below 0 aura", -25, Category.SHAME);
        register("rock_bottom", "Rock Bottom", "Reach -500 aura", -100, Category.SHAME);
    }

    private void register(String id, String name, String description, int auraReward, Category category) {
        achievements.put(id, new Achievement(id, name, description, auraReward, category));
    }

    /**
     * Award an achievement to a player
     */
    public boolean award(UUID uuid, String achievementId) {
        Achievement achievement = achievements.get(achievementId);
        if (achievement == null) {
            plugin.getLogger().warning("Unknown achievement: " + achievementId);
            return false;
        }

        // Check if already earned
        if (hasAchievement(uuid, achievementId)) {
            return false;
        }

        // Add to cache
        playerAchievements.computeIfAbsent(uuid, k -> ConcurrentHashMap.newKeySet()).add(achievementId);

        // Save to database
        int runId = plugin.getRunManager().getCurrentRunId();
        Bukkit.getAsyncScheduler().runNow(plugin, task -> {
            saveAchievement(uuid, achievementId, runId);
        });

        // Award aura
        plugin.getAuraManager().addAura(uuid, achievement.auraReward(), achievement.name());

        // Broadcast
        Player player = Bukkit.getPlayer(uuid);
        String playerName = player != null ? player.getName() : Bukkit.getOfflinePlayer(uuid).getName();
        if (playerName == null) playerName = "Unknown";

        Bukkit.broadcast(MessageUtil.achievementUnlocked(
                playerName,
                achievement.name(),
                achievement.description(),
                achievement.auraReward()
        ));

        // Update scoreboard (achievements changed, aura changed)
        if (player != null && player.isOnline()) {
            plugin.getScoreboardManager().updateScoreboard(player);
            plugin.getScoreboardManager().updatePlayerTabList(player);
        }

        return true;
    }

    /**
     * Check if player has an achievement
     */
    public boolean hasAchievement(UUID uuid, String achievementId) {
        Set<String> earned = playerAchievements.get(uuid);
        return earned != null && earned.contains(achievementId);
    }

    /**
     * Get all achievements a player has earned
     */
    public Set<String> getPlayerAchievements(UUID uuid) {
        return playerAchievements.getOrDefault(uuid, Collections.emptySet());
    }

    /**
     * Get all achievement definitions
     */
    public Collection<Achievement> getAllAchievements() {
        return achievements.values();
    }

    /**
     * Get achievement by ID
     */
    public Achievement getAchievement(String id) {
        return achievements.get(id);
    }

    /**
     * Load player achievements from database
     */
    public void loadPlayer(UUID uuid) {
        Bukkit.getAsyncScheduler().runNow(plugin, task -> {
            Set<String> earned = ConcurrentHashMap.newKeySet();
            String sql = "SELECT achievement_id FROM achievements_earned WHERE uuid = ?";

            try (Connection conn = database.getConnection();
                 PreparedStatement stmt = conn.prepareStatement(sql)) {
                stmt.setString(1, uuid.toString());
                try (ResultSet rs = stmt.executeQuery()) {
                    while (rs.next()) {
                        earned.add(rs.getString("achievement_id"));
                    }
                }
            } catch (SQLException e) {
                plugin.getLogger().warning("Failed to load achievements for " + uuid + ": " + e.getMessage());
            }

            playerAchievements.put(uuid, earned);
        });
    }

    /**
     * Unload player from cache
     */
    public void unloadPlayer(UUID uuid) {
        playerAchievements.remove(uuid);
    }

    private void saveAchievement(UUID uuid, String achievementId, int runId) {
        String sql = "INSERT INTO achievements_earned (uuid, achievement_id, run_id) VALUES (?, ?, ?) " +
                "ON CONFLICT (uuid, achievement_id) DO NOTHING";

        try (Connection conn = database.getConnection();
             PreparedStatement stmt = conn.prepareStatement(sql)) {
            stmt.setString(1, uuid.toString());
            stmt.setString(2, achievementId);
            stmt.setInt(3, runId);
            stmt.executeUpdate();
        } catch (SQLException e) {
            plugin.getLogger().warning("Failed to save achievement: " + e.getMessage());
        }
    }

    /**
     * Get count of achievements by category for a player
     */
    public Map<Category, int[]> getPlayerProgress(UUID uuid) {
        Map<Category, int[]> progress = new EnumMap<>(Category.class);
        Set<String> earned = getPlayerAchievements(uuid);

        for (Category cat : Category.values()) {
            int total = 0;
            int unlocked = 0;
            for (Achievement a : achievements.values()) {
                if (a.category() == cat) {
                    total++;
                    if (earned.contains(a.id())) {
                        unlocked++;
                    }
                }
            }
            progress.put(cat, new int[]{unlocked, total});
        }

        return progress;
    }

    // Achievement record
    public record Achievement(String id, String name, String description, int auraReward, Category category) {
        public boolean isPositive() {
            return auraReward >= 0;
        }
    }

    // Achievement categories
    public enum Category {
        PROGRESSION("Progression"),
        COMBAT("Combat"),
        SURVIVAL("Survival"),
        SOCIAL("Social"),
        ECONOMY("Economy"),
        SPEEDRUN("Speedrun"),
        SHAME("Shame");

        private final String displayName;

        Category(String displayName) {
            this.displayName = displayName;
        }

        public String getDisplayName() {
            return displayName;
        }
    }
}
