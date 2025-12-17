package com.dragonrun.commands;

import com.dragonrun.DragonRunPlugin;
import io.papermc.paper.command.brigadier.CommandSourceStack;
import io.papermc.paper.command.brigadier.Commands;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import net.kyori.adventure.text.format.TextDecoration;
import org.bukkit.Bukkit;
import org.bukkit.Location;
import org.bukkit.attribute.Attribute;
import org.bukkit.attribute.AttributeInstance;
import org.bukkit.entity.Player;

@SuppressWarnings("UnstableApiUsage")
public class LiveCommand {

    private final DragonRunPlugin plugin;

    public LiveCommand(DragonRunPlugin plugin) {
        this.plugin = plugin;
    }

    public void register(Commands commands) {
        commands.register(
            Commands.literal("live")
                .executes(ctx -> showLiveStats(ctx.getSource()))
                .build(),
            "View live player locations and stats",
            java.util.List.of("locations", "where")
        );
    }

    private int showLiveStats(CommandSourceStack source) {
        if (!(source.getSender() instanceof Player player)) {
            source.getSender().sendMessage(Component.text("Only players can use this command.", NamedTextColor.RED));
            return 0;
        }

        var runManager = plugin.getRunManager();
        var auraManager = plugin.getAuraManager();
        var bettingManager = plugin.getBettingManager();

        player.sendMessage(Component.empty());
        player.sendMessage(Component.text("╔════════════════════════════════════════╗", NamedTextColor.DARK_GRAY));
        player.sendMessage(Component.text("║ ", NamedTextColor.DARK_GRAY)
                .append(Component.text("       LIVE PLAYER TRACKER", NamedTextColor.AQUA, TextDecoration.BOLD))
                .append(Component.text("        ║", NamedTextColor.DARK_GRAY)));
        player.sendMessage(Component.text("╠════════════════════════════════════════╣", NamedTextColor.DARK_GRAY));

        // Show run info
        int runId = runManager.getCurrentRunId();
        long runDuration = runManager.getRunDurationSeconds();
        int onlinePlayers = Bukkit.getOnlinePlayers().size();

        player.sendMessage(Component.text("║ ", NamedTextColor.DARK_GRAY)
                .append(Component.text("Run #" + runId, NamedTextColor.GOLD))
                .append(Component.text(" │ ", NamedTextColor.DARK_GRAY))
                .append(Component.text(formatDuration(runDuration), NamedTextColor.WHITE))
                .append(Component.text(" │ ", NamedTextColor.DARK_GRAY))
                .append(Component.text(onlinePlayers + " players", NamedTextColor.GREEN))
                .append(Component.text(padRight("", 40 - ("Run #" + runId).length() - formatDuration(runDuration).length() - (onlinePlayers + " players").length() - 7) + "║", NamedTextColor.DARK_GRAY)));

        player.sendMessage(Component.text("╠════════════════════════════════════════╣", NamedTextColor.DARK_GRAY));

        // Show each player
        for (Player p : Bukkit.getOnlinePlayers()) {
            Location loc = p.getLocation();
            int aura = auraManager.getAura(p.getUniqueId());
            int totalBets = bettingManager.getTotalBetsOnPlayer(p.getUniqueId());

            // Player name and health
            String healthBar = getHealthBar(p);
            NamedTextColor nameColor = p.equals(player) ? NamedTextColor.AQUA : NamedTextColor.WHITE;

            player.sendMessage(Component.text("║ ", NamedTextColor.DARK_GRAY)
                    .append(Component.text(p.getName(), nameColor, TextDecoration.BOLD))
                    .append(Component.text(padRight("", Math.max(0, 40 - p.getName().length())) + "║", NamedTextColor.DARK_GRAY)));

            // Health bar
            player.sendMessage(Component.text("║  ", NamedTextColor.DARK_GRAY)
                    .append(Component.text("❤ ", NamedTextColor.RED))
                    .append(Component.text(healthBar))
                    .append(Component.text(padRight("", Math.max(0, 37 - healthBar.length())) + "║", NamedTextColor.DARK_GRAY)));

            // Location
            String world = getWorldName(loc.getWorld().getName());
            String coords = String.format("%d, %d, %d", loc.getBlockX(), loc.getBlockY(), loc.getBlockZ());
            player.sendMessage(Component.text("║  ", NamedTextColor.DARK_GRAY)
                    .append(Component.text("📍 ", NamedTextColor.YELLOW))
                    .append(Component.text(world + " ", NamedTextColor.GRAY))
                    .append(Component.text(coords, NamedTextColor.WHITE))
                    .append(Component.text(padRight("", Math.max(0, 35 - world.length() - coords.length())) + "║", NamedTextColor.DARK_GRAY)));

            // Aura and bets
            String auraStr = (aura >= 0 ? "+" : "") + aura + " aura";
            String betsStr = totalBets > 0 ? " │ " + totalBets + " bet on them" : "";
            NamedTextColor auraColor = aura >= 0 ? NamedTextColor.LIGHT_PURPLE : NamedTextColor.RED;

            player.sendMessage(Component.text("║  ", NamedTextColor.DARK_GRAY)
                    .append(Component.text("✦ ", NamedTextColor.GOLD))
                    .append(Component.text(auraStr, auraColor))
                    .append(Component.text(betsStr, NamedTextColor.DARK_GRAY))
                    .append(Component.text(padRight("", Math.max(0, 35 - auraStr.length() - betsStr.length())) + "║", NamedTextColor.DARK_GRAY)));

            player.sendMessage(Component.text("╟────────────────────────────────────────╢", NamedTextColor.DARK_GRAY));
        }

        player.sendMessage(Component.text("╚════════════════════════════════════════╝", NamedTextColor.DARK_GRAY));
        player.sendMessage(Component.empty());

        return 1;
    }

    private String getHealthBar(Player player) {
        double health = player.getHealth();
        // Use reflection-safe approach - get max health from absorptionAmount or default
        double maxHealth = 20.0;
        try {
            // Try to get the max health attribute dynamically
            for (Attribute attr : Attribute.values()) {
                if (attr.name().contains("MAX_HEALTH") || attr.name().contains("HEALTH")) {
                    AttributeInstance instance = player.getAttribute(attr);
                    if (instance != null) {
                        maxHealth = instance.getValue();
                        break;
                    }
                }
            }
        } catch (Exception e) {
            // Fallback to default 20
        }

        double percentage = health / maxHealth;
        int bars = (int) Math.ceil(percentage * 10);

        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 10; i++) {
            if (i < bars) {
                if (percentage > 0.5) {
                    sb.append("§a█");
                } else if (percentage > 0.25) {
                    sb.append("§e█");
                } else {
                    sb.append("§c█");
                }
            } else {
                sb.append("§8█");
            }
        }

        sb.append(String.format(" §f%.1f§8/§f%.0f", health, maxHealth));
        return sb.toString();
    }

    private String getWorldName(String worldName) {
        if (worldName.contains("nether")) return "Nether";
        if (worldName.contains("end")) return "The End";
        return "Overworld";
    }

    private String formatDuration(long seconds) {
        long hours = seconds / 3600;
        long minutes = (seconds % 3600) / 60;
        long secs = seconds % 60;

        if (hours > 0) {
            return String.format("%dh %dm", hours, minutes);
        } else if (minutes > 0) {
            return String.format("%dm %ds", minutes, secs);
        } else {
            return String.format("%ds", secs);
        }
    }

    private String padRight(String s, int n) {
        if (n <= 0) return "";
        return String.format("%-" + n + "s", s);
    }
}
