package com.dragonrun.listeners;

import com.dragonrun.DragonRunPlugin;
import com.google.gson.JsonObject;
import org.bukkit.Material;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.entity.EntityPickupItemEvent;
import org.bukkit.event.inventory.CraftItemEvent;
import org.bukkit.inventory.ItemStack;

import java.util.HashSet;
import java.util.Set;

/**
 * Tracks resource milestones and broadcasts them to Eris.
 * These are first-time-per-run achievements that mark progress.
 */
public class ResourceMilestoneListener implements Listener {

    private final DragonRunPlugin plugin;

    // Track which players have hit which milestones this run
    private final Set<String> achievedMilestones = new HashSet<>();

    public ResourceMilestoneListener(DragonRunPlugin plugin) {
        this.plugin = plugin;
    }

    /**
     * Reset milestones when a new run starts.
     */
    public void resetMilestones() {
        achievedMilestones.clear();
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onItemPickup(EntityPickupItemEvent event) {
        if (event.isCancelled()) return;
        if (!(event.getEntity() instanceof Player player)) return;
        if (plugin.getDirectorServer() == null) return;

        ItemStack item = event.getItem().getItemStack();
        Material type = item.getType();

        // Check for milestone items
        switch (type) {
            case IRON_INGOT -> checkMilestone(player, "first_iron_obtained", "iron");
            case DIAMOND -> checkMilestone(player, "first_diamond_obtained", "diamond");
            case BLAZE_ROD -> checkMilestone(player, "blaze_rod_obtained", "blaze_rod");
            case ENDER_PEARL -> checkMilestone(player, "first_ender_pearl", "ender_pearl");
            default -> {}
        }
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onCraftItem(CraftItemEvent event) {
        if (event.isCancelled()) return;
        if (!(event.getWhoClicked() instanceof Player player)) return;
        if (plugin.getDirectorServer() == null) return;

        Material result = event.getRecipe().getResult().getType();

        // Check for milestone crafts
        switch (result) {
            case ENDER_EYE -> checkMilestone(player, "ender_eye_crafted", "ender_eye");
            case DIAMOND_PICKAXE -> checkMilestone(player, "diamond_pickaxe_crafted", "diamond_pickaxe");
            case DIAMOND_SWORD -> checkMilestone(player, "diamond_sword_crafted", "diamond_sword");
            case BREWING_STAND -> checkMilestone(player, "brewing_stand_crafted", "brewing_stand");
            default -> {}
        }
    }

    private void checkMilestone(Player player, String eventType, String milestone) {
        String key = player.getUniqueId() + ":" + milestone;

        // Only broadcast first time per player per run
        if (achievedMilestones.contains(key)) {
            return;
        }

        achievedMilestones.add(key);

        // Broadcast to Eris
        JsonObject data = new JsonObject();
        data.addProperty("player", player.getName());
        data.addProperty("playerUuid", player.getUniqueId().toString());
        data.addProperty("milestone", milestone);
        data.addProperty("dimension", player.getWorld().getEnvironment().name().toLowerCase());

        plugin.getDirectorServer().broadcastEvent(eventType, data);
    }
}
