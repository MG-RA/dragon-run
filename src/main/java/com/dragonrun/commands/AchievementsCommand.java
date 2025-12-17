package com.dragonrun.commands;

import com.dragonrun.DragonRunPlugin;
import com.dragonrun.managers.AchievementManager;
import com.dragonrun.managers.AchievementManager.Achievement;
import com.dragonrun.managers.AchievementManager.Category;
import io.papermc.paper.command.brigadier.CommandSourceStack;
import io.papermc.paper.command.brigadier.Commands;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import net.kyori.adventure.text.format.TextDecoration;
import org.bukkit.entity.Player;

import java.util.Set;

@SuppressWarnings("UnstableApiUsage")
public class AchievementsCommand {

    private final DragonRunPlugin plugin;

    public AchievementsCommand(DragonRunPlugin plugin) {
        this.plugin = plugin;
    }

    public void register(Commands commands) {
        commands.register(
            Commands.literal("achievements")
                .executes(ctx -> {
                    return showAchievements(ctx.getSource());
                })
                .build(),
            "View your achievements",
            java.util.List.of("ach", "achieve")
        );
    }

    private int showAchievements(CommandSourceStack source) {
        if (!(source.getSender() instanceof Player player)) {
            source.getSender().sendMessage(Component.text("Only players can use this command.", NamedTextColor.RED));
            return 0;
        }

        AchievementManager manager = plugin.getAchievementManager();
        Set<String> earned = manager.getPlayerAchievements(player.getUniqueId());

        // Header
        player.sendMessage(Component.empty());
        player.sendMessage(Component.text("═══ ", NamedTextColor.DARK_GRAY)
                .append(Component.text("YOUR ACHIEVEMENTS", NamedTextColor.GOLD, TextDecoration.BOLD))
                .append(Component.text(" ═══", NamedTextColor.DARK_GRAY)));
        player.sendMessage(Component.empty());

        // Show by category
        for (Category category : Category.values()) {
            var achievements = manager.getAllAchievements().stream()
                    .filter(a -> a.category() == category)
                    .toList();

            if (achievements.isEmpty()) continue;

            long unlockedCount = achievements.stream()
                    .filter(a -> earned.contains(a.id()))
                    .count();

            // Category header
            NamedTextColor catColor = category == Category.SHAME ? NamedTextColor.DARK_RED : NamedTextColor.AQUA;
            player.sendMessage(Component.text(category.getDisplayName(), catColor, TextDecoration.BOLD)
                    .append(Component.text(" [" + unlockedCount + "/" + achievements.size() + "]", NamedTextColor.GRAY)));

            // Show achievements (max 5 per category to keep it readable)
            int shown = 0;
            for (Achievement ach : achievements) {
                if (shown >= 5) {
                    int remaining = achievements.size() - shown;
                    player.sendMessage(Component.text("  ... and " + remaining + " more", NamedTextColor.DARK_GRAY, TextDecoration.ITALIC));
                    break;
                }

                boolean unlocked = earned.contains(ach.id());
                String icon = unlocked ? "✓" : "✗";
                NamedTextColor iconColor = unlocked ? NamedTextColor.GREEN : NamedTextColor.DARK_GRAY;
                NamedTextColor nameColor = unlocked ? NamedTextColor.WHITE : NamedTextColor.GRAY;

                String auraStr = (ach.auraReward() >= 0 ? "+" : "") + ach.auraReward();
                NamedTextColor auraColor = ach.auraReward() >= 0 ? NamedTextColor.GREEN : NamedTextColor.RED;

                player.sendMessage(Component.text("  " + icon + " ", iconColor)
                        .append(Component.text(ach.name(), nameColor))
                        .append(Component.text(" (" + auraStr + ")", auraColor)));

                shown++;
            }

            player.sendMessage(Component.empty());
        }

        // Summary
        int totalEarned = earned.size();
        int totalAchievements = manager.getAllAchievements().size();
        int totalAura = earned.stream()
                .map(manager::getAchievement)
                .filter(a -> a != null)
                .mapToInt(Achievement::auraReward)
                .sum();

        player.sendMessage(Component.text("Total: ", NamedTextColor.GRAY)
                .append(Component.text(totalEarned + "/" + totalAchievements, NamedTextColor.WHITE))
                .append(Component.text(" achievements, ", NamedTextColor.GRAY))
                .append(Component.text((totalAura >= 0 ? "+" : "") + totalAura + " aura",
                        totalAura >= 0 ? NamedTextColor.GREEN : NamedTextColor.RED)));
        player.sendMessage(Component.empty());

        return 1;
    }
}
