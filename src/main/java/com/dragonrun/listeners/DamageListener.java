package com.dragonrun.listeners;

import com.dragonrun.DragonRunPlugin;
import com.google.gson.JsonObject;
import org.bukkit.entity.Entity;
import org.bukkit.entity.Player;
import org.bukkit.entity.Projectile;
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

        // Check if damage was Eris-caused
        boolean isErisCaused = checkIfErisCaused(event, player);

        // Build event data
        JsonObject data = new JsonObject();
        data.addProperty("player", player.getName());
        data.addProperty("playerUuid", player.getUniqueId().toString());
        data.addProperty("damage", Math.round(damage * 10.0) / 10.0);
        data.addProperty("source", source);
        data.addProperty("healthBefore", Math.round(player.getHealth() * 10.0) / 10.0);
        data.addProperty("healthAfter", Math.round(healthAfter * 10.0) / 10.0);
        data.addProperty("isCloseCall", isCloseCall);
        data.addProperty("isErisCaused", isErisCaused);
        data.addProperty("dimension", player.getWorld().getEnvironment().name().toLowerCase());

        // Send different event types for Eris-caused close calls
        if (isErisCaused && isCloseCall) {
            data.addProperty("needsProtection", true);
            plugin.getDirectorServer().broadcastEvent("eris_close_call", data);
        } else {
            plugin.getDirectorServer().broadcastEvent("player_damaged", data);
        }
    }

    /**
     * Check if damage was caused by Eris's interventions.
     */
    private boolean checkIfErisCaused(EntityDamageEvent event, Player player) {
        var causalityManager = plugin.getCausalityManager();
        if (causalityManager == null) return false;

        // Check entity attack (mobs spawned by Eris)
        if (event instanceof EntityDamageByEntityEvent entityDamage) {
            Entity damager = entityDamage.getDamager();

            // Direct entity damage
            if (causalityManager.isErisCaused(damager)) {
                return true;
            }

            // Projectile from Eris-spawned entity
            if (damager instanceof Projectile projectile) {
                if (projectile.getShooter() instanceof Entity shooter) {
                    if (causalityManager.isErisCaused(shooter)) {
                        return true;
                    }
                }
            }
        }

        // Check block explosion (TNT spawned by Eris)
        if (event.getCause() == EntityDamageEvent.DamageCause.BLOCK_EXPLOSION) {
            if (causalityManager.wasRecentErisTntNear(player.getLocation())) {
                return true;
            }
        }

        // Check entity explosion (creeper spawned by Eris)
        if (event.getCause() == EntityDamageEvent.DamageCause.ENTITY_EXPLOSION) {
            if (event instanceof EntityDamageByEntityEvent entityDamage) {
                if (causalityManager.isErisCaused(entityDamage.getDamager())) {
                    return true;
                }
            }
        }

        // Check effects (poison, wither from Eris)
        if (event.getCause() == EntityDamageEvent.DamageCause.POISON ||
            event.getCause() == EntityDamageEvent.DamageCause.WITHER) {
            if (causalityManager.isErisEffect(player.getUniqueId(),
                    event.getCause().name().toLowerCase())) {
                return true;
            }
        }

        // Check falling block (anvil, dripstone from Eris)
        if (event.getCause() == EntityDamageEvent.DamageCause.FALLING_BLOCK) {
            if (event instanceof EntityDamageByEntityEvent blockDamage) {
                if (causalityManager.isErisCaused(blockDamage.getDamager())) {
                    return true;
                }
            }
        }

        // Check lightning (from Eris)
        if (event.getCause() == EntityDamageEvent.DamageCause.LIGHTNING) {
            if (causalityManager.wasRecentErisLightningNear(player.getLocation())) {
                return true;
            }
        }

        return false;
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
