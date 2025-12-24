package com.dragonrun.util;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import net.kyori.adventure.text.format.TextColor;
import net.kyori.adventure.text.format.TextDecoration;
import net.kyori.adventure.text.minimessage.MiniMessage;

public final class MessageUtil {

    // Color palette
    public static final TextColor AURA_COLOR = TextColor.color(0xAA55FF); // Purple
    public static final TextColor POSITIVE_COLOR = NamedTextColor.GREEN;
    public static final TextColor NEGATIVE_COLOR = NamedTextColor.RED;
    public static final TextColor RESET_COLOR = NamedTextColor.DARK_RED;
    public static final TextColor SUBTITLE_COLOR = NamedTextColor.GRAY;
    public static final TextColor PREFIX_COLOR = TextColor.color(0xFF5555);
    public static final TextColor GOLD_COLOR = NamedTextColor.GOLD;

    private static final Component PREFIX = Component.text()
            .append(Component.text("[", NamedTextColor.DARK_GRAY))
            .append(Component.text("DR", PREFIX_COLOR, TextDecoration.BOLD))
            .append(Component.text("] ", NamedTextColor.DARK_GRAY))
            .build();

    private MessageUtil() {
        // Utility class
    }

    /**
     * Create a prefixed message
     */
    public static Component prefixed(Component message) {
        return Component.text().append(PREFIX).append(message).build();
    }

    /**
     * Aura change notification for a player
     */
    public static Component auraChange(int amount, String reason) {
        MiniMessage mm = MiniMessage.miniMessage();
        String sign = amount >= 0 ? "+" : "";
        String color = amount >= 0 ? "<green>" : "<red>";

        return Component.text()
                .append(PREFIX)
                .append(mm.deserialize(color + "<b>" + sign + amount + "</b> <dark_purple>aura</dark_purple> <gray>(" + reason + ")"))
                .build();
    }

    /**
     * Broadcast message for significant aura gain
     */
    public static Component auraBroadcastGain(String playerName, int amount, String reason) {
        MiniMessage mm = MiniMessage.miniMessage();
        return Component.text()
                .append(PREFIX)
                .append(mm.deserialize("<white>" + playerName + "</white> <gray>gained</gray> <green><b>+" + amount + "</b></green> <dark_purple>aura</dark_purple> <gray>(" + reason + ")"))
                .build();
    }

    /**
     * Broadcast message for significant aura loss
     */
    public static Component auraBroadcastLoss(String playerName, int amount, String reason) {
        MiniMessage mm = MiniMessage.miniMessage();
        return Component.text()
                .append(PREFIX)
                .append(mm.deserialize("<white>" + playerName + "</white> <gray>lost</gray> <red><b>-" + amount + "</b></red> <dark_purple>aura</dark_purple> <gray>(" + reason + ")"))
                .build();
    }

    /**
     * Death announcement with roast
     */
    public static Component deathAnnouncement(String playerName, String roast) {
        return Component.text()
                .append(Component.newline())
                .append(Component.text("  ", NEGATIVE_COLOR))
                .append(Component.text(playerName, NamedTextColor.WHITE, TextDecoration.BOLD))
                .append(Component.text(" " + roast, NamedTextColor.GRAY))
                .append(Component.newline())
                .append(Component.text("  WORLD RESETTING...", RESET_COLOR, TextDecoration.BOLD))
                .append(Component.newline())
                .build();
    }

    /**
     * Countdown message
     */
    public static Component countdownMessage(int seconds) {
        return Component.text()
                .append(PREFIX)
                .append(Component.text("Reset in ", NamedTextColor.GRAY))
                .append(Component.text(String.valueOf(seconds), NEGATIVE_COLOR, TextDecoration.BOLD))
                .append(Component.text("...", NamedTextColor.GRAY))
                .build();
    }

    /**
     * Kick message when world resets
     */
    public static Component kickMessage(String causePlayer) {
        return Component.text()
                .append(Component.text("WORLD RESET", RESET_COLOR, TextDecoration.BOLD))
                .append(Component.newline())
                .append(Component.newline())
                .append(Component.text(causePlayer + " got cooked.", NamedTextColor.GRAY))
                .append(Component.newline())
                .append(Component.text("GG go next.", NamedTextColor.WHITE))
                .build();
    }

    /**
     * Player join message with aura
     */
    public static Component joinMessage(String playerName, int aura) {
        TextColor auraColor = aura >= 0 ? AURA_COLOR : NEGATIVE_COLOR;
        return Component.text()
                .append(PREFIX)
                .append(Component.text(playerName, NamedTextColor.WHITE))
                .append(Component.text(" joined ", NamedTextColor.GRAY))
                .append(Component.text("[", NamedTextColor.DARK_GRAY))
                .append(Component.text(aura + " aura", auraColor))
                .append(Component.text("]", NamedTextColor.DARK_GRAY))
                .build();
    }

    /**
     * Player quit message
     */
    public static Component quitMessage(String playerName) {
        return Component.text()
                .append(PREFIX)
                .append(Component.text(playerName, NamedTextColor.WHITE))
                .append(Component.text(" left", NamedTextColor.GRAY))
                .build();
    }

    /**
     * Dragon killed announcement
     */
    public static Component dragonKilledAnnouncement(String killerName, long durationSeconds) {
        String duration = TimeUtil.formatDuration(durationSeconds);
        return Component.text()
                .append(Component.newline())
                .append(Component.text("  DRAGON DOWN ", GOLD_COLOR, TextDecoration.BOLD))
                .append(Component.newline())
                .append(Component.newline())
                .append(Component.text("  " + killerName, NamedTextColor.WHITE, TextDecoration.BOLD))
                .append(Component.text(" KILLED THE ENDER DRAGON", GOLD_COLOR))
                .append(Component.newline())
                .append(Component.newline())
                .append(Component.text("  Run Duration: ", NamedTextColor.GRAY))
                .append(Component.text(duration, NamedTextColor.WHITE))
                .append(Component.newline())
                .append(Component.text("  GGs in chat only", NamedTextColor.GRAY, TextDecoration.ITALIC))
                .append(Component.newline())
                .build();
    }

    /**
     * Achievement unlocked message
     */
    public static Component achievementUnlocked(String playerName, String achievementName,
                                                 String description, int auraChange) {
        TextColor auraColor = auraChange >= 0 ? POSITIVE_COLOR : NEGATIVE_COLOR;
        String sign = auraChange >= 0 ? "+" : "";
        String header = auraChange >= 0 ? "ACHIEVEMENT UNLOCKED!" : "ACHIEVEMENT UNLOCKED (DEROGATORY)";

        return Component.text()
                .append(PREFIX)
                .append(Component.text(header, GOLD_COLOR, TextDecoration.BOLD))
                .append(Component.newline())
                .append(PREFIX)
                .append(Component.text(playerName, NamedTextColor.WHITE))
                .append(Component.text(" earned ", NamedTextColor.GRAY))
                .append(Component.text(achievementName, GOLD_COLOR))
                .append(Component.newline())
                .append(PREFIX)
                .append(Component.text("\"" + description + "\"", NamedTextColor.GRAY, TextDecoration.ITALIC))
                .append(Component.newline())
                .append(PREFIX)
                .append(Component.text("Aura: ", NamedTextColor.GRAY))
                .append(Component.text(sign + auraChange, auraColor, TextDecoration.BOLD))
                .build();
    }

    /**
     * Simple error message
     */
    public static Component error(String message) {
        return Component.text()
                .append(PREFIX)
                .append(Component.text(message, NEGATIVE_COLOR))
                .build();
    }

    /**
     * Simple success message
     */
    public static Component success(String message) {
        return Component.text()
                .append(PREFIX)
                .append(Component.text(message, POSITIVE_COLOR))
                .build();
    }

    /**
     * Simple info message
     */
    public static Component info(String message) {
        return Component.text()
                .append(PREFIX)
                .append(Component.text(message, NamedTextColor.GRAY))
                .build();
    }
}
