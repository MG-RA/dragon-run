package com.dragonrun.managers;

import com.dragonrun.DragonRunPlugin;
import com.dragonrun.util.TimeUtil;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import net.kyori.adventure.text.format.TextDecoration;
import net.kyori.adventure.text.minimessage.MiniMessage;
import org.bukkit.Bukkit;
import org.bukkit.entity.Player;
import org.bukkit.scoreboard.*;
import io.papermc.paper.scoreboard.numbers.NumberFormat;

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

        // Use MiniMessage for the title
        MiniMessage mm = MiniMessage.miniMessage();
        Component title = mm.deserialize("<gradient:#FF5555:#AA0000><b>DRAGON RUN</b></gradient>");

        Objective objective = scoreboard.registerNewObjective(
                "dragonrun",
                Criteria.DUMMY,
                title
        );
        objective.setDisplaySlot(DisplaySlot.SIDEBAR);

        // Hide the score numbers on the right side using blank number format
        objective.numberFormat(NumberFormat.blank());

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

            setScoreComponent(objective, Component.text("LOBBY", NamedTextColor.YELLOW, TextDecoration.BOLD), line--);
            setScoreComponent(objective,
                Component.text()
                    .append(Component.text("Players: ", NamedTextColor.GRAY))
                    .append(Component.text(lobbyPlayers, NamedTextColor.GREEN))
                    .build(), line--);
            setScoreComponent(objective,
                Component.text()
                    .append(Component.text("Votes: ", NamedTextColor.GRAY))
                    .append(Component.text(votes, NamedTextColor.AQUA))
                    .append(Component.text("/", NamedTextColor.GRAY))
                    .append(Component.text(required, NamedTextColor.AQUA))
                    .build(), line--);
            setScoreComponent(objective,
                Component.text()
                    .append(Component.text("Use ", NamedTextColor.GRAY))
                    .append(Component.text("/vote", NamedTextColor.GREEN))
                    .append(Component.text(" to start!", NamedTextColor.GRAY))
                    .build(), line--);
        } else if (state == GameState.GENERATING) {
            setScoreComponent(objective, Component.text("GENERATING...", NamedTextColor.GOLD, TextDecoration.BOLD), line--);
            setScoreComponent(objective, Component.text("Creating world...", NamedTextColor.GRAY), line--);
            setScore(objective, "  ", line--);
            setScore(objective, "   ", line--);
        } else if (state == GameState.ACTIVE) {
            // Active run
            int runId = plugin.getRunManager().getCurrentRunId();
            long runDuration = plugin.getRunManager().getRunDurationSeconds();
            boolean dragonAlive = plugin.getRunManager().isDragonAlive();

            setScoreComponent(objective,
                Component.text()
                    .append(Component.text("Run #" + runId, NamedTextColor.AQUA, TextDecoration.BOLD))
                    .build(), line--);
            setScoreComponent(objective,
                Component.text()
                    .append(Component.text("⏱ ", NamedTextColor.DARK_GRAY))
                    .append(Component.text(TimeUtil.formatDuration(runDuration), NamedTextColor.WHITE))
                    .build(), line--);
            setScoreComponent(objective,
                Component.text()
                    .append(Component.text("Players: ", NamedTextColor.GRAY))
                    .append(Component.text(plugin.getWorldManager().getHardcorePlayerCount(), NamedTextColor.GREEN))
                    .build(), line--);

            // Dragon status
            if (dragonAlive) {
                setScoreComponent(objective,
                    Component.text()
                        .append(Component.text("🐉 ", NamedTextColor.DARK_PURPLE))
                        .append(Component.text("Dragon ", NamedTextColor.DARK_PURPLE))
                        .append(Component.text("Alive", NamedTextColor.RED, TextDecoration.BOLD))
                        .build(), line--);
            } else {
                setScoreComponent(objective,
                    Component.text()
                        .append(Component.text("🐉 ", NamedTextColor.GRAY))
                        .append(Component.text("Dragon ", NamedTextColor.GRAY))
                        .append(Component.text("Dead", NamedTextColor.GREEN, TextDecoration.BOLD))
                        .build(), line--);
            }
            setScore(objective, "  ", line--);
        } else if (state == GameState.RESETTING) {
            setScoreComponent(objective, Component.text("RESETTING...", NamedTextColor.RED, TextDecoration.BOLD), line--);
            setScoreComponent(objective, Component.text("Returning to lobby...", NamedTextColor.GRAY), line--);
            setScore(objective, "  ", line--);
            setScore(objective, "   ", line--);
        }

        // Blank line
        setScore(objective, "    ", line--);

        // Your stats
        setScoreComponent(objective,
            Component.text("Your Stats", NamedTextColor.LIGHT_PURPLE, TextDecoration.BOLD), line--);

        NamedTextColor auraColor = aura >= 0 ? NamedTextColor.LIGHT_PURPLE : NamedTextColor.RED;
        setScoreComponent(objective,
            Component.text()
                .append(Component.text("Aura: ", NamedTextColor.GRAY))
                .append(Component.text(aura, auraColor))
                .build(), line--);

        setScoreComponent(objective,
            Component.text()
                .append(Component.text("Achievements: ", NamedTextColor.GRAY))
                .append(Component.text(achievements, NamedTextColor.YELLOW))
                .append(Component.text("/", NamedTextColor.DARK_GRAY))
                .append(Component.text(totalAchievements, NamedTextColor.GRAY))
                .build(), line--);

        // Blank line
        setScore(objective, "     ", line--);

        // Server
        setScoreComponent(objective, Component.text("dragonrun.server", NamedTextColor.DARK_GRAY), line--);
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

    /**
     * Set a scoreboard line using a Component (supports modern formatting)
     */
    private void setScoreComponent(Objective objective, Component component, int score) {
        // Convert Component to legacy string for scoreboard entry
        // Scoreboard entries need a unique string key, so we use a combination of score and hash
        String entry = net.kyori.adventure.text.serializer.legacy.LegacyComponentSerializer.legacySection().serialize(component);
        Score s = objective.getScore(entry);
        s.setScore(score);
    }
}