package com.dragonrun.listeners;

import com.dragonrun.DragonRunPlugin;
import com.google.gson.JsonObject;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.entity.EntityDamageEvent;
import org.bukkit.event.entity.EntityDamageByEntityEvent;

/**
 * Listens to player damage events and forwards significant ones to Eris.
 */
public class DamageListener implements Listener {

    private final DragonRunPlugin plugin;

    // Minimum damage to report (4 hearts = 8 damage)
    private static final double MIN_DAMAGE_THRESHOLD = 8.0;
    // Health threshold for "close call" (4 hearts = 8 health)
    private static final double CLOSE_CALL_THRESHOLD = 8.0;

    public DamageListener(DragonRunPlugin plugin) {
        this.plugin = plugin;
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onPlayerDamage(EntityDamageEvent event) {
        if (event.isCancelled()) return;
        if (!(event.getEntity() instanceof Player player)) return;
        if (plugin.getDirectorServer() == null) return;

        double damage = event.getFinalDamage();
        double healthAfter = Math.max(0, player.getHealth() - damage);

        // Only report significant damage (> 4 hearts) or close calls
        boolean isSignificantDamage = damage >= MIN_DAMAGE_THRESHOLD;
        boolean isCloseCall = healthAfter > 0 && healthAfter < CLOSE_CALL_THRESHOLD;

        if (!isSignificantDamage && !isCloseCall) return;

        // Get damage source description
        String source = getDamageSource(event);

        // Build event data
        JsonObject data = new JsonObject();
        data.addProperty("player", player.getName());
        data.addProperty("playerUuid", player.getUniqueId().toString());
        data.addProperty("damage", Math.round(damage * 10.0) / 10.0);
        data.addProperty("source", source);
        data.addProperty("healthBefore", Math.round(player.getHealth() * 10.0) / 10.0);
        data.addProperty("healthAfter", Math.round(healthAfter * 10.0) / 10.0);
        data.addProperty("isCloseCall", isCloseCall);
        data.addProperty("dimension", player.getWorld().getEnvironment().name().toLowerCase());

        plugin.getDirectorServer().broadcastEvent("player_damaged", data);
    }

    private String getDamageSource(EntityDamageEvent event) {
        // Check if it was an entity attack
        if (event instanceof EntityDamageByEntityEvent entityEvent) {
            return entityEvent.getDamager().getType().name().toLowerCase().replace("_", " ");
        }

        // Map damage causes to readable strings
        return switch (event.getCause()) {
            case FALL -> "fall damage";
            case FIRE, FIRE_TICK -> "fire";
            case LAVA -> "lava";
            case DROWNING -> "drowning";
            case VOID -> "the void";
            case STARVATION -> "starvation";
            case POISON -> "poison";
            case WITHER -> "wither effect";
            case FALLING_BLOCK -> "falling block";
            case LIGHTNING -> "lightning";
            case SUFFOCATION -> "suffocation";
            case BLOCK_EXPLOSION, ENTITY_EXPLOSION -> "explosion";
            case CONTACT -> "cactus";
            case CRAMMING -> "entity cramming";
            case FLY_INTO_WALL -> "kinetic energy";
            case FREEZE -> "freezing";
            case HOT_FLOOR -> "magma block";
            case MAGIC -> "magic";
            case THORNS -> "thorns";
            default -> event.getCause().name().toLowerCase().replace("_", " ");
        };
    }
}
