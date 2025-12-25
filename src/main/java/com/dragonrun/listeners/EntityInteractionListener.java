package com.dragonrun.listeners;

import com.dragonrun.DragonRunPlugin;
import com.google.gson.JsonObject;
import org.bukkit.entity.*;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.entity.PlayerLeashEntityEvent;

/**
 * Tracks player interactions with entities like leashing animals.
 * Helps Eris understand player strategies involving pets/allies.
 */
public class EntityInteractionListener implements Listener {

    private final DragonRunPlugin plugin;

    public EntityInteractionListener(DragonRunPlugin plugin) {
        this.plugin = plugin;
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onPlayerLeashEntity(PlayerLeashEntityEvent event) {
        Player player = event.getPlayer();
        if (plugin.getDirectorServer() == null) return;

        // Ignore lobby world
        if (plugin.getWorldManager().isLobbyWorld(player.getWorld())) return;

        Entity entity = event.getEntity();
        String entityType = getEntityTypeName(entity);

        // Build event data
        JsonObject data = new JsonObject();
        data.addProperty("player", player.getName());
        data.addProperty("playerUuid", player.getUniqueId().toString());
        data.addProperty("entityType", entityType);
        data.addProperty("dimension", player.getWorld().getEnvironment().name().toLowerCase());

        // Add custom name if present
        if (entity.customName() != null) {
            data.addProperty("entityName", net.kyori.adventure.text.serializer.plain.PlainTextComponentSerializer.plainText().serialize(entity.customName()));
        }

        plugin.getDirectorServer().broadcastEvent("entity_leashed", data);
    }

    /**
     * Get a readable entity type name with variants.
     */
    private String getEntityTypeName(Entity entity) {
        // Handle specific variants
        if (entity instanceof Wolf wolf) {
            if (wolf.isTamed()) return "tamed_wolf";
            return "wolf";
        }

        if (entity instanceof Horse horse) {
            return switch (horse.getColor()) {
                case WHITE -> "white_horse";
                case CREAMY -> "cream_horse";
                case DARK_BROWN -> "dark_brown_horse";
                case BROWN -> "brown_horse";
                case BLACK -> "black_horse";
                case GRAY -> "gray_horse";
                case CHESTNUT -> "chestnut_horse";
            };
        }

        if (entity instanceof Donkey) return "donkey";
        if (entity instanceof Mule) return "mule";
        if (entity instanceof SkeletonHorse) return "skeleton_horse";
        if (entity instanceof ZombieHorse) return "zombie_horse";
        if (entity instanceof Llama) return "llama";
        if (entity instanceof TraderLlama) return "trader_llama";
        if (entity instanceof IronGolem) return "iron_golem";
        if (entity instanceof Cat) return "cat";
        if (entity instanceof Parrot) return "parrot";
        if (entity instanceof Fox) return "fox";

        return entity.getType().name().toLowerCase();
    }
}
