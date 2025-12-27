package com.dragonrun.director;

import com.dragonrun.DragonRunPlugin;
import com.mojang.brigadier.arguments.IntegerArgumentType;
import com.mojang.brigadier.arguments.StringArgumentType;
import io.papermc.paper.command.brigadier.CommandSourceStack;
import io.papermc.paper.command.brigadier.Commands;
import net.kyori.adventure.key.Key;
import net.kyori.adventure.sound.Sound;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import net.kyori.adventure.text.minimessage.MiniMessage;
import org.bukkit.Bukkit;
import org.bukkit.Color;
import org.bukkit.FireworkEffect;
import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.NamespacedKey;
import org.bukkit.Registry;
import org.bukkit.World;
import org.bukkit.entity.EntityType;
import org.bukkit.entity.Firework;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.meta.FireworkMeta;
import org.bukkit.potion.PotionEffect;
import org.bukkit.potion.PotionEffectType;
import org.bukkit.Particle;

/**
 * Brigadier commands for the Director AI system.
 * These commands are executed by the Director AI via WebSocket.
 */
@SuppressWarnings("UnstableApiUsage")
public class DirectorCommands {

    private final DragonRunPlugin plugin;

    public DirectorCommands(DragonRunPlugin plugin) {
        this.plugin = plugin;
    }

    public void register(Commands commands) {
        // /director broadcast <message>
        commands.register(
            Commands.literal("director")
                .requires(source -> source.getSender().hasPermission("dragonrun.director"))
                .then(Commands.literal("broadcast")
                    .then(Commands.argument("message", StringArgumentType.greedyString())
                        .executes(ctx -> {
                            String message = StringArgumentType.getString(ctx, "message");
                            return executeBroadcast(ctx.getSource(), message);
                        })
                    )
                )
                .then(Commands.literal("message")
                    .then(Commands.argument("player", StringArgumentType.word())
                        .then(Commands.argument("message", StringArgumentType.greedyString())
                            .executes(ctx -> {
                                String playerName = StringArgumentType.getString(ctx, "player");
                                String message = StringArgumentType.getString(ctx, "message");
                                return executePlayerMessage(ctx.getSource(), playerName, message);
                            })
                        )
                    )
                )
                .then(Commands.literal("spawn")
                    .then(Commands.literal("mob")
                        .then(Commands.argument("type", StringArgumentType.word())
                            .then(Commands.literal("near")
                                .then(Commands.argument("player", StringArgumentType.word())
                                    .executes(ctx -> {
                                        String mobType = StringArgumentType.getString(ctx, "type");
                                        String playerName = StringArgumentType.getString(ctx, "player");
                                        return executeSpawnMob(ctx.getSource(), mobType, playerName, 1);
                                    })
                                    .then(Commands.argument("count", IntegerArgumentType.integer(1, 10))
                                        .executes(ctx -> {
                                            String mobType = StringArgumentType.getString(ctx, "type");
                                            String playerName = StringArgumentType.getString(ctx, "player");
                                            int count = IntegerArgumentType.getInteger(ctx, "count");
                                            return executeSpawnMob(ctx.getSource(), mobType, playerName, count);
                                        })
                                    )
                                )
                            )
                        )
                    )
                    .then(Commands.literal("tnt")
                        .then(Commands.literal("near")
                            .then(Commands.argument("player", StringArgumentType.word())
                                .executes(ctx -> {
                                    String playerName = StringArgumentType.getString(ctx, "player");
                                    return executeSpawnTNT(ctx.getSource(), playerName, 1, 60);
                                })
                                .then(Commands.argument("count", IntegerArgumentType.integer(1, 5))
                                    .executes(ctx -> {
                                        String playerName = StringArgumentType.getString(ctx, "player");
                                        int count = IntegerArgumentType.getInteger(ctx, "count");
                                        return executeSpawnTNT(ctx.getSource(), playerName, count, 60);
                                    })
                                    .then(Commands.argument("fuseTicks", IntegerArgumentType.integer(20, 100))
                                        .executes(ctx -> {
                                            String playerName = StringArgumentType.getString(ctx, "player");
                                            int count = IntegerArgumentType.getInteger(ctx, "count");
                                            int fuseTicks = IntegerArgumentType.getInteger(ctx, "fuseTicks");
                                            return executeSpawnTNT(ctx.getSource(), playerName, count, fuseTicks);
                                        })
                                    )
                                )
                            )
                        )
                    )
                    .then(Commands.literal("falling")
                        .then(Commands.argument("blockType", StringArgumentType.word())
                            .suggests((ctx, builder) -> {
                                builder.suggest("anvil");
                                builder.suggest("pointed_dripstone");
                                builder.suggest("sand");
                                builder.suggest("gravel");
                                builder.suggest("concrete_powder");
                                return builder.buildFuture();
                            })
                            .then(Commands.literal("near")
                                .then(Commands.argument("player", StringArgumentType.word())
                                    .executes(ctx -> {
                                        String blockType = StringArgumentType.getString(ctx, "blockType");
                                        String playerName = StringArgumentType.getString(ctx, "player");
                                        return executeSpawnFallingBlock(ctx.getSource(), blockType, playerName, 1, 15);
                                    })
                                    .then(Commands.argument("count", IntegerArgumentType.integer(1, 8))
                                        .executes(ctx -> {
                                            String blockType = StringArgumentType.getString(ctx, "blockType");
                                            String playerName = StringArgumentType.getString(ctx, "player");
                                            int count = IntegerArgumentType.getInteger(ctx, "count");
                                            return executeSpawnFallingBlock(ctx.getSource(), blockType, playerName, count, 15);
                                        })
                                        .then(Commands.argument("height", IntegerArgumentType.integer(5, 30))
                                            .executes(ctx -> {
                                                String blockType = StringArgumentType.getString(ctx, "blockType");
                                                String playerName = StringArgumentType.getString(ctx, "player");
                                                int count = IntegerArgumentType.getInteger(ctx, "count");
                                                int height = IntegerArgumentType.getInteger(ctx, "height");
                                                return executeSpawnFallingBlock(ctx.getSource(), blockType, playerName, count, height);
                                            })
                                        )
                                    )
                                )
                            )
                        )
                    )
                )
                .then(Commands.literal("give")
                    .then(Commands.argument("player", StringArgumentType.word())
                        .then(Commands.argument("item", StringArgumentType.word())
                            .executes(ctx -> {
                                String playerName = StringArgumentType.getString(ctx, "player");
                                String item = StringArgumentType.getString(ctx, "item");
                                return executeGiveItem(ctx.getSource(), playerName, item, 1);
                            })
                            .then(Commands.argument("count", IntegerArgumentType.integer(1, 64))
                                .executes(ctx -> {
                                    String playerName = StringArgumentType.getString(ctx, "player");
                                    String item = StringArgumentType.getString(ctx, "item");
                                    int count = IntegerArgumentType.getInteger(ctx, "count");
                                    return executeGiveItem(ctx.getSource(), playerName, item, count);
                                })
                            )
                        )
                    )
                )
                .then(Commands.literal("effect")
                    .then(Commands.argument("player", StringArgumentType.word())
                        .then(Commands.argument("effect", StringArgumentType.word())
                            .executes(ctx -> {
                                String playerName = StringArgumentType.getString(ctx, "player");
                                String effect = StringArgumentType.getString(ctx, "effect");
                                return executeApplyEffect(ctx.getSource(), playerName, effect, 60, 0);
                            })
                            .then(Commands.argument("duration", IntegerArgumentType.integer(1, 600))
                                .executes(ctx -> {
                                    String playerName = StringArgumentType.getString(ctx, "player");
                                    String effect = StringArgumentType.getString(ctx, "effect");
                                    int duration = IntegerArgumentType.getInteger(ctx, "duration");
                                    return executeApplyEffect(ctx.getSource(), playerName, effect, duration, 0);
                                })
                                .then(Commands.argument("amplifier", IntegerArgumentType.integer(0, 5))
                                    .executes(ctx -> {
                                        String playerName = StringArgumentType.getString(ctx, "player");
                                        String effect = StringArgumentType.getString(ctx, "effect");
                                        int duration = IntegerArgumentType.getInteger(ctx, "duration");
                                        int amplifier = IntegerArgumentType.getInteger(ctx, "amplifier");
                                        return executeApplyEffect(ctx.getSource(), playerName, effect, duration, amplifier);
                                    })
                                )
                            )
                        )
                    )
                )
                .then(Commands.literal("lightning")
                    .then(Commands.literal("near")
                        .then(Commands.argument("player", StringArgumentType.word())
                            .executes(ctx -> {
                                String playerName = StringArgumentType.getString(ctx, "player");
                                return executeLightning(ctx.getSource(), playerName);
                            })
                        )
                    )
                )
                .then(Commands.literal("weather")
                    .then(Commands.argument("type", StringArgumentType.word())
                        .suggests((ctx, builder) -> {
                            builder.suggest("clear");
                            builder.suggest("rain");
                            builder.suggest("thunder");
                            return builder.buildFuture();
                        })
                        .executes(ctx -> {
                            String weatherType = StringArgumentType.getString(ctx, "type");
                            return executeWeather(ctx.getSource(), weatherType);
                        })
                    )
                )
                .then(Commands.literal("firework")
                    .then(Commands.literal("near")
                        .then(Commands.argument("player", StringArgumentType.word())
                            .executes(ctx -> {
                                String playerName = StringArgumentType.getString(ctx, "player");
                                return executeFirework(ctx.getSource(), playerName, 1);
                            })
                            .then(Commands.argument("count", IntegerArgumentType.integer(1, 5))
                                .executes(ctx -> {
                                    String playerName = StringArgumentType.getString(ctx, "player");
                                    int count = IntegerArgumentType.getInteger(ctx, "count");
                                    return executeFirework(ctx.getSource(), playerName, count);
                                })
                            )
                        )
                    )
                )
                .then(Commands.literal("sound")
                    .then(Commands.argument("sound", StringArgumentType.greedyString())
                        .executes(ctx -> {
                            String soundStr = StringArgumentType.getString(ctx, "sound");
                            String[] parts = soundStr.split(" ");
                            String sound = parts[0];
                            String target = parts.length > 1 ? parts[1] : "@a";
                            float volume = parts.length > 2 ? Float.parseFloat(parts[2]) : 1.0f;
                            float pitch = parts.length > 3 ? Float.parseFloat(parts[3]) : 1.0f;
                            return executePlaySound(ctx.getSource(), sound, target, volume, pitch);
                        })
                    )
                )
                .then(Commands.literal("title")
                    .then(Commands.argument("titleArgs", StringArgumentType.greedyString())
                        .executes(ctx -> {
                            String args = StringArgumentType.getString(ctx, "titleArgs");
                            // Format: player fadeIn stay fadeOut titleText|||subtitleText
                            // First split by space with limit 5 to get player and timing params
                            String[] parts = args.split(" ", 5);
                            String player = parts[0];
                            int fadeIn = Integer.parseInt(parts[1]);
                            int stay = Integer.parseInt(parts[2]);
                            int fadeOut = Integer.parseInt(parts[3]);
                            // The rest contains "titleText|||subtitleText"
                            String textPart = parts.length > 4 ? parts[4] : "|||";
                            String[] texts = textPart.split("\\|\\|\\|", 2);
                            String title = texts.length > 0 ? texts[0] : "";
                            String subtitle = texts.length > 1 ? texts[1] : "";
                            return executeShowTitle(ctx.getSource(), player, title, subtitle, fadeIn, stay, fadeOut);
                        })
                    )
                )
                .then(Commands.literal("tp")
                    .then(Commands.literal("random")
                        .then(Commands.argument("player", StringArgumentType.word())
                            .then(Commands.argument("radius", IntegerArgumentType.integer(10, 500))
                                .executes(ctx -> {
                                    String player = StringArgumentType.getString(ctx, "player");
                                    int radius = IntegerArgumentType.getInteger(ctx, "radius");
                                    return executeTeleportRandom(ctx.getSource(), player, radius);
                                })
                            )
                        )
                    )
                    .then(Commands.literal("swap")
                        .then(Commands.argument("player1", StringArgumentType.word())
                            .then(Commands.argument("player2", StringArgumentType.word())
                                .executes(ctx -> {
                                    String p1 = StringArgumentType.getString(ctx, "player1");
                                    String p2 = StringArgumentType.getString(ctx, "player2");
                                    return executeTeleportSwap(ctx.getSource(), p1, p2);
                                })
                            )
                        )
                    )
                    .then(Commands.literal("isolate")
                        .then(Commands.argument("player", StringArgumentType.word())
                            .then(Commands.argument("distance", IntegerArgumentType.integer(50, 1000))
                                .executes(ctx -> {
                                    String player = StringArgumentType.getString(ctx, "player");
                                    int distance = IntegerArgumentType.getInteger(ctx, "distance");
                                    return executeTeleportIsolate(ctx.getSource(), player, distance);
                                })
                            )
                        )
                    )
                )
                .then(Commands.literal("damage")
                    .then(Commands.argument("player", StringArgumentType.word())
                        .then(Commands.argument("amount", IntegerArgumentType.integer(1, 10))
                            .executes(ctx -> {
                                String player = StringArgumentType.getString(ctx, "player");
                                int amount = IntegerArgumentType.getInteger(ctx, "amount");
                                return executeDamage(ctx.getSource(), player, amount);
                            })
                        )
                    )
                )
                .then(Commands.literal("heal")
                    .then(Commands.argument("player", StringArgumentType.word())
                        .executes(ctx -> {
                            String player = StringArgumentType.getString(ctx, "player");
                            return executeHeal(ctx.getSource(), player, false);
                        })
                        .then(Commands.literal("full")
                            .executes(ctx -> {
                                String player = StringArgumentType.getString(ctx, "player");
                                return executeHeal(ctx.getSource(), player, true);
                            })
                        )
                    )
                )
                .then(Commands.literal("aura")
                    .then(Commands.argument("player", StringArgumentType.word())
                        .then(Commands.argument("amount", IntegerArgumentType.integer(-100, 100))
                            .then(Commands.argument("reason", StringArgumentType.greedyString())
                                .executes(ctx -> {
                                    String player = StringArgumentType.getString(ctx, "player");
                                    int amount = IntegerArgumentType.getInteger(ctx, "amount");
                                    String reason = StringArgumentType.getString(ctx, "reason");
                                    return executeAuraModify(ctx.getSource(), player, amount, reason);
                                })
                            )
                        )
                    )
                )
                .then(Commands.literal("lookat")
                    .then(Commands.literal("position")
                        .then(Commands.argument("player", StringArgumentType.word())
                            .then(Commands.argument("x", IntegerArgumentType.integer())
                                .then(Commands.argument("y", IntegerArgumentType.integer())
                                    .then(Commands.argument("z", IntegerArgumentType.integer())
                                        .executes(ctx -> {
                                            String player = StringArgumentType.getString(ctx, "player");
                                            int x = IntegerArgumentType.getInteger(ctx, "x");
                                            int y = IntegerArgumentType.getInteger(ctx, "y");
                                            int z = IntegerArgumentType.getInteger(ctx, "z");
                                            return executeLookAtPosition(ctx.getSource(), player, x, y, z);
                                        })
                                    )
                                )
                            )
                        )
                    )
                    .then(Commands.literal("entity")
                        .then(Commands.argument("player", StringArgumentType.word())
                            .then(Commands.argument("target", StringArgumentType.word())
                                .executes(ctx -> {
                                    String player = StringArgumentType.getString(ctx, "player");
                                    String target = StringArgumentType.getString(ctx, "target");
                                    return executeLookAtEntity(ctx.getSource(), player, target);
                                })
                            )
                        )
                    )
                )
                .then(Commands.literal("particles")
                    .then(Commands.argument("particleArgs", StringArgumentType.greedyString())
                        .executes(ctx -> {
                            String args = StringArgumentType.getString(ctx, "particleArgs");
                            String[] parts = args.split(" ");
                            String particle = parts[0];
                            String nearPlayer = parts[1];
                            int count = parts.length > 2 ? Integer.parseInt(parts[2]) : 20;
                            double spread = parts.length > 3 ? Double.parseDouble(parts[3]) : 1.0;
                            return executeSpawnParticles(ctx.getSource(), particle, nearPlayer, count, spread);
                        })
                    )
                )
                .then(Commands.literal("fakedeath")
                    .then(Commands.argument("player", StringArgumentType.word())
                        .then(Commands.argument("cause", StringArgumentType.word())
                            .executes(ctx -> {
                                String player = StringArgumentType.getString(ctx, "player");
                                String cause = StringArgumentType.getString(ctx, "cause");
                                return executeFakeDeath(ctx.getSource(), player, cause);
                            })
                        )
                    )
                )
                .then(Commands.literal("protect")
                    .then(Commands.argument("player", StringArgumentType.word())
                        .executes(ctx -> {
                            String player = StringArgumentType.getString(ctx, "player");
                            return executeProtect(ctx.getSource(), player, 25);
                        })
                        .then(Commands.argument("auraCost", IntegerArgumentType.integer(10, 100))
                            .executes(ctx -> {
                                String player = StringArgumentType.getString(ctx, "player");
                                int auraCost = IntegerArgumentType.getInteger(ctx, "auraCost");
                                return executeProtect(ctx.getSource(), player, auraCost);
                            })
                        )
                    )
                )
                .then(Commands.literal("rescue")
                    .then(Commands.argument("player", StringArgumentType.word())
                        .executes(ctx -> {
                            String player = StringArgumentType.getString(ctx, "player");
                            return executeRescueTeleport(ctx.getSource(), player, 20);
                        })
                        .then(Commands.argument("auraCost", IntegerArgumentType.integer(10, 50))
                            .executes(ctx -> {
                                String player = StringArgumentType.getString(ctx, "player");
                                int auraCost = IntegerArgumentType.getInteger(ctx, "auraCost");
                                return executeRescueTeleport(ctx.getSource(), player, auraCost);
                            })
                        )
                    )
                )
                .then(Commands.literal("respawn")
                    .then(Commands.argument("player", StringArgumentType.word())
                        .executes(ctx -> {
                            String player = StringArgumentType.getString(ctx, "player");
                            return executeRespawnOverride(ctx.getSource(), player, 50);
                        })
                        .then(Commands.argument("auraCost", IntegerArgumentType.integer(25, 200))
                            .executes(ctx -> {
                                String player = StringArgumentType.getString(ctx, "player");
                                int auraCost = IntegerArgumentType.getInteger(ctx, "auraCost");
                                return executeRespawnOverride(ctx.getSource(), player, auraCost);
                            })
                        )
                    )
                )
                .then(Commands.literal("debug")
                    .requires(source -> source.getSender().hasPermission("dragonrun.admin"))
                    .then(Commands.literal("apocalypse")
                        .executes(ctx -> {
                            return executeDebugApocalypse(ctx.getSource());
                        })
                    )
                    .then(Commands.literal("fracture")
                        .then(Commands.argument("level", IntegerArgumentType.integer(0, 300))
                            .executes(ctx -> {
                                int level = IntegerArgumentType.getInteger(ctx, "level");
                                return executeDebugSetFracture(ctx.getSource(), level);
                            })
                        )
                    )
                )
                .build(),
            "Director AI commands",
            java.util.List.of()
        );
    }

    private int executeBroadcast(CommandSourceStack source, String message) {
        // Parse MiniMessage formatting tags
        MiniMessage miniMessage = MiniMessage.miniMessage();
        Component messageComponent = miniMessage.deserialize(message);

        Component broadcastMessage = Component.text("[Eris] ", NamedTextColor.LIGHT_PURPLE)
            .append(messageComponent);

        Bukkit.broadcast(broadcastMessage);
        return 1;
    }

    private int executePlayerMessage(CommandSourceStack source, String playerName, String message) {
        Player player = Bukkit.getPlayer(playerName);
        if (player == null) {
            source.getSender().sendMessage(Component.text("Player not found: " + playerName, NamedTextColor.RED));
            return 0;
        }

        // Parse MiniMessage formatting tags
        MiniMessage miniMessage = MiniMessage.miniMessage();
        Component messageComponent = miniMessage.deserialize(message);

        Component playerMessage = Component.text("[Eris] ", NamedTextColor.LIGHT_PURPLE)
            .append(messageComponent);

        player.sendMessage(playerMessage);
        return 1;
    }

    private int executeSpawnMob(CommandSourceStack source, String mobType, String playerName, int count) {
        Player player = Bukkit.getPlayer(playerName);
        if (player == null) {
            source.getSender().sendMessage(Component.text("Player not found: " + playerName, NamedTextColor.RED));
            return 0;
        }

        EntityType entityType;
        try {
            entityType = EntityType.valueOf(mobType.toUpperCase());
        } catch (IllegalArgumentException e) {
            source.getSender().sendMessage(Component.text("Invalid mob type: " + mobType, NamedTextColor.RED));
            return 0;
        }

        if (!entityType.isSpawnable() || !entityType.isAlive()) {
            source.getSender().sendMessage(Component.text("Cannot spawn " + mobType, NamedTextColor.RED));
            return 0;
        }

        // Calculate random offset position
        double offsetX = (Math.random() - 0.5) * 10;
        double offsetZ = (Math.random() - 0.5) * 10;
        Location baseLoc = player.getLocation().add(offsetX, 0, offsetZ);

        for (int i = 0; i < count; i++) {
            // Find safe spawn location (not inside blocks)
            Location spawnLoc = findSafeSpawnLocation(baseLoc);
            if (spawnLoc != null) {
                org.bukkit.entity.Entity spawned = player.getWorld().spawnEntity(spawnLoc, entityType);
                // Register with CausalityManager for divine protection system
                plugin.getCausalityManager().registerErisMob(spawned, player.getUniqueId(), mobType);
            }
        }

        source.getSender().sendMessage(Component.text("Spawned " + count + " " + mobType + " near " + playerName, NamedTextColor.GREEN));
        return 1;
    }

    private int executeGiveItem(CommandSourceStack source, String playerName, String itemName, int count) {
        Player player = Bukkit.getPlayer(playerName);
        if (player == null) {
            source.getSender().sendMessage(Component.text("Player not found: " + playerName, NamedTextColor.RED));
            return 0;
        }

        Material material;
        try {
            material = Material.valueOf(itemName.toUpperCase());
        } catch (IllegalArgumentException e) {
            source.getSender().sendMessage(Component.text("Invalid item: " + itemName, NamedTextColor.RED));
            return 0;
        }

        if (!material.isItem()) {
            source.getSender().sendMessage(Component.text("Cannot give " + itemName, NamedTextColor.RED));
            return 0;
        }

        ItemStack item = new ItemStack(material, count);
        player.getInventory().addItem(item);

        source.getSender().sendMessage(Component.text("Gave " + count + " " + itemName + " to " + playerName, NamedTextColor.GREEN));
        return 1;
    }

    private int executeApplyEffect(CommandSourceStack source, String playerName, String effectName, int duration, int amplifier) {
        Player player = Bukkit.getPlayer(playerName);
        if (player == null) {
            source.getSender().sendMessage(Component.text("Player not found: " + playerName, NamedTextColor.RED));
            return 0;
        }

        // Try to get effect type from registry
        NamespacedKey key = NamespacedKey.minecraft(effectName.toLowerCase());
        PotionEffectType effectType = Registry.EFFECT.get(key);

        if (effectType == null) {
            source.getSender().sendMessage(Component.text("Invalid effect: " + effectName, NamedTextColor.RED));
            return 0;
        }

        PotionEffect effect = new PotionEffect(effectType, duration * 20, amplifier);
        player.addPotionEffect(effect);

        // Register harmful effects with CausalityManager for divine protection system
        if (isHarmfulEffect(effectName)) {
            plugin.getCausalityManager().registerErisEffect(player.getUniqueId(), effectName);
        }

        source.getSender().sendMessage(Component.text("Applied " + effectName + " to " + playerName, NamedTextColor.GREEN));
        return 1;
    }

    private boolean isHarmfulEffect(String effectName) {
        String lower = effectName.toLowerCase();
        return lower.equals("poison") || lower.equals("wither") || lower.equals("harm") ||
               lower.equals("slowness") || lower.equals("weakness") || lower.equals("hunger") ||
               lower.equals("mining_fatigue") || lower.equals("blindness") || lower.equals("nausea");
    }

    private int executeLightning(CommandSourceStack source, String playerName) {
        Player player = Bukkit.getPlayer(playerName);
        if (player == null) {
            source.getSender().sendMessage(Component.text("Player not found: " + playerName, NamedTextColor.RED));
            return 0;
        }

        // Lightning has only ~20% chance to be close (within 5 blocks)
        // Otherwise strikes in a much wider area (up to 20 blocks away)
        double radius;
        if (Math.random() < 0.2) {
            // 20% chance: Close strike (2-5 blocks) - scary but rarely hits
            radius = 2 + Math.random() * 3;
        } else {
            // 80% chance: Far strike (8-20 blocks) - dramatic but safe
            radius = 8 + Math.random() * 12;
        }

        // Random angle for more variation
        double angle = Math.random() * 2 * Math.PI;
        double offsetX = Math.cos(angle) * radius;
        double offsetZ = Math.sin(angle) * radius;

        Location strikeLoc = player.getLocation().add(offsetX, 0, offsetZ);
        player.getWorld().strikeLightning(strikeLoc);

        // Register lightning with CausalityManager for divine protection system
        plugin.getCausalityManager().registerErisLightning(strikeLoc, player.getUniqueId());

        source.getSender().sendMessage(Component.text("Lightning struck near " + playerName, NamedTextColor.GREEN));
        return 1;
    }

    private int executeWeather(CommandSourceStack source, String weatherType) {
        String worldName = plugin.getRunManager().getCurrentWorldName();

        // If no active run, use lobby world instead
        if (worldName == null) {
            worldName = "world_lobby";
        }

        World world = Bukkit.getWorld(worldName);
        if (world == null) {
            source.getSender().sendMessage(Component.text("World not found: " + worldName, NamedTextColor.RED));
            return 0;
        }

        int duration = 0;
        switch (weatherType.toLowerCase()) {
            case "clear":
                world.setStorm(false);
                world.setThundering(false);
                world.setWeatherDuration(0); // Clear indefinitely
                break;
            case "rain":
                world.setStorm(true);
                world.setThundering(false);
                // Rain lasts 30-90 seconds (600-1800 ticks)
                duration = 600 + (int)(Math.random() * 1200);
                world.setWeatherDuration(duration);
                break;
            case "thunder":
                world.setStorm(true);
                world.setThundering(true);
                // Thunder lasts 20-60 seconds (400-1200 ticks) - shorter and more dramatic
                duration = 400 + (int)(Math.random() * 800);
                world.setWeatherDuration(duration);
                world.setThunderDuration(duration);
                break;
            default:
                source.getSender().sendMessage(Component.text("Invalid weather type: " + weatherType, NamedTextColor.RED));
                return 0;
        }

        if (duration > 0) {
            int seconds = duration / 20;
            source.getSender().sendMessage(Component.text("Weather set to " + weatherType + " for " + seconds + " seconds", NamedTextColor.GREEN));
        } else {
            source.getSender().sendMessage(Component.text("Weather set to " + weatherType, NamedTextColor.GREEN));
        }
        return 1;
    }

    private int executeFirework(CommandSourceStack source, String playerName, int count) {
        Player player = Bukkit.getPlayer(playerName);
        if (player == null) {
            source.getSender().sendMessage(Component.text("Player not found: " + playerName, NamedTextColor.RED));
            return 0;
        }

        Color[] colors = {Color.RED, Color.GREEN, Color.BLUE, Color.YELLOW, Color.PURPLE, Color.AQUA, Color.WHITE};
        FireworkEffect.Type[] types = {FireworkEffect.Type.BALL, FireworkEffect.Type.BALL_LARGE, FireworkEffect.Type.STAR, FireworkEffect.Type.BURST};

        for (int i = 0; i < count; i++) {
            Location loc = player.getLocation().add(
                (Math.random() - 0.5) * 8,
                2,
                (Math.random() - 0.5) * 8
            );

            Firework fw = player.getWorld().spawn(loc, Firework.class);
            FireworkMeta meta = fw.getFireworkMeta();

            Color primary = colors[(int) (Math.random() * colors.length)];
            Color fade = colors[(int) (Math.random() * colors.length)];
            FireworkEffect.Type type = types[(int) (Math.random() * types.length)];

            FireworkEffect effect = FireworkEffect.builder()
                .with(type)
                .withColor(primary)
                .withFade(fade)
                .trail(Math.random() > 0.5)
                .flicker(Math.random() > 0.5)
                .build();

            meta.addEffect(effect);
            meta.setPower(1 + (int) (Math.random() * 2));
            fw.setFireworkMeta(meta);
        }

        source.getSender().sendMessage(Component.text("Spawned " + count + " fireworks near " + playerName, NamedTextColor.GREEN));
        return 1;
    }

    // ==================== NEW CINEMATIC COMMANDS ====================

    private int executeTeleportRandom(CommandSourceStack source, String playerName, int radius) {
        Player player = Bukkit.getPlayer(playerName);
        if (player == null) {
            source.getSender().sendMessage(Component.text("Player not found: " + playerName, NamedTextColor.RED));
            return 0;
        }

        org.bukkit.Location current = player.getLocation();
        org.bukkit.World world = current.getWorld();

        // Find random safe location
        for (int attempts = 0; attempts < 10; attempts++) {
            double angle = Math.random() * 2 * Math.PI;
            double distance = Math.random() * radius;
            double x = current.getX() + Math.cos(angle) * distance;
            double z = current.getZ() + Math.sin(angle) * distance;

            org.bukkit.Location target = new org.bukkit.Location(world, x, world.getHighestBlockYAt((int)x, (int)z) + 1, z);
            if (target.getBlock().getType() == org.bukkit.Material.AIR) {
                player.teleport(target);
                source.getSender().sendMessage(Component.text("Teleported " + playerName + " randomly", NamedTextColor.GREEN));
                return 1;
            }
        }

        source.getSender().sendMessage(Component.text("Failed to find safe location", NamedTextColor.RED));
        return 0;
    }

    private int executeTeleportSwap(CommandSourceStack source, String player1Name, String player2Name) {
        Player p1 = Bukkit.getPlayer(player1Name);
        Player p2 = Bukkit.getPlayer(player2Name);

        if (p1 == null || p2 == null) {
            source.getSender().sendMessage(Component.text("One or both players not found", NamedTextColor.RED));
            return 0;
        }

        org.bukkit.Location loc1 = p1.getLocation().clone();
        org.bukkit.Location loc2 = p2.getLocation().clone();

        p1.teleport(loc2);
        p2.teleport(loc1);

        source.getSender().sendMessage(Component.text("Swapped " + player1Name + " and " + player2Name, NamedTextColor.GREEN));
        return 1;
    }

    private int executeTeleportIsolate(CommandSourceStack source, String playerName, int distance) {
        Player player = Bukkit.getPlayer(playerName);
        if (player == null) {
            source.getSender().sendMessage(Component.text("Player not found: " + playerName, NamedTextColor.RED));
            return 0;
        }

        org.bukkit.Location current = player.getLocation();
        double angle = Math.random() * 2 * Math.PI;
        double x = current.getX() + Math.cos(angle) * distance;
        double z = current.getZ() + Math.sin(angle) * distance;

        org.bukkit.Location target = new org.bukkit.Location(current.getWorld(), x,
            current.getWorld().getHighestBlockYAt((int)x, (int)z) + 1, z);

        player.teleport(target);
        source.getSender().sendMessage(Component.text("Isolated " + playerName + " " + distance + " blocks away", NamedTextColor.GREEN));
        return 1;
    }

    private int executePlaySound(CommandSourceStack source, String sound, String target, float volume, float pitch) {
        // Parse sound key - handle both "minecraft:sound" and "sound" formats
        Key soundKey;
        if (sound.contains(":")) {
            soundKey = Key.key(sound);
        } else {
            soundKey = Key.key("minecraft", sound);
        }

        // Create Adventure Sound with proper volume and pitch
        Sound adventureSound = Sound.sound(soundKey, Sound.Source.MASTER, volume, pitch);

        if ("@a".equals(target)) {
            for (Player player : Bukkit.getOnlinePlayers()) {
                player.playSound(adventureSound, player.getLocation().x(), player.getLocation().y(), player.getLocation().z());
            }
            source.getSender().sendMessage(Component.text("Played sound to all players", NamedTextColor.GREEN));
        } else {
            Player player = Bukkit.getPlayer(target);
            if (player == null) {
                source.getSender().sendMessage(Component.text("Player not found: " + target, NamedTextColor.RED));
                return 0;
            }
            player.playSound(adventureSound, player.getLocation().x(), player.getLocation().y(), player.getLocation().z());
            source.getSender().sendMessage(Component.text("Played sound to " + target, NamedTextColor.GREEN));
        }
        return 1;
    }

    private int executeShowTitle(CommandSourceStack source, String playerName, String titleText, String subtitleText, int fadeIn, int stay, int fadeOut) {
        Player player = Bukkit.getPlayer(playerName);
        if (player == null) {
            source.getSender().sendMessage(Component.text("Player not found: " + playerName, NamedTextColor.RED));
            return 0;
        }

        // Parse MiniMessage formatting for both title and subtitle
        MiniMessage miniMessage = MiniMessage.miniMessage();
        Component title = titleText.isEmpty() ? Component.empty() : miniMessage.deserialize(titleText);
        Component subtitle = subtitleText.isEmpty() ? Component.empty() : miniMessage.deserialize(subtitleText);

        player.showTitle(net.kyori.adventure.title.Title.title(
            title,
            subtitle,
            net.kyori.adventure.title.Title.Times.times(
                java.time.Duration.ofMillis(fadeIn * 50),
                java.time.Duration.ofMillis(stay * 50),
                java.time.Duration.ofMillis(fadeOut * 50)
            )
        ));

        source.getSender().sendMessage(Component.text("Showed title to " + playerName, NamedTextColor.GREEN));
        return 1;
    }

    private int executeDamage(CommandSourceStack source, String playerName, int amount) {
        Player player = Bukkit.getPlayer(playerName);
        if (player == null) {
            source.getSender().sendMessage(Component.text("Player not found: " + playerName, NamedTextColor.RED));
            return 0;
        }

        // Don't kill the player - cap damage
        double maxDamage = player.getHealth() - 1.0;
        double actualDamage = Math.min(amount, maxDamage);

        if (actualDamage > 0) {
            player.damage(actualDamage);
            source.getSender().sendMessage(Component.text("Damaged " + playerName + " for " + actualDamage + " hearts", NamedTextColor.GREEN));
        } else {
            source.getSender().sendMessage(Component.text(playerName + " is too low health to damage safely", NamedTextColor.YELLOW));
        }

        return 1;
    }

    private int executeHeal(CommandSourceStack source, String playerName, boolean full) {
        Player player = Bukkit.getPlayer(playerName);
        if (player == null) {
            source.getSender().sendMessage(Component.text("Player not found: " + playerName, NamedTextColor.RED));
            return 0;
        }

        if (full) {
            player.setHealth(player.getMaxHealth());
            player.setFoodLevel(20);
            player.setSaturation(20.0f);
            source.getSender().sendMessage(Component.text("Fully healed " + playerName, NamedTextColor.GREEN));
        } else {
            player.setHealth(Math.min(player.getHealth() + 6.0, player.getMaxHealth()));
            source.getSender().sendMessage(Component.text("Partially healed " + playerName, NamedTextColor.GREEN));
        }

        return 1;
    }

    private int executeAuraModify(CommandSourceStack source, String playerName, int amount, String reason) {
        Player player = Bukkit.getPlayer(playerName);
        if (player == null) {
            source.getSender().sendMessage(Component.text("Player not found: " + playerName, NamedTextColor.RED));
            return 0;
        }

        plugin.getAuraManager().addAura(player.getUniqueId(), amount, reason);

        String action = amount > 0 ? "Added" : "Removed";
        source.getSender().sendMessage(Component.text(
            action + " " + Math.abs(amount) + " aura " + (amount > 0 ? "to" : "from") + " " + playerName + ": " + reason,
            NamedTextColor.GREEN
        ));

        return 1;
    }

    private int executeSpawnTNT(CommandSourceStack source, String playerName, int count, int fuseTicks) {
        Player player = Bukkit.getPlayer(playerName);
        if (player == null) {
            source.getSender().sendMessage(Component.text("Player not found: " + playerName, NamedTextColor.RED));
            return 0;
        }

        for (int i = 0; i < count; i++) {
            // Spawn TNT in a random offset around the player (3-8 blocks away)
            double distance = 3 + Math.random() * 5;
            double angle = Math.random() * 2 * Math.PI;
            double offsetX = Math.cos(angle) * distance;
            double offsetZ = Math.sin(angle) * distance;

            Location spawnLoc = player.getLocation().add(offsetX, 1.5, offsetZ);

            // Spawn primed TNT entity
            org.bukkit.entity.TNTPrimed tnt = player.getWorld().spawn(spawnLoc, org.bukkit.entity.TNTPrimed.class);
            tnt.setFuseTicks(fuseTicks);

            // Register with CausalityManager for divine protection system
            plugin.getCausalityManager().registerErisTnt(tnt, player.getUniqueId());

            // Add some initial velocity for dramatic effect
            double vx = (Math.random() - 0.5) * 0.3;
            double vy = 0.1 + Math.random() * 0.2;
            double vz = (Math.random() - 0.5) * 0.3;
            tnt.setVelocity(new org.bukkit.util.Vector(vx, vy, vz));
        }

        source.getSender().sendMessage(Component.text(
            "Spawned " + count + " TNT near " + playerName + " (" + (fuseTicks / 20.0) + "s fuse)",
            NamedTextColor.GREEN
        ));
        return 1;
    }

    private int executeSpawnFallingBlock(CommandSourceStack source, String blockType, String playerName, int count, int height) {
        Player player = Bukkit.getPlayer(playerName);
        if (player == null) {
            source.getSender().sendMessage(Component.text("Player not found: " + playerName, NamedTextColor.RED));
            return 0;
        }

        // Convert block type string to Material
        Material blockMaterial;
        try {
            blockMaterial = Material.valueOf(blockType.toUpperCase());
        } catch (IllegalArgumentException e) {
            source.getSender().sendMessage(Component.text("Invalid block type: " + blockType, NamedTextColor.RED));
            return 0;
        }

        // Validate it's a gravity-affected block
        if (!blockMaterial.isBlock()) {
            source.getSender().sendMessage(Component.text(blockType + " is not a valid block", NamedTextColor.RED));
            return 0;
        }

        for (int i = 0; i < count; i++) {
            // Spawn blocks in a spread pattern above the player
            double offsetX = (Math.random() - 0.5) * 4;
            double offsetZ = (Math.random() - 0.5) * 4;

            Location spawnLoc = player.getLocation().add(offsetX, height, offsetZ);

            // Spawn falling block using newer API
            org.bukkit.entity.FallingBlock fallingBlock = player.getWorld().spawn(
                spawnLoc,
                org.bukkit.entity.FallingBlock.class,
                fb -> fb.setBlockData(blockMaterial.createBlockData())
            );

            // Make sure it can hurt entities
            fallingBlock.setHurtEntities(true);
            fallingBlock.setDropItem(false); // Don't drop item when it lands

            // Register with CausalityManager for divine protection system
            plugin.getCausalityManager().registerErisFallingBlock(fallingBlock, player.getUniqueId(), blockType);

            // Anvils and dripstone do more damage
            if (blockMaterial == Material.ANVIL || blockMaterial == Material.POINTED_DRIPSTONE) {
                fallingBlock.setDamagePerBlock(2.0f); // Vanilla is 2.0
                fallingBlock.setMaxDamage(40); // Max 20 hearts damage
            }
        }

        source.getSender().sendMessage(Component.text(
            "Spawned " + count + " falling " + blockType + " " + height + " blocks above " + playerName,
            NamedTextColor.GREEN
        ));
        return 1;
    }

    /**
     * Find a safe location to spawn mobs without suffocation.
     * Searches upward and downward from the base location.
     */
    private Location findSafeSpawnLocation(Location base) {
        World world = base.getWorld();
        int baseX = base.getBlockX();
        int baseZ = base.getBlockZ();

        // Start from player's Y level and search up and down
        int startY = base.getBlockY();

        // Try current level and nearby levels (prefer close to player)
        for (int yOffset = 0; yOffset <= 5; yOffset++) {
            // Try above first
            if (startY + yOffset < world.getMaxHeight()) {
                Location loc = new Location(world, baseX + 0.5, startY + yOffset, baseZ + 0.5);
                if (isSafeSpawnLocation(loc)) {
                    return loc;
                }
            }

            // Then try below
            if (yOffset > 0 && startY - yOffset >= world.getMinHeight()) {
                Location loc = new Location(world, baseX + 0.5, startY - yOffset, baseZ + 0.5);
                if (isSafeSpawnLocation(loc)) {
                    return loc;
                }
            }
        }

        // Fallback: use highest solid block at this position
        int highestY = world.getHighestBlockYAt(baseX, baseZ);
        return new Location(world, baseX + 0.5, highestY + 1, baseZ + 0.5);
    }

    /**
     * Check if a location is safe for mob spawning (feet and head are air).
     */
    private boolean isSafeSpawnLocation(Location loc) {
        World world = loc.getWorld();
        int x = loc.getBlockX();
        int y = loc.getBlockY();
        int z = loc.getBlockZ();

        // Check feet level (must be air)
        Material feetBlock = world.getBlockAt(x, y, z).getType();
        if (!feetBlock.isAir()) {
            return false;
        }

        // Check head level (must be air)
        Material headBlock = world.getBlockAt(x, y + 1, z).getType();
        if (!headBlock.isAir()) {
            return false;
        }

        // Check ground below (must be solid, not air/water/lava)
        Material groundBlock = world.getBlockAt(x, y - 1, z).getType();
        return groundBlock.isSolid() && groundBlock != Material.LAVA && groundBlock != Material.WATER;
    }

    private int executeLookAtPosition(CommandSourceStack source, String playerName, int x, int y, int z) {
        Player player = Bukkit.getPlayer(playerName);
        if (player == null) {
            source.getSender().sendMessage(Component.text("Player not found: " + playerName, NamedTextColor.RED));
            return 0;
        }

        Location targetLoc = new Location(player.getWorld(), x + 0.5, y + 0.5, z + 0.5);
        Location playerLoc = player.getLocation();

        // Calculate direction vector from player to target
        double dx = targetLoc.getX() - playerLoc.getX();
        double dy = targetLoc.getY() - playerLoc.getY();
        double dz = targetLoc.getZ() - playerLoc.getZ();

        // Calculate yaw and pitch
        double distance = Math.sqrt(dx * dx + dz * dz);
        float yaw = (float) Math.toDegrees(Math.atan2(-dx, dz));
        float pitch = (float) Math.toDegrees(-Math.atan2(dy, distance));

        // Set player's view direction
        playerLoc.setYaw(yaw);
        playerLoc.setPitch(pitch);
        player.teleport(playerLoc);

        source.getSender().sendMessage(Component.text(
            playerName + " is now looking at (" + x + ", " + y + ", " + z + ")",
            NamedTextColor.GREEN
        ));
        return 1;
    }

    private int executeLookAtEntity(CommandSourceStack source, String playerName, String targetName) {
        Player player = Bukkit.getPlayer(playerName);
        if (player == null) {
            source.getSender().sendMessage(Component.text("Player not found: " + playerName, NamedTextColor.RED));
            return 0;
        }

        Player target = Bukkit.getPlayer(targetName);
        if (target == null) {
            source.getSender().sendMessage(Component.text("Target player not found: " + targetName, NamedTextColor.RED));
            return 0;
        }

        Location playerLoc = player.getLocation();
        Location targetLoc = target.getLocation();

        // Calculate direction vector from player to target (aim at eye level)
        double dx = targetLoc.getX() - playerLoc.getX();
        double dy = (targetLoc.getY() + 1.62) - (playerLoc.getY() + 1.62); // Eye height
        double dz = targetLoc.getZ() - playerLoc.getZ();

        // Calculate yaw and pitch
        double distance = Math.sqrt(dx * dx + dz * dz);
        float yaw = (float) Math.toDegrees(Math.atan2(-dx, dz));
        float pitch = (float) Math.toDegrees(-Math.atan2(dy, distance));

        // Set player's view direction
        playerLoc.setYaw(yaw);
        playerLoc.setPitch(pitch);
        player.teleport(playerLoc);

        source.getSender().sendMessage(Component.text(
            playerName + " is now looking at " + targetName,
            NamedTextColor.GREEN
        ));
        return 1;
    }

    private int executeSpawnParticles(CommandSourceStack source, String particleName, String playerName, int count, double spread) {
        Player player = Bukkit.getPlayer(playerName);
        if (player == null) {
            source.getSender().sendMessage(Component.text("Player not found: " + playerName, NamedTextColor.RED));
            return 0;
        }

        // Normalize particle name - handle common aliases
        String normalizedName = particleName.toUpperCase().replace("-", "_");

        // Parse particle type
        Particle particle;
        try {
            particle = Particle.valueOf(normalizedName);
        } catch (IllegalArgumentException e) {
            source.getSender().sendMessage(Component.text("Invalid particle: " + particleName, NamedTextColor.RED));
            return 0;
        }

        // Spawn at player's eye location so particles are visible even in tunnels
        Location loc = player.getEyeLocation();
        World world = player.getWorld();

        // Spawn particles - some need special handling
        try {
            // Particles that need extra speed/data parameter to be visible
            if (particle == Particle.DRAGON_BREATH || particle == Particle.END_ROD ||
                particle == Particle.PORTAL || particle == Particle.REVERSE_PORTAL) {
                // These particles need a non-zero speed to show properly
                world.spawnParticle(particle, loc, count, spread, spread, spread, 0.05);
            } else if (particle == Particle.DUST) {
                // Dust requires DustOptions
                world.spawnParticle(particle, loc, count, spread, spread, spread, 0,
                    new Particle.DustOptions(Color.PURPLE, 1.0f));
            } else {
                world.spawnParticle(particle, loc, count, spread, spread, spread, 0.0);
            }
        } catch (Exception e) {
            // Fall back to a safe particle
            source.getSender().sendMessage(Component.text(
                "Particle " + particleName + " failed, using SOUL instead: " + e.getMessage(),
                NamedTextColor.YELLOW
            ));
            world.spawnParticle(Particle.SOUL, loc, count, spread, spread, spread, 0.0);
        }

        source.getSender().sendMessage(Component.text(
            "Spawned " + count + " " + particleName + " particles near " + playerName,
            NamedTextColor.GREEN
        ));
        return 1;
    }

    private int executeFakeDeath(CommandSourceStack source, String playerName, String cause) {
        Player player = Bukkit.getPlayer(playerName);
        if (player == null) {
            source.getSender().sendMessage(Component.text("Player not found: " + playerName, NamedTextColor.RED));
            return 0;
        }

        // Create fake death message based on cause
        String deathMessage = switch (cause.toLowerCase()) {
            case "fell" -> playerName + " fell from a high place";
            case "lava" -> playerName + " tried to swim in lava";
            case "fire" -> playerName + " went up in flames";
            case "suffocated" -> playerName + " suffocated in a wall";
            case "drowned" -> playerName + " drowned";
            case "exploded" -> playerName + " blew up";
            case "magic" -> playerName + " was killed by magic";
            case "wither" -> playerName + " withered away";
            case "anvil" -> playerName + " was squashed by a falling anvil";
            case "lightning" -> playerName + " was struck by lightning";
            case "kinetic" -> playerName + " experienced kinetic energy";
            case "void" -> playerName + " fell out of the world";
            default -> playerName + " died";
        };

        // Broadcast fake death message
        MiniMessage miniMessage = MiniMessage.miniMessage();
        Component fakeDeathComponent = miniMessage.deserialize("<dark_gray>" + deathMessage + "</dark_gray>");
        Bukkit.broadcast(fakeDeathComponent);

        source.getSender().sendMessage(Component.text("Broadcast fake death for " + playerName, NamedTextColor.GREEN));
        return 1;
    }

    // ==================== DIVINE PROTECTION COMMANDS ====================

    private int executeProtect(CommandSourceStack source, String playerName, int auraCost) {
        Player player = Bukkit.getPlayer(playerName);
        if (player == null) {
            source.getSender().sendMessage(Component.text("Player not found: " + playerName, NamedTextColor.RED));
            return 0;
        }

        // Remove harmful effects that Eris may have applied
        player.removePotionEffect(PotionEffectType.POISON);
        player.removePotionEffect(PotionEffectType.WITHER);
        player.removePotionEffect(PotionEffectType.HUNGER);
        player.removePotionEffect(PotionEffectType.BLINDNESS);
        player.removePotionEffect(PotionEffectType.DARKNESS);
        player.removePotionEffect(PotionEffectType.LEVITATION);
        player.removePotionEffect(PotionEffectType.SLOWNESS);
        player.removePotionEffect(PotionEffectType.WEAKNESS);

        // Heal to 50% health
        double targetHealth = player.getMaxHealth() * 0.5;
        player.setHealth(Math.max(player.getHealth(), targetHealth));

        // Restore food level (regenerating health costs hunger)
        player.setFoodLevel(Math.max(player.getFoodLevel(), 14));  // 14 = 7 drumsticks
        player.setSaturation(Math.max(player.getSaturation(), 5.0f));

        // Apply short resistance effect (3 seconds, level 1)
        player.addPotionEffect(new PotionEffect(PotionEffectType.RESISTANCE, 60, 1));

        // Apply regeneration to recover from DOT damage (5 seconds, level 2)
        player.addPotionEffect(new PotionEffect(PotionEffectType.REGENERATION, 100, 1));

        // Apply aura cost
        plugin.getAuraManager().removeAura(player.getUniqueId(), auraCost, "divine protection from Eris");

        // Visual effects - totem animation
        player.getWorld().spawnParticle(Particle.TOTEM_OF_UNDYING, player.getLocation().add(0, 1, 0), 50, 0.5, 1, 0.5, 0.1);
        player.playSound(player.getLocation(), org.bukkit.Sound.ITEM_TOTEM_USE, 1.0f, 1.0f);

        // Send WebSocket event so Python knows protection was used
        com.google.gson.JsonObject data = new com.google.gson.JsonObject();
        data.addProperty("player", playerName);
        data.addProperty("auraCost", auraCost);
        data.addProperty("healthAfter", player.getHealth());
        if (plugin.getDirectorServer() != null) {
            plugin.getDirectorServer().broadcastEvent("eris_protection_used", data);
        }

        source.getSender().sendMessage(Component.text("Protected " + playerName + " (cost: " + auraCost + " aura)", NamedTextColor.GREEN));
        return 1;
    }

    private int executeRescueTeleport(CommandSourceStack source, String playerName, int auraCost) {
        Player player = Bukkit.getPlayer(playerName);
        if (player == null) {
            source.getSender().sendMessage(Component.text("Player not found: " + playerName, NamedTextColor.RED));
            return 0;
        }

        Location current = player.getLocation();
        World world = current.getWorld();

        // Find a safe location away from danger (10-20 blocks away)
        Location safeLoc = null;
        for (int attempts = 0; attempts < 20; attempts++) {
            double angle = Math.random() * 2 * Math.PI;
            double distance = 10 + Math.random() * 10;
            double x = current.getX() + Math.cos(angle) * distance;
            double z = current.getZ() + Math.sin(angle) * distance;
            int y = world.getHighestBlockYAt((int) x, (int) z);

            Location candidate = new Location(world, x, y + 1, z);
            if (isSafeRescueLocation(candidate)) {
                safeLoc = candidate;
                break;
            }
        }

        if (safeLoc == null) {
            // Fallback: teleport straight up
            safeLoc = current.clone().add(0, 5, 0);
        }

        // Visual effect before teleport
        player.getWorld().spawnParticle(Particle.REVERSE_PORTAL, player.getLocation().add(0, 1, 0), 30, 0.3, 0.5, 0.3, 0.05);

        // Teleport player
        player.teleport(safeLoc);

        // Visual effect after teleport
        player.getWorld().spawnParticle(Particle.REVERSE_PORTAL, safeLoc.add(0, 1, 0), 30, 0.3, 0.5, 0.3, 0.05);
        player.playSound(safeLoc, org.bukkit.Sound.ENTITY_ENDERMAN_TELEPORT, 1.0f, 1.0f);

        // Apply aura cost
        plugin.getAuraManager().removeAura(player.getUniqueId(), auraCost, "rescue teleport from Eris");

        // Send WebSocket event
        com.google.gson.JsonObject data = new com.google.gson.JsonObject();
        data.addProperty("player", playerName);
        data.addProperty("auraCost", auraCost);
        if (plugin.getDirectorServer() != null) {
            plugin.getDirectorServer().broadcastEvent("eris_rescue_used", data);
        }

        source.getSender().sendMessage(Component.text("Rescued " + playerName + " via teleport (cost: " + auraCost + " aura)", NamedTextColor.GREEN));
        return 1;
    }

    private boolean isSafeRescueLocation(Location loc) {
        World world = loc.getWorld();
        int x = loc.getBlockX();
        int y = loc.getBlockY();
        int z = loc.getBlockZ();

        // Check feet and head are air
        if (!world.getBlockAt(x, y, z).getType().isAir()) return false;
        if (!world.getBlockAt(x, y + 1, z).getType().isAir()) return false;

        // Check ground is solid and safe
        Material ground = world.getBlockAt(x, y - 1, z).getType();
        if (!ground.isSolid()) return false;
        if (ground == Material.LAVA || ground == Material.MAGMA_BLOCK) return false;
        if (ground == Material.CACTUS || ground == Material.SWEET_BERRY_BUSH) return false;

        // Check not near lava
        for (int dx = -2; dx <= 2; dx++) {
            for (int dz = -2; dz <= 2; dz++) {
                for (int dy = -1; dy <= 1; dy++) {
                    if (world.getBlockAt(x + dx, y + dy, z + dz).getType() == Material.LAVA) {
                        return false;
                    }
                }
            }
        }

        return true;
    }

    private int executeRespawnOverride(CommandSourceStack source, String playerName, int auraCost) {
        Player player = Bukkit.getPlayer(playerName);
        if (player == null) {
            source.getSender().sendMessage(Component.text("Player not found: " + playerName, NamedTextColor.RED));
            return 0;
        }

        // Check if respawns are available
        if (!plugin.getCausalityManager().canUseRespawn()) {
            source.getSender().sendMessage(Component.text("No respawns remaining this run", NamedTextColor.RED));
            return 0;
        }

        // Clear pending death
        plugin.getCausalityManager().clearPendingDeath(player.getUniqueId());

        // Mark respawn as used
        plugin.getCausalityManager().useRespawn();

        // Apply aura cost
        plugin.getAuraManager().removeAura(player.getUniqueId(), auraCost, "divine respawn intervention");

        // Schedule the respawn flow (player needs to respawn first)
        Bukkit.getScheduler().runTaskLater(plugin, () -> {
            // Force respawn if not already
            if (player.isDead()) {
                player.spigot().respawn();
            }

            // Teleport to hardcore world and wait for it to complete
            plugin.getWorldManager().teleportToHardcore(player).thenAccept(success -> {
                if (!success) {
                    player.sendMessage(Component.text("Failed to teleport to hardcore world", NamedTextColor.RED));
                    return;
                }

                // Run the rest on the main thread
                Bukkit.getScheduler().runTask(plugin, () -> {
                    // Set to spectator mode at hardcore spawn (elevated for safety)
                    Location spawnLoc = player.getLocation().add(0, 5, 0);
                    player.setGameMode(org.bukkit.GameMode.SPECTATOR);
                    player.teleport(spawnLoc);

                    // Show countdown title
                    showRespawnCountdown(player, 5);

                    // After 5 seconds, switch to survival at current location
                    Bukkit.getScheduler().runTaskLater(plugin, () -> {
                        Location finalLoc = player.getLocation();
                        player.setGameMode(org.bukkit.GameMode.SURVIVAL);
                        player.teleport(finalLoc);
                        player.setHealth(player.getMaxHealth() * 0.5);
                        player.setFoodLevel(20);

                        // Dramatic effects
                        player.getWorld().strikeLightningEffect(finalLoc);
                        player.getWorld().spawnParticle(Particle.TOTEM_OF_UNDYING, finalLoc.add(0, 1, 0), 100, 1, 2, 1, 0.1);

                        // Broadcast message
                        MiniMessage mm = MiniMessage.miniMessage();
                        Bukkit.broadcast(mm.deserialize(
                            "<gold><b>DIVINE INTERVENTION</b></gold> <dark_gray>-</dark_gray> <light_purple>Eris has spared <white>" + playerName + "</white>... <i>this time.</i></light_purple>"
                        ));
                    }, 100L); // 5 seconds = 100 ticks
                });
            });
        }, 1L);

        // Send WebSocket event
        com.google.gson.JsonObject data = new com.google.gson.JsonObject();
        data.addProperty("player", playerName);
        data.addProperty("auraCost", auraCost);
        data.addProperty("respawnsRemaining", plugin.getCausalityManager().getRemainingRespawns());
        if (plugin.getDirectorServer() != null) {
            plugin.getDirectorServer().broadcastEvent("eris_respawn_override", data);
        }

        source.getSender().sendMessage(Component.text("Respawn override for " + playerName + " (cost: " + auraCost + " aura)", NamedTextColor.GREEN));
        return 1;
    }

    private void showRespawnCountdown(Player player, int seconds) {
        if (seconds <= 0) return;

        MiniMessage mm = MiniMessage.miniMessage();
        player.showTitle(net.kyori.adventure.title.Title.title(
            mm.deserialize("<gold><b>DIVINE INTERVENTION</b></gold>"),
            mm.deserialize("<gray>Find a safe spot... <white>" + seconds + "</white></gray>"),
            net.kyori.adventure.title.Title.Times.times(
                java.time.Duration.ZERO,
                java.time.Duration.ofMillis(1100),
                java.time.Duration.ZERO
            )
        ));

        // Play tick sound
        player.playSound(player.getLocation(), org.bukkit.Sound.BLOCK_NOTE_BLOCK_PLING, 0.5f, 1.0f + (5 - seconds) * 0.1f);

        // Schedule next countdown
        Bukkit.getScheduler().runTaskLater(plugin, () -> showRespawnCountdown(player, seconds - 1), 20L);
    }

    // ==================== DEBUG COMMANDS ====================

    private int executeDebugApocalypse(CommandSourceStack source) {
        if (plugin.getDirectorServer() == null) {
            source.getSender().sendMessage(Component.text("Director WebSocket not connected", NamedTextColor.RED));
            return 0;
        }

        // Send debug event to Python to trigger apocalypse
        com.google.gson.JsonObject data = new com.google.gson.JsonObject();
        data.addProperty("source", "debug_command");
        plugin.getDirectorServer().broadcastEvent("debug_trigger_apocalypse", data);

        source.getSender().sendMessage(Component.text("🍎 DEBUG: Sent apocalypse trigger event to Director", NamedTextColor.GOLD));
        return 1;
    }

    private int executeDebugSetFracture(CommandSourceStack source, int level) {
        if (plugin.getDirectorServer() == null) {
            source.getSender().sendMessage(Component.text("Director WebSocket not connected", NamedTextColor.RED));
            return 0;
        }

        // Send debug event to Python to set fracture level
        com.google.gson.JsonObject data = new com.google.gson.JsonObject();
        data.addProperty("fracture", level);
        data.addProperty("source", "debug_command");
        plugin.getDirectorServer().broadcastEvent("debug_set_fracture", data);

        source.getSender().sendMessage(Component.text("🔧 DEBUG: Set fracture level to " + level, NamedTextColor.GOLD));
        return 1;
    }
}
