package com.dragonrun.listeners;

import com.dragonrun.DragonRunPlugin;
import com.dragonrun.managers.GameState;
import com.dragonrun.util.MessageUtil;
import org.bukkit.GameMode;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.player.PlayerChangedWorldEvent;
import org.bukkit.event.player.PlayerJoinEvent;
import org.bukkit.event.player.PlayerQuitEvent;

public class JoinListener implements Listener {

    private final DragonRunPlugin plugin;

    public JoinListener(DragonRunPlugin plugin) {
        this.plugin = plugin;
    }

    @EventHandler
    public void onPlayerJoin(PlayerJoinEvent event) {
        Player player = event.getPlayer();

        // Load player data (creates record if new player)
        plugin.getAuraManager().loadPlayer(player);

        // Load achievements
        plugin.getAchievementManager().loadPlayer(player.getUniqueId());

        // Set up scoreboard and tab list
        plugin.getScoreboardManager().setScoreboard(player);
        plugin.getScoreboardManager().updateTabList();

        // Custom join message with aura
        int aura = plugin.getAuraManager().getAura(player.getUniqueId());
        event.joinMessage(MessageUtil.joinMessage(player.getName(), aura));

        // Handle world placement based on game state
        GameState state = plugin.getRunManager().getGameState();

        switch (state) {
            case IDLE, GENERATING, RESETTING -> {
                // Teleport to lobby, set creative mode
                plugin.getWorldManager().teleportToLobby(player);
                player.setGameMode(GameMode.CREATIVE);
            }
            case ACTIVE -> {
                // Mid-run joiner: spectator mode if spectators enabled, otherwise lobby
                if (plugin.getConfig().getBoolean("spectator.enabled", true)) {
                    // Teleport to hardcore world as spectator
                    plugin.getWorldManager().teleportToHardcoreSpectator(player);
                    player.setGameMode(GameMode.SPECTATOR);
                    player.sendMessage(MessageUtil.info("Run in progress. You are spectating."));
                } else {
                    // Spectators disabled - send to lobby
                    plugin.getWorldManager().teleportToLobby(player);
                    player.setGameMode(GameMode.CREATIVE);
                    player.sendMessage(MessageUtil.info("Run in progress. Wait in lobby for next run."));
                }
            }
        }

        // Only increment run count if joining an active run as participant
        // (spectators don't count as participants)
        if (state == GameState.ACTIVE && player.getGameMode() == GameMode.SURVIVAL) {
            plugin.getAuraManager().incrementRunCount(player.getUniqueId());
            plugin.getRunManager().updatePeakPlayers();
        }
    }

    @EventHandler
    public void onPlayerQuit(PlayerQuitEvent event) {
        Player player = event.getPlayer();

        // Remove any pending vote
        plugin.getVoteManager().removeVote(player.getUniqueId());

        // Unload player from cache
        plugin.getAuraManager().unloadPlayer(player.getUniqueId());
        plugin.getAchievementManager().unloadPlayer(player.getUniqueId());

        // Update tab list for remaining players
        plugin.getScoreboardManager().updateTabList();

        // Custom quit message
        event.quitMessage(MessageUtil.quitMessage(player.getName()));
    }

    /**
     * Enforce game modes when players change worlds.
     */
    @EventHandler
    public void onWorldChange(PlayerChangedWorldEvent event) {
        Player player = event.getPlayer();

        if (plugin.getWorldManager().isLobbyWorld(player.getWorld())) {
            // Entering lobby - creative mode
            player.setGameMode(GameMode.CREATIVE);
        } else if (plugin.getWorldManager().isHardcoreWorld(player.getWorld())) {
            // Entering hardcore world
            GameState state = plugin.getRunManager().getGameState();

            if (state == GameState.ACTIVE) {
                // If run is active, survival mode (unless already spectator)
                if (player.getGameMode() != GameMode.SPECTATOR) {
                    player.setGameMode(GameMode.SURVIVAL);
                }
            } else {
                // Run not active (resetting) - spectator mode
                player.setGameMode(GameMode.SPECTATOR);
            }
        }
    }
}
