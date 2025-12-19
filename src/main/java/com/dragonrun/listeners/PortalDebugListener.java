package com.dragonrun.listeners;

import com.dragonrun.DragonRunPlugin;
import com.dragonrun.managers.PortalManager;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.entity.EntityPortalEnterEvent;
import org.bukkit.event.entity.EntityPortalEvent;
import org.bukkit.event.player.PlayerPortalEvent;
import org.bukkit.event.world.PortalCreateEvent;

/**
 * Debug listener to track portal events and help diagnose nether/end portal issues.
 */
public class PortalDebugListener implements Listener {

    private final DragonRunPlugin plugin;

    public PortalDebugListener(DragonRunPlugin plugin) {
        this.plugin = plugin;
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onPortalCreate(PortalCreateEvent event) {
        plugin.getLogger().info("[PORTAL DEBUG] Portal created: " +
                "Type=" + event.getReason() +
                ", World=" + event.getWorld().getName() +
                ", Cancelled=" + event.isCancelled());
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onPlayerPortal(PlayerPortalEvent event) {
        plugin.getLogger().info("[PORTAL DEBUG] Player portal event: " +
                "Player=" + event.getPlayer().getName() +
                ", From=" + event.getFrom().getWorld().getName() +
                ", To=" + (event.getTo() != null ? event.getTo().getWorld().getName() : "null") +
                ", Cause=" + event.getCause() +
                ", Cancelled=" + event.isCancelled());
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onEntityPortalEnter(EntityPortalEnterEvent event) {
        if (event.getEntity() instanceof org.bukkit.entity.Player) {
            org.bukkit.entity.Player player = (org.bukkit.entity.Player) event.getEntity();
            org.bukkit.Location loc = event.getLocation();
            org.bukkit.block.Block block = loc.getBlock();

            plugin.getLogger().info("[PORTAL DEBUG] Entity entered portal: " +
                    "Entity=" + event.getEntity().getType() +
                    ", Player=" + player.getName() +
                    ", GameMode=" + player.getGameMode() +
                    ", Location=" + event.getLocation() +
                    ", World=" + event.getLocation().getWorld().getName() +
                    ", BlockType=" + block.getType() +
                    ", PortalCooldown=" + player.getPortalCooldown());

            // WORKAROUND: Manually trigger portal travel if PlayerPortalEvent doesn't fire
            if (player.getPortalCooldown() == 0) {
                org.bukkit.Material blockType = block.getType();

                // Handle NETHER portals
                if (blockType == org.bukkit.Material.NETHER_PORTAL) {
                    org.bukkit.World currentWorld = player.getWorld();
                    String worldName = currentWorld.getName();
                    plugin.getLogger().warning("[PORTAL DEBUG] Nether portal - attempting teleport from " + worldName);

                    // Set cooldown IMMEDIATELY to prevent spam (300 ticks = 15 seconds)
                    player.setPortalCooldown(300);

                    org.bukkit.Server server = plugin.getServer();
                    org.bukkit.World targetWorld;
                    org.bukkit.Location targetLoc;

                    // Determine target world
                    if (worldName.endsWith("_nether")) {
                        // Going from nether to overworld
                        String overworldName = worldName.replace("_nether", "");
                        targetWorld = server.getWorld(overworldName);

                        if (targetWorld == null) {
                            plugin.getLogger().severe("[PORTAL DEBUG] Overworld not found: " + overworldName);
                            return;
                        }
                    } else {
                        // Going from overworld to nether
                        targetWorld = server.getWorld(worldName + "_nether");

                        if (targetWorld == null) {
                            plugin.getLogger().warning("[PORTAL DEBUG] Nether world doesn't exist, creating it...");
                            org.bukkit.WorldCreator creator = new org.bukkit.WorldCreator(worldName + "_nether")
                                    .environment(org.bukkit.World.Environment.NETHER)
                                    .seed(currentWorld.getSeed());
                            targetWorld = creator.createWorld();
                            if (targetWorld != null) {
                                plugin.getLogger().warning("[PORTAL DEBUG] Created nether world: " + targetWorld.getName());
                            } else {
                                plugin.getLogger().severe("[PORTAL DEBUG] Failed to create nether world!");
                                return;
                            }
                        }
                    }

                    // Use PortalManager to handle portal creation and linking
                    plugin.getLogger().warning("[PORTAL DEBUG] Using PortalManager to handle portal teleport");
                    targetLoc = PortalManager.handlePortalTeleport(player, targetWorld);
                    plugin.getLogger().warning("[PORTAL DEBUG] Teleporting to " + targetLoc);

                    player.teleport(targetLoc);
                }

                // Handle END portals
                else if (blockType == org.bukkit.Material.END_PORTAL) {
                    org.bukkit.World currentWorld = player.getWorld();
                    String worldName = currentWorld.getName();
                    plugin.getLogger().warning("[PORTAL DEBUG] End portal - attempting teleport from " + worldName);

                    // Set cooldown to prevent spam
                    player.setPortalCooldown(300);

                    org.bukkit.Server server = plugin.getServer();
                    org.bukkit.World targetWorld;
                    org.bukkit.Location targetLoc;

                    // Check if in the End (return to overworld)
                    if (worldName.endsWith("_the_end")) {
                        plugin.getLogger().warning("[PORTAL DEBUG] Returning from End to Overworld");
                        String overworldName = worldName.replace("_the_end", "");
                        targetWorld = server.getWorld(overworldName);

                        if (targetWorld == null) {
                            plugin.getLogger().severe("[PORTAL DEBUG] Overworld not found: " + overworldName);
                            return;
                        }

                        // Teleport to world spawn
                        targetLoc = targetWorld.getSpawnLocation();
                        plugin.getLogger().warning("[PORTAL DEBUG] Teleporting to overworld spawn at " + targetLoc);
                        player.teleport(targetLoc);
                        player.sendMessage("§a[Portal] Returning to the Overworld...");
                        return;
                    }

                    // Going to the End - Get or create the End world
                    targetWorld = server.getWorld(worldName + "_the_end");
                    if (targetWorld == null) {
                        plugin.getLogger().warning("[PORTAL DEBUG] End world doesn't exist, creating it...");
                        org.bukkit.WorldCreator creator = new org.bukkit.WorldCreator(worldName + "_the_end")
                                .environment(org.bukkit.World.Environment.THE_END)
                                .seed(currentWorld.getSeed());
                        targetWorld = creator.createWorld();
                        if (targetWorld != null) {
                            plugin.getLogger().warning("[PORTAL DEBUG] Created End world: " + targetWorld.getName());
                        } else {
                            plugin.getLogger().severe("[PORTAL DEBUG] Failed to create End world!");
                            return;
                        }
                    }

                    // Create obsidian platform at a safe distance from center (like vanilla)
                    // Vanilla uses 100, 48, 0 for the platform
                    int platformX = 100;
                    int platformY = 48;
                    int platformZ = 0;

                    plugin.getLogger().warning("[PORTAL DEBUG] Creating End platform at " + platformX + ", " + platformY + ", " + platformZ);

                    // Create 5x5 obsidian platform
                    for (int x = platformX - 2; x <= platformX + 2; x++) {
                        for (int z = platformZ - 2; z <= platformZ + 2; z++) {
                            targetWorld.getBlockAt(x, platformY - 1, z).setType(org.bukkit.Material.OBSIDIAN);
                            // Clear blocks above platform
                            targetWorld.getBlockAt(x, platformY, z).setType(org.bukkit.Material.AIR);
                            targetWorld.getBlockAt(x, platformY + 1, z).setType(org.bukkit.Material.AIR);
                            targetWorld.getBlockAt(x, platformY + 2, z).setType(org.bukkit.Material.AIR);
                        }
                    }

                    // Teleport to center of platform
                    targetLoc = new org.bukkit.Location(targetWorld, platformX + 0.5, platformY, platformZ + 0.5);
                    plugin.getLogger().warning("[PORTAL DEBUG] Teleporting to End platform at " + targetLoc);
                    player.teleport(targetLoc);
                    player.sendMessage("§d[Portal] Entering the End...");
                }
            }
        }
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onEntityPortal(EntityPortalEvent event) {
        plugin.getLogger().info("[PORTAL DEBUG] Entity portal teleport: " +
                "Entity=" + event.getEntity().getType() +
                ", From=" + event.getFrom().getWorld().getName() +
                ", To=" + (event.getTo() != null ? event.getTo().getWorld().getName() : "null") +
                ", Cancelled=" + event.isCancelled());
    }

    @EventHandler(priority = EventPriority.HIGHEST)
    public void onPlayerPortalEarly(PlayerPortalEvent event) {
        plugin.getLogger().warning("[PORTAL DEBUG EARLY] PlayerPortalEvent triggered!" +
                " Player=" + event.getPlayer().getName() +
                ", GameMode=" + event.getPlayer().getGameMode() +
                ", From=" + event.getFrom().getWorld().getName() +
                ", Cause=" + event.getCause() +
                ", SearchRadius=" + event.getSearchRadius() +
                ", CreationRadius=" + event.getCreationRadius());
    }
}
