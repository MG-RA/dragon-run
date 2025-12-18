package com.dragonrun.websocket;

import com.dragonrun.DragonRunPlugin;
import com.google.gson.Gson;
import com.google.gson.JsonObject;
import org.java_websocket.WebSocket;
import org.java_websocket.handshake.ClientHandshake;
import org.java_websocket.server.WebSocketServer;

import java.net.InetSocketAddress;
import java.util.Set;
import java.util.concurrent.CopyOnWriteArraySet;

/**
 * WebSocket server for broadcasting game state to Director AI clients.
 * Runs on a separate port and broadcasts real-time game updates.
 */
public class DirectorWebSocketServer extends WebSocketServer {

    private final DragonRunPlugin plugin;
    private final Gson gson;
    private final Set<WebSocket> clients;

    public DirectorWebSocketServer(DragonRunPlugin plugin, int port) {
        super(new InetSocketAddress(port));
        this.plugin = plugin;
        this.gson = new Gson();
        this.clients = new CopyOnWriteArraySet<>();
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
        // Director AI can send commands here in the future
        plugin.getLogger().info("Received from Director AI: " + message);
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

        String json = gson.toJson(event);

        for (WebSocket client : clients) {
            if (client.isOpen()) {
                client.send(json);
            }
        }
    }

    /**
     * Build complete game state JSON.
     */
    private JsonObject buildGameState() {
        JsonObject state = new JsonObject();

        state.addProperty("type", "state");
        state.addProperty("timestamp", System.currentTimeMillis());

        // Game state
        state.addProperty("gameState", plugin.getRunManager().getGameState().name());
        state.addProperty("runId", plugin.getRunManager().getCurrentRunId());
        state.addProperty("runDuration", plugin.getRunManager().getRunDurationSeconds());
        state.addProperty("dragonAlive", plugin.getRunManager().isDragonAlive());

        // World info
        state.addProperty("worldName", plugin.getRunManager().getCurrentWorldName());

        // Player counts
        state.addProperty("lobbyPlayers", plugin.getWorldManager().getLobbyPlayerCount());
        state.addProperty("hardcorePlayers", plugin.getWorldManager().getHardcorePlayerCount());
        state.addProperty("totalPlayers", org.bukkit.Bukkit.getOnlinePlayers().size());

        // Vote info (if in IDLE state)
        if (plugin.getRunManager().getGameState() == com.dragonrun.managers.GameState.IDLE) {
            state.addProperty("voteCount", plugin.getVoteManager().getVoteCount());
            state.addProperty("votesRequired", plugin.getVoteManager().getRequiredVotes());
        }

        return state;
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
