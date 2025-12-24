package com.dragonrun.listeners;

import com.dragonrun.DragonRunPlugin;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import org.bukkit.entity.*;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.entity.EntityDeathEvent;
import org.bukkit.inventory.ItemStack;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;

/**
 * Tracks mob kills and batches them before sending to Eris.
 * Aggregates kills by mob type per player, sends summary every 30 seconds.
 * Boss kills (Wither, Elder Guardian, Warden) are sent immediately.
 */
public class MobKillListener implements Listener {

    private final DragonRunPlugin plugin;

    // Batch storage: playerUUID -> (mobType -> count)
    private final Map<UUID, Map<String, Integer>> killBatches = new ConcurrentHashMap<>();

    // Track total kills per player for context
    private final Map<UUID, Integer> totalKillsThisRun = new ConcurrentHashMap<>();

    public MobKillListener(DragonRunPlugin plugin) {
        this.plugin = plugin;
        startBatchProcessor();
    }

    /**
     * Start the batch processor that sends aggregated kills every 30 seconds.
     */
    private void startBatchProcessor() {
        plugin.getServer().getAsyncScheduler().runAtFixedRate(plugin, task -> {
            flushBatches();
        }, 30, 30, TimeUnit.SECONDS);
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onEntityDeath(EntityDeathEvent event) {
        Player killer = event.getEntity().getKiller();
        if (killer == null) return;

        Entity entity = event.getEntity();
        if (!(entity instanceof LivingEntity)) return;

        // Ignore player deaths (handled elsewhere)
        if (entity instanceof Player) return;

        // Ignore lobby world kills
        if (plugin.getWorldManager().isLobbyWorld(entity.getWorld())) return;

        UUID playerUuid = killer.getUniqueId();
        String mobType = getMobType(entity);
        String weapon = getWeaponName(killer);
        boolean isBoss = isBossMob(entity);

        // Track total kills
        totalKillsThisRun.merge(playerUuid, 1, Integer::sum);

        // Boss kills are sent immediately (rare, important events)
        if (isBoss) {
            sendBossKillEvent(killer, entity, mobType, weapon);
            return;
        }

        // Regular kills are batched
        killBatches
            .computeIfAbsent(playerUuid, k -> new ConcurrentHashMap<>())
            .merge(mobType, 1, Integer::sum);
    }

    /**
     * Get a readable mob type name.
     */
    private String getMobType(Entity entity) {
        // Special handling for named entities
        if (entity.getCustomName() != null) {
            return entity.getType().name().toLowerCase() + " (named)";
        }

        // Specific mob variants
        if (entity instanceof Zombie zombie) {
            if (zombie instanceof Drowned) return "drowned";
            if (zombie instanceof Husk) return "husk";
            if (zombie instanceof ZombieVillager) return "zombie_villager";
            return "zombie";
        }

        if (entity instanceof Skeleton skeleton) {
            if (skeleton instanceof WitherSkeleton) return "wither_skeleton";
            if (skeleton instanceof Stray) return "stray";
            return "skeleton";
        }

        if (entity instanceof Spider spider) {
            if (spider instanceof CaveSpider) return "cave_spider";
            return "spider";
        }

        if (entity instanceof Creeper creeper) {
            return creeper.isPowered() ? "charged_creeper" : "creeper";
        }

        return entity.getType().name().toLowerCase();
    }

    /**
     * Get the weapon name used for the kill.
     */
    private String getWeaponName(Player killer) {
        ItemStack mainHand = killer.getInventory().getItemInMainHand();
        if (mainHand.getType().isAir()) {
            return "fists";
        }

        // Check for custom name
        if (mainHand.hasItemMeta() && mainHand.getItemMeta().hasDisplayName()) {
            return mainHand.getType().name().toLowerCase() + " (custom)";
        }

        return mainHand.getType().name().toLowerCase();
    }

    /**
     * Check if entity is a boss mob (warrants immediate notification).
     */
    private boolean isBossMob(Entity entity) {
        return entity instanceof Wither ||
               entity instanceof ElderGuardian ||
               entity instanceof Warden ||
               entity instanceof EnderDragon;  // Dragon is also handled elsewhere but include for completeness
    }

    /**
     * Send an immediate boss kill event.
     */
    private void sendBossKillEvent(Player killer, Entity boss, String mobType, String weapon) {
        if (plugin.getDirectorServer() == null) return;

        JsonObject data = new JsonObject();
        data.addProperty("player", killer.getName());
        data.addProperty("playerUuid", killer.getUniqueId().toString());
        data.addProperty("mobType", mobType);
        data.addProperty("weapon", weapon);
        data.addProperty("dimension", killer.getWorld().getEnvironment().name().toLowerCase());
        data.addProperty("isBoss", true);
        data.addProperty("totalKillsThisRun", totalKillsThisRun.getOrDefault(killer.getUniqueId(), 0));

        plugin.getDirectorServer().broadcastEvent("boss_killed", data);
    }

    /**
     * Flush all batched kills and send aggregated event to Eris.
     */
    private void flushBatches() {
        if (plugin.getDirectorServer() == null) return;
        if (killBatches.isEmpty()) return;

        // Take a snapshot and clear
        Map<UUID, Map<String, Integer>> snapshot = new ConcurrentHashMap<>(killBatches);
        killBatches.clear();

        // Build aggregated event
        JsonObject data = new JsonObject();
        JsonArray playerKills = new JsonArray();
        int totalKills = 0;

        for (Map.Entry<UUID, Map<String, Integer>> playerEntry : snapshot.entrySet()) {
            UUID playerUuid = playerEntry.getKey();
            Map<String, Integer> mobCounts = playerEntry.getValue();

            // Try to get player name
            Player player = plugin.getServer().getPlayer(playerUuid);
            String playerName = player != null ? player.getName() : playerUuid.toString();

            JsonObject playerData = new JsonObject();
            playerData.addProperty("player", playerName);
            playerData.addProperty("playerUuid", playerUuid.toString());

            // Build mob kill summary
            JsonObject kills = new JsonObject();
            int playerTotal = 0;
            for (Map.Entry<String, Integer> mobEntry : mobCounts.entrySet()) {
                kills.addProperty(mobEntry.getKey(), mobEntry.getValue());
                playerTotal += mobEntry.getValue();
            }
            playerData.add("kills", kills);
            playerData.addProperty("count", playerTotal);
            playerData.addProperty("totalThisRun", totalKillsThisRun.getOrDefault(playerUuid, 0));

            playerKills.add(playerData);
            totalKills += playerTotal;
        }

        if (totalKills == 0) return;

        data.add("playerKills", playerKills);
        data.addProperty("totalKills", totalKills);
        data.addProperty("batchPeriodSeconds", 30);

        plugin.getDirectorServer().broadcastEvent("mob_kills_batch", data);
    }

    /**
     * Get total kills for a player this run.
     */
    public int getTotalKills(UUID playerUuid) {
        return totalKillsThisRun.getOrDefault(playerUuid, 0);
    }

    /**
     * Reset tracking data for a new run.
     */
    public void resetRunData() {
        killBatches.clear();
        totalKillsThisRun.clear();
    }
}
