package com.dragonrun.managers;

import org.bukkit.*;
import org.bukkit.block.Block;
import org.bukkit.block.BlockFace;
import org.bukkit.entity.Player;

/**
 * Manages nether portal creation and linking between overworld and nether.
 * Implements vanilla Minecraft portal mechanics with proper coordinate scaling and portal creation.
 */
public class PortalManager {

    private static final int PORTAL_SEARCH_RADIUS = 128;
    private static final BlockFace[] PORTAL_DIRECTIONS = {BlockFace.NORTH, BlockFace.EAST};

    /**
     * Handle portal teleportation with proper portal creation/linking.
     */
    public static Location handlePortalTeleport(Player player, World targetWorld) {
        Location fromLoc = player.getLocation();
        World fromWorld = player.getWorld();

        // Calculate target coordinates based on dimension
        int targetX, targetZ;
        if (targetWorld.getEnvironment() == World.Environment.NETHER) {
            // Going to nether: divide by 8
            targetX = fromLoc.getBlockX() / 8;
            targetZ = fromLoc.getBlockZ() / 8;
        } else {
            // Going to overworld: multiply by 8
            targetX = fromLoc.getBlockX() * 8;
            targetZ = fromLoc.getBlockZ() * 8;
        }

        player.sendMessage("§7[Portal] From: " + fromLoc.getBlockX() + ", " + fromLoc.getBlockZ() +
                          " → Target: " + targetX + ", " + targetZ);

        // Try to find existing portal near target coordinates
        Location portalLoc = findNearbyPortal(targetWorld, targetX, targetZ);

        if (portalLoc != null) {
            // Found existing portal, teleport to it
            player.sendMessage("§a[Portal] Found existing portal at " + portalLoc.getBlockX() + ", " + portalLoc.getBlockZ());
            return portalLoc.add(0.5, 0, 0.5);
        }

        // No portal found, create one
        player.sendMessage("§e[Portal] Creating new portal at " + targetX + ", " + targetZ);
        return createPortalAt(targetWorld, targetX, targetZ);
    }

    /**
     * Find an existing portal within search radius.
     * Uses spiral search to find closest portal first.
     */
    private static Location findNearbyPortal(World world, int x, int z) {
        int searchRadius = PORTAL_SEARCH_RADIUS;

        // Spiral search from center outward for better performance and finding closest portal
        for (int radius = 0; radius <= searchRadius; radius++) {
            // Check points in a square at this radius
            for (int dx = -radius; dx <= radius; dx++) {
                for (int dz = -radius; dz <= radius; dz++) {
                    // Only check perimeter of square (not interior, already checked)
                    if (Math.abs(dx) != radius && Math.abs(dz) != radius) {
                        continue;
                    }

                    // Search all Y levels at this horizontal position
                    for (int y = world.getMaxHeight() - 1; y >= world.getMinHeight(); y--) {
                        Block block = world.getBlockAt(x + dx, y, z + dz);
                        if (block.getType() == Material.NETHER_PORTAL) {
                            // Find the bottom of the portal
                            while (y > world.getMinHeight() &&
                                   world.getBlockAt(x + dx, y - 1, z + dz).getType() == Material.NETHER_PORTAL) {
                                y--;
                            }
                            return new Location(world, x + dx + 0.5, y, z + dz + 0.5);
                        }
                    }
                }
            }
        }

        return null;
    }

    /**
     * Create a new nether portal at the specified coordinates.
     */
    private static Location createPortalAt(World world, int x, int z) {
        // Find safe Y coordinate
        int y = findSafePortalY(world, x, z);

        // Create portal platform
        createPlatform(world, x, y - 1, z);

        // Create portal frame (4x5, north-south orientation)
        createPortalFrame(world, x, y, z, BlockFace.NORTH);

        // Fill the portal frame with portal blocks (2 wide x 3 tall inner space)
        for (int dy = 1; dy <= 3; dy++) {
            for (int dx = 0; dx <= 1; dx++) {
                world.getBlockAt(x + dx, y + dy, z).setType(Material.NETHER_PORTAL);
            }
        }

        return new Location(world, x + 0.5, y, z + 0.5);
    }

    /**
     * Find safe Y coordinate for portal placement.
     */
    private static int findSafePortalY(World world, int x, int z) {
        if (world.getEnvironment() == World.Environment.NETHER) {
            // In nether, prefer Y=70-120 (natural cave height), then search lower
            // Search from top down to find caves/open spaces
            for (int y = 120; y >= 70; y--) {
                if (isSafeForPortal(world, x, y, z)) {
                    return y;
                }
            }

            // If no good spot found in preferred range, search lower (avoid lava ocean at Y=31)
            for (int y = 69; y >= 35; y--) {
                if (isSafeForPortal(world, x, y, z)) {
                    return y;
                }
            }

            // Last resort: create platform above lava ocean
            return 96; // Fallback to safe height
        } else {
            // In overworld, use surface or find cave
            int surfaceY = world.getHighestBlockYAt(x, z);
            if (surfaceY < 0) surfaceY = 64;

            // Check if surface is safe
            if (isSafeForPortal(world, x, surfaceY, z)) {
                return surfaceY;
            }

            // Search downward for cave
            for (int y = surfaceY - 1; y >= world.getMinHeight() + 10; y--) {
                if (isSafeForPortal(world, x, y, z)) {
                    return y;
                }
            }

            return surfaceY; // Fallback to surface
        }
    }

    /**
     * Check if location is safe for portal placement (has space for 4x5 portal).
     * Requires: solid floor below, air space for portal frame, no lava nearby.
     */
    private static boolean isSafeForPortal(World world, int x, int y, int z) {
        // Check floor is solid (Y-1 level)
        for (int dx = -1; dx <= 2; dx++) {
            for (int dz = -1; dz <= 1; dz++) {
                Block floor = world.getBlockAt(x + dx, y - 1, z + dz);
                if (!floor.getType().isSolid() || floor.getType() == Material.LAVA) {
                    return false; // Need solid floor
                }
            }
        }

        // Check portal space is clear (2 wide x 3 tall inner space + frame area)
        for (int dx = -1; dx <= 2; dx++) {
            for (int dz = -1; dz <= 1; dz++) {
                for (int dy = 0; dy <= 4; dy++) {
                    Block block = world.getBlockAt(x + dx, y + dy, z + dz);
                    Material type = block.getType();

                    // Reject lava or fire
                    if (type == Material.LAVA || type == Material.FIRE) {
                        return false;
                    }

                    // Inner portal space must be air or replaceable
                    if (dy >= 1 && dy <= 3 && dx >= 0 && dx <= 1 && dz == 0) {
                        if (type.isSolid() && type != Material.NETHERRACK && type != Material.STONE) {
                            return false; // Inner space must be clearable
                        }
                    }
                }
            }
        }

        // Check for lava in wider area (don't spawn near lava lakes)
        for (int dx = -3; dx <= 3; dx++) {
            for (int dz = -3; dz <= 3; dz++) {
                for (int dy = -2; dy <= 5; dy++) {
                    Block block = world.getBlockAt(x + dx, y + dy, z + dz);
                    if (block.getType() == Material.LAVA) {
                        return false; // Too close to lava
                    }
                }
            }
        }

        return true;
    }

    /**
     * Create a platform below the portal.
     */
    private static void createPlatform(World world, int x, int y, int z) {
        Material platformMaterial = world.getEnvironment() == World.Environment.NETHER ?
            Material.NETHERRACK : Material.STONE;

        // Create 5x5 platform
        for (int dx = -2; dx <= 2; dx++) {
            for (int dz = -2; dz <= 2; dz++) {
                world.getBlockAt(x + dx, y, z + dz).setType(platformMaterial);
            }
        }

        // Clear space above platform
        for (int dx = -2; dx <= 2; dx++) {
            for (int dz = -2; dz <= 2; dz++) {
                for (int dy = 1; dy <= 5; dy++) {
                    Block block = world.getBlockAt(x + dx, y + dy, z + dz);
                    if (!block.getType().isSolid() || block.getType() == Material.OBSIDIAN) {
                        continue; // Don't clear air or obsidian
                    }
                    block.setType(Material.AIR);
                }
            }
        }
    }

    /**
     * Create obsidian portal frame.
     * Creates a 4-wide x 5-tall obsidian frame with 2-wide x 3-tall inner space.
     */
    private static void createPortalFrame(World world, int x, int y, int z, BlockFace direction) {
        if (direction == BlockFace.NORTH || direction == BlockFace.SOUTH) {
            // North-South orientation (portal faces east-west)
            // Frame is at: x-1 (left), x and x+1 (middle air), x+2 (right)
            // Vertical sides (5 blocks tall)
            for (int dy = 0; dy <= 4; dy++) {
                world.getBlockAt(x - 1, y + dy, z).setType(Material.OBSIDIAN); // Left pillar
                world.getBlockAt(x + 2, y + dy, z).setType(Material.OBSIDIAN); // Right pillar
            }
            // Horizontal top and bottom (2 blocks wide between pillars)
            for (int dx = 0; dx <= 1; dx++) {
                world.getBlockAt(x + dx, y, z).setType(Material.OBSIDIAN); // Bottom
                world.getBlockAt(x + dx, y + 4, z).setType(Material.OBSIDIAN); // Top
            }
        } else {
            // East-West orientation (portal faces north-south)
            // Frame is at: z-1 (left), z and z+1 (middle air), z+2 (right)
            // Vertical sides (5 blocks tall)
            for (int dy = 0; dy <= 4; dy++) {
                world.getBlockAt(x, y + dy, z - 1).setType(Material.OBSIDIAN); // Left pillar
                world.getBlockAt(x, y + dy, z + 2).setType(Material.OBSIDIAN); // Right pillar
            }
            // Horizontal top and bottom (2 blocks wide between pillars)
            for (int dz = 0; dz <= 1; dz++) {
                world.getBlockAt(x, y, z + dz).setType(Material.OBSIDIAN); // Bottom
                world.getBlockAt(x, y + 4, z + dz).setType(Material.OBSIDIAN); // Top
            }
        }
    }
}
