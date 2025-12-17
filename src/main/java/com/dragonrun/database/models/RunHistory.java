package com.dragonrun.database.models;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.util.UUID;

public class RunHistory {
    private final int runId;
    private final Timestamp startedAt;
    private final Timestamp endedAt;
    private final Integer durationSeconds;
    private final String outcome;
    private final UUID endedByUuid;
    private final UUID dragonKillerUuid;
    private final int peakPlayers;

    private RunHistory(int runId, Timestamp startedAt, Timestamp endedAt,
                       Integer durationSeconds, String outcome, UUID endedByUuid,
                       UUID dragonKillerUuid, int peakPlayers) {
        this.runId = runId;
        this.startedAt = startedAt;
        this.endedAt = endedAt;
        this.durationSeconds = durationSeconds;
        this.outcome = outcome;
        this.endedByUuid = endedByUuid;
        this.dragonKillerUuid = dragonKillerUuid;
        this.peakPlayers = peakPlayers;
    }

    public static RunHistory fromResultSet(ResultSet rs) throws SQLException {
        String endedByStr = rs.getString("ended_by_uuid");
        String dragonKillerStr = rs.getString("dragon_killer_uuid");

        return new RunHistory(
                rs.getInt("run_id"),
                rs.getTimestamp("started_at"),
                rs.getTimestamp("ended_at"),
                rs.getObject("duration_seconds") != null ? rs.getInt("duration_seconds") : null,
                rs.getString("outcome"),
                endedByStr != null ? UUID.fromString(endedByStr) : null,
                dragonKillerStr != null ? UUID.fromString(dragonKillerStr) : null,
                rs.getInt("peak_players")
        );
    }

    // Getters
    public int getRunId() {
        return runId;
    }

    public Timestamp getStartedAt() {
        return startedAt;
    }

    public Timestamp getEndedAt() {
        return endedAt;
    }

    public Integer getDurationSeconds() {
        return durationSeconds;
    }

    public String getOutcome() {
        return outcome;
    }

    public UUID getEndedByUuid() {
        return endedByUuid;
    }

    public UUID getDragonKillerUuid() {
        return dragonKillerUuid;
    }

    public int getPeakPlayers() {
        return peakPlayers;
    }

    public boolean isCompleted() {
        return endedAt != null;
    }

    public boolean wasSuccessful() {
        return "DRAGON_KILLED".equals(outcome);
    }
}
