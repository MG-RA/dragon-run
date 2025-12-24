package com.dragonrun.director;

import com.dragonrun.DragonRunPlugin;
import com.mojang.brigadier.arguments.IntegerArgumentType;
import com.mojang.brigadier.arguments.StringArgumentType;
import io.papermc.paper.command.brigadier.CommandSourceStack;
import io.papermc.paper.command.brigadier.Commands;
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
                            String[] parts = args.split(" ", 6);
                            String player = parts[0];
                            int fadeIn = Integer.parseInt(parts[1]);
                            int stay = Integer.parseInt(parts[2]);
                            int fadeOut = Integer.parseInt(parts[3]);
                            String[] texts = parts.length > 4 ? parts[4].split(" \\| ", 2) : new String[]{"", ""};
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
                player.getWorld().spawnEntity(spawnLoc, entityType);
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

        source.getSender().sendMessage(Component.text("Applied " + effectName + " to " + playerName, NamedTextColor.GREEN));
        return 1;
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

        switch (weatherType.toLowerCase()) {
            case "clear":
                world.setStorm(false);
                world.setThundering(false);
                break;
            case "rain":
                world.setStorm(true);
                world.setThundering(false);
                break;
            case "thunder":
                world.setStorm(true);
                world.setThundering(true);
                break;
            default:
                source.getSender().sendMessage(Component.text("Invalid weather type: " + weatherType, NamedTextColor.RED));
                return 0;
        }

        source.getSender().sendMessage(Component.text("Weather set to " + weatherType, NamedTextColor.GREEN));
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
        if ("@a".equals(target)) {
            for (Player player : Bukkit.getOnlinePlayers()) {
                player.playSound(player.getLocation(), sound, volume, pitch);
            }
            source.getSender().sendMessage(Component.text("Played sound to all players", NamedTextColor.GREEN));
        } else {
            Player player = Bukkit.getPlayer(target);
            if (player == null) {
                source.getSender().sendMessage(Component.text("Player not found: " + target, NamedTextColor.RED));
                return 0;
            }
            player.playSound(player.getLocation(), sound, volume, pitch);
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

        Component title = titleText.isEmpty() ? Component.empty() : Component.text(titleText);
        Component subtitle = subtitleText.isEmpty() ? Component.empty() : Component.text(subtitleText);

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
}
