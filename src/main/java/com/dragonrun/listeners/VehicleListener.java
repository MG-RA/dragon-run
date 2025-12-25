package com.dragonrun.listeners;

import com.dragonrun.DragonRunPlugin;
import com.google.gson.JsonObject;
import org.bukkit.entity.*;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.vehicle.VehicleEnterEvent;
import org.bukkit.event.vehicle.VehicleExitEvent;

/**
 * Tracks vehicle usage (boats, minecarts, mounts).
 * Helps Eris understand movement strategies like nether ice roads or rail systems.
 */
public class VehicleListener implements Listener {

    private final DragonRunPlugin plugin;

    public VehicleListener(DragonRunPlugin plugin) {
        this.plugin = plugin;
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onVehicleEnter(VehicleEnterEvent event) {
        if (!(event.getEntered() instanceof Player player)) return;
        if (plugin.getDirectorServer() == null) return;

        // Ignore lobby world
        if (plugin.getWorldManager().isLobbyWorld(player.getWorld())) return;

        Entity vehicle = event.getVehicle();
        String vehicleType = getVehicleTypeName(vehicle);

        // Build event data
        JsonObject data = new JsonObject();
        data.addProperty("player", player.getName());
        data.addProperty("playerUuid", player.getUniqueId().toString());
        data.addProperty("vehicleType", vehicleType);
        data.addProperty("dimension", player.getWorld().getEnvironment().name().toLowerCase());

        plugin.getDirectorServer().broadcastEvent("vehicle_entered", data);
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onVehicleExit(VehicleExitEvent event) {
        if (!(event.getExited() instanceof Player player)) return;
        if (plugin.getDirectorServer() == null) return;

        // Ignore lobby world
        if (plugin.getWorldManager().isLobbyWorld(player.getWorld())) return;

        Entity vehicle = event.getVehicle();
        String vehicleType = getVehicleTypeName(vehicle);

        // Build event data
        JsonObject data = new JsonObject();
        data.addProperty("player", player.getName());
        data.addProperty("playerUuid", player.getUniqueId().toString());
        data.addProperty("vehicleType", vehicleType);
        data.addProperty("dimension", player.getWorld().getEnvironment().name().toLowerCase());

        plugin.getDirectorServer().broadcastEvent("vehicle_exited", data);
    }

    /**
     * Get a readable vehicle type name.
     */
    private String getVehicleTypeName(Entity vehicle) {
        // Boats
        if (vehicle instanceof Boat boat) {
            return boat.getBoatType().name().toLowerCase() + "_boat";
        }

        // Minecarts - use entity type for variants
        if (vehicle instanceof Minecart) {
            return switch (vehicle.getType()) {
                case MINECART -> "minecart";
                case CHEST_MINECART -> "chest_minecart";
                case FURNACE_MINECART -> "furnace_minecart";
                case HOPPER_MINECART -> "hopper_minecart";
                case TNT_MINECART -> "tnt_minecart";
                case COMMAND_BLOCK_MINECART -> "command_minecart";
                case SPAWNER_MINECART -> "spawner_minecart";
                default -> "minecart";
            };
        }

        // Mounts (horses, pigs, striders)
        if (vehicle instanceof Horse) return "horse";
        if (vehicle instanceof Donkey) return "donkey";
        if (vehicle instanceof Mule) return "mule";
        if (vehicle instanceof SkeletonHorse) return "skeleton_horse";
        if (vehicle instanceof ZombieHorse) return "zombie_horse";
        if (vehicle instanceof Llama) return "llama";
        if (vehicle instanceof Pig) return "pig";
        if (vehicle instanceof Strider) return "strider";
        if (vehicle instanceof Camel) return "camel";

        return vehicle.getType().name().toLowerCase();
    }
}
