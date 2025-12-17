package com.dragonrun.util;

public final class TimeUtil {

    private TimeUtil() {
        // Utility class
    }

    /**
     * Format duration in seconds to human-readable string
     * Examples: "45s", "2m 30s", "1h 15m 30s"
     */
    public static String formatDuration(long seconds) {
        if (seconds < 0) {
            return "0s";
        }

        if (seconds < 60) {
            return seconds + "s";
        } else if (seconds < 3600) {
            long minutes = seconds / 60;
            long secs = seconds % 60;
            return secs > 0 ? String.format("%dm %ds", minutes, secs) : String.format("%dm", minutes);
        } else {
            long hours = seconds / 3600;
            long minutes = (seconds % 3600) / 60;
            long secs = seconds % 60;

            if (secs > 0) {
                return String.format("%dh %dm %ds", hours, minutes, secs);
            } else if (minutes > 0) {
                return String.format("%dh %dm", hours, minutes);
            } else {
                return String.format("%dh", hours);
            }
        }
    }

    /**
     * Format duration in seconds to compact string
     * Examples: "0:45", "2:30", "1:15:30"
     */
    public static String formatDurationCompact(long seconds) {
        if (seconds < 0) {
            return "0:00";
        }

        if (seconds < 3600) {
            return String.format("%d:%02d", seconds / 60, seconds % 60);
        } else {
            return String.format("%d:%02d:%02d",
                    seconds / 3600,
                    (seconds % 3600) / 60,
                    seconds % 60);
        }
    }

    /**
     * Format milliseconds to duration string
     */
    public static String formatMillis(long millis) {
        return formatDuration(millis / 1000);
    }

    /**
     * Format milliseconds to compact duration string
     */
    public static String formatMillisCompact(long millis) {
        return formatDurationCompact(millis / 1000);
    }

    /**
     * Convert ticks to seconds (20 ticks = 1 second)
     */
    public static long ticksToSeconds(long ticks) {
        return ticks / 20;
    }

    /**
     * Convert seconds to ticks (20 ticks = 1 second)
     */
    public static long secondsToTicks(long seconds) {
        return seconds * 20;
    }

    /**
     * Get a relative time string (e.g., "5 minutes ago", "2 hours ago")
     */
    public static String getRelativeTime(long timestampMillis) {
        long now = System.currentTimeMillis();
        long diff = now - timestampMillis;

        if (diff < 0) {
            return "in the future";
        }

        long seconds = diff / 1000;
        if (seconds < 60) {
            return seconds == 1 ? "1 second ago" : seconds + " seconds ago";
        }

        long minutes = seconds / 60;
        if (minutes < 60) {
            return minutes == 1 ? "1 minute ago" : minutes + " minutes ago";
        }

        long hours = minutes / 60;
        if (hours < 24) {
            return hours == 1 ? "1 hour ago" : hours + " hours ago";
        }

        long days = hours / 24;
        if (days < 30) {
            return days == 1 ? "1 day ago" : days + " days ago";
        }

        long months = days / 30;
        if (months < 12) {
            return months == 1 ? "1 month ago" : months + " months ago";
        }

        long years = months / 12;
        return years == 1 ? "1 year ago" : years + " years ago";
    }
}
