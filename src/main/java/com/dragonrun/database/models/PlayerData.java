package com.dragonrun.database.models;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.util.UUID;

public class PlayerData {
    private final UUID uuid;
    private final String username;
    private final int aura;
    private final int totalRuns;
    private final int totalDeaths;
    private final int dragonsKilled;
    private final String equippedTitle;
    private final Timestamp firstJoined;
    private final Timestamp lastSeen;

    private PlayerData(Builder builder) {
        this.uuid = builder.uuid;
        this.username = builder.username;
        this.aura = builder.aura;
        this.totalRuns = builder.totalRuns;
        this.totalDeaths = builder.totalDeaths;
        this.dragonsKilled = builder.dragonsKilled;
        this.equippedTitle = builder.equippedTitle;
        this.firstJoined = builder.firstJoined;
        this.lastSeen = builder.lastSeen;
    }

    public static PlayerData fromResultSet(ResultSet rs) throws SQLException {
        return new Builder()
                .uuid(UUID.fromString(rs.getString("uuid")))
                .username(rs.getString("username"))
                .aura(rs.getInt("aura"))
                .totalRuns(rs.getInt("total_runs"))
                .totalDeaths(rs.getInt("total_deaths"))
                .dragonsKilled(rs.getInt("dragons_killed"))
                .equippedTitle(rs.getString("equipped_title"))
                .firstJoined(rs.getTimestamp("first_joined"))
                .lastSeen(rs.getTimestamp("last_seen"))
                .build();
    }

    // Getters
    public UUID getUuid() {
        return uuid;
    }

    public String getUsername() {
        return username;
    }

    public int getAura() {
        return aura;
    }

    public int getTotalRuns() {
        return totalRuns;
    }

    public int getTotalDeaths() {
        return totalDeaths;
    }

    public int getDragonsKilled() {
        return dragonsKilled;
    }

    public String getEquippedTitle() {
        return equippedTitle;
    }

    public Timestamp getFirstJoined() {
        return firstJoined;
    }

    public Timestamp getLastSeen() {
        return lastSeen;
    }

    public static class Builder {
        private UUID uuid;
        private String username;
        private int aura;
        private int totalRuns;
        private int totalDeaths;
        private int dragonsKilled;
        private String equippedTitle;
        private Timestamp firstJoined;
        private Timestamp lastSeen;

        public Builder uuid(UUID uuid) {
            this.uuid = uuid;
            return this;
        }

        public Builder username(String username) {
            this.username = username;
            return this;
        }

        public Builder aura(int aura) {
            this.aura = aura;
            return this;
        }

        public Builder totalRuns(int totalRuns) {
            this.totalRuns = totalRuns;
            return this;
        }

        public Builder totalDeaths(int totalDeaths) {
            this.totalDeaths = totalDeaths;
            return this;
        }

        public Builder dragonsKilled(int dragonsKilled) {
            this.dragonsKilled = dragonsKilled;
            return this;
        }

        public Builder equippedTitle(String equippedTitle) {
            this.equippedTitle = equippedTitle;
            return this;
        }

        public Builder firstJoined(Timestamp firstJoined) {
            this.firstJoined = firstJoined;
            return this;
        }

        public Builder lastSeen(Timestamp lastSeen) {
            this.lastSeen = lastSeen;
            return this;
        }

        public PlayerData build() {
            return new PlayerData(this);
        }
    }
}
