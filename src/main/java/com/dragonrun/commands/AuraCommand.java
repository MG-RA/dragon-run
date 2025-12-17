package com.dragonrun.commands;

import com.dragonrun.DragonRunPlugin;
import com.dragonrun.util.MessageUtil;
import com.mojang.brigadier.arguments.StringArgumentType;
import io.papermc.paper.command.brigadier.CommandSourceStack;
import io.papermc.paper.command.brigadier.Commands;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.Bukkit;
import org.bukkit.OfflinePlayer;
import org.bukkit.entity.Player;

@SuppressWarnings("UnstableApiUsage")
public class AuraCommand {

    private final DragonRunPlugin plugin;

    public AuraCommand(DragonRunPlugin plugin) {
        this.plugin = plugin;
    }

    public void register(Commands commands) {
        commands.register(
            Commands.literal("aura")
                .executes(ctx -> {
                    return executeAura(ctx.getSource(), null);
                })
                .then(Commands.argument("player", StringArgumentType.word())
                    .suggests((ctx, builder) -> {
                        String input = builder.getRemaining().toLowerCase();
                        for (Player player : Bukkit.getOnlinePlayers()) {
                            if (player.getName().toLowerCase().startsWith(input)) {
                                builder.suggest(player.getName());
                            }
                        }
                        return builder.buildFuture();
                    })
                    .executes(ctx -> {
                        String playerName = StringArgumentType.getString(ctx, "player");
                        return executeAura(ctx.getSource(), playerName);
                    })
                )
                .build(),
            "Check your aura balance",
            java.util.List.of("balance", "points")
        );
    }

    private int executeAura(CommandSourceStack source, String targetName) {
        if (targetName == null) {
            // Check own aura
            if (!(source.getSender() instanceof Player player)) {
                source.getSender().sendMessage(MessageUtil.error("Console must specify a player name."));
                return 0;
            }

            int aura = plugin.getAuraManager().getAura(player.getUniqueId());
            source.getSender().sendMessage(createAuraMessage("Your", aura));
        } else {
            // Check another player's aura
            Player onlineTarget = Bukkit.getPlayer(targetName);
            if (onlineTarget != null) {
                int aura = plugin.getAuraManager().getAura(onlineTarget.getUniqueId());
                source.getSender().sendMessage(createAuraMessage(onlineTarget.getName() + "'s", aura));
                return 1;
            }

            // Try offline player
            @SuppressWarnings("deprecation")
            OfflinePlayer offlineTarget = Bukkit.getOfflinePlayer(targetName);

            if (!offlineTarget.hasPlayedBefore()) {
                source.getSender().sendMessage(MessageUtil.error("Player '" + targetName + "' not found."));
                return 0;
            }

            int aura = plugin.getAuraManager().getAura(offlineTarget.getUniqueId());
            String displayName = offlineTarget.getName() != null ? offlineTarget.getName() : targetName;
            source.getSender().sendMessage(createAuraMessage(displayName + "'s", aura));
        }

        return 1;
    }

    private Component createAuraMessage(String prefix, int aura) {
        return Component.text()
                .append(Component.text(prefix + " aura: ", NamedTextColor.GRAY))
                .append(Component.text(String.valueOf(aura),
                        aura >= 0 ? MessageUtil.AURA_COLOR : NamedTextColor.RED))
                .append(getAuraRankSuffix(aura))
                .build();
    }

    private Component getAuraRankSuffix(int aura) {
        String rank = getAuraRank(aura);
        if (rank == null) {
            return Component.empty();
        }

        return Component.text()
                .append(Component.text(" (", NamedTextColor.DARK_GRAY))
                .append(Component.text(rank, aura >= 0 ? NamedTextColor.LIGHT_PURPLE : NamedTextColor.DARK_RED))
                .append(Component.text(")", NamedTextColor.DARK_GRAY))
                .build();
    }

    private String getAuraRank(int aura) {
        // Positive ranks
        if (aura >= 10000) return "Aura Deity";
        if (aura >= 5000) return "Aura Emperor";
        if (aura >= 2500) return "Aura Lord";
        if (aura >= 1000) return "Aura Merchant";
        if (aura >= 500) return "Aura Haver";
        if (aura >= 100) return "Aura Student";

        // Negative ranks
        if (aura <= -5000) return "Aura Demon";
        if (aura <= -2500) return "Aura Void";
        if (aura <= -1000) return "Aura Vampire";
        if (aura <= -500) return "Aura Bankrupt";
        if (aura <= -100) return "Aura Debt";

        return null;
    }
}
