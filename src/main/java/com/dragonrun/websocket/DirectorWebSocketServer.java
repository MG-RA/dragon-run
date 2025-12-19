package com.dragonrun.websocket;

import com.dragonrun.DragonRunPlugin;
import com.dragonrun.websocket.models.PlayerStateSnapshot;
import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import org.bukkit.Bukkit;
import org.bukkit.World;
import org.bukkit.boss.DragonBattle;
import org.bukkit.entity.EnderDragon;
import org.bukkit.entity.Player;
import org.java_websocket.WebSocket;
import org.java_websocket.handshake.ClientHandshake;
import org.java_websocket.server.WebSocketServer;

import java.net.InetSocketAddress;
import java.util.*;
import java.util.concurrent.CopyOnWriteArraySet;
import java.util.concurrent.LinkedBlockingQueue;

/**
 * WebSocket server for broadcasting game state to Director AI clients.
 * Runs on a separate port and broadcasts real-time game updates.
 */
public class DirectorWebSocketServer extends WebSocketServer {

    private final DragonRunPlugin plugin;
    private final Gson gson;
    private final Set<WebSocket> clients;
    private final Queue<JsonObject> recentEvents;
    private static final int MAX_EVENT_HISTORY = 20;

    public DirectorWebSocketServer(DragonRunPlugin plugin, int port) {
        super(new InetSocketAddress(port));
        this.plugin = plugin;
        this.gson = new Gson();
        this.clients = new CopyOnWriteArraySet<>();
        this.recentEvents = new LinkedBlockingQueue<>();
    }

    @Override
    public void onOpen(WebSocket conn, ClientHandshake handshake) {
        clients.add(conn);
        plugin.getLogger().info("Director AI client connected from " + conn.getRemoteSocketAddress());

        // Send initial state
        sendCurrentState(conn);
    }

    @Override
    public void onClose(WebSocket conn, int code, String reason, boolean remote) {
        clients.remove(conn);
        plugin.getLogger().info("Director AI client disconnected: " + reason);
    }

    @Override
    public void onMessage(WebSocket conn, String message) {
        try {
            JsonObject json = gson.fromJson(message, JsonObject.class);

            if (!json.has("type")) {
                plugin.getLogger().warning("Director message missing 'type' field");
                return;
            }

            String type = json.get("type").getAsString();

            if ("command".equals(type)) {
                handleCommand(conn, json);
            } else {
                plugin.getLogger().info("Received unknown message type from Director: " + type);
            }
        } catch (Exception e) {
            plugin.getLogger().warning("Error processing Director message: " + e.getMessage());
        }
    }

    /**
     * Handle a command request from the Director AI.
     */
    private void handleCommand(WebSocket conn, JsonObject commandJson) {
        com.dragonrun.director.DirectorCommandExecutor.execute(plugin, commandJson, result -> {
            // Send result back to director
            JsonObject response = new JsonObject();
            response.addProperty("type", "command_result");
            response.addProperty("success", result.success());
            response.addProperty("message", result.message());
            response.addProperty("timestamp", System.currentTimeMillis());

            if (conn.isOpen()) {
                conn.send(gson.toJson(response));
            }

            // Log the command execution
            plugin.getLogger().info(String.format("Director command executed: %s - %s",
                result.success() ? "SUCCESS" : "FAILED",
                result.message()));
        });
    }

    @Override
    public void onError(WebSocket conn, Exception ex) {
        plugin.getLogger().warning("WebSocket error: " + ex.getMessage());
    }

    @Override
    public void onStart() {
        plugin.getLogger().info("Director WebSocket server started on port " + getPort());
    }

    /**
     * Send current game state to a specific client.
     */
    private void sendCurrentState(WebSocket conn) {
        JsonObject state = buildGameState();
        conn.send(gson.toJson(state));
    }

    /**
     * Broadcast game state to all connected clients.
     */
    public void broadcastGameState() {
        if (clients.isEmpty()) return;

        JsonObject state = buildGameState();
        String json = gson.toJson(state);

        for (WebSocket client : clients) {
            if (client.isOpen()) {
                client.send(json);
            }
        }
    }

    /**
     * Broadcast a specific event to all connected clients.
     */
    public void broadcastEvent(String eventType, JsonObject data) {
        if (clients.isEmpty()) return;

        JsonObject event = new JsonObject();
        event.addProperty("type", "event");
        event.addProperty("eventType", eventType);
        event.add("data", data);
        event.addProperty("timestamp", System.currentTimeMillis());

        // Add to recent events history
        recentEvents.offer(event);
        while (recentEvents.size() > MAX_EVENT_HISTORY) {
            recentEvents.poll();
        }

        String json = gson.toJson(event);

        for (WebSocket client : clients) {
            if (client.isOpen()) {
                client.send(json);
            }
        }
    }

    /**
     * Build complete game state JSON with enhanced player details.
     */
    private JsonObject buildGameState() {
        JsonObject state = new JsonObject();

        state.addProperty("type", "state");
        state.addProperty("timestamp", System.currentTimeMillis());

        // Basic game state
        state.addProperty("gameState", plugin.getRunManager().getGameState().name());
        state.addProperty("runId", plugin.getRunManager().getCurrentRunId());
        state.addProperty("runDuration", plugin.getRunManager().getRunDurationSeconds());
        state.addProperty("dragonAlive", plugin.getRunManager().isDragonAlive());

        // Dragon health
        state.addProperty("dragonHealth", getDragonHealth());

        // World info
        String worldName = plugin.getRunManager().getCurrentWorldName();
        state.addProperty("worldName", worldName);

        if (worldName != null) {
            World world = Bukkit.getWorld(worldName);
            if (world != null) {
                state.addProperty("worldSeed", world.getSeed());
                state.addProperty("weatherState", world.hasStorm() ? (world.isThundering() ? "thunder" : "rain") : "clear");
                state.addProperty("timeOfDay", world.getTime());
            }
        }

        // Player counts
        state.addProperty("lobbyPlayers", plugin.getWorldManager().getLobbyPlayerCount());
        state.addProperty("hardcorePlayers", plugin.getWorldManager().getHardcorePlayerCount());
        state.addProperty("totalPlayers", Bukkit.getOnlinePlayers().size());

        // Vote info (if in IDLE state)
        if (plugin.getRunManager().getGameState() == com.dragonrun.managers.GameState.IDLE) {
            state.addProperty("voteCount", plugin.getVoteManager().getVoteCount());
            state.addProperty("votesRequired", plugin.getVoteManager().getRequiredVotes());
        }

        // Detailed player states
        JsonArray players = new JsonArray();
        for (Player player : Bukkit.getOnlinePlayers()) {
            // Only filter by world if there's an active run
            if (worldName == null || player.getWorld().getName().equals(worldName)) {
                PlayerStateSnapshot snapshot = new PlayerStateSnapshot(player);

                // Enrich with data from other managers
                snapshot.setAura(plugin.getAuraManager().getAura(player.getUniqueId()));

                // Add achievement listener stats if available
                com.dragonrun.listeners.AchievementListener listener = plugin.getAchievementListener();
                if (listener != null) {
                    snapshot.setMobKills(listener.getRunMobKills(player.getUniqueId()));
                    snapshot.setAliveSeconds(listener.getAliveSeconds(player.getUniqueId()));
                    snapshot.setEnteredNether(listener.hasEnteredNether(player.getUniqueId()));
                    snapshot.setEnteredEnd(listener.hasEnteredEnd(player.getUniqueId()));
                }

                players.add(gson.toJsonTree(snapshot));
            }
        }
        state.add("players", players);

        // Recent events history
        JsonArray events = new JsonArray();
        for (JsonObject event : recentEvents) {
            events.add(event);
        }
        state.add("recentEvents", events);

        return state;
    }

    /**
     * Get current dragon health, or 0 if dragon is dead/not found.
     */
    private double getDragonHealth() {
        if (!plugin.getRunManager().isDragonAlive()) {
            return 0.0;
        }

        String worldName = plugin.getRunManager().getCurrentWorldName();
        if (worldName == null) return 0.0;

        World world = Bukkit.getWorld(worldName);
        if (world == null) return 0.0;

        World endWorld = Bukkit.getWorld(worldName + "_the_end");
        if (endWorld == null) return 0.0;

        DragonBattle battle = endWorld.getEnderDragonBattle();
        if (battle == null) return 0.0;

        EnderDragon dragon = battle.getEnderDragon();
        if (dragon == null || dragon.isDead()) return 0.0;

        return dragon.getHealth();
    }

    /**
     * Shutdown the WebSocket server gracefully.
     */
    public void shutdown() {
        try {
            plugin.getLogger().info("Shutting down Director WebSocket server...");
            stop(1000);
        } catch (InterruptedException e) {
            plugin.getLogger().warning("WebSocket shutdown interrupted: " + e.getMessage());
        }
    }

    /**
     * Get number of connected clients.
     */
    public int getClientCount() {
        return clients.size();
    }
}
