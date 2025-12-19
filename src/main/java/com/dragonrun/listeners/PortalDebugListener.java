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
        // Debug logging disabled - uncomment if needed for troubleshooting
        // plugin.getLogger().info("[PORTAL] Portal created: Type=" + event.getReason() + ", World=" + event.getWorld().getName());
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onPlayerPortal(PlayerPortalEvent event) {
        // Debug logging disabled - uncomment if needed for troubleshooting
        // plugin.getLogger().info("[PORTAL] Player portal: " + event.getPlayer().getName() + " " + event.getCause());
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onEntityPortalEnter(EntityPortalEnterEvent event) {
        if (event.getEntity() instanceof org.bukkit.entity.Player) {
            org.bukkit.entity.Player player = (org.bukkit.entity.Player) event.getEntity();
            org.bukkit.Location loc = event.getLocation();
            org.bukkit.block.Block block = loc.getBlock();

            // Debug logging disabled - uncomment if needed for troubleshooting
            // plugin.getLogger().info("[PORTAL] " + player.getName() + " entered " + block.getType());

            // WORKAROUND: Manually trigger portal travel if PlayerPortalEvent doesn't fire
            if (player.getPortalCooldown() == 0) {
                org.bukkit.Material blockType = block.getType();

                // Handle NETHER portals
                if (blockType == org.bukkit.Material.NETHER_PORTAL) {
                    org.bukkit.World currentWorld = player.getWorld();
                    String worldName = currentWorld.getName();

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
                            plugin.getLogger().severe("[PORTAL] Overworld not found: " + overworldName);
                            return;
                        }
                    } else {
                        // Going from overworld to nether
                        targetWorld = server.getWorld(worldName + "_nether");

                        if (targetWorld == null) {
                            org.bukkit.WorldCreator creator = new org.bukkit.WorldCreator(worldName + "_nether")
                                    .environment(org.bukkit.World.Environment.NETHER)
                                    .seed(currentWorld.getSeed());
                            targetWorld = creator.createWorld();
                            if (targetWorld == null) {
                                plugin.getLogger().severe("[PORTAL] Failed to create nether world!");
                                return;
                            }
                        }
                    }

                    // Use PortalManager to handle portal creation and linking
                    targetLoc = PortalManager.handlePortalTeleport(player, targetWorld);
                    player.teleport(targetLoc);
                }

                // Handle END portals
                else if (blockType == org.bukkit.Material.END_PORTAL) {
                    org.bukkit.World currentWorld = player.getWorld();
                    String worldName = currentWorld.getName();

                    // Set cooldown to prevent spam
                    player.setPortalCooldown(300);

                    org.bukkit.Server server = plugin.getServer();
                    org.bukkit.World targetWorld;
                    org.bukkit.Location targetLoc;

                    // Check if in the End (return to overworld)
                    if (worldName.endsWith("_the_end")) {
                        String overworldName = worldName.replace("_the_end", "");
                        targetWorld = server.getWorld(overworldName);

                        if (targetWorld == null) {
                            plugin.getLogger().severe("[PORTAL] Overworld not found: " + overworldName);
                            return;
                        }

                        // Check if dragon is dead and run is still active - trigger victory!
                        // This handles the case where dragon death event didn't fire properly
                        if (!plugin.getRunManager().isDragonAlive() &&
                            plugin.getRunManager().getGameState() == com.dragonrun.managers.GameState.ACTIVE) {
                            plugin.getRunManager().endRunByDragonKill(player.getUniqueId());
                        }

                        // Teleport to world spawn
                        targetLoc = targetWorld.getSpawnLocation();
                        player.teleport(targetLoc);
                        player.sendMessage("§a[Portal] Returning to the Overworld...");
                        return;
                    }

                    // Going to the End - Get or create the End world
                    targetWorld = server.getWorld(worldName + "_the_end");
                    if (targetWorld == null) {
                        org.bukkit.WorldCreator creator = new org.bukkit.WorldCreator(worldName + "_the_end")
                                .environment(org.bukkit.World.Environment.THE_END)
                                .seed(currentWorld.getSeed());
                        targetWorld = creator.createWorld();
                        if (targetWorld == null) {
                            plugin.getLogger().severe("[PORTAL] Failed to create End world!");
                            return;
                        }
                    }

                    // Create obsidian platform at a safe distance from center (like vanilla)
                    // Vanilla uses 100, 48, 0 for the platform
                    int platformX = 100;
                    int platformY = 48;
                    int platformZ = 0;

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
                    player.teleport(targetLoc);
                    player.sendMessage("§d[Portal] Entering the End...");
                }
            }
        }
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onEntityPortal(EntityPortalEvent event) {
        // Debug logging disabled - uncomment if needed for troubleshooting
        // plugin.getLogger().info("[PORTAL] Entity teleport: " + event.getEntity().getType());
    }

    @EventHandler(priority = EventPriority.HIGHEST)
    public void onPlayerPortalEarly(PlayerPortalEvent event) {
        // Debug logging disabled - uncomment if needed for troubleshooting
        // plugin.getLogger().info("[PORTAL] PlayerPortalEvent: " + event.getPlayer().getName() + " " + event.getCause());
    }
}
