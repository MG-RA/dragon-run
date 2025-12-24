package com.dragonrun.listeners;

import com.dragonrun.DragonRunPlugin;
import com.google.gson.JsonObject;
import org.bukkit.advancement.Advancement;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.player.PlayerAdvancementDoneEvent;

import java.util.Map;
import java.util.Set;

/**
 * Tracks Minecraft vanilla advancements and sends relevant ones to Eris.
 * Different from custom DragonRun achievements - these are vanilla game progress.
 * Only tracks advancements that indicate meaningful progression.
 */
public class MinecraftAdvancementListener implements Listener {

    private final DragonRunPlugin plugin;

    // Advancements that matter for speedrun context
    // Format: advancement key -> friendly name
    private static final Map<String, String> NOTABLE_ADVANCEMENTS = Map.ofEntries(
        // Story progression (critical path)
        Map.entry("minecraft:story/mine_stone", "Stone Age"),
        Map.entry("minecraft:story/upgrade_tools", "Getting an Upgrade"),
        Map.entry("minecraft:story/smelt_iron", "Acquire Hardware"),
        Map.entry("minecraft:story/obtain_armor", "Suit Up"),
        Map.entry("minecraft:story/lava_bucket", "Hot Stuff"),
        Map.entry("minecraft:story/iron_tools", "Isn't It Iron Pick"),
        Map.entry("minecraft:story/deflect_arrow", "Not Today, Thank You"),
        Map.entry("minecraft:story/form_obsidian", "Ice Bucket Challenge"),
        Map.entry("minecraft:story/mine_diamond", "Diamonds!"),
        Map.entry("minecraft:story/enter_the_nether", "We Need to Go Deeper"),
        Map.entry("minecraft:story/shiny_gear", "Cover Me with Diamonds"),
        Map.entry("minecraft:story/enchant_item", "Enchanter"),
        Map.entry("minecraft:story/cure_zombie_villager", "Zombie Doctor"),
        Map.entry("minecraft:story/follow_ender_eye", "Eye Spy"),
        Map.entry("minecraft:story/enter_the_end", "The End?"),

        // Nether progression
        Map.entry("minecraft:nether/return_to_sender", "Return to Sender"),
        Map.entry("minecraft:nether/find_bastion", "Those Were the Days"),
        Map.entry("minecraft:nether/obtain_blaze_rod", "Into Fire"),
        Map.entry("minecraft:nether/get_wither_skull", "Spooky Scary Skeleton"),
        Map.entry("minecraft:nether/obtain_crying_obsidian", "Who is Cutting Onions?"),
        Map.entry("minecraft:nether/distract_piglin", "Oh Shiny"),
        Map.entry("minecraft:nether/ride_strider", "This Boat Has Legs"),
        Map.entry("minecraft:nether/loot_bastion", "War Pigs"),
        Map.entry("minecraft:nether/find_fortress", "A Terrible Fortress"),
        Map.entry("minecraft:nether/fast_travel", "Subspace Bubble"),
        Map.entry("minecraft:nether/summon_wither", "Withering Heights"),
        Map.entry("minecraft:nether/brew_potion", "Local Brewery"),
        Map.entry("minecraft:nether/create_beacon", "Bring Home the Beacon"),
        Map.entry("minecraft:nether/all_potions", "A Furious Cocktail"),
        Map.entry("minecraft:nether/create_full_beacon", "Beaconator"),
        Map.entry("minecraft:nether/all_effects", "How Did We Get Here?"),
        Map.entry("minecraft:nether/netherite_armor", "Cover Me in Debris"),
        Map.entry("minecraft:nether/explore_nether", "Hot Tourist Destinations"),
        Map.entry("minecraft:nether/use_lodestone", "Country Lode, Take Me Home"),
        Map.entry("minecraft:nether/charge_respawn_anchor", "Not Quite \"Nine\" Lives"),
        Map.entry("minecraft:nether/uneasy_alliance", "Uneasy Alliance"),

        // End progression
        Map.entry("minecraft:end/kill_dragon", "Free the End"),
        Map.entry("minecraft:end/dragon_egg", "The Next Generation"),
        Map.entry("minecraft:end/enter_end_gateway", "Remote Getaway"),
        Map.entry("minecraft:end/respawn_dragon", "The End... Again..."),
        Map.entry("minecraft:end/dragon_breath", "You Need a Mint"),
        Map.entry("minecraft:end/find_end_city", "The City at the End of the Game"),
        Map.entry("minecraft:end/elytra", "Sky's the Limit"),
        Map.entry("minecraft:end/levitate", "Great View From Up Here"),

        // Adventure (combat/exploration)
        Map.entry("minecraft:adventure/kill_a_mob", "Monster Hunter"),
        Map.entry("minecraft:adventure/trade", "What a Deal!"),
        Map.entry("minecraft:adventure/sleep_in_bed", "Sweet Dreams"),
        Map.entry("minecraft:adventure/shoot_arrow", "Take Aim"),
        Map.entry("minecraft:adventure/kill_all_mobs", "Monsters Hunted"),
        Map.entry("minecraft:adventure/totem_of_undying", "Postmortal"),
        Map.entry("minecraft:adventure/summon_iron_golem", "Hired Help"),
        Map.entry("minecraft:adventure/voluntary_exile", "Voluntary Exile"),
        Map.entry("minecraft:adventure/hero_of_the_village", "Hero of the Village"),
        Map.entry("minecraft:adventure/arbalistic", "Arbalistic"),
        Map.entry("minecraft:adventure/two_birds_one_arrow", "Two Birds, One Arrow"),
        Map.entry("minecraft:adventure/whos_the_pillager_now", "Who's the Pillager Now?"),
        Map.entry("minecraft:adventure/adventuring_time", "Adventuring Time"),
        Map.entry("minecraft:adventure/very_very_frightening", "Very Very Frightening"),
        Map.entry("minecraft:adventure/sniper_duel", "Sniper Duel"),
        Map.entry("minecraft:adventure/bullseye", "Bullseye"),
        Map.entry("minecraft:adventure/lightning_rod_with_villager_no_fire", "Surge Protector"),
        Map.entry("minecraft:adventure/fall_from_world_height", "Caves & Cliffs"),
        Map.entry("minecraft:adventure/walk_on_powder_snow_with_leather_boots", "Light as a Rabbit"),
        Map.entry("minecraft:adventure/spyglass_at_parrot", "Is It a Bird?"),
        Map.entry("minecraft:adventure/spyglass_at_ghast", "Is It a Balloon?"),
        Map.entry("minecraft:adventure/spyglass_at_dragon", "Is It a Plane?"),
        Map.entry("minecraft:adventure/kill_mob_near_sculk_catalyst", "It Spreads"),
        Map.entry("minecraft:adventure/avoid_vibration", "Sneak 100"),
        Map.entry("minecraft:adventure/salvage_sherd", "Respecting the Remnants"),
        Map.entry("minecraft:adventure/craft_decorated_pot_using_only_sherds", "Careful Restoration"),
        Map.entry("minecraft:adventure/read_power_of_chiseled_bookshelf", "The Power of Books"),
        Map.entry("minecraft:adventure/trim_with_any_armor_pattern", "Crafting a New Look"),
        Map.entry("minecraft:adventure/trim_with_all_exclusive_armor_patterns", "Smithing with Style")
    );

    // Priority levels for different advancement categories
    private static final Map<String, String> CATEGORY_PRIORITY = Map.of(
        "story", "medium",
        "nether", "medium",
        "end", "high",
        "adventure", "low"
    );

    // Critical advancements that are speedrun milestones
    private static final Set<String> CRITICAL_ADVANCEMENTS = Set.of(
        "minecraft:story/enter_the_nether",
        "minecraft:nether/obtain_blaze_rod",
        "minecraft:nether/find_fortress",
        "minecraft:story/follow_ender_eye",
        "minecraft:story/enter_the_end",
        "minecraft:end/kill_dragon"
    );

    public MinecraftAdvancementListener(DragonRunPlugin plugin) {
        this.plugin = plugin;
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onAdvancement(PlayerAdvancementDoneEvent event) {
        if (plugin.getDirectorServer() == null) return;

        Advancement advancement = event.getAdvancement();
        String advancementKey = advancement.getKey().toString();

        // Only track notable advancements
        if (!NOTABLE_ADVANCEMENTS.containsKey(advancementKey)) return;

        Player player = event.getPlayer();

        // Ignore lobby world
        if (plugin.getWorldManager().isLobbyWorld(player.getWorld())) return;

        String friendlyName = NOTABLE_ADVANCEMENTS.get(advancementKey);
        String category = getCategory(advancementKey);
        String priority = CRITICAL_ADVANCEMENTS.contains(advancementKey) ? "critical" :
                         CATEGORY_PRIORITY.getOrDefault(category, "low");

        // Build and send event
        JsonObject data = new JsonObject();
        data.addProperty("player", player.getName());
        data.addProperty("playerUuid", player.getUniqueId().toString());
        data.addProperty("advancementKey", advancementKey);
        data.addProperty("advancementName", friendlyName);
        data.addProperty("category", category);
        data.addProperty("priority", priority);
        data.addProperty("isCritical", CRITICAL_ADVANCEMENTS.contains(advancementKey));
        data.addProperty("dimension", player.getWorld().getEnvironment().name().toLowerCase());

        plugin.getDirectorServer().broadcastEvent("advancement_made", data);

        // Log critical advancements
        if (CRITICAL_ADVANCEMENTS.contains(advancementKey)) {
            plugin.getLogger().info("🏆 " + player.getName() + " achieved: " + friendlyName);
        }
    }

    /**
     * Get the category from an advancement key.
     */
    private String getCategory(String advancementKey) {
        // Format: minecraft:category/name
        String[] parts = advancementKey.split(":");
        if (parts.length < 2) return "unknown";

        String[] pathParts = parts[1].split("/");
        if (pathParts.length < 1) return "unknown";

        return pathParts[0];
    }
}
