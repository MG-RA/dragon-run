package com.dragonrun.commands;

import com.dragonrun.DragonRunPlugin;
import com.dragonrun.util.TimeUtil;
import io.papermc.paper.command.brigadier.CommandSourceStack;
import io.papermc.paper.command.brigadier.Commands;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import net.kyori.adventure.text.format.TextDecoration;
import org.bukkit.Bukkit;
import org.bukkit.entity.Player;

@SuppressWarnings("UnstableApiUsage")
public class StatsCommand {

    private final DragonRunPlugin plugin;

    public StatsCommand(DragonRunPlugin plugin) {
        this.plugin = plugin;
    }

    public void register(Commands commands) {
        commands.register(
            Commands.literal("stats")
                .executes(ctx -> {
                    return showStats(ctx.getSource());
                })
                .build(),
            "View run stats and player dashboard",
            java.util.List.of("dashboard", "info")
        );
    }

    private int showStats(CommandSourceStack source) {
        if (!(source.getSender() instanceof Player player)) {
            source.getSender().sendMessage(Component.text("Only players can use this command.", NamedTextColor.RED));
            return 0;
        }

        var auraManager = plugin.getAuraManager();
        var runManager = plugin.getRunManager();
        var achievementManager = plugin.getAchievementManager();

        int aura = auraManager.getAura(player.getUniqueId());
        int runId = runManager.getCurrentRunId();
        long runDuration = runManager.getRunDurationSeconds();
        int onlinePlayers = Bukkit.getOnlinePlayers().size();
        int achievements = achievementManager.getPlayerAchievements(player.getUniqueId()).size();
        int totalAchievements = achievementManager.getAllAchievements().size();

        // Build dashboard
        player.sendMessage(Component.empty());
        player.sendMessage(Component.text("╔════════════════════════════════╗", NamedTextColor.DARK_GRAY));
        player.sendMessage(Component.text("║ ", NamedTextColor.DARK_GRAY)
                .append(Component.text("     DRAGON RUN DASHBOARD", NamedTextColor.GOLD, TextDecoration.BOLD))
                .append(Component.text("      ║", NamedTextColor.DARK_GRAY)));
        player.sendMessage(Component.text("╠════════════════════════════════╣", NamedTextColor.DARK_GRAY));

        // Current Run Info
        player.sendMessage(Component.text("║ ", NamedTextColor.DARK_GRAY)
                .append(Component.text("RUN #" + runId, NamedTextColor.AQUA, TextDecoration.BOLD))
                .append(Component.text(padRight("", 26 - ("RUN #" + runId).length()) + "║", NamedTextColor.DARK_GRAY)));

        player.sendMessage(Component.text("║ ", NamedTextColor.DARK_GRAY)
                .append(Component.text("Duration: ", NamedTextColor.GRAY))
                .append(Component.text(TimeUtil.formatDuration(runDuration), NamedTextColor.WHITE))
                .append(Component.text(padRight("", 22 - TimeUtil.formatDuration(runDuration).length()) + "║", NamedTextColor.DARK_GRAY)));

        player.sendMessage(Component.text("║ ", NamedTextColor.DARK_GRAY)
                .append(Component.text("Players: ", NamedTextColor.GRAY))
                .append(Component.text(onlinePlayers + " online", NamedTextColor.GREEN))
                .append(Component.text(padRight("", 22 - (onlinePlayers + " online").length()) + "║", NamedTextColor.DARK_GRAY)));

        player.sendMessage(Component.text("║ ", NamedTextColor.DARK_GRAY)
                .append(Component.text("Dragon: ", NamedTextColor.GRAY))
                .append(runManager.isDragonAlive()
                        ? Component.text("ALIVE", NamedTextColor.RED, TextDecoration.BOLD)
                        : Component.text("DEAD", NamedTextColor.GREEN, TextDecoration.BOLD))
                .append(Component.text(padRight("", runManager.isDragonAlive() ? 19 : 20) + "║", NamedTextColor.DARK_GRAY)));

        player.sendMessage(Component.text("╠════════════════════════════════╣", NamedTextColor.DARK_GRAY));

        // Player Stats
        player.sendMessage(Component.text("║ ", NamedTextColor.DARK_GRAY)
                .append(Component.text("YOUR STATS", NamedTextColor.LIGHT_PURPLE, TextDecoration.BOLD))
                .append(Component.text(padRight("", 22) + "║", NamedTextColor.DARK_GRAY)));

        String auraStr = String.valueOf(aura);
        NamedTextColor auraColor = aura >= 0 ? NamedTextColor.LIGHT_PURPLE : NamedTextColor.RED;
        player.sendMessage(Component.text("║ ", NamedTextColor.DARK_GRAY)
                .append(Component.text("Aura: ", NamedTextColor.GRAY))
                .append(Component.text(auraStr, auraColor))
                .append(Component.text(" " + getAuraRank(aura), NamedTextColor.DARK_GRAY))
                .append(Component.text(padRight("", Math.max(0, 19 - auraStr.length() - getAuraRank(aura).length())) + "║", NamedTextColor.DARK_GRAY)));

        String achStr = achievements + "/" + totalAchievements;
        player.sendMessage(Component.text("║ ", NamedTextColor.DARK_GRAY)
                .append(Component.text("Achievements: ", NamedTextColor.GRAY))
                .append(Component.text(achStr, NamedTextColor.YELLOW))
                .append(Component.text(padRight("", 18 - achStr.length()) + "║", NamedTextColor.DARK_GRAY)));

        player.sendMessage(Component.text("╠════════════════════════════════╣", NamedTextColor.DARK_GRAY));

        // Online Players
        player.sendMessage(Component.text("║ ", NamedTextColor.DARK_GRAY)
                .append(Component.text("PLAYERS", NamedTextColor.GREEN, TextDecoration.BOLD))
                .append(Component.text(padRight("", 25) + "║", NamedTextColor.DARK_GRAY)));

        int shown = 0;
        for (Player p : Bukkit.getOnlinePlayers()) {
            if (shown >= 5) {
                int remaining = onlinePlayers - shown;
                player.sendMessage(Component.text("║ ", NamedTextColor.DARK_GRAY)
                        .append(Component.text("  +" + remaining + " more...", NamedTextColor.DARK_GRAY))
                        .append(Component.text(padRight("", 20 - String.valueOf(remaining).length()) + "║", NamedTextColor.DARK_GRAY)));
                break;
            }

            int pAura = auraManager.getAura(p.getUniqueId());
            String pAuraStr = "[" + pAura + "]";
            NamedTextColor pColor = p.equals(player) ? NamedTextColor.AQUA : NamedTextColor.WHITE;

            String line = "  " + p.getName();
            player.sendMessage(Component.text("║ ", NamedTextColor.DARK_GRAY)
                    .append(Component.text(line, pColor))
                    .append(Component.text(" " + pAuraStr, pAura >= 0 ? NamedTextColor.LIGHT_PURPLE : NamedTextColor.RED))
                    .append(Component.text(padRight("", Math.max(0, 28 - line.length() - pAuraStr.length())) + "║", NamedTextColor.DARK_GRAY)));
            shown++;
        }

        player.sendMessage(Component.text("╚════════════════════════════════╝", NamedTextColor.DARK_GRAY));
        player.sendMessage(Component.empty());

        return 1;
    }

    private String padRight(String s, int n) {
        if (n <= 0) return "";
        return String.format("%-" + n + "s", s);
    }

    private String getAuraRank(int aura) {
        if (aura >= 10000) return "(Deity)";
        if (aura >= 5000) return "(Emperor)";
        if (aura >= 2500) return "(Lord)";
        if (aura >= 1000) return "(Merchant)";
        if (aura >= 500) return "(Haver)";
        if (aura >= 100) return "(Student)";
        if (aura <= -5000) return "(Demon)";
        if (aura <= -2500) return "(Void)";
        if (aura <= -1000) return "(Vampire)";
        if (aura <= -500) return "(Bankrupt)";
        if (aura <= -100) return "(Debt)";
        return "";
    }
}
