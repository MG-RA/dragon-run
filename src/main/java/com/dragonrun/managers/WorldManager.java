package com.dragonrun.managers;

import com.dragonrun.DragonRunPlugin;
import org.bukkit.*;
import org.bukkit.entity.Player;

import java.io.File;
import java.util.Random;
import java.util.concurrent.CompletableFuture;

/**
 * Manages the multi-world system for Dragon Run.
 * Handles lobby world (persistent) and hardcore run worlds (created/deleted per run).
 */
public class WorldManager {

    private final DragonRunPlugin plugin;

    // World name constants
    public static final String LOBBY_WORLD_NAME = "world_lobby";
    public static final String HARDCORE_WORLD_NAME = "world"; // Use standard name for nether/end support

    // Lobby spawn location
    private Location lobbySpawn;

    // Current hardcore world (null if none active)
    private World hardcoreWorld;
    private String currentHardcoreWorldName;

    // Track world generation seed
    private long currentWorldSeed;

    public WorldManager(DragonRunPlugin plugin) {
        this.plugin = plugin;
    }

    // ==================== INITIALIZATION ====================

    /**
     * Initialize the world manager. Called on plugin enable.
     * Ensures lobby world exists and is configured properly.
     */
    public void initialize() {
        // Clean up lobby nether/end - lobby doesn't need them
        cleanupLobbyDimensions();

        if (!ensureLobbyWorld()) {
            plugin.getLogger().severe("Failed to create/load lobby world!");
            return;
        }

        // Clean up any leftover hardcore worlds from previous runs
        cleanupOldHardcoreWorlds();

        // Pre-create hardcore world so it's ready when vote passes
        preCreateHardcoreWorld();

        // Schedule a delayed cleanup of lobby dimensions (server may recreate them after plugin loads)
        Bukkit.getScheduler().runTaskLater(plugin, this::cleanupLobbyDimensions, 100L); // 5 seconds

        plugin.getLogger().info("WorldManager initialized. Lobby ready at " + LOBBY_WORLD_NAME);
    }

    /**
     * Pre-create the hardcore world so it's ready when players vote.
     * This saves time when the run actually starts.
     */
    private void preCreateHardcoreWorld() {
        plugin.getLogger().info("Pre-creating hardcore world...");
        createHardcoreWorld(null).thenAccept(world -> {
            if (world != null) {
                plugin.getLogger().info("Hardcore world pre-created: " + world.getName());
            } else {
                plugin.getLogger().warning("Failed to pre-create hardcore world");
            }
        });
    }

    /**
     * Remove lobby nether and end worlds - lobby doesn't need extra dimensions.
     */
    private void cleanupLobbyDimensions() {
        String[] lobbyDimensions = {
            LOBBY_WORLD_NAME + "_nether",
            LOBBY_WORLD_NAME + "_the_end"
        };

        for (String dimName : lobbyDimensions) {
            // Unload if loaded
            World world = Bukkit.getWorld(dimName);
            if (world != null) {
                plugin.getLogger().info("Unloading lobby dimension: " + dimName);
                Bukkit.unloadWorld(world, false);
            }

            // Delete folder if exists
            File folder = new File(Bukkit.getWorldContainer(), dimName);
            if (folder.exists()) {
                plugin.getLogger().info("Deleting lobby dimension folder: " + dimName);
                deleteDirectory(folder);
            }
        }
    }

    /**
     * Ensure the lobby world exists, creating it if necessary.
     * Uses FLAT generator for a simple lobby environment.
     */
    public boolean ensureLobbyWorld() {
        World lobby = Bukkit.getWorld(LOBBY_WORLD_NAME);

        if (lobby == null) {
            plugin.getLogger().info("Creating lobby world: " + LOBBY_WORLD_NAME);

            WorldCreator creator = new WorldCreator(LOBBY_WORLD_NAME)
                    .type(WorldType.FLAT)
                    .environment(World.Environment.NORMAL)
                    .generateStructures(false);

            lobby = creator.createWorld();

            if (lobby == null) {
                return false;
            }
        }

        // Always ensure spawn platform exists and is safe (may need rebuilding)
        //ensureSpawnPlatform(lobby);
        configureLobbyWorld(lobby);
        lobbySpawn = getLobbySpawnLocation(lobby);

        return true;
    }

    /**
     * Configure lobby world settings (no mobs, no weather, etc.)
     */
    private void configureLobbyWorld(World lobby) {
        plugin.getLogger().info("Configuring lobby world: " + lobby.getName());

        lobby.setDifficulty(Difficulty.HARD);
        lobby.setGameRule(GameRule.DO_DAYLIGHT_CYCLE, true);
        lobby.setGameRule(GameRule.DO_WEATHER_CYCLE, true);
        lobby.setGameRule(GameRule.DO_MOB_SPAWNING, true);
        lobby.setGameRule(GameRule.DO_FIRE_TICK, true);
        lobby.setGameRule(GameRule.MOB_GRIEFING, false);
        lobby.setGameRule(GameRule.FALL_DAMAGE, false);
        lobby.setGameRule(GameRule.DROWNING_DAMAGE, false);
        lobby.setGameRule(GameRule.FIRE_DAMAGE, false);
        lobby.setGameRule(GameRule.FREEZE_DAMAGE, false);
        lobby.setGameRule(GameRule.ANNOUNCE_ADVANCEMENTS, false);
        //lobby.setTime(6000); // Noon
        //lobby.setStorm(false);
        //lobby.setThundering(false);

        // Clear any existing mobs
        lobby.getEntities().stream()
                .filter(e -> !(e instanceof org.bukkit.entity.Player))
                .filter(e -> e instanceof org.bukkit.entity.LivingEntity)
                .filter(e -> !(e instanceof org.bukkit.entity.ArmorStand))
                .forEach(org.bukkit.entity.Entity::remove);

        plugin.getLogger().info("Lobby world configured: difficulty=" + lobby.getDifficulty() +
                ", doMobSpawning=" + lobby.getGameRuleValue(GameRule.DO_MOB_SPAWNING));
    }

    /**
     * Ensure spawn platform exists in lobby (builds if missing or damaged).
     */
    private void ensureSpawnPlatform(World lobby) {
        int y = 64;
        Material platformMaterial = Material.SMOOTH_QUARTZ;
        Material borderMaterial = Material.GOLD_BLOCK;

        plugin.getLogger().info("Building spawn platform at Y=" + y);

        // 11x11 platform
        for (int x = -5; x <= 5; x++) {
            for (int z = -5; z <= 5; z++) {
                boolean isBorder = Math.abs(x) == 5 || Math.abs(z) == 5;
                lobby.getBlockAt(x, y, z).setType(isBorder ? borderMaterial : platformMaterial);
            }
        }

        // Clear space above
        for (int x = -5; x <= 5; x++) {
            for (int z = -5; z <= 5; z++) {
                for (int clearY = y + 1; clearY <= y + 4; clearY++) {
                    lobby.getBlockAt(x, clearY, z).setType(Material.AIR);
                }
            }
        }

        // Set spawn point - MUST be done after platform is built
        lobby.setSpawnLocation(0, y + 1, 0);
        plugin.getLogger().info("Lobby spawn set to: 0, " + (y + 1) + ", 0");
    }

    /**
     * Get the lobby spawn location.
     */
    private Location getLobbySpawnLocation(World lobby) {
        Location spawn = lobby.getSpawnLocation();
        spawn.setY(spawn.getY() + 0.5);
        spawn.setYaw(0);
        spawn.setPitch(0);
        return spawn;
    }

    /**
     * Get the cached lobby spawn location.
     */
    public Location getLobbySpawn() {
        if (lobbySpawn == null) {
            World lobby = getLobbyWorld();
            if (lobby != null) {
                lobbySpawn = getLobbySpawnLocation(lobby);
            }
        }
        return lobbySpawn;
    }

    /**
     * Clean up any leftover hardcore worlds from crashed runs.
     */
    private void cleanupOldHardcoreWorlds() {
        // Clean up the main hardcore world and its dimensions
        String[] worldsToClean = {
            HARDCORE_WORLD_NAME,
            HARDCORE_WORLD_NAME + "_nether",
            HARDCORE_WORLD_NAME + "_the_end"
        };

        for (String worldName : worldsToClean) {
            // Try to unload if loaded
            World world = Bukkit.getWorld(worldName);
            if (world != null) {
                plugin.getLogger().info("Unloading old hardcore world: " + worldName);
                Bukkit.unloadWorld(world, false);
            }

            // Delete folder if exists
            File folder = new File(Bukkit.getWorldContainer(), worldName);
            if (folder.exists()) {
                plugin.getLogger().info("Deleting old hardcore world: " + worldName);
                deleteDirectory(folder);
            }
        }
    }

    // ==================== HARDCORE WORLD LIFECYCLE ====================

    /**
     * Create a new hardcore world for a run.
     * @param seed Optional seed (null for random)
     * @return CompletableFuture that completes when world is ready
     */
    public CompletableFuture<World> createHardcoreWorld(Long seed) {
        CompletableFuture<World> future = new CompletableFuture<>();

        currentWorldSeed = seed != null ? seed : new Random().nextLong();
        currentHardcoreWorldName = HARDCORE_WORLD_NAME;

        plugin.getLogger().info("Creating hardcore world: " + currentHardcoreWorldName + " (seed: " + currentWorldSeed + ")");

        // World creation must happen on main thread
        Bukkit.getScheduler().runTask(plugin, () -> {
            try {
                WorldCreator creator = new WorldCreator(currentHardcoreWorldName)
                        .environment(World.Environment.NORMAL)
                        .type(WorldType.NORMAL)
                        .seed(currentWorldSeed);

                World world = creator.createWorld();

                if (world != null) {
                    configureHardcoreWorld(world);
                    hardcoreWorld = world;

                    plugin.getLogger().info("Hardcore world created. Dimensions will be created automatically on portal use.");
                    future.complete(world);
                } else {
                    future.completeExceptionally(new RuntimeException("Failed to create world"));
                }
            } catch (Exception e) {
                plugin.getLogger().severe("Error creating hardcore world: " + e.getMessage());
                future.completeExceptionally(e);
            }
        });

        return future;
    }

    /**
     * Configure hardcore world settings.
     */
    private void configureHardcoreWorld(World world) {
        world.setDifficulty(Difficulty.HARD);
        world.setGameRule(GameRule.DO_IMMEDIATE_RESPAWN, true);
        world.setGameRule(GameRule.KEEP_INVENTORY, false);
        world.setGameRule(GameRule.SPAWN_RADIUS, 0);
        world.setGameRule(GameRule.ANNOUNCE_ADVANCEMENTS, false);
        world.setGameRule(GameRule.SPECTATORS_GENERATE_CHUNKS, false);

        // Set world border
        WorldBorder border = world.getWorldBorder();
        border.setCenter(world.getSpawnLocation());
        border.setSize(30000); // Configurable
    }


    /**
     * Unload and delete the current hardcore world (including nether and end dimensions).
     * Must teleport all players to lobby FIRST.
     * @return CompletableFuture that completes when world is deleted
     */
    public CompletableFuture<Void> deleteHardcoreWorld() {
        if (hardcoreWorld == null) {
            return CompletableFuture.completedFuture(null);
        }

        String worldName = currentHardcoreWorldName;
        World world = hardcoreWorld;
        File worldFolder = world.getWorldFolder();

        // Get dimension worlds
        World netherWorld = Bukkit.getWorld(worldName + "_nether");
        World endWorld = Bukkit.getWorld(worldName + "_the_end");
        File netherFolder = new File(Bukkit.getWorldContainer(), worldName + "_nether");
        File endFolder = new File(Bukkit.getWorldContainer(), worldName + "_the_end");

        // Clear references
        hardcoreWorld = null;
        currentHardcoreWorldName = null;

        return teleportAllToLobby()
                .thenRunAsync(() -> {
                    // Small delay to ensure teleports complete
                    try {
                        Thread.sleep(500);
                    } catch (InterruptedException ignored) {}
                })
                .thenRunAsync(() -> {
                    // Unload all dimensions on main thread
                    Bukkit.getScheduler().runTask(plugin, () -> {
                        plugin.getLogger().info("Unloading world: " + worldName);
                        Bukkit.unloadWorld(world, false);

                        if (netherWorld != null) {
                            plugin.getLogger().info("Unloading nether: " + worldName + "_nether");
                            Bukkit.unloadWorld(netherWorld, false);
                        }

                        if (endWorld != null) {
                            plugin.getLogger().info("Unloading end: " + worldName + "_the_end");
                            Bukkit.unloadWorld(endWorld, false);
                        }
                    });
                })
                .thenRunAsync(() -> {
                    // Wait for unload
                    try {
                        Thread.sleep(1000);
                    } catch (InterruptedException ignored) {}
                })
                .thenRunAsync(() -> {
                    // Delete all world folders
                    plugin.getLogger().info("Deleting world folder: " + worldFolder.getPath());
                    deleteDirectoryAsync(worldFolder);

                    if (netherFolder.exists()) {
                        plugin.getLogger().info("Deleting nether folder: " + netherFolder.getPath());
                        deleteDirectoryAsync(netherFolder);
                    }

                    if (endFolder.exists()) {
                        plugin.getLogger().info("Deleting end folder: " + endFolder.getPath());
                        deleteDirectoryAsync(endFolder);
                    }
                });
    }

    /**
     * Async delete a directory.
     */
    private void deleteDirectoryAsync(File directory) {
        Bukkit.getAsyncScheduler().runNow(plugin, task -> {
            deleteDirectory(directory);
        });
    }

    /**
     * Recursively delete a directory.
     */
    private boolean deleteDirectory(File directory) {
        if (!directory.exists()) return true;

        File[] files = directory.listFiles();
        if (files != null) {
            for (File file : files) {
                if (file.isDirectory()) {
                    deleteDirectory(file);
                } else {
                    file.delete();
                }
            }
        }
        return directory.delete();
    }

    // ==================== PLAYER MANAGEMENT ====================

    /**
     * Teleport a player to the lobby spawn.
     */
    public CompletableFuture<Boolean> teleportToLobby(Player player) {
        Location spawn = getLobbySpawn();
        if (spawn == null) {
            return CompletableFuture.completedFuture(false);
        }

        return player.teleportAsync(spawn).thenApply(success -> {
            if (success) {
                player.setGameMode(GameMode.CREATIVE);
                player.setHealth(20.0);
                player.setFoodLevel(20);
                player.setSaturation(20f);
                player.setFireTicks(0);
                player.setFallDistance(0);
            }
            return success;
        });
    }

    /**
     * Teleport all online players to the lobby.
     */
    public CompletableFuture<Void> teleportAllToLobby() {
        CompletableFuture<?>[] futures = Bukkit.getOnlinePlayers().stream()
                .map(this::teleportToLobby)
                .toArray(CompletableFuture[]::new);

        return CompletableFuture.allOf(futures);
    }

    /**
     * Teleport a player to the hardcore world spawn.
     */
    public CompletableFuture<Boolean> teleportToHardcore(Player player) {
        if (hardcoreWorld == null) {
            return CompletableFuture.completedFuture(false);
        }

        Location spawn = hardcoreWorld.getSpawnLocation();
        spawn.setY(spawn.getY() + 0.5);

        return player.teleportAsync(spawn).thenApply(success -> {
            if (success) {
                player.setGameMode(GameMode.SURVIVAL);
                // Clear inventory for fresh start
                player.getInventory().clear();
                // Reset health and food
                player.setHealth(20.0);
                player.setFoodLevel(20);
                player.setSaturation(5.0f);
                // Reset portal cooldown to allow immediate portal use
                player.setPortalCooldown(0);
            }
            return success;
        });
    }

    /**
     * Teleport all lobby players to the hardcore world.
     */
    public CompletableFuture<Void> teleportAllToHardcore() {
        CompletableFuture<?>[] futures = Bukkit.getOnlinePlayers().stream()
                .filter(this::isPlayerInLobby)
                .map(this::teleportToHardcore)
                .toArray(CompletableFuture[]::new);

        return CompletableFuture.allOf(futures);
    }

    /**
     * Teleport a player to the hardcore world as a spectator.
     * Used for mid-run joiners.
     */
    public CompletableFuture<Boolean> teleportToHardcoreSpectator(Player player) {
        if (hardcoreWorld == null) {
            return CompletableFuture.completedFuture(false);
        }

        Location spawn = hardcoreWorld.getSpawnLocation();
        spawn.setY(spawn.getY() + 10); // Spawn above ground for spectators

        return player.teleportAsync(spawn).thenApply(success -> {
            if (success) {
                player.setGameMode(GameMode.SPECTATOR);
            }
            return success;
        });
    }

    // ==================== QUERY METHODS ====================

    /**
     * Check if a world is the lobby world.
     */
    public boolean isLobbyWorld(World world) {
        return world != null && world.getName().equals(LOBBY_WORLD_NAME);
    }

    /**
     * Check if a world is the current hardcore world (includes nether and end dimensions).
     */
    public boolean isHardcoreWorld(World world) {
        if (world == null || hardcoreWorld == null) {
            return false;
        }
        String worldName = world.getName();
        String baseName = hardcoreWorld.getName();
        return worldName.equals(baseName) ||
               worldName.equals(baseName + "_nether") ||
               worldName.equals(baseName + "_the_end");
    }

    /**
     * Check if a player is in the lobby.
     */
    public boolean isPlayerInLobby(Player player) {
        return isLobbyWorld(player.getWorld());
    }

    /**
     * Check if a player is in the hardcore world.
     */
    public boolean isPlayerInHardcore(Player player) {
        return isHardcoreWorld(player.getWorld());
    }

    /**
     * Get the current hardcore world (may be null).
     */
    public World getHardcoreWorld() {
        return hardcoreWorld;
    }

    /**
     * Get the hardcore world name (may be null).
     */
    public String getHardcoreWorldName() {
        return currentHardcoreWorldName;
    }

    /**
     * Get the lobby world.
     */
    public World getLobbyWorld() {
        return Bukkit.getWorld(LOBBY_WORLD_NAME);
    }

    /**
     * Get the seed used for the current hardcore world.
     */
    public long getCurrentWorldSeed() {
        return currentWorldSeed;
    }

    /**
     * Get player count in lobby.
     */
    public int getLobbyPlayerCount() {
        World lobby = getLobbyWorld();
        return lobby != null ? lobby.getPlayers().size() : 0;
    }

    /**
     * Get player count in hardcore world.
     */
    public int getHardcorePlayerCount() {
        return hardcoreWorld != null ? hardcoreWorld.getPlayers().size() : 0;
    }

    // ==================== SHUTDOWN ====================

    /**
     * Clean up on plugin disable.
     */
    public void shutdown() {
        // Unload hardcore world if exists (don't delete on clean shutdown)
        if (hardcoreWorld != null) {
            plugin.getLogger().info("Unloading hardcore world on shutdown: " + currentHardcoreWorldName);
            Bukkit.unloadWorld(hardcoreWorld, true);
            hardcoreWorld = null;
        }
    }
}
