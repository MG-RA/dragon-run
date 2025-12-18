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

        // 1. Get death cause and roast
        String deathCause = getDeathCause(event);
        String roast = getRoast(deathCause);

        // 2. Remove aura based on death type
        int auraLoss = getAuraLoss(deathCause);
        plugin.getAuraManager().removeAura(uuid, auraLoss, "died (" + deathCause.toLowerCase() + ")");

        // 3. Increment death count
        plugin.getAuraManager().incrementDeathCount(uuid);

        // 4. Broadcast death with roast
        Component deathMessage = MessageUtil.deathAnnouncement(playerName, roast);
        Bukkit.broadcast(deathMessage);

        // 5. Override vanilla death message
        event.deathMessage(null);

        // 6. Process bets (all bets on deceased are lost, deceased bets are cleared)
        plugin.getBettingManager().processDeath(uuid);

        // 7. End the run (handles teleport to lobby and world cleanup)
        plugin.getRunManager().endRunByDeath(uuid);

        // 8. Show reset countdown (visual only - RunManager handles actual reset)
        showResetCountdown(playerName);
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
