package com.dragonrun.listeners;

import com.dragonrun.managers.WorldManager;
import org.bukkit.entity.EntityType;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.entity.CreatureSpawnEvent;
import org.bukkit.event.entity.EntityDamageEvent;
import org.bukkit.event.entity.FoodLevelChangeEvent;

/**
 * Protects the lobby world from harmful events.
 * Lobby is creative mode - players can build freely.
 * No damage, no hunger, no hostile mobs (including slimes).
 */
public class LobbyProtectionListener implements Listener {

    private final WorldManager worldManager;

    public LobbyProtectionListener(WorldManager worldManager) {
        this.worldManager = worldManager;
    }

    /**
     * Prevent all damage in lobby.
     
    @EventHandler(priority = EventPriority.HIGHEST)
    public void onEntityDamage(EntityDamageEvent event) {
        if (worldManager.isLobbyWorld(event.getEntity().getWorld())) {
            event.setCancelled(true);
        }
    }*/

    /**
     * Prevent hunger in lobby.
     */
    @EventHandler(priority = EventPriority.HIGHEST)
    public void onFoodLevelChange(FoodLevelChangeEvent event) {
        if (event.getEntity() instanceof Player player) {
            if (worldManager.isLobbyWorld(player.getWorld())) {
                event.setCancelled(true);
                player.setFoodLevel(20);
                player.setSaturation(20f);
            }
        }
    }

    /**
     * Prevent ALL creature spawning in lobby (mobs, slimes, etc).
     
    @EventHandler(priority = EventPriority.HIGHEST)
    public void onCreatureSpawn(CreatureSpawnEvent event) {
        if (worldManager.isLobbyWorld(event.getEntity().getWorld())) {
            // Allow players and armor stands
            EntityType type = event.getEntityType();
            if (type == EntityType.PLAYER || type == EntityType.ARMOR_STAND) {
                return;
            }
            // Block all other creatures
            event.setCancelled(true);
        }
    }*/
}
