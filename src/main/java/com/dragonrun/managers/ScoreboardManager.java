package com.dragonrun.managers;

import com.dragonrun.DragonRunPlugin;
import com.dragonrun.util.TimeUtil;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import net.kyori.adventure.text.format.TextDecoration;
import org.bukkit.Bukkit;
import org.bukkit.entity.Player;
import org.bukkit.scoreboard.*;

import java.util.UUID;

public class ScoreboardManager {

    private final DragonRunPlugin plugin;

    public ScoreboardManager(DragonRunPlugin plugin) {
        this.plugin = plugin;
    }

    /**
     * Create and set a player's scoreboard
     */
    public void setScoreboard(Player player) {
        Scoreboard scoreboard = Bukkit.getScoreboardManager().getNewScoreboard();
        Objective objective = scoreboard.registerNewObjective(
                "dragonrun",
                Criteria.DUMMY,
                Component.text("DRAGON RUN", NamedTextColor.GOLD, TextDecoration.BOLD)
        );
        objective.setDisplaySlot(DisplaySlot.SIDEBAR);

        player.setScoreboard(scoreboard);
        updateScoreboard(player);
    }

    /**
     * Update a player's scoreboard with current info
     */
    public void updateScoreboard(Player player) {
        Scoreboard scoreboard = player.getScoreboard();
        if (scoreboard == null) return;

        Objective objective = scoreboard.getObjective("dragonrun");
        if (objective == null) return;

        // Clear old scores
        for (String entry : scoreboard.getEntries()) {
            scoreboard.resetScores(entry);
        }

        UUID uuid = player.getUniqueId();
        int aura = plugin.getAuraManager().getAura(uuid);
        GameState state = plugin.getRunManager().getGameState();
        int achievements = plugin.getAchievementManager().getPlayerAchievements(uuid).size();
        int totalAchievements = plugin.getAchievementManager().getAllAchievements().size();

        int line = 15;

        // Blank line
        setScore(objective, " ", line--);

        // Show different info based on game state
        if (state == GameState.IDLE) {
            // Lobby - show vote info
            int votes = plugin.getVoteManager().getVoteCount();
            int required = plugin.getVoteManager().getRequiredVotes();
            int lobbyPlayers = plugin.getWorldManager().getLobbyPlayerCount();

            setScore(objective, "§e§lLOBBY", line--);
            setScore(objective, "§7Players: §a" + lobbyPlayers, line--);
            setScore(objective, "§7Votes: §b" + votes + "§7/§b" + required, line--);
            setScore(objective, "§7Use §a/vote §7to start!", line--);
        } else if (state == GameState.GENERATING) {
            setScore(objective, "§6§lGENERATING...", line--);
            setScore(objective, "§7Creating world...", line--);
            setScore(objective, "  ", line--);
            setScore(objective, "   ", line--);
        } else if (state == GameState.ACTIVE) {
            // Active run
            int runId = plugin.getRunManager().getCurrentRunId();
            long runDuration = plugin.getRunManager().getRunDurationSeconds();

            setScore(objective, "§b§lRun #" + runId, line--);
            setScore(objective, "§7Duration: §f" + TimeUtil.formatDuration(runDuration), line--);
            setScore(objective, "§7Players: §a" + plugin.getWorldManager().getHardcorePlayerCount(), line--);
            setScore(objective, "  ", line--);
        } else if (state == GameState.RESETTING) {
            setScore(objective, "§c§lRESETTING...", line--);
            setScore(objective, "§7Returning to lobby...", line--);
            setScore(objective, "  ", line--);
            setScore(objective, "   ", line--);
        }

        // Blank line
        setScore(objective, "    ", line--);

        // Your stats
        setScore(objective, "§d§lYour Stats", line--);
        String auraColor = aura >= 0 ? "§d" : "§c";
        setScore(objective, "§7Aura: " + auraColor + aura, line--);
        setScore(objective, "§7Achievements: §e" + achievements + "§8/§7" + totalAchievements, line--);

        // Blank line
        setScore(objective, "     ", line--);

        // Server
        setScore(objective, "§8dragonrun.server", line--);
    }

    /**
     * Update all online players' scoreboards
     */
    public void updateAllScoreboards() {
        for (Player player : Bukkit.getOnlinePlayers()) {
            updateScoreboard(player);
        }
    }

    /**
     * Update tab list for all players
     */
    public void updateTabList() {
        for (Player player : Bukkit.getOnlinePlayers()) {
            updatePlayerTabList(player);
        }
    }

    /**
     * Update a single player's tab list name
     */
    public void updatePlayerTabList(Player player) {
        int aura = plugin.getAuraManager().getAura(player.getUniqueId());
        String auraStr = String.valueOf(aura);
        NamedTextColor auraColor = aura >= 0 ? NamedTextColor.LIGHT_PURPLE : NamedTextColor.RED;

        Component tabName = Component.text()
                .append(Component.text(player.getName(), NamedTextColor.WHITE))
                .append(Component.text(" [", NamedTextColor.DARK_GRAY))
                .append(Component.text(auraStr, auraColor))
                .append(Component.text("]", NamedTextColor.DARK_GRAY))
                .build();

        player.playerListName(tabName);
    }

    private void setScore(Objective objective, String text, int score) {
        Score s = objective.getScore(text);
        s.setScore(score);
    }
}