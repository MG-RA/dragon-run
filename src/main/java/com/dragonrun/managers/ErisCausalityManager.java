package com.dragonrun.managers;

import com.dragonrun.DragonRunPlugin;
import org.bukkit.Bukkit;
import org.bukkit.Location;
import org.bukkit.entity.Entity;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;

/**
 * Tracks entities, effects, and actions caused by Eris (the AI Director).
 * This allows the system to distinguish between player-caused deaths
 * and Eris-caused deaths for the divine protection and respawn override systems.
 */
public class ErisCausalityManager {

    private final DragonRunPlugin plugin;

    // Entity UUID -> CausalEntry (who Eris targeted when spawning this entity)
    private final Map<UUID, CausalEntry> erisEntities = new ConcurrentHashMap<>();

    // Player UUID -> Set of active effect types caused by Eris
    private final Map<UUID, Set<String>> erisEffects = new ConcurrentHashMap<>();

    // Recent lightning strike locations (Location hash -> timestamp + target player)
    private final Map<String, LightningEntry> recentLightning = new ConcurrentHashMap<>();

    // Recent TNT explosions (for attribution after the TNT entity is gone)
    private final Map<String, TntEntry> recentTntExplosions = new ConcurrentHashMap<>();

    // Pending Eris-caused deaths waiting for Python response
    private final Map<UUID, PendingDeathEntry> pendingDeaths = new ConcurrentHashMap<>();

    // Respawn overrides used this run
    private int respawnsUsedThisRun = 0;
    private static final int MAX_RESPAWNS_PER_RUN = 2;

    // Expiry time for tracked entries (5 minutes)
    private static final long EXPIRY_MS = 5 * 60 * 1000;

    // Lightning attribution radius (blocks)
    private static final double LIGHTNING_RADIUS = 10.0;

    // TNT attribution radius (blocks)
    private static final double TNT_RADIUS = 15.0;

    public ErisCausalityManager(DragonRunPlugin plugin) {
        this.plugin = plugin;
        startCleanupTask();
    }

    // ==================== ENTITY REGISTRATION ====================

    /**
     * Register an entity spawned by Eris targeting a specific player.
     */
    public void registerErisMob(Entity entity, UUID targetPlayer, String mobType) {
        erisEntities.put(entity.getUniqueId(), new CausalEntry(
                targetPlayer,
                "mob",
                mobType,
                System.currentTimeMillis()
        ));
        plugin.getLogger().info("Registered Eris mob: " + mobType + " -> " +
                Bukkit.getOfflinePlayer(targetPlayer).getName());
    }

    /**
     * Register TNT spawned by Eris.
     */
    public void registerErisTnt(Entity tnt, UUID targetPlayer) {
        erisEntities.put(tnt.getUniqueId(), new CausalEntry(
                targetPlayer,
                "tnt",
                "tnt",
                System.currentTimeMillis()
        ));
        // Also store by location for post-explosion attribution
        String locKey = locationKey(tnt.getLocation());
        recentTntExplosions.put(locKey, new TntEntry(targetPlayer, System.currentTimeMillis()));
        plugin.getLogger().info("Registered Eris TNT -> " +
                Bukkit.getOfflinePlayer(targetPlayer).getName());
    }

    /**
     * Register a falling block spawned by Eris.
     */
    public void registerErisFallingBlock(Entity block, UUID targetPlayer, String blockType) {
        erisEntities.put(block.getUniqueId(), new CausalEntry(
                targetPlayer,
                "falling_block",
                blockType,
                System.currentTimeMillis()
        ));
        plugin.getLogger().info("Registered Eris falling block: " + blockType + " -> " +
                Bukkit.getOfflinePlayer(targetPlayer).getName());
    }

    /**
     * Register a harmful effect applied by Eris.
     */
    public void registerErisEffect(UUID player, String effectType) {
        erisEffects.computeIfAbsent(player, k -> ConcurrentHashMap.newKeySet())
                .add(effectType.toLowerCase());
        plugin.getLogger().info("Registered Eris effect: " + effectType + " -> " +
                Bukkit.getOfflinePlayer(player).getName());
    }

    /**
     * Unregister an effect (when it expires or is removed).
     */
    public void unregisterErisEffect(UUID player, String effectType) {
        Set<String> effects = erisEffects.get(player);
        if (effects != null) {
            effects.remove(effectType.toLowerCase());
            if (effects.isEmpty()) {
                erisEffects.remove(player);
            }
        }
    }

    /**
     * Register a lightning strike caused by Eris.
     */
    public void registerErisLightning(Location location, UUID targetPlayer) {
        String locKey = locationKey(location);
        recentLightning.put(locKey, new LightningEntry(targetPlayer, System.currentTimeMillis()));
        plugin.getLogger().info("Registered Eris lightning near " +
                Bukkit.getOfflinePlayer(targetPlayer).getName());
    }

    // ==================== CAUSALITY CHECKS ====================

    /**
     * Check if an entity was spawned by Eris.
     */
    public boolean isErisCaused(Entity entity) {
        if (entity == null) return false;
        return erisEntities.containsKey(entity.getUniqueId());
    }

    /**
     * Get the target player for an Eris-spawned entity.
     */
    public Optional<UUID> getErisTarget(Entity entity) {
        if (entity == null) return Optional.empty();
        CausalEntry entry = erisEntities.get(entity.getUniqueId());
        return entry != null ? Optional.of(entry.targetPlayer) : Optional.empty();
    }

    /**
     * Check if a player has an Eris-caused effect active.
     */
    public boolean isErisEffect(UUID player, String effectType) {
        Set<String> effects = erisEffects.get(player);
        return effects != null && effects.contains(effectType.toLowerCase());
    }

    /**
     * Check if a player has any Eris-caused effects active.
     */
    public boolean hasAnyErisEffect(UUID player) {
        Set<String> effects = erisEffects.get(player);
        return effects != null && !effects.isEmpty();
    }

    /**
     * Check if there was a recent Eris lightning strike near a location.
     */
    public boolean wasRecentErisLightningNear(Location location) {
        long now = System.currentTimeMillis();
        for (Map.Entry<String, LightningEntry> entry : recentLightning.entrySet()) {
            if (now - entry.getValue().timestamp > 5000) continue; // Only check last 5 seconds

            Location lightningLoc = parseLocationKey(entry.getKey(), location.getWorld());
            if (lightningLoc != null && lightningLoc.distance(location) < LIGHTNING_RADIUS) {
                return true;
            }
        }
        return false;
    }

    /**
     * Check if there was a recent Eris TNT explosion near a location.
     */
    public boolean wasRecentErisTntNear(Location location) {
        long now = System.currentTimeMillis();
        for (Map.Entry<String, TntEntry> entry : recentTntExplosions.entrySet()) {
            if (now - entry.getValue().timestamp > 10000) continue; // Only check last 10 seconds

            Location tntLoc = parseLocationKey(entry.getKey(), location.getWorld());
            if (tntLoc != null && tntLoc.distance(location) < TNT_RADIUS) {
                return true;
            }
        }
        return false;
    }

    // ==================== PENDING DEATHS ====================

    /**
     * Register a pending Eris-caused death awaiting Python response.
     */
    public void setPendingErisDeath(UUID playerUuid, String deathCause, Location deathLocation) {
        pendingDeaths.put(playerUuid, new PendingDeathEntry(
                deathCause,
                deathLocation,
                System.currentTimeMillis()
        ));
        plugin.getLogger().info("Pending Eris death registered for " +
                Bukkit.getOfflinePlayer(playerUuid).getName());
    }

    /**
     * Check if there's a pending death for a player.
     */
    public boolean hasPendingDeath(UUID playerUuid) {
        return pendingDeaths.containsKey(playerUuid);
    }

    /**
     * Get and remove pending death entry.
     */
    public Optional<PendingDeathEntry> consumePendingDeath(UUID playerUuid) {
        return Optional.ofNullable(pendingDeaths.remove(playerUuid));
    }

    /**
     * Clear pending death (Python responded or timeout).
     */
    public void clearPendingDeath(UUID playerUuid) {
        pendingDeaths.remove(playerUuid);
    }

    // ==================== RESPAWN TRACKING ====================

    /**
     * Check if a respawn override can be used this run.
     */
    public boolean canUseRespawn() {
        return respawnsUsedThisRun < MAX_RESPAWNS_PER_RUN;
    }

    /**
     * Mark that a respawn was used.
     */
    public void useRespawn() {
        respawnsUsedThisRun++;
        plugin.getLogger().info("Respawn override used (" + respawnsUsedThisRun + "/" + MAX_RESPAWNS_PER_RUN + ")");
    }

    /**
     * Get remaining respawns this run.
     */
    public int getRemainingRespawns() {
        return MAX_RESPAWNS_PER_RUN - respawnsUsedThisRun;
    }

    // ==================== RUN LIFECYCLE ====================

    /**
     * Reset all tracking data for a new run.
     */
    public void resetForNewRun() {
        erisEntities.clear();
        erisEffects.clear();
        recentLightning.clear();
        recentTntExplosions.clear();
        pendingDeaths.clear();
        respawnsUsedThisRun = 0;
        plugin.getLogger().info("ErisCausalityManager reset for new run");
    }

    // ==================== CLEANUP ====================

    private void startCleanupTask() {
        Bukkit.getAsyncScheduler().runAtFixedRate(plugin, task -> cleanup(),
                60, 60, TimeUnit.SECONDS);
    }

    private void cleanup() {
        long now = System.currentTimeMillis();

        // Clean up expired entity entries
        erisEntities.entrySet().removeIf(entry ->
                now - entry.getValue().timestamp > EXPIRY_MS);

        // Clean up expired lightning entries
        recentLightning.entrySet().removeIf(entry ->
                now - entry.getValue().timestamp > EXPIRY_MS);

        // Clean up expired TNT entries
        recentTntExplosions.entrySet().removeIf(entry ->
                now - entry.getValue().timestamp > EXPIRY_MS);

        // Clean up expired pending deaths (should have been handled within 500ms)
        pendingDeaths.entrySet().removeIf(entry ->
                now - entry.getValue().timestamp > 10000);
    }

    // ==================== UTILITY ====================

    private String locationKey(Location loc) {
        return loc.getWorld().getName() + ":" +
                (int) loc.getX() + ":" +
                (int) loc.getY() + ":" +
                (int) loc.getZ();
    }

    private Location parseLocationKey(String key, org.bukkit.World fallbackWorld) {
        String[] parts = key.split(":");
        if (parts.length != 4) return null;

        org.bukkit.World world = Bukkit.getWorld(parts[0]);
        if (world == null) world = fallbackWorld;
        if (world == null) return null;

        try {
            return new Location(world,
                    Integer.parseInt(parts[1]),
                    Integer.parseInt(parts[2]),
                    Integer.parseInt(parts[3]));
        } catch (NumberFormatException e) {
            return null;
        }
    }

    // ==================== DATA CLASSES ====================

    public record CausalEntry(UUID targetPlayer, String sourceType, String sourceDetail, long timestamp) {}
    public record LightningEntry(UUID targetPlayer, long timestamp) {}
    public record TntEntry(UUID targetPlayer, long timestamp) {}
    public record PendingDeathEntry(String deathCause, Location deathLocation, long timestamp) {}
}
