package com.dragonrun.listeners;

import com.dragonrun.DragonRunPlugin;
import com.dragonrun.util.MessageUtil;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
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

        // Increment run participation
        plugin.getAuraManager().incrementRunCount(player.getUniqueId());

        // Update peak players for current run
        plugin.getRunManager().updatePeakPlayers();

        // Set up scoreboard and tab list
        plugin.getScoreboardManager().setScoreboard(player);
        plugin.getScoreboardManager().updateTabList();

        // Custom join message with aura
        int aura = plugin.getAuraManager().getAura(player.getUniqueId());
        event.joinMessage(MessageUtil.joinMessage(player.getName(), aura));
    }

    @EventHandler
    public void onPlayerQuit(PlayerQuitEvent event) {
        Player player = event.getPlayer();

        // Unload player from cache
        plugin.getAuraManager().unloadPlayer(player.getUniqueId());
        plugin.getAchievementManager().unloadPlayer(player.getUniqueId());

        // Update tab list for remaining players
        plugin.getScoreboardManager().updateTabList();

        // Custom quit message
        event.quitMessage(MessageUtil.quitMessage(player.getName()));
    }
}
