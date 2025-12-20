package com.dragonrun.director;

import com.dragonrun.DragonRunPlugin;
import com.mojang.brigadier.arguments.IntegerArgumentType;
import com.mojang.brigadier.arguments.StringArgumentType;
import io.papermc.paper.command.brigadier.CommandSourceStack;
import io.papermc.paper.command.brigadier.Commands;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
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
                .build(),
            "Director AI commands",
            java.util.List.of()
        );
    }

    private int executeBroadcast(CommandSourceStack source, String message) {
        Component broadcastMessage = Component.text("[Eris] ", NamedTextColor.LIGHT_PURPLE)
            .append(Component.text(message, NamedTextColor.WHITE));

        Bukkit.broadcast(broadcastMessage);
        return 1;
    }

    private int executePlayerMessage(CommandSourceStack source, String playerName, String message) {
        Player player = Bukkit.getPlayer(playerName);
        if (player == null) {
            source.getSender().sendMessage(Component.text("Player not found: " + playerName, NamedTextColor.RED));
            return 0;
        }

        Component playerMessage = Component.text("[Eris] ", NamedTextColor.LIGHT_PURPLE)
            .append(Component.text(message, NamedTextColor.WHITE));

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

        Location spawnLoc = player.getLocation().add(
            (Math.random() - 0.5) * 10,
            0,
            (Math.random() - 0.5) * 10
        );
        spawnLoc.setY(player.getLocation().getY());

        for (int i = 0; i < count; i++) {
            player.getWorld().spawnEntity(spawnLoc, entityType);
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

        Location strikeLoc = player.getLocation().add(
            (Math.random() - 0.5) * 5,
            0,
            (Math.random() - 0.5) * 5
        );

        player.getWorld().strikeLightning(strikeLoc);

        source.getSender().sendMessage(Component.text("Lightning struck near " + playerName, NamedTextColor.GREEN));
        return 1;
    }

    private int executeWeather(CommandSourceStack source, String weatherType) {
        String worldName = plugin.getRunManager().getCurrentWorldName();
        World world = Bukkit.getWorld(worldName);

        if (world == null) {
            source.getSender().sendMessage(Component.text("World not found", NamedTextColor.RED));
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
}
