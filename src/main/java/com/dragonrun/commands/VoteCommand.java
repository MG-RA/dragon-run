package com.dragonrun.commands;

import com.dragonrun.DragonRunPlugin;
import com.dragonrun.managers.GameState;
import com.dragonrun.util.MessageUtil;
import io.papermc.paper.command.brigadier.CommandSourceStack;
import io.papermc.paper.command.brigadier.Commands;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.entity.Player;

import java.util.List;

@SuppressWarnings("UnstableApiUsage")
public class VoteCommand {

    private final DragonRunPlugin plugin;

    public VoteCommand(DragonRunPlugin plugin) {
        this.plugin = plugin;
    }

    public void register(Commands commands) {
        plugin.getLogger().info("Registering vote commands...");

        // /vote - toggle vote to start (no permission required - everyone can vote)
        commands.register(
            Commands.literal("vote")
                .executes(ctx -> handleVote(ctx.getSource()))
                .build(),
            "Vote to start a new run",
            List.of("ready", "v")
        );

        // /unvote - remove vote
        commands.register(
            Commands.literal("unvote")
                .executes(ctx -> handleUnvote(ctx.getSource()))
                .build(),
            "Remove your vote to start"
        );

        // /forcestart - admin command
        commands.register(
            Commands.literal("forcestart")
                .requires(source -> source.getSender().hasPermission("dragonrun.admin.forcestart"))
                .executes(ctx -> handleForceStart(ctx.getSource()))
                .build(),
            "Force start a run (admin)"
        );

        // /votestatus - show current vote status
        commands.register(
            Commands.literal("votestatus")
                .executes(ctx -> handleVoteStatus(ctx.getSource()))
                .build(),
            "Show current vote status",
            List.of("votes", "vs")
        );

        plugin.getLogger().info("Vote commands registered: /vote, /unvote, /votestatus, /forcestart");
    }

    private int handleVote(CommandSourceStack source) {
        if (!(source.getSender() instanceof Player player)) {
            source.getSender().sendMessage(Component.text("Only players can vote.", NamedTextColor.RED));
            return 0;
        }

        plugin.getVoteManager().toggleVote(player);
        return 1;
    }

    private int handleUnvote(CommandSourceStack source) {
        if (!(source.getSender() instanceof Player player)) {
            source.getSender().sendMessage(Component.text("Only players can vote.", NamedTextColor.RED));
            return 0;
        }

        plugin.getVoteManager().unvote(player);
        return 1;
    }

    private int handleForceStart(CommandSourceStack source) {
        GameState state = plugin.getRunManager().getGameState();

        if (state != GameState.IDLE) {
            source.getSender().sendMessage(MessageUtil.error("Cannot force start - game state is " + state));
            return 0;
        }

        if (plugin.getWorldManager().getLobbyPlayerCount() == 0) {
            source.getSender().sendMessage(MessageUtil.error("No players in lobby!"));
            return 0;
        }

        plugin.getVoteManager().forceStart();
        return 1;
    }

    private int handleVoteStatus(CommandSourceStack source) {
        int currentVotes = plugin.getVoteManager().getVoteCount();
        int required = plugin.getVoteManager().getRequiredVotes();
        int lobbyPlayers = plugin.getVoteManager().getLobbyPlayerCount();
        GameState state = plugin.getRunManager().getGameState();

        source.getSender().sendMessage(Component.empty());
        source.getSender().sendMessage(Component.text("═══ Vote Status ═══", NamedTextColor.GOLD));
        source.getSender().sendMessage(Component.text("Game State: ", NamedTextColor.GRAY)
                .append(Component.text(state.name(), getStateColor(state))));
        source.getSender().sendMessage(Component.text("Lobby Players: ", NamedTextColor.GRAY)
                .append(Component.text(String.valueOf(lobbyPlayers), NamedTextColor.WHITE)));
        source.getSender().sendMessage(Component.text("Votes: ", NamedTextColor.GRAY)
                .append(Component.text(currentVotes + "/" + required,
                        currentVotes >= required ? NamedTextColor.GREEN : NamedTextColor.YELLOW)));

        if (state == GameState.IDLE) {
            int needed = required - currentVotes;
            if (needed > 0) {
                source.getSender().sendMessage(Component.text("Need " + needed + " more vote(s) to start!", NamedTextColor.AQUA));
            } else {
                source.getSender().sendMessage(Component.text("Ready to start!", NamedTextColor.GREEN));
            }
        }

        source.getSender().sendMessage(Component.empty());
        return 1;
    }

    private NamedTextColor getStateColor(GameState state) {
        return switch (state) {
            case IDLE -> NamedTextColor.GRAY;
            case GENERATING -> NamedTextColor.YELLOW;
            case ACTIVE -> NamedTextColor.GREEN;
            case RESETTING -> NamedTextColor.RED;
        };
    }
}
