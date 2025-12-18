package com.dragonrun.managers;

import com.dragonrun.DragonRunPlugin;
import com.dragonrun.util.MessageUtil;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.Bukkit;
import org.bukkit.entity.Player;

import java.util.HashSet;
import java.util.Set;
import java.util.UUID;

/**
 * Manages the vote-to-start system for Dragon Run.
 * Players vote when ready, and the run starts when majority is reached.
 */
public class VoteManager {

    private final DragonRunPlugin plugin;
    private final Set<UUID> votes = new HashSet<>();

    public VoteManager(DragonRunPlugin plugin) {
        this.plugin = plugin;
    }

    /**
     * Toggle vote for a player.
     * @return true if player is now voting, false if vote was removed
     */
    public boolean toggleVote(Player player) {
        UUID uuid = player.getUniqueId();

        plugin.getLogger().info("Vote toggle requested by " + player.getName() +
                " in world: " + player.getWorld().getName() +
                " at location: " + player.getLocation());

        // Can only vote in lobby during IDLE state
        boolean inLobby = plugin.getWorldManager().isPlayerInLobby(player);
        plugin.getLogger().info("Player in lobby: " + inLobby);

        if (!inLobby) {
            player.sendMessage(MessageUtil.error("You can only vote from the lobby."));
            return false;
        }

        GameState state = plugin.getRunManager().getGameState();
        plugin.getLogger().info("Current game state: " + state);

        if (state != GameState.IDLE) {
            player.sendMessage(MessageUtil.error("A run is already in progress or starting."));
            return false;
        }

        if (votes.contains(uuid)) {
            votes.remove(uuid);
            broadcastVoteUpdate(player, false);
            return false;
        } else {
            votes.add(uuid);
            broadcastVoteUpdate(player, true);
            checkAndStart();
            return true;
        }
    }

    /**
     * Add a vote for a player.
     */
    public void vote(Player player) {
        UUID uuid = player.getUniqueId();

        if (!plugin.getWorldManager().isPlayerInLobby(player)) {
            player.sendMessage(MessageUtil.error("You can only vote from the lobby."));
            return;
        }

        if (plugin.getRunManager().getGameState() != GameState.IDLE) {
            player.sendMessage(MessageUtil.error("A run is already in progress or starting."));
            return;
        }

        if (votes.contains(uuid)) {
            player.sendMessage(MessageUtil.info("You have already voted. Use /vote again to unvote."));
            return;
        }

        votes.add(uuid);
        broadcastVoteUpdate(player, true);
        checkAndStart();
    }

    /**
     * Remove a vote for a player.
     */
    public void unvote(Player player) {
        UUID uuid = player.getUniqueId();

        if (!votes.contains(uuid)) {
            player.sendMessage(MessageUtil.info("You haven't voted yet."));
            return;
        }

        votes.remove(uuid);
        broadcastVoteUpdate(player, false);
    }

    /**
     * Remove a player's vote when they leave.
     */
    public void removeVote(UUID uuid) {
        votes.remove(uuid);
    }

    /**
     * Get current vote count.
     */
    public int getVoteCount() {
        // Only count votes from players still in lobby
        return (int) votes.stream()
                .filter(uuid -> {
                    Player player = Bukkit.getPlayer(uuid);
                    return player != null && plugin.getWorldManager().isPlayerInLobby(player);
                })
                .count();
    }

    /**
     * Get required votes (majority of lobby players).
     */
    public int getRequiredVotes() {
        int lobbyPlayers = plugin.getWorldManager().getLobbyPlayerCount();
        if (lobbyPlayers == 0) return 1;

        // Majority: more than half
        return (lobbyPlayers / 2) + 1;
    }

    /**
     * Get total lobby player count.
     */
    public int getLobbyPlayerCount() {
        return plugin.getWorldManager().getLobbyPlayerCount();
    }

    /**
     * Check if a player has voted.
     */
    public boolean hasVoted(UUID uuid) {
        return votes.contains(uuid);
    }

    /**
     * Check if we have enough votes to start, and start if so.
     */
    public void checkAndStart() {
        int currentVotes = getVoteCount();
        int required = getRequiredVotes();

        if (currentVotes >= required) {
            startRun();
        }
    }

    /**
     * Start the run.
     */
    private void startRun() {
        clearVotes();

        Bukkit.broadcast(MessageUtil.success("Vote passed! Starting run..."));

        plugin.getRunManager().startRun(null)
                .thenAccept(success -> {
                    if (!success) {
                        Bukkit.broadcast(MessageUtil.error("Failed to start run. Try again."));
                    }
                });
    }

    /**
     * Clear all votes.
     */
    public void clearVotes() {
        votes.clear();
    }

    /**
     * Broadcast vote update to all players.
     */
    private void broadcastVoteUpdate(Player voter, boolean voted) {
        int current = getVoteCount();
        int required = getRequiredVotes();

        Component message;
        if (voted) {
            message = Component.text(voter.getName(), NamedTextColor.AQUA)
                    .append(Component.text(" voted to start! ", NamedTextColor.GREEN))
                    .append(Component.text("[" + current + "/" + required + "]", NamedTextColor.GRAY));
        } else {
            message = Component.text(voter.getName(), NamedTextColor.AQUA)
                    .append(Component.text(" removed their vote. ", NamedTextColor.YELLOW))
                    .append(Component.text("[" + current + "/" + required + "]", NamedTextColor.GRAY));
        }

        Bukkit.broadcast(message);
    }

    /**
     * Force start a run (admin command).
     */
    public void forceStart() {
        if (plugin.getRunManager().getGameState() != GameState.IDLE) {
            return;
        }

        clearVotes();
        Bukkit.broadcast(MessageUtil.info("Admin force-starting run..."));

        plugin.getRunManager().startRun(null);
    }
}
