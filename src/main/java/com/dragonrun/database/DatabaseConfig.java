package com.dragonrun.database;

import org.bukkit.configuration.file.FileConfiguration;

public class DatabaseConfig {
    private final String host;
    private final int port;
    private final String database;
    private final String username;
    private final String password;
    private final int maxPoolSize;
    private final int minIdle;
    private final long connectionTimeout;
    private final long idleTimeout;
    private final long maxLifetime;

    private DatabaseConfig(String host, int port, String database, String username,
                           String password, int maxPoolSize, int minIdle,
                           long connectionTimeout, long idleTimeout, long maxLifetime) {
        this.host = host;
        this.port = port;
        this.database = database;
        this.username = username;
        this.password = password;
        this.maxPoolSize = maxPoolSize;
        this.minIdle = minIdle;
        this.connectionTimeout = connectionTimeout;
        this.idleTimeout = idleTimeout;
        this.maxLifetime = maxLifetime;
    }

    public static DatabaseConfig fromConfig(FileConfiguration config) {
        return new DatabaseConfig(
                config.getString("database.host", "localhost"),
                config.getInt("database.port", 5432),
                config.getString("database.name", "dragonrun"),
                config.getString("database.user", "dragonrun"),
                config.getString("database.password", "changeme"),
                config.getInt("database.pool.maximum-size", 10),
                config.getInt("database.pool.minimum-idle", 2),
                config.getLong("database.pool.connection-timeout", 30000),
                config.getLong("database.pool.idle-timeout", 600000),
                config.getLong("database.pool.max-lifetime", 1800000)
        );
    }

    public String getHost() {
        return host;
    }

    public int getPort() {
        return port;
    }

    public String getDatabase() {
        return database;
    }

    public String getUsername() {
        return username;
    }

    public String getPassword() {
        return password;
    }

    public int getMaxPoolSize() {
        return maxPoolSize;
    }

    public int getMinIdle() {
        return minIdle;
    }

    public long getConnectionTimeout() {
        return connectionTimeout;
    }

    public long getIdleTimeout() {
        return idleTimeout;
    }

    public long getMaxLifetime() {
        return maxLifetime;
    }
}
