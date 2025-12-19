package com.dragonrun.websocket.models;

import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.PlayerInventory;

import java.util.UUID;

/**
 * Snapshot of a player's current state for Director AI.
 */
public class PlayerStateSnapshot {
    private final UUID uuid;
    private final String username;
    private final double health;
    private final double maxHealth;
    private final int foodLevel;
    private final float saturation;
    private final String dimension;
    private final LocationData location;
    private final String gameMode;

    // Inventory summary
    private final int diamondCount;
    private final int enderPearlCount;
    private final boolean hasElytra;
    private final String armorTier;

    // Current stats (will be populated from achievement listener data if available)
    private int mobKills;
    private long aliveSeconds;
    private boolean enteredNether;
    private boolean enteredEnd;
    private int aura;

    public PlayerStateSnapshot(Player player) {
        this.uuid = player.getUniqueId();
        this.username = player.getName();
        this.health = player.getHealth();
        this.maxHealth = player.getMaxHealth();
        this.foodLevel = player.getFoodLevel();
        this.saturation = player.getSaturation();
        this.dimension = getDimensionName(player.getWorld().getName());
        this.location = new LocationData(player.getLocation());
        this.gameMode = player.getGameMode().name();

        // Analyze inventory
        PlayerInventory inv = player.getInventory();
        this.diamondCount = countItem(inv, Material.DIAMOND);
        this.enderPearlCount = countItem(inv, Material.ENDER_PEARL);
        this.hasElytra = inv.contains(Material.ELYTRA);
        this.armorTier = determineArmorTier(inv);

        // Stats will be set separately
        this.mobKills = 0;
        this.aliveSeconds = 0;
        this.enteredNether = false;
        this.enteredEnd = false;
        this.aura = 0;
    }

    private String getDimensionName(String worldName) {
        if (worldName.contains("nether")) return "nether";
        if (worldName.contains("end")) return "end";
        return "overworld";
    }

    private int countItem(PlayerInventory inv, Material material) {
        int count = 0;
        for (ItemStack item : inv.getContents()) {
            if (item != null && item.getType() == material) {
                count += item.getAmount();
            }
        }
        return count;
    }

    private String determineArmorTier(PlayerInventory inv) {
        ItemStack chestplate = inv.getChestplate();
        if (chestplate == null) return "none";

        Material type = chestplate.getType();
        if (type == Material.NETHERITE_CHESTPLATE) return "netherite";
        if (type == Material.DIAMOND_CHESTPLATE) return "diamond";
        if (type == Material.IRON_CHESTPLATE) return "iron";
        if (type == Material.CHAINMAIL_CHESTPLATE) return "chainmail";
        if (type == Material.GOLDEN_CHESTPLATE) return "gold";
        if (type == Material.LEATHER_CHESTPLATE) return "leather";

        return "none";
    }

    // Setters for stats that come from other sources
    public void setMobKills(int mobKills) {
        this.mobKills = mobKills;
    }

    public void setAliveSeconds(long aliveSeconds) {
        this.aliveSeconds = aliveSeconds;
    }

    public void setEnteredNether(boolean enteredNether) {
        this.enteredNether = enteredNether;
    }

    public void setEnteredEnd(boolean enteredEnd) {
        this.enteredEnd = enteredEnd;
    }

    public void setAura(int aura) {
        this.aura = aura;
    }

    // Getters
    public UUID getUuid() { return uuid; }
    public String getUsername() { return username; }
    public double getHealth() { return health; }
    public double getMaxHealth() { return maxHealth; }
    public int getFoodLevel() { return foodLevel; }
    public float getSaturation() { return saturation; }
    public String getDimension() { return dimension; }
    public LocationData getLocation() { return location; }
    public String getGameMode() { return gameMode; }
    public int getDiamondCount() { return diamondCount; }
    public int getEnderPearlCount() { return enderPearlCount; }
    public boolean hasElytra() { return hasElytra; }
    public String getArmorTier() { return armorTier; }
    public int getMobKills() { return mobKills; }
    public long getAliveSeconds() { return aliveSeconds; }
    public boolean hasEnteredNether() { return enteredNether; }
    public boolean hasEnteredEnd() { return enteredEnd; }
    public int getAura() { return aura; }

    /**
     * Simple location data class for JSON serialization.
     */
    public static class LocationData {
        private final double x;
        private final double y;
        private final double z;

        public LocationData(Location loc) {
            this.x = Math.round(loc.getX() * 10.0) / 10.0; // Round to 1 decimal
            this.y = Math.round(loc.getY() * 10.0) / 10.0;
            this.z = Math.round(loc.getZ() * 10.0) / 10.0;
        }

        public double getX() { return x; }
        public double getY() { return y; }
        public double getZ() { return z; }
    }
}
