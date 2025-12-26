package com.dragonrun.listeners;

import com.dragonrun.DragonRunPlugin;
import com.dragonrun.managers.GameState;
import com.dragonrun.util.MessageUtil;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.title.Title;
import org.bukkit.Bukkit;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.entity.Entity;
import org.bukkit.entity.Projectile;
import org.bukkit.event.entity.EntityDamageByEntityEvent;
import org.bukkit.event.entity.EntityDamageEvent;
import org.bukkit.event.entity.PlayerDeathEvent;

import java.time.Duration;
import java.util.List;
import java.util.Random;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

public class DeathListener implements Listener {

    private final DragonRunPlugin plugin;
    private final Random random = new Random();

    // Death roasts by damage type
    private static final List<String> FALL_ROASTS = List.of(
            "forgot how gravity works",
            "failed the vibe check with the ground",
            "thought they had MLG water (they didn't)"
    );

    private static final List<String> LAVA_ROASTS = List.of(
            "tried to swim in the forbidden orange juice",
            "took 'getting cooked' too literally"
    );

    private static final List<String> VOID_ROASTS = List.of(
            "went to the backrooms",
            "fell into the abyss (real)"
    );

    private static final List<String> DROWNING_ROASTS = List.of(
            "forgor they need oxygen",
            "went full NPC in water"
    );

    private static final List<String> EXPLOSION_ROASTS = List.of(
            "got ratio'd by a creeper",
            "received an explosive L"
    );

    private static final List<String> STARVATION_ROASTS = List.of(
            "forgor food exists",
            "was too busy to eat. Certified NPC."
    );

    private static final List<String> GENERIC_ROASTS = List.of(
            "simply wasn't him",
            "caught a stray",
            "got cooked fr fr",
            "had a skill issue"
    );

    public DeathListener(DragonRunPlugin plugin) {
        this.plugin = plugin;
    }

    @EventHandler(priority = EventPriority.HIGHEST)
    public void onPlayerDeath(PlayerDeathEvent event) {
        Player player = event.getEntity();
        UUID uuid = player.getUniqueId();
        String playerName = player.getName();

        // Ignore deaths in lobby world - only process hardcore deaths
        if (plugin.getWorldManager().isLobbyWorld(player.getWorld())) {
            event.deathMessage(null);
            return;
        }

        // Ignore deaths if run is not active
        if (plugin.getRunManager().getGameState() != GameState.ACTIVE) {
            event.deathMessage(null);
            return;
        }

        // 1. Get death cause
        String deathCause = getDeathCause(event);

        // 2. Check if this death was Eris-caused
        boolean isErisCaused = checkIfErisCaused(event);

        if (isErisCaused && plugin.getCausalityManager().canUseRespawn()) {
            // Eris-caused death - give Python time to respond with respawn override
            handleErisCausedDeath(event, player, uuid, playerName, deathCause);
        } else {
            // Normal death - process immediately
            processNormalDeath(event, player, uuid, playerName, deathCause);
        }
    }

    /**
     * Handle an Eris-caused death - give Python 500ms to respond with respawn override.
     */
    private void handleErisCausedDeath(PlayerDeathEvent event, Player player, UUID uuid, String playerName, String deathCause) {
        // Suppress vanilla death message
        event.deathMessage(null);

        // Store pending death
        plugin.getCausalityManager().setPendingErisDeath(uuid, deathCause, player.getLocation());

        // Send event to Python
        com.google.gson.JsonObject data = new com.google.gson.JsonObject();
        data.addProperty("player", playerName);
        data.addProperty("playerUuid", uuid.toString());
        data.addProperty("cause", deathCause);
        data.addProperty("isErisCaused", true);
        data.addProperty("respawnsRemaining", plugin.getCausalityManager().getRemainingRespawns());
        if (plugin.getDirectorServer() != null) {
            plugin.getDirectorServer().broadcastEvent("eris_caused_death", data);
        }

        plugin.getLogger().info("Eris-caused death detected for " + playerName + " - waiting 500ms for Python response");

        // Give Python 500ms to respond with respawn override
        Bukkit.getScheduler().runTaskLater(plugin, () -> {
            if (plugin.getCausalityManager().hasPendingDeath(uuid)) {
                // Python didn't intervene, proceed with normal death
                plugin.getLogger().info("No respawn override received for " + playerName + " - processing death normally");
                plugin.getCausalityManager().clearPendingDeath(uuid);
                processNormalDeathDelayed(player, uuid, playerName, deathCause);
            } else {
                plugin.getLogger().info("Respawn override was used for " + playerName);
            }
        }, 10L); // 10 ticks = 500ms
    }

    /**
     * Process a normal death immediately.
     */
    private void processNormalDeath(PlayerDeathEvent event, Player player, UUID uuid, String playerName, String deathCause) {
        String roast = getRoast(deathCause);

        // Send player_death event to Director AI FIRST (before run ends)
        if (plugin.getDirectorServer() != null) {
            com.google.gson.JsonObject data = new com.google.gson.JsonObject();
            data.addProperty("player", playerName);
            data.addProperty("playerUuid", uuid.toString());
            data.addProperty("cause", deathCause);
            data.addProperty("roast", roast);
            data.addProperty("isErisCaused", false);
            plugin.getDirectorServer().broadcastEvent("player_death", data);
        }

        // Remove aura based on death type
        int auraLoss = getAuraLoss(deathCause);
        plugin.getAuraManager().removeAura(uuid, auraLoss, "died (" + deathCause.toLowerCase() + ")");

        // Increment death count
        plugin.getAuraManager().incrementDeathCount(uuid);

        // Broadcast death with roast
        Component deathMessage = MessageUtil.deathAnnouncement(playerName, roast);
        Bukkit.broadcast(deathMessage);

        // Override vanilla death message
        event.deathMessage(null);

        // Process bets
        plugin.getBettingManager().processDeath(uuid);

        // End the run
        plugin.getRunManager().endRunByDeath(uuid);

        // Show reset countdown
        showResetCountdown(playerName);
    }

    /**
     * Process a death that was delayed waiting for Python response.
     */
    private void processNormalDeathDelayed(Player player, UUID uuid, String playerName, String deathCause) {
        String roast = getRoast(deathCause);

        // Send player_death event to Director AI FIRST (before run ends)
        if (plugin.getDirectorServer() != null) {
            com.google.gson.JsonObject data = new com.google.gson.JsonObject();
            data.addProperty("player", playerName);
            data.addProperty("playerUuid", uuid.toString());
            data.addProperty("cause", deathCause);
            data.addProperty("roast", roast);
            data.addProperty("isErisCaused", true);  // Was Eris-caused but Python didn't intervene
            plugin.getDirectorServer().broadcastEvent("player_death", data);
        }

        // Remove aura based on death type
        int auraLoss = getAuraLoss(deathCause);
        plugin.getAuraManager().removeAura(uuid, auraLoss, "died (" + deathCause.toLowerCase() + ")");

        // Increment death count
        plugin.getAuraManager().incrementDeathCount(uuid);

        // Broadcast death with roast
        Component deathMessage = MessageUtil.deathAnnouncement(playerName, roast);
        Bukkit.broadcast(deathMessage);

        // Process bets
        plugin.getBettingManager().processDeath(uuid);

        // End the run
        plugin.getRunManager().endRunByDeath(uuid);

        // Show reset countdown
        showResetCountdown(playerName);
    }

    /**
     * Check if a death was caused by Eris's interventions.
     */
    private boolean checkIfErisCaused(PlayerDeathEvent event) {
        EntityDamageEvent damageEvent = event.getEntity().getLastDamageCause();
        if (damageEvent == null) return false;

        var causalityManager = plugin.getCausalityManager();

        // Check entity attack (mobs spawned by Eris)
        if (damageEvent instanceof EntityDamageByEntityEvent entityDamage) {
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
        if (damageEvent.getCause() == EntityDamageEvent.DamageCause.BLOCK_EXPLOSION) {
            if (causalityManager.wasRecentErisTntNear(event.getEntity().getLocation())) {
                return true;
            }
        }

        // Check entity explosion (creeper spawned by Eris)
        if (damageEvent.getCause() == EntityDamageEvent.DamageCause.ENTITY_EXPLOSION) {
            if (damageEvent instanceof EntityDamageByEntityEvent entityDamage) {
                if (causalityManager.isErisCaused(entityDamage.getDamager())) {
                    return true;
                }
            }
        }

        // Check effects (poison, wither from Eris)
        if (damageEvent.getCause() == EntityDamageEvent.DamageCause.POISON ||
            damageEvent.getCause() == EntityDamageEvent.DamageCause.WITHER) {
            if (causalityManager.isErisEffect(event.getEntity().getUniqueId(),
                    damageEvent.getCause().name().toLowerCase())) {
                return true;
            }
        }

        // Check falling block (anvil, dripstone from Eris)
        if (damageEvent.getCause() == EntityDamageEvent.DamageCause.FALLING_BLOCK) {
            if (damageEvent instanceof EntityDamageByEntityEvent blockDamage) {
                if (causalityManager.isErisCaused(blockDamage.getDamager())) {
                    return true;
                }
            }
        }

        // Check lightning (from Eris)
        if (damageEvent.getCause() == EntityDamageEvent.DamageCause.LIGHTNING) {
            if (causalityManager.wasRecentErisLightningNear(event.getEntity().getLocation())) {
                return true;
            }
        }

        return false;
    }

    /**
     * Show visual reset countdown to all players.
     * The actual reset is handled by RunManager.endRunByDeath().
     */
    private void showResetCountdown(String playerName) {
        int delaySeconds = plugin.getConfig().getInt("game.reset-delay-seconds", 10);

        // Show title to all players
        Title resetTitle = Title.title(
                Component.text("RUN ENDED", MessageUtil.RESET_COLOR),
                Component.text(playerName + " got cooked - returning to lobby", MessageUtil.SUBTITLE_COLOR),
                Title.Times.times(
                        Duration.ZERO,
                        Duration.ofSeconds(delaySeconds),
                        Duration.ofMillis(500)
                )
        );

        for (Player p : Bukkit.getOnlinePlayers()) {
            p.showTitle(resetTitle);
        }

        // Countdown announcements starting at 5
        int countdownStart = Math.min(5, delaySeconds - 1);
        if (countdownStart > 0) {
            long delayUntilCountdown = (delaySeconds - countdownStart) * 1000L;
            Bukkit.getAsyncScheduler().runDelayed(plugin, task -> {
                broadcastCountdown(countdownStart);
            }, delayUntilCountdown, TimeUnit.MILLISECONDS);
        }
    }

    private void broadcastCountdown(int secondsRemaining) {
        if (secondsRemaining <= 0) return;

        Bukkit.broadcast(MessageUtil.countdownMessage(secondsRemaining));

        if (secondsRemaining > 1) {
            Bukkit.getAsyncScheduler().runDelayed(plugin, task -> {
                broadcastCountdown(secondsRemaining - 1);
            }, 1, TimeUnit.SECONDS);
        }
    }

    private String getDeathCause(PlayerDeathEvent event) {
        EntityDamageEvent damageCause = event.getEntity().getLastDamageCause();
        if (damageCause == null) return "UNKNOWN";

        return switch (damageCause.getCause()) {
            case FALL -> "FALL";
            case LAVA -> "LAVA";
            case FIRE, FIRE_TICK -> "FIRE";
            case DROWNING -> "DROWNING";
            case VOID -> "VOID";
            case STARVATION -> "STARVATION";
            case ENTITY_EXPLOSION, BLOCK_EXPLOSION -> "EXPLOSION";
            case ENTITY_ATTACK, ENTITY_SWEEP_ATTACK -> "MOB";
            case SUFFOCATION -> "SUFFOCATION";
            case CONTACT -> "CONTACT"; // Cactus, berry bush
            case MAGIC -> "MAGIC";
            case POISON -> "POISON";
            case WITHER -> "WITHER";
            case THORNS -> "THORNS";
            case CRAMMING -> "CRAMMING";
            case FLY_INTO_WALL -> "ELYTRA_CRASH";
            default -> "OTHER";
        };
    }

    private String getRoast(String deathCause) {
        if (!plugin.getConfig().getBoolean("death-messages.roasts", true)) {
            return "died";
        }

        List<String> roasts = switch (deathCause) {
            case "FALL" -> FALL_ROASTS;
            case "LAVA", "FIRE" -> LAVA_ROASTS;
            case "VOID" -> VOID_ROASTS;
            case "DROWNING" -> DROWNING_ROASTS;
            case "EXPLOSION" -> EXPLOSION_ROASTS;
            case "STARVATION" -> STARVATION_ROASTS;
            default -> GENERIC_ROASTS;
        };

        return roasts.get(random.nextInt(roasts.size()));
    }

    private int getAuraLoss(String deathCause) {
        return switch (deathCause) {
            case "VOID" -> 30;
            case "LAVA" -> 25;
            case "STARVATION" -> 50;
            case "DROWNING" -> 20;
            case "FALL" -> 15;
            case "CONTACT" -> 25; // Cactus/berry bush
            case "SUFFOCATION" -> 20; // Gravel
            default -> 20;
        };
    }
}
