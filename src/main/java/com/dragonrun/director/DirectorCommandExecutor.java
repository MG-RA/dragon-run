package com.dragonrun.director;

import com.dragonrun.DragonRunPlugin;
import com.google.gson.JsonObject;
import org.bukkit.Bukkit;

import java.util.function.Consumer;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Executes director commands received via WebSocket.
 */
public class DirectorCommandExecutor {

    // Track how many commands are queued to spread them across ticks
    private static final AtomicInteger queuedCommands = new AtomicInteger(0);

    /**
     * Execute a command from the Director AI.
     * Commands are spread across multiple ticks to prevent server freezing.
     *
     * @param plugin The plugin instance
     * @param commandJson The command JSON from director
     * @param callback Callback with execution result
     */
    public static void execute(DragonRunPlugin plugin, JsonObject commandJson, Consumer<CommandResult> callback) {
        // Spread commands across ticks to prevent server freezing when Eris sends multiple actions
        // Each subsequent command gets a 1-tick delay (50ms)
        long delay = queuedCommands.getAndIncrement();

        // Run on main server thread for thread safety, but spread across ticks
        Bukkit.getScheduler().runTaskLater(plugin, () -> {
            // Decrement counter when command executes
            queuedCommands.decrementAndGet();
            try {
                String command = commandJson.get("command").getAsString();
                JsonObject params = commandJson.has("parameters")
                    ? commandJson.getAsJsonObject("parameters")
                    : new JsonObject();

                // Build the brigadier command string from the structured data
                String brigadierCommand = buildBrigadierCommand(command, params);

                if (brigadierCommand == null) {
                    plugin.getLogger().warning("[Director] Unknown command: " + command);
                    callback.accept(new CommandResult(false, "Unknown command: " + command));
                    return;
                }

                // Log the command being executed
                plugin.getLogger().info("[Director] Executing: " + brigadierCommand);
                plugin.getLogger().info("[Director] Parameters: " + params.toString());

                // Execute the command as console (with director permission)
                boolean success = Bukkit.dispatchCommand(Bukkit.getConsoleSender(), brigadierCommand);

                String resultMsg = success ? "SUCCESS" : "FAILED";
                plugin.getLogger().info("[Director] Command result: " + resultMsg);

                callback.accept(new CommandResult(success,
                    success ? "Command executed successfully" : "Command execution failed"));

            } catch (Exception e) {
                callback.accept(new CommandResult(false, "Error: " + e.getMessage()));
                plugin.getLogger().warning("Director command execution error: " + e.getMessage());
            }
        }, delay);
    }

    /**
     * Build a Brigadier command string from structured command data.
     */
    private static String buildBrigadierCommand(String command, JsonObject params) {
        return switch (command.toLowerCase()) {
            case "broadcast" -> {
                String message = params.get("message").getAsString();
                // greedyString takes all remaining text, no quotes needed
                yield "director broadcast " + message;
            }
            case "player_message", "message" -> {
                String player = params.get("player").getAsString();
                String message = params.get("message").getAsString();
                yield "director message " + player + " " + message;
            }
            case "spawn_mob", "spawn" -> {
                // Support both camelCase and snake_case
                String mobType = params.has("mobType")
                    ? params.get("mobType").getAsString()
                    : params.get("mob_type").getAsString();
                String nearPlayer = params.has("nearPlayer")
                    ? params.get("nearPlayer").getAsString()
                    : params.get("near_player").getAsString();
                int count = params.has("count") ? params.get("count").getAsInt() : 1;
                yield "director spawn mob " + mobType + " near " + nearPlayer + " " + count;
            }
            case "give_item", "give" -> {
                String player = params.get("player").getAsString();
                String item = params.get("item").getAsString();
                int count = params.has("count") ? params.get("count").getAsInt() : 1;
                yield "director give " + player + " " + item + " " + count;
            }
            case "apply_effect", "effect" -> {
                String player = params.get("player").getAsString();
                String effect = params.get("effect").getAsString();
                int duration = params.has("duration") ? params.get("duration").getAsInt() : 60;
                int amplifier = params.has("amplifier") ? params.get("amplifier").getAsInt() : 0;
                yield "director effect " + player + " " + effect + " " + duration + " " + amplifier;
            }
            case "lightning", "strike_lightning" -> {
                // Support both camelCase and snake_case, and direct "player" param
                String nearPlayer = params.has("nearPlayer")
                    ? params.get("nearPlayer").getAsString()
                    : params.has("near_player")
                        ? params.get("near_player").getAsString()
                        : params.get("player").getAsString();
                yield "director lightning near " + nearPlayer;
            }
            case "weather", "change_weather" -> {
                String weatherType = params.has("type")
                    ? params.get("type").getAsString()
                    : params.get("weather_type").getAsString();
                yield "director weather " + weatherType;
            }
            case "firework", "launch_firework" -> {
                // Support both camelCase and snake_case, and direct "player" param
                String nearPlayer = params.has("nearPlayer")
                    ? params.get("nearPlayer").getAsString()
                    : params.has("near_player")
                        ? params.get("near_player").getAsString()
                        : params.get("player").getAsString();
                int count = params.has("count") ? params.get("count").getAsInt() : 1;
                yield "director firework near " + nearPlayer + " " + count;
            }
            case "teleport", "tp", "teleport_player" -> {
                String player = params.get("player").getAsString();
                String mode = params.has("mode") ? params.get("mode").getAsString() : "random";
                if ("swap".equals(mode)) {
                    String target = params.get("target").getAsString();
                    yield "director tp swap " + player + " " + target;
                } else if ("isolate".equals(mode)) {
                    int distance = params.has("distance") ? params.get("distance").getAsInt() : 200;
                    yield "director tp isolate " + player + " " + distance;
                } else { // random
                    int radius = params.has("radius") ? params.get("radius").getAsInt() : 100;
                    yield "director tp random " + player + " " + radius;
                }
            }
            case "sound", "play_sound" -> {
                String sound = params.get("sound").getAsString();
                String target = params.has("target") ? params.get("target").getAsString() : "@a";
                float volume = params.has("volume") ? params.get("volume").getAsFloat() : 1.0f;
                float pitch = params.has("pitch") ? params.get("pitch").getAsFloat() : 1.0f;
                yield "director sound " + sound + " " + target + " " + volume + " " + pitch;
            }
            case "title", "show_title" -> {
                String player = params.get("player").getAsString();
                String titleText = params.has("title") ? params.get("title").getAsString() : "";
                String subtitleText = params.has("subtitle") ? params.get("subtitle").getAsString() : "";
                // Support both camelCase and snake_case
                int fadeIn = params.has("fadeIn") ? params.get("fadeIn").getAsInt()
                    : params.has("fade_in") ? params.get("fade_in").getAsInt() : 10;
                int stay = params.has("stay") ? params.get("stay").getAsInt() : 70;
                int fadeOut = params.has("fadeOut") ? params.get("fadeOut").getAsInt()
                    : params.has("fade_out") ? params.get("fade_out").getAsInt() : 20;
                yield "director title " + player + " " + fadeIn + " " + stay + " " + fadeOut + " " + titleText + " | " + subtitleText;
            }
            case "gamerule" -> {
                String rule = params.get("rule").getAsString();
                String value = params.get("value").getAsString();
                int duration = params.has("duration") ? params.get("duration").getAsInt() : 0; // 0 = permanent
                yield "director gamerule " + rule + " " + value + (duration > 0 ? " " + duration : "");
            }
            case "damage", "damage_player" -> {
                String player = params.get("player").getAsString();
                int amount = params.has("amount") ? params.get("amount").getAsInt() : 4; // 2 hearts
                yield "director damage " + player + " " + amount;
            }
            case "heal", "heal_player" -> {
                String player = params.get("player").getAsString();
                boolean full = params.has("full") ? params.get("full").getAsBoolean() : true;
                yield "director heal " + player + (full ? " full" : "");
            }
            case "aura", "modify_aura" -> {
                String player = params.get("player").getAsString();
                int amount = params.get("amount").getAsInt();
                String reason = params.get("reason").getAsString();
                yield "director aura " + player + " " + amount + " " + reason;
            }
            case "spawn_tnt" -> {
                // Support both camelCase and snake_case
                String nearPlayer = params.has("nearPlayer")
                    ? params.get("nearPlayer").getAsString()
                    : params.get("near_player").getAsString();
                int count = params.has("count") ? params.get("count").getAsInt() : 1;
                int fuseTicks = params.has("fuseTicks") ? params.get("fuseTicks").getAsInt()
                    : params.has("fuse_ticks") ? params.get("fuse_ticks").getAsInt() : 60;
                yield "director spawn tnt near " + nearPlayer + " " + count + " " + fuseTicks;
            }
            case "spawn_falling", "spawn_falling_block" -> {
                // Support both camelCase and snake_case
                String blockType = params.has("blockType")
                    ? params.get("blockType").getAsString()
                    : params.get("block_type").getAsString();
                String nearPlayer = params.has("nearPlayer")
                    ? params.get("nearPlayer").getAsString()
                    : params.get("near_player").getAsString();
                int count = params.has("count") ? params.get("count").getAsInt() : 1;
                int height = params.has("height") ? params.get("height").getAsInt() : 15;
                yield "director spawn falling " + blockType + " near " + nearPlayer + " " + count + " " + height;
            }
            case "lookat_position" -> {
                String player = params.get("player").getAsString();
                int x = params.get("x").getAsInt();
                int y = params.get("y").getAsInt();
                int z = params.get("z").getAsInt();
                yield "director lookat position " + player + " " + x + " " + y + " " + z;
            }
            case "lookat_entity" -> {
                String player = params.get("player").getAsString();
                String target = params.get("target").getAsString();
                yield "director lookat entity " + player + " " + target;
            }
            case "force_look_at" -> {
                // Handle force_look_at tool (maps to lookat position/entity)
                String player = params.get("player").getAsString();
                String mode = params.has("mode") ? params.get("mode").getAsString() : "position";
                if ("entity".equals(mode) && params.has("target")) {
                    String target = params.get("target").getAsString();
                    yield "director lookat entity " + player + " " + target;
                } else {
                    int x = params.has("x") ? params.get("x").getAsInt() : 0;
                    int y = params.has("y") ? params.get("y").getAsInt() : 64;
                    int z = params.has("z") ? params.get("z").getAsInt() : 0;
                    yield "director lookat position " + player + " " + x + " " + y + " " + z;
                }
            }
            case "spawn_particles" -> {
                String particle = params.get("particle").getAsString();
                // Support both camelCase and snake_case for nearPlayer
                String nearPlayer = params.has("nearPlayer")
                    ? params.get("nearPlayer").getAsString()
                    : params.get("near_player").getAsString();
                int count = params.has("count") ? params.get("count").getAsInt() : 20;
                double spread = params.has("spread") ? params.get("spread").getAsDouble() : 1.0;
                yield "director particles " + particle + " " + nearPlayer + " " + count + " " + spread;
            }
            case "fake_death" -> {
                String player = params.get("player").getAsString();
                String cause = params.has("cause") ? params.get("cause").getAsString() : "fell";
                yield "director fakedeath " + player + " " + cause;
            }
            // Divine Protection System commands
            case "protect", "protect_player" -> {
                String player = params.get("player").getAsString();
                // Support both camelCase and snake_case
                int auraCost = params.has("auraCost") ? params.get("auraCost").getAsInt()
                    : params.has("aura_cost") ? params.get("aura_cost").getAsInt() : 25;
                yield "director protect " + player + " " + auraCost;
            }
            case "rescue", "rescue_teleport" -> {
                String player = params.get("player").getAsString();
                // Support both camelCase and snake_case
                int auraCost = params.has("auraCost") ? params.get("auraCost").getAsInt()
                    : params.has("aura_cost") ? params.get("aura_cost").getAsInt() : 20;
                yield "director rescue " + player + " " + auraCost;
            }
            case "respawn", "respawn_override" -> {
                String player = params.get("player").getAsString();
                // Support both camelCase and snake_case
                int auraCost = params.has("auraCost") ? params.get("auraCost").getAsInt()
                    : params.has("aura_cost") ? params.get("aura_cost").getAsInt() : 50;
                yield "director respawn " + player + " " + auraCost;
            }
            default -> null;
        };
    }

    /**
     * Result of command execution.
     */
    public static class CommandResult {
        private final boolean success;
        private final String message;

        public CommandResult(boolean success, String message) {
            this.success = success;
            this.message = message;
        }

        public boolean success() {
            return success;
        }

        public String message() {
            return message;
        }
    }
}
