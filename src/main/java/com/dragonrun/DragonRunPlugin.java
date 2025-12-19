package com.dragonrun;

import com.dragonrun.commands.AuraCommand;
import com.dragonrun.commands.AchievementsCommand;
import com.dragonrun.commands.StatsCommand;
import com.dragonrun.commands.BetCommand;
import com.dragonrun.commands.LiveCommand;
import com.dragonrun.commands.VoteCommand;
import com.dragonrun.database.Database;
import com.dragonrun.listeners.AchievementListener;
import com.dragonrun.listeners.DeathListener;
import com.dragonrun.listeners.JoinListener;
import com.dragonrun.listeners.LobbyProtectionListener;
import com.dragonrun.managers.AchievementManager;
import com.dragonrun.managers.AuraManager;
import com.dragonrun.managers.BettingManager;
import com.dragonrun.managers.RunManager;
import com.dragonrun.managers.ScoreboardManager;
import com.dragonrun.managers.VoteManager;
import com.dragonrun.managers.WorldManager;
import com.dragonrun.websocket.DirectorWebSocketServer;
import io.papermc.paper.command.brigadier.Commands;
import io.papermc.paper.plugin.lifecycle.event.types.LifecycleEvents;
import org.bukkit.plugin.java.JavaPlugin;

public class DragonRunPlugin extends JavaPlugin {

    private static DragonRunPlugin instance;

    private Database database;
    private WorldManager worldManager;
    private AuraManager auraManager;
    private RunManager runManager;
    private AchievementManager achievementManager;
    private BettingManager bettingManager;
    private VoteManager voteManager;
    private ScoreboardManager scoreboardManager;
    private AchievementListener achievementListener;
    private com.dragonrun.listeners.ResourceMilestoneListener resourceMilestoneListener;
    private DirectorWebSocketServer directorServer;

    @Override
    public void onEnable() {
        instance = this;

        // 1. Load configuration
        saveDefaultConfig();

        // 2. Initialize database
        database = new Database(this);
        if (!database.connect()) {
            getLogger().severe("Failed to connect to database! Disabling plugin.");
            getServer().getPluginManager().disablePlugin(this);
            return;
        }
        database.initializeSchema();

        // 3. Initialize WorldManager FIRST (other managers may depend on it)
        worldManager = new WorldManager(this);
        worldManager.initialize();

        // 4. Initialize managers (order matters - dependencies first)
        auraManager = new AuraManager(this, database);
        runManager = new RunManager(this, database, worldManager);
        achievementManager = new AchievementManager(this, database);
        bettingManager = new BettingManager(this, database);
        voteManager = new VoteManager(this);
        scoreboardManager = new ScoreboardManager(this);

        // 5. Register listeners
        getServer().getPluginManager().registerEvents(new DeathListener(this), this);
        getServer().getPluginManager().registerEvents(new JoinListener(this), this);
        achievementListener = new AchievementListener(this);
        getServer().getPluginManager().registerEvents(achievementListener, this);
        getServer().getPluginManager().registerEvents(new LobbyProtectionListener(worldManager), this);
        getServer().getPluginManager().registerEvents(new com.dragonrun.listeners.PortalDebugListener(this), this);
        getServer().getPluginManager().registerEvents(new com.dragonrun.listeners.DirectorChatListener(this), this);
        getServer().getPluginManager().registerEvents(new com.dragonrun.listeners.DamageListener(this), this);
        resourceMilestoneListener = new com.dragonrun.listeners.ResourceMilestoneListener(this);
        getServer().getPluginManager().registerEvents(resourceMilestoneListener, this);

        // 6. Register commands using Paper's lifecycle events
        registerCommands();

        // 7. Game starts in IDLE state - players wait in lobby until vote passes
        // DO NOT auto-start run anymore
        getLogger().info("Game state: " + runManager.getGameState());

        // 8. Start periodic scoreboard updates (every second)
        getServer().getScheduler().runTaskTimer(this, () -> {
            scoreboardManager.updateAllScoreboards();
        }, 20L, 20L);

        // 9. Initialize Director AI WebSocket server (if enabled)
        if (getConfig().getBoolean("director.enabled", false)) {
            int port = getConfig().getInt("director.port", 8765);
            int broadcastInterval = getConfig().getInt("director.broadcast-interval", 100);

            directorServer = new DirectorWebSocketServer(this, port);
            directorServer.start();

            // Start periodic state broadcasts
            getServer().getScheduler().runTaskTimer(this, () -> {
                if (directorServer != null) {
                    directorServer.broadcastGameState();
                }
            }, broadcastInterval, broadcastInterval);

            getLogger().info("Director AI WebSocket enabled on port " + port);
        }

        getLogger().info("DragonRun enabled! Game starting in IDLE state. Use /vote to start a run.");
    }

    @Override
    public void onDisable() {
        // Shutdown Director WebSocket server
        if (directorServer != null) {
            directorServer.shutdown();
        }

        // Shutdown world manager (unload worlds cleanly)
        if (worldManager != null) {
            worldManager.shutdown();
        }

        // Save any pending data
        if (runManager != null) {
            runManager.saveRunState();
        }

        // Close database connections
        if (database != null) {
            database.close();
        }

        getLogger().info("DragonRun disabled. GGs.");
    }

    // Getters for dependency injection
    public static DragonRunPlugin getInstance() {
        return instance;
    }

    public Database getDatabase() {
        return database;
    }

    public WorldManager getWorldManager() {
        return worldManager;
    }

    public AuraManager getAuraManager() {
        return auraManager;
    }

    public RunManager getRunManager() {
        return runManager;
    }

    public AchievementManager getAchievementManager() {
        return achievementManager;
    }

    public AchievementListener getAchievementListener() {
        return achievementListener;
    }

    public ScoreboardManager getScoreboardManager() {
        return scoreboardManager;
    }

    public BettingManager getBettingManager() {
        return bettingManager;
    }

    public VoteManager getVoteManager() {
        return voteManager;
    }

    public DirectorWebSocketServer getDirectorServer() {
        return directorServer;
    }

    public com.dragonrun.listeners.ResourceMilestoneListener getResourceMilestoneListener() {
        return resourceMilestoneListener;
    }

    @SuppressWarnings("UnstableApiUsage")
    private void registerCommands() {
        getLifecycleManager().registerEventHandler(LifecycleEvents.COMMANDS, event -> {
            Commands commands = event.registrar();
            new AuraCommand(this).register(commands);
            new AchievementsCommand(this).register(commands);
            new StatsCommand(this).register(commands);
            new BetCommand(this).register(commands);
            new LiveCommand(this).register(commands);
            new VoteCommand(this).register(commands);
            new com.dragonrun.director.DirectorCommands(this).register(commands);
        });
    }
}
