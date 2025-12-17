package com.dragonrun;

import com.dragonrun.commands.AuraCommand;
import com.dragonrun.commands.AchievementsCommand;
import com.dragonrun.commands.StatsCommand;
import com.dragonrun.commands.BetCommand;
import com.dragonrun.commands.LiveCommand;
import com.dragonrun.database.Database;
import com.dragonrun.listeners.AchievementListener;
import com.dragonrun.listeners.DeathListener;
import com.dragonrun.listeners.JoinListener;
import com.dragonrun.managers.AchievementManager;
import com.dragonrun.managers.AuraManager;
import com.dragonrun.managers.BettingManager;
import com.dragonrun.managers.RunManager;
import com.dragonrun.managers.ScoreboardManager;
import io.papermc.paper.command.brigadier.Commands;
import io.papermc.paper.plugin.lifecycle.event.types.LifecycleEvents;
import org.bukkit.plugin.java.JavaPlugin;

public class DragonRunPlugin extends JavaPlugin {

    private static DragonRunPlugin instance;

    private Database database;
    private AuraManager auraManager;
    private RunManager runManager;
    private AchievementManager achievementManager;
    private BettingManager bettingManager;
    private ScoreboardManager scoreboardManager;
    private AchievementListener achievementListener;

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

        // 3. Initialize managers (order matters - dependencies first)
        auraManager = new AuraManager(this, database);
        runManager = new RunManager(this, database);
        achievementManager = new AchievementManager(this, database);
        bettingManager = new BettingManager(this, database);
        scoreboardManager = new ScoreboardManager(this);

        // 4. Register listeners
        getServer().getPluginManager().registerEvents(new DeathListener(this), this);
        getServer().getPluginManager().registerEvents(new JoinListener(this), this);
        achievementListener = new AchievementListener(this);
        getServer().getPluginManager().registerEvents(achievementListener, this);

        // 5. Register commands using Paper's lifecycle events
        registerCommands();

        // 6. Start new run if none active
        runManager.ensureActiveRun();

        // 6b. Load active bets for current run
        bettingManager.loadActiveBets(runManager.getCurrentRunId());

        // 7. Start periodic scoreboard updates (every second)
        getServer().getScheduler().runTaskTimer(this, () -> {
            scoreboardManager.updateAllScoreboards();
        }, 20L, 20L);

        getLogger().info("DragonRun enabled! May the aura be with you.");
    }

    @Override
    public void onDisable() {
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

    @SuppressWarnings("UnstableApiUsage")
    private void registerCommands() {
        getLifecycleManager().registerEventHandler(LifecycleEvents.COMMANDS, event -> {
            Commands commands = event.registrar();
            new AuraCommand(this).register(commands);
            new AchievementsCommand(this).register(commands);
            new StatsCommand(this).register(commands);
            new BetCommand(this).register(commands);
            new LiveCommand(this).register(commands);
        });
    }
}
