package com.dragonrun.websocket;

import com.dragonrun.DragonRunPlugin;
import com.dragonrun.websocket.models.GameSnapshot;
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
import java.util.Map;
import java.util.Queue;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
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

    // Command journal for reliable command delivery
    private final Map<String, PendingCommand> commandJournal;
    private final long commandTtlMs;

    // State throttling
    private volatile long lastStateBroadcast = 0;
    private volatile int lastStateHash = 0;
    private final long minStateIntervalMs;

    /**
     * Represents a pending command in the journal.
     */
    private record PendingCommand(
        String commandId,
        JsonObject commandJson,
        long receivedAt,
        boolean acknowledged
    ) {
        PendingCommand withAcknowledged(boolean ack) {
            return new PendingCommand(commandId, commandJson, receivedAt, ack);
        }
    }

    public DirectorWebSocketServer(DragonRunPlugin plugin, int port) {
        super(new InetSocketAddress(port));
        this.plugin = plugin;
        this.gson = new Gson();
        this.clients = new CopyOnWriteArraySet<>();
        this.recentEvents = new LinkedBlockingQueue<>();
        this.commandJournal = new ConcurrentHashMap<>();

        // Load config values with defaults
        this.commandTtlMs = plugin.getConfig().getLong("director.command-journal-ttl-seconds", 60) * 1000L;
        this.minStateIntervalMs = plugin.getConfig().getLong("director.min-state-interval-ms", 1000);

        // Enable automatic ping/pong handling - responds to client pings
        // and detects dead connections. Value is in seconds (0 = disabled).
        setConnectionLostTimeout(30);
    }

    @Override
    public void onOpen(WebSocket conn, ClientHandshake handshake) {
        clients.add(conn);
        plugin.getLogger().info("Director AI client connected from " + conn.getRemoteSocketAddress());

        // Send initial state
        sendCurrentState(conn);

        // Replay unacknowledged commands from journal
        replayUnacknowledgedCommands(conn);
    }

    /**
     * Replay unacknowledged commands to a newly connected client.
     * This ensures commands survive reconnects.
     */
    private void replayUnacknowledgedCommands(WebSocket conn) {
        long now = System.currentTimeMillis();
        int replayed = 0;

        for (PendingCommand cmd : commandJournal.values()) {
            // Only replay if: not acknowledged AND within TTL
            if (!cmd.acknowledged() && (now - cmd.receivedAt()) < commandTtlMs) {
                JsonObject replay = new JsonObject();
                replay.addProperty("type", "command_replay");
                replay.addProperty("command_id", cmd.commandId());
                replay.add("original_command", cmd.commandJson());
                replay.addProperty("original_timestamp", cmd.receivedAt());

                if (conn.isOpen()) {
                    conn.send(gson.toJson(replay));
                    replayed++;
                }
            }
        }

        if (replayed > 0) {
            plugin.getLogger().info("Replayed " + replayed + " unacknowledged commands to reconnected client");
        }
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
        // Extract or generate command_id for correlation and journaling
        String commandId = commandJson.has("command_id")
            ? commandJson.get("command_id").getAsString()
            : "srv_" + UUID.randomUUID().toString().substring(0, 8);

        // Add to journal before execution
        long receivedAt = System.currentTimeMillis();
        commandJournal.put(commandId, new PendingCommand(commandId, commandJson, receivedAt, false));

        com.dragonrun.director.DirectorCommandExecutor.execute(plugin, commandJson, result -> {
            // Mark command as acknowledged in journal
            commandJournal.computeIfPresent(commandId, (k, v) -> v.withAcknowledged(true));

            // Send result back to director
            JsonObject response = new JsonObject();
            response.addProperty("type", "command_result");
            response.addProperty("success", result.success());
            response.addProperty("message", result.message());
            response.addProperty("timestamp", System.currentTimeMillis());
            response.addProperty("command_id", commandId);

            if (conn.isOpen()) {
                conn.send(gson.toJson(response));
            }

            // Log the command execution
            plugin.getLogger().info(String.format("Director command executed: %s - %s",
                result.success() ? "SUCCESS" : "FAILED",
                result.message()));

            // Schedule removal from journal after a short delay (let client process result)
            Bukkit.getScheduler().runTaskLater(plugin, () -> {
                commandJournal.remove(commandId);
            }, 100L); // 5 seconds
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
     * @deprecated Use captureSnapshot() on main thread, then broadcastSnapshot() on async thread.
     */
    @Deprecated
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
     * Capture a snapshot of the current game state.
     * MUST be called from the main server thread.
     *
     * @return Immutable game snapshot, or null if no clients connected
     */
    public GameSnapshot captureSnapshot() {
        if (clients.isEmpty()) return null;
        return GameSnapshot.capture(plugin, recentEvents);
    }

    /**
     * Broadcast a pre-captured game snapshot to all connected clients.
     * Safe to call from any thread (async recommended).
     * Includes throttling: skips broadcast if state unchanged and within min interval.
     *
     * @param snapshot The immutable game snapshot to broadcast
     */
    public void broadcastSnapshot(GameSnapshot snapshot) {
        if (snapshot == null || clients.isEmpty()) return;

        JsonObject state = snapshotToJson(snapshot);
        String json = gson.toJson(state);

        // State throttling: skip if unchanged and within interval
        long now = System.currentTimeMillis();
        int newHash = json.hashCode();

        if (newHash == lastStateHash && (now - lastStateBroadcast) < minStateIntervalMs) {
            return; // Skip - nothing changed
        }

        lastStateHash = newHash;
        lastStateBroadcast = now;

        for (WebSocket client : clients) {
            if (client.isOpen()) {
                client.send(json);
            }
        }
    }

    /**
     * Convert an immutable GameSnapshot to JSON for transmission.
     */
    private JsonObject snapshotToJson(GameSnapshot snapshot) {
        JsonObject state = new JsonObject();

        state.addProperty("type", "state");
        state.addProperty("timestamp", snapshot.timestamp());
        state.addProperty("gameState", snapshot.gameState());
        state.addProperty("runId", snapshot.runId());
        state.addProperty("runDuration", snapshot.runDuration());
        state.addProperty("dragonAlive", snapshot.dragonAlive());
        state.addProperty("dragonHealth", snapshot.dragonHealth());
        state.addProperty("worldName", snapshot.worldName());

        if (snapshot.worldSeed() != null) {
            state.addProperty("worldSeed", snapshot.worldSeed());
        }
        state.addProperty("weatherState", snapshot.weatherState());
        state.addProperty("timeOfDay", snapshot.timeOfDay());

        state.addProperty("lobbyPlayers", snapshot.lobbyPlayers());
        state.addProperty("hardcorePlayers", snapshot.hardcorePlayers());
        state.addProperty("totalPlayers", snapshot.totalPlayers());

        if (snapshot.voteCount() != null) {
            state.addProperty("voteCount", snapshot.voteCount());
        }
        if (snapshot.votesRequired() != null) {
            state.addProperty("votesRequired", snapshot.votesRequired());
        }

        // Players
        JsonArray players = new JsonArray();
        for (PlayerStateSnapshot player : snapshot.players()) {
            players.add(gson.toJsonTree(player));
        }
        state.add("players", players);

        // Recent events
        JsonArray events = new JsonArray();
        for (JsonObject event : snapshot.recentEvents()) {
            events.add(event);
        }
        state.add("recentEvents", events);

        return state;
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
            commandJournal.clear();
            stop(1000);
        } catch (InterruptedException e) {
            plugin.getLogger().warning("WebSocket shutdown interrupted: " + e.getMessage());
        }
    }

    /**
     * Clean up expired entries from the command journal.
     * Should be called periodically (e.g., every 30 seconds).
     */
    public void cleanupCommandJournal() {
        long now = System.currentTimeMillis();
        int removed = 0;

        var iterator = commandJournal.entrySet().iterator();
        while (iterator.hasNext()) {
            var entry = iterator.next();
            PendingCommand cmd = entry.getValue();

            // Remove if expired (regardless of acknowledged status)
            if ((now - cmd.receivedAt()) > commandTtlMs) {
                iterator.remove();
                removed++;
            }
        }

        if (removed > 0) {
            plugin.getLogger().fine("Cleaned up " + removed + " expired commands from journal");
        }
    }

    /**
     * Get number of connected clients.
     */
    public int getClientCount() {
        return clients.size();
    }

    /**
     * Get number of pending commands in journal.
     */
    public int getPendingCommandCount() {
        return (int) commandJournal.values().stream()
            .filter(cmd -> !cmd.acknowledged())
            .count();
    }
}
