package com.dragonrun.listeners;

import com.dragonrun.DragonRunPlugin;
import com.google.gson.JsonObject;
import org.bukkit.Location;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.player.PlayerMoveEvent;
import org.bukkit.generator.structure.Structure;

import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Tracks when players discover notable structures.
 * Sends immediate events for structure discoveries (rare, important).
 * Uses chunk-based detection to avoid spamming on every move event.
 */
public class StructureDiscoveryListener implements Listener {

    private final DragonRunPlugin plugin;

    // Track which structures each player has discovered this run
    // Format: playerUUID -> Set of "structureType:chunkX:chunkZ"
    private final Map<UUID, Set<String>> discoveredStructures = new ConcurrentHashMap<>();

    // Structures we care about tracking
    private static final Set<String> NOTABLE_STRUCTURES = Set.of(
        "minecraft:stronghold",
        "minecraft:fortress",
        "minecraft:bastion_remnant",
        "minecraft:end_city",
        "minecraft:monument",
        "minecraft:mansion",
        "minecraft:ancient_city",
        "minecraft:trial_chambers",
        "minecraft:village_plains",
        "minecraft:village_desert",
        "minecraft:village_savanna",
        "minecraft:village_snowy",
        "minecraft:village_taiga",
        "minecraft:pillager_outpost",
        "minecraft:ruined_portal",
        "minecraft:ruined_portal_nether"
    );

    // Friendly names for structures
    private static final Map<String, String> STRUCTURE_NAMES = Map.ofEntries(
        Map.entry("minecraft:stronghold", "Stronghold"),
        Map.entry("minecraft:fortress", "Nether Fortress"),
        Map.entry("minecraft:bastion_remnant", "Bastion Remnant"),
        Map.entry("minecraft:end_city", "End City"),
        Map.entry("minecraft:monument", "Ocean Monument"),
        Map.entry("minecraft:mansion", "Woodland Mansion"),
        Map.entry("minecraft:ancient_city", "Ancient City"),
        Map.entry("minecraft:trial_chambers", "Trial Chambers"),
        Map.entry("minecraft:village_plains", "Village"),
        Map.entry("minecraft:village_desert", "Village"),
        Map.entry("minecraft:village_savanna", "Village"),
        Map.entry("minecraft:village_snowy", "Village"),
        Map.entry("minecraft:village_taiga", "Village"),
        Map.entry("minecraft:pillager_outpost", "Pillager Outpost"),
        Map.entry("minecraft:ruined_portal", "Ruined Portal"),
        Map.entry("minecraft:ruined_portal_nether", "Ruined Portal")
    );

    // Priority levels for structures (higher = more important)
    private static final Map<String, String> STRUCTURE_PRIORITY = Map.ofEntries(
        Map.entry("minecraft:stronghold", "critical"),      // Run objective
        Map.entry("minecraft:fortress", "high"),            // Blaze rods needed
        Map.entry("minecraft:bastion_remnant", "medium"),   // Good loot
        Map.entry("minecraft:end_city", "high"),            // End game
        Map.entry("minecraft:monument", "low"),             // Optional
        Map.entry("minecraft:mansion", "low"),              // Rare but optional
        Map.entry("minecraft:ancient_city", "medium"),      // Dangerous, good loot
        Map.entry("minecraft:trial_chambers", "medium"),    // New content
        Map.entry("minecraft:village_plains", "low"),
        Map.entry("minecraft:village_desert", "low"),
        Map.entry("minecraft:village_savanna", "low"),
        Map.entry("minecraft:village_snowy", "low"),
        Map.entry("minecraft:village_taiga", "low"),
        Map.entry("minecraft:pillager_outpost", "low"),
        Map.entry("minecraft:ruined_portal", "low"),
        Map.entry("minecraft:ruined_portal_nether", "low")
    );

    // Last checked chunk per player (to avoid checking every movement)
    private final Map<UUID, String> lastCheckedChunk = new ConcurrentHashMap<>();

    public StructureDiscoveryListener(DragonRunPlugin plugin) {
        this.plugin = plugin;
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onPlayerMove(PlayerMoveEvent event) {
        // Only check if player moved to a new chunk
        Location from = event.getFrom();
        Location to = event.getTo();

        if (from.getChunk().equals(to.getChunk())) return;

        Player player = event.getPlayer();

        // Ignore lobby world
        if (plugin.getWorldManager().isLobbyWorld(player.getWorld())) return;

        UUID playerUuid = player.getUniqueId();
        String currentChunk = to.getChunk().getX() + ":" + to.getChunk().getZ() + ":" + to.getWorld().getName();

        // Skip if we already checked this chunk for this player
        if (currentChunk.equals(lastCheckedChunk.get(playerUuid))) return;
        lastCheckedChunk.put(playerUuid, currentChunk);

        // Check for structures at player's location
        checkForStructures(player, to);
    }

    /**
     * Check if the player is near any notable structures.
     */
    private void checkForStructures(Player player, Location location) {
        if (plugin.getDirectorServer() == null) return;

        UUID playerUuid = player.getUniqueId();
        Set<String> playerDiscovered = discoveredStructures
            .computeIfAbsent(playerUuid, k -> ConcurrentHashMap.newKeySet());

        // Get structures at this location
        var world = location.getWorld();
        var chunk = location.getChunk();

        // Use Paper's structure location API
        for (String structureKey : NOTABLE_STRUCTURES) {
            try {
                // Get the structure registry
                var structureRegistry = org.bukkit.Registry.STRUCTURE;
                var structure = structureRegistry.get(org.bukkit.NamespacedKey.fromString(structureKey));

                if (structure == null) continue;

                // Check if structure is nearby (within 48 blocks ~3 chunks)
                var nearestStructure = world.locateNearestStructure(location, structure, 48, false);

                if (nearestStructure != null) {
                    // Calculate distance
                    double distance = location.distance(nearestStructure.getLocation());

                    // Only trigger if within 32 blocks (close enough to have "discovered" it)
                    if (distance <= 32) {
                        String discoveryKey = structureKey + ":" + nearestStructure.getLocation().getChunk().getX() +
                                             ":" + nearestStructure.getLocation().getChunk().getZ();

                        // Only broadcast if not already discovered
                        if (playerDiscovered.add(discoveryKey)) {
                            broadcastStructureDiscovery(player, structureKey, nearestStructure.getLocation(), distance);
                        }
                    }
                }
            } catch (Exception e) {
                // Structure lookup can fail for various reasons, ignore
            }
        }
    }

    /**
     * Broadcast a structure discovery event.
     */
    private void broadcastStructureDiscovery(Player player, String structureKey, Location structureLocation, double distance) {
        JsonObject data = new JsonObject();
        data.addProperty("player", player.getName());
        data.addProperty("playerUuid", player.getUniqueId().toString());
        data.addProperty("structureType", structureKey);
        data.addProperty("structureName", STRUCTURE_NAMES.getOrDefault(structureKey, structureKey));
        data.addProperty("priority", STRUCTURE_PRIORITY.getOrDefault(structureKey, "low"));
        data.addProperty("dimension", player.getWorld().getEnvironment().name().toLowerCase());
        data.addProperty("distance", Math.round(distance));

        // Add coordinates (approximate, for context)
        data.addProperty("x", structureLocation.getBlockX());
        data.addProperty("z", structureLocation.getBlockZ());

        plugin.getDirectorServer().broadcastEvent("structure_discovered", data);

        // Log locally too
        plugin.getLogger().info(player.getName() + " discovered " +
            STRUCTURE_NAMES.getOrDefault(structureKey, structureKey) +
            " at " + structureLocation.getBlockX() + ", " + structureLocation.getBlockZ());
    }

    /**
     * Reset tracking data for a new run.
     */
    public void resetRunData() {
        discoveredStructures.clear();
        lastCheckedChunk.clear();
    }

    /**
     * Get number of structures discovered by a player this run.
     */
    public int getDiscoveryCount(UUID playerUuid) {
        Set<String> discovered = discoveredStructures.get(playerUuid);
        return discovered != null ? discovered.size() : 0;
    }
}
