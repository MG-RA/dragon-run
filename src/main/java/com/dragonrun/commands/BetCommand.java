package com.dragonrun.commands;

import com.dragonrun.DragonRunPlugin;
import com.mojang.brigadier.arguments.IntegerArgumentType;
import com.mojang.brigadier.arguments.StringArgumentType;
import io.papermc.paper.command.brigadier.CommandSourceStack;
import io.papermc.paper.command.brigadier.Commands;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import net.kyori.adventure.text.format.TextDecoration;
import org.bukkit.Bukkit;
import org.bukkit.entity.Player;

import java.util.Map;
import java.util.UUID;

@SuppressWarnings("UnstableApiUsage")
public class BetCommand {

    private final DragonRunPlugin plugin;

    public BetCommand(DragonRunPlugin plugin) {
        this.plugin = plugin;
    }

    public void register(Commands commands) {
        commands.register(
            Commands.literal("bet")
                .executes(ctx -> showBets(ctx.getSource()))
                .then(Commands.argument("player", StringArgumentType.word())
                    .suggests((ctx, builder) -> {
                        // Suggest online players
                        for (Player p : Bukkit.getOnlinePlayers()) {
                            builder.suggest(p.getName());
                        }
                        return builder.buildFuture();
                    })
                    .then(Commands.argument("amount", IntegerArgumentType.integer(1))
                        .executes(ctx -> placeBet(
                            ctx.getSource(),
                            StringArgumentType.getString(ctx, "player"),
                            IntegerArgumentType.getInteger(ctx, "amount")
                        ))
                    )
                )
                .build(),
            "Bet aura on a player's survival",
            java.util.List.of("wager", "gamble")
        );
    }

    private int showBets(CommandSourceStack source) {
        if (!(source.getSender() instanceof Player player)) {
            source.getSender().sendMessage(Component.text("Only players can use this command.", NamedTextColor.RED));
            return 0;
        }

        Map<UUID, Integer> bets = plugin.getBettingManager().getPlayerBets(player.getUniqueId());

        player.sendMessage(Component.empty());
        player.sendMessage(Component.text("═══ ", NamedTextColor.DARK_GRAY)
                .append(Component.text("YOUR ACTIVE BETS", NamedTextColor.GOLD, TextDecoration.BOLD))
                .append(Component.text(" ═══", NamedTextColor.DARK_GRAY)));
        player.sendMessage(Component.empty());

        if (bets.isEmpty()) {
            player.sendMessage(Component.text("You have no active bets.", NamedTextColor.GRAY, TextDecoration.ITALIC));
            player.sendMessage(Component.empty());
            player.sendMessage(Component.text("Usage: /bet <player> <amount>", NamedTextColor.YELLOW));
            player.sendMessage(Component.text("Bet on a player to survive. If they die, you lose your bet.", NamedTextColor.GRAY));
            player.sendMessage(Component.text("If the run completes successfully, you win 2x your bet!", NamedTextColor.GREEN));
        } else {
            int totalBet = 0;
            for (Map.Entry<UUID, Integer> entry : bets.entrySet()) {
                UUID targetUuid = entry.getKey();
                int amount = entry.getValue();
                totalBet += amount;

                String targetName = Bukkit.getOfflinePlayer(targetUuid).getName();
                if (targetName == null) targetName = "Unknown";

                boolean isOnline = Bukkit.getPlayer(targetUuid) != null;
                NamedTextColor statusColor = isOnline ? NamedTextColor.GREEN : NamedTextColor.RED;
                String status = isOnline ? "ALIVE" : "OFFLINE";

                player.sendMessage(Component.text("  ➤ ", NamedTextColor.DARK_GRAY)
                        .append(Component.text(targetName, NamedTextColor.WHITE))
                        .append(Component.text(" - ", NamedTextColor.DARK_GRAY))
                        .append(Component.text(amount + " aura", NamedTextColor.GOLD))
                        .append(Component.text(" [" + status + "]", statusColor)));
            }

            player.sendMessage(Component.empty());
            player.sendMessage(Component.text("Total bet: ", NamedTextColor.GRAY)
                    .append(Component.text(totalBet + " aura", NamedTextColor.GOLD)));
            player.sendMessage(Component.text("Potential payout: ", NamedTextColor.GRAY)
                    .append(Component.text((totalBet * 2) + " aura", NamedTextColor.GREEN)));
        }

        player.sendMessage(Component.empty());
        return 1;
    }

    private int placeBet(CommandSourceStack source, String targetName, int amount) {
        if (!(source.getSender() instanceof Player player)) {
            source.getSender().sendMessage(Component.text("Only players can use this command.", NamedTextColor.RED));
            return 0;
        }

        // Find target player
        Player target = Bukkit.getPlayer(targetName);
        if (target == null) {
            player.sendMessage(Component.text("Player not found: " + targetName, NamedTextColor.RED));
            return 0;
        }

        UUID playerUuid = player.getUniqueId();
        UUID targetUuid = target.getUniqueId();

        // Check if betting on self
        if (playerUuid.equals(targetUuid)) {
            player.sendMessage(Component.text("You can't bet on yourself!", NamedTextColor.RED));
            return 0;
        }

        // Check if player has enough aura
        int currentAura = plugin.getAuraManager().getAura(playerUuid);
        if (currentAura < amount) {
            player.sendMessage(Component.text("You don't have enough aura! ", NamedTextColor.RED)
                    .append(Component.text("(You have " + currentAura + ")", NamedTextColor.GRAY)));
            return 0;
        }

        // Place the bet
        boolean success = plugin.getBettingManager().placeBet(playerUuid, targetUuid, amount);

        if (success) {
            int totalBet = plugin.getBettingManager().getActiveBet(playerUuid, targetUuid);

            player.sendMessage(Component.text("✓ ", NamedTextColor.GREEN, TextDecoration.BOLD)
                    .append(Component.text("Bet placed!", NamedTextColor.GREEN))
                    .append(Component.text(" You bet ", NamedTextColor.GRAY))
                    .append(Component.text(amount + " aura", NamedTextColor.GOLD))
                    .append(Component.text(" on ", NamedTextColor.GRAY))
                    .append(Component.text(target.getName(), NamedTextColor.AQUA)));

            player.sendMessage(Component.text("  Total bet on " + target.getName() + ": ", NamedTextColor.GRAY)
                    .append(Component.text(totalBet + " aura", NamedTextColor.GOLD)));

            // Notify target
            target.sendMessage(Component.text(player.getName(), NamedTextColor.AQUA)
                    .append(Component.text(" bet ", NamedTextColor.GRAY))
                    .append(Component.text(amount + " aura", NamedTextColor.GOLD))
                    .append(Component.text(" on your survival!", NamedTextColor.GRAY)));

            return 1;
        } else {
            player.sendMessage(Component.text("Failed to place bet.", NamedTextColor.RED));
            return 0;
        }
    }
}
