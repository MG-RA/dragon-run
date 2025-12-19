package com.dragonrun.listeners;

import com.dragonrun.DragonRunPlugin;
import com.dragonrun.managers.AchievementManager;
import org.bukkit.Material;
import org.bukkit.Statistic;
import org.bukkit.entity.*;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.entity.EntityDeathEvent;
import org.bukkit.event.entity.PlayerDeathEvent;
import org.bukkit.event.inventory.CraftItemEvent;
import org.bukkit.event.player.PlayerChangedWorldEvent;
import org.bukkit.event.player.PlayerJoinEvent;
import org.bukkit.inventory.ItemStack;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

public class AchievementListener implements Listener {

    private final DragonRunPlugin plugin;
    private final AchievementManager achievementManager;

    // Track per-run stats
    private final Map<UUID, Integer> runMobKills = new ConcurrentHashMap<>();
    private final Map<UUID, Integer> runFoodEaten = new ConcurrentHashMap<>();
    private final Map<UUID, Long> runJoinTime = new ConcurrentHashMap<>();
    private final Map<UUID, Integer> runsEnded = new ConcurrentHashMap<>();
    private final Map<UUID, Boolean> netherVisited = new ConcurrentHashMap<>();
    private final Map<UUID, Boolean> endVisited = new ConcurrentHashMap<>();

    // Track lifetime stats (loaded from DB would be better, but tracking in-memory for now)
    private final Map<UUID, Integer> lifetimeDeaths = new ConcurrentHashMap<>();
    private final Map<UUID, Integer> lavaDeaths = new ConcurrentHashMap<>();
    private final Map<UUID, Integer> fallDeaths = new ConcurrentHashMap<>();
    private final Map<UUID, Integer> drownDeaths = new ConcurrentHashMap<>();
    private final Map<UUID, Integer> voidDeaths = new ConcurrentHashMap<>();

    public AchievementListener(DragonRunPlugin plugin) {
        this.plugin = plugin;
        this.achievementManager = plugin.getAchievementManager();
    }

    @EventHandler
    public void onPlayerJoin(PlayerJoinEvent event) {
        Player player = event.getPlayer();
        UUID uuid = player.getUniqueId();

        // Track join time for survival achievements
        runJoinTime.put(uuid, System.currentTimeMillis());

        // Reset run-specific counters
        runMobKills.put(uuid, 0);
        runFoodEaten.put(uuid, 0);

        // Check social achievements
        int onlinePlayers = plugin.getServer().getOnlinePlayers().size();
        if (onlinePlayers >= 5) {
            achievementManager.award(uuid, "team_player");
        }
        if (onlinePlayers >= 10) {
            achievementManager.award(uuid, "party_time");
        }
        if (onlinePlayers >= 20) {
            // Award to all online players
            for (Player p : plugin.getServer().getOnlinePlayers()) {
                achievementManager.award(p.getUniqueId(), "popular");
            }
        }

        // Check aura-based achievements
        checkAuraAchievements(uuid);
    }

    @EventHandler
    public void onEntityDeath(EntityDeathEvent event) {
        Player killer = event.getEntity().getKiller();
        if (killer == null) return;

        UUID uuid = killer.getUniqueId();
        Entity entity = event.getEntity();

        // First kill achievement
        if (entity instanceof Monster) {
            int kills = runMobKills.merge(uuid, 1, Integer::sum);

            if (kills == 1) {
                achievementManager.award(uuid, "first_blood");
            }
            if (kills >= 50) {
                achievementManager.award(uuid, "monster_hunter");
            }
            if (kills >= 100) {
                achievementManager.award(uuid, "mass_extinction");
            }
            if (kills >= 500) {
                achievementManager.award(uuid, "genocide");
            }
        }

        // Specific mob kills
        if (entity instanceof Blaze) {
            achievementManager.award(uuid, "blaze_hunter");
        }

        if (entity instanceof Wither) {
            achievementManager.award(uuid, "wither_killer");
        }

        if (entity instanceof EnderDragon) {
            achievementManager.award(uuid, "dragon_slayer");

            // End the run with victory!
            plugin.getRunManager().endRunByDragonKill(uuid);

            // Check speedrun achievements
            long runDuration = plugin.getRunManager().getRunDurationSeconds();
            if (runDuration < 15 * 60) { // Under 15 minutes
                achievementManager.award(uuid, "world_record");
            }
            if (runDuration < 30 * 60) { // Under 30 minutes
                achievementManager.award(uuid, "speed_demon");
            }
            if (runDuration < 60 * 60) { // Under 1 hour
                achievementManager.award(uuid, "speedrunner");
            }

            // Check if player took no damage (simplified check - at full health)
            if (killer.getHealth() >= 20.0) {
                achievementManager.award(uuid, "no_hit");
            }
        }

        // Long-range skeleton kill
        if (entity instanceof Skeleton) {
            double distance = killer.getLocation().distance(entity.getLocation());
            if (distance >= 50) {
                achievementManager.award(uuid, "skeleton_sniper");
            }
        }
    }

    @EventHandler
    public void onWorldChange(PlayerChangedWorldEvent event) {
        Player player = event.getPlayer();
        UUID uuid = player.getUniqueId();
        String worldName = player.getWorld().getName().toLowerCase();
        String fromWorld = event.getFrom().getName().toLowerCase();

        // Determine dimension names
        String toDimension = getDimensionName(worldName);
        String fromDimension = getDimensionName(fromWorld);

        // Only broadcast if it's a real dimension change (not just world reload)
        if (!toDimension.equals(fromDimension) && plugin.getDirectorServer() != null) {
            com.google.gson.JsonObject data = new com.google.gson.JsonObject();
            data.addProperty("player", player.getName());
            data.addProperty("uuid", uuid.toString());
            data.addProperty("from", fromDimension);
            data.addProperty("to", toDimension);
            plugin.getDirectorServer().broadcastEvent("player_dimension_change", data);
        }

        if (worldName.contains("nether")) {
            netherVisited.put(uuid, true);
            achievementManager.award(uuid, "nether_explorer");
        }

        if (worldName.contains("end")) {
            endVisited.put(uuid, true);
            achievementManager.award(uuid, "the_end");
        }
    }

    private String getDimensionName(String worldName) {
        if (worldName.contains("nether")) return "nether";
        if (worldName.contains("end")) return "end";
        return "overworld";
    }

    @EventHandler
    public void onCraftItem(CraftItemEvent event) {
        if (!(event.getWhoClicked() instanceof Player player)) return;

        UUID uuid = player.getUniqueId();
        ItemStack result = event.getRecipe().getResult();
        Material type = result.getType();

        // Iron armor check
        if (type == Material.IRON_HELMET || type == Material.IRON_CHESTPLATE ||
            type == Material.IRON_LEGGINGS || type == Material.IRON_BOOTS) {
            // Check if player has full set after crafting
            plugin.getServer().getScheduler().runTaskLater(plugin, () -> {
                if (hasFullIronArmor(player)) {
                    achievementManager.award(uuid, "iron_age");
                }
            }, 1L);
        }

        // Eye of Ender
        if (type == Material.ENDER_EYE) {
            achievementManager.award(uuid, "ender_eyes");
        }
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onPlayerDeath(PlayerDeathEvent event) {
        Player player = event.getEntity();
        UUID uuid = player.getUniqueId();

        // First death
        int deaths = lifetimeDeaths.merge(uuid, 1, Integer::sum);
        if (deaths == 1) {
            achievementManager.award(uuid, "first_death");
        }
        if (deaths >= 10) {
            achievementManager.award(uuid, "serial_dier");
        }
        if (deaths >= 50) {
            achievementManager.award(uuid, "professional_dier");
        }

        // Skill issue - died within 1 minute
        Long joinTime = runJoinTime.get(uuid);
        if (joinTime != null && System.currentTimeMillis() - joinTime < 60_000) {
            achievementManager.award(uuid, "skill_issue");
        }

        // Track run endings
        int runsEndedCount = runsEnded.merge(uuid, 1, Integer::sum);
        achievementManager.award(uuid, "team_killer");
        if (runsEndedCount >= 5) {
            achievementManager.award(uuid, "run_ender");
        }
        if (runsEndedCount >= 10) {
            achievementManager.award(uuid, "cursed");
        }

        // Death type specific
        var cause = player.getLastDamageCause();
        if (cause != null) {
            switch (cause.getCause()) {
                case LAVA -> {
                    int lava = lavaDeaths.merge(uuid, 1, Integer::sum);
                    if (lava >= 5) achievementManager.award(uuid, "lava_swimmer");
                }
                case FALL -> {
                    int fall = fallDeaths.merge(uuid, 1, Integer::sum);
                    if (fall >= 10) achievementManager.award(uuid, "ground_inspector");
                }
                case DROWNING -> {
                    int drown = drownDeaths.merge(uuid, 1, Integer::sum);
                    if (drown >= 5) achievementManager.award(uuid, "fish_food");
                }
                case VOID -> {
                    int voidD = voidDeaths.merge(uuid, 1, Integer::sum);
                    if (voidD >= 3) achievementManager.award(uuid, "void_walker");
                }
                case STARVATION -> achievementManager.award(uuid, "starving_artist");
                default -> {}
            }
        }
    }

    /**
     * Check aura-based achievements for a player
     */
    public void checkAuraAchievements(UUID uuid) {
        int aura = plugin.getAuraManager().getAura(uuid);

        if (aura >= 500) achievementManager.award(uuid, "aura_haver");
        if (aura >= 1000) achievementManager.award(uuid, "aura_merchant");
        if (aura >= 2500) achievementManager.award(uuid, "aura_lord");
        if (aura >= 5000) achievementManager.award(uuid, "aura_emperor");

        if (aura < 0) achievementManager.award(uuid, "aura_debt");
        if (aura <= -500) achievementManager.award(uuid, "rock_bottom");
    }

    /**
     * Check survival time achievements (call periodically)
     */
    public void checkSurvivalAchievements(Player player) {
        UUID uuid = player.getUniqueId();
        Long joinTime = runJoinTime.get(uuid);
        if (joinTime == null) return;

        long aliveMinutes = (System.currentTimeMillis() - joinTime) / 60_000;

        if (aliveMinutes >= 30) achievementManager.award(uuid, "survivor");
        if (aliveMinutes >= 60) achievementManager.award(uuid, "veteran");
        if (aliveMinutes >= 120) achievementManager.award(uuid, "legend");
    }

    /**
     * Track diamond pickup for achievements
     */
    public void onDiamondObtained(Player player) {
        achievementManager.award(player.getUniqueId(), "diamond_hands");
    }

    /**
     * Track food consumption
     */
    public void onFoodEaten(Player player) {
        UUID uuid = player.getUniqueId();
        int eaten = runFoodEaten.merge(uuid, 1, Integer::sum);
        if (eaten >= 100) {
            achievementManager.award(uuid, "iron_stomach");
        }
    }

    /**
     * Track shop spending
     */
    public void onShopPurchase(UUID uuid, int amount) {
        // This would need cumulative tracking, simplified for now
        achievementManager.award(uuid, "big_spender");
    }

    private boolean hasFullIronArmor(Player player) {
        var inv = player.getInventory();
        return inv.getHelmet() != null && inv.getHelmet().getType() == Material.IRON_HELMET &&
               inv.getChestplate() != null && inv.getChestplate().getType() == Material.IRON_CHESTPLATE &&
               inv.getLeggings() != null && inv.getLeggings().getType() == Material.IRON_LEGGINGS &&
               inv.getBoots() != null && inv.getBoots().getType() == Material.IRON_BOOTS;
    }

    /**
     * Clear run-specific data (call on world reset)
     */
    public void clearRunData() {
        runMobKills.clear();
        runFoodEaten.clear();
        runJoinTime.clear();
        netherVisited.clear();
        endVisited.clear();
    }

    /**
     * Get mob kills for a player in current run.
     */
    public int getRunMobKills(UUID uuid) {
        return runMobKills.getOrDefault(uuid, 0);
    }

    /**
     * Get seconds alive for a player in current run.
     */
    public long getAliveSeconds(UUID uuid) {
        Long joinTime = runJoinTime.get(uuid);
        if (joinTime == null) return 0;
        return (System.currentTimeMillis() - joinTime) / 1000;
    }

    /**
     * Check if player has entered nether in current run.
     */
    public boolean hasEnteredNether(UUID uuid) {
        return netherVisited.getOrDefault(uuid, false);
    }

    /**
     * Check if player has entered the end in current run.
     */
    public boolean hasEnteredEnd(UUID uuid) {
        return endVisited.getOrDefault(uuid, false);
    }
}
