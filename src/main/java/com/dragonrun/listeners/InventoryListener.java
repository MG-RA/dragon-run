package com.dragonrun.listeners;

import com.dragonrun.DragonRunPlugin;
import com.google.gson.JsonObject;
import org.bukkit.Material;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.entity.EntityPickupItemEvent;
import org.bukkit.inventory.ItemStack;

import java.util.Set;

/**
 * Tracks valuable item pickups and broadcasts them to Eris.
 * Unlike ResourceMilestoneListener (which tracks firsts), this tracks ALL valuable pickups
 * to give Eris context about resource hoarding and strategies.
 */
public class InventoryListener implements Listener {

    private final DragonRunPlugin plugin;

    // Valuable items that Eris should know about
    private static final Set<Material> VALUABLE_ITEMS = Set.of(
            // Ores & Ingots
            Material.IRON_INGOT, Material.GOLD_INGOT, Material.DIAMOND,
            Material.EMERALD, Material.NETHERITE_INGOT, Material.NETHERITE_SCRAP,

            // Speedrun Critical
            Material.BLAZE_ROD, Material.ENDER_PEARL, Material.ENDER_EYE,
            Material.OBSIDIAN,

            // All bed colors for bed bombing
            Material.WHITE_BED, Material.ORANGE_BED, Material.MAGENTA_BED,
            Material.LIGHT_BLUE_BED, Material.YELLOW_BED, Material.LIME_BED,
            Material.PINK_BED, Material.GRAY_BED, Material.LIGHT_GRAY_BED,
            Material.CYAN_BED, Material.PURPLE_BED, Material.BLUE_BED,
            Material.BROWN_BED, Material.GREEN_BED, Material.RED_BED,
            Material.BLACK_BED,

            // Combat/Survival
            Material.GOLDEN_APPLE, Material.ENCHANTED_GOLDEN_APPLE,
            Material.TOTEM_OF_UNDYING, Material.SHIELD,

            // Potions
            Material.POTION, Material.SPLASH_POTION, Material.LINGERING_POTION,

            // Rare Finds
            Material.TRIDENT, Material.ELYTRA, Material.DRAGON_EGG,
            Material.NETHER_STAR, Material.HEART_OF_THE_SEA
    );

    public InventoryListener(DragonRunPlugin plugin) {
        this.plugin = plugin;
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onItemPickup(EntityPickupItemEvent event) {
        if (!(event.getEntity() instanceof Player player)) return;
        if (plugin.getDirectorServer() == null) return;

        // Ignore lobby world
        if (plugin.getWorldManager().isLobbyWorld(player.getWorld())) return;

        ItemStack item = event.getItem().getItemStack();
        Material type = item.getType();

        // Check if it's a valuable item OR has enchantments
        boolean isValuable = VALUABLE_ITEMS.contains(type);
        boolean isEnchanted = item.hasItemMeta() && item.getItemMeta().hasEnchants();

        if (!isValuable && !isEnchanted) return;

        // Build event data
        JsonObject data = new JsonObject();
        data.addProperty("player", player.getName());
        data.addProperty("playerUuid", player.getUniqueId().toString());
        data.addProperty("itemType", type.name());
        data.addProperty("quantity", item.getAmount());
        data.addProperty("dimension", player.getWorld().getEnvironment().name().toLowerCase());
        data.addProperty("isEnchanted", isEnchanted);

        plugin.getDirectorServer().broadcastEvent("item_collected", data);
    }
}
