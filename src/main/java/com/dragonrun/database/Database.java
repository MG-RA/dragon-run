package com.dragonrun.database;

import com.dragonrun.DragonRunPlugin;
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Statement;

public class Database {

    private final DragonRunPlugin plugin;
    private HikariDataSource dataSource;

    public Database(DragonRunPlugin plugin) {
        this.plugin = plugin;
    }

    public boolean connect() {
        DatabaseConfig config = DatabaseConfig.fromConfig(plugin.getConfig());

        // Explicitly load the PostgreSQL driver
        try {
            Class.forName("org.postgresql.Driver");
        } catch (ClassNotFoundException e) {
            plugin.getLogger().severe("PostgreSQL driver not found: " + e.getMessage());
            return false;
        }

        HikariConfig hikariConfig = new HikariConfig();
        hikariConfig.setDriverClassName("org.postgresql.Driver");
        hikariConfig.setJdbcUrl(String.format(
                "jdbc:postgresql://%s:%d/%s",
                config.getHost(),
                config.getPort(),
                config.getDatabase()
        ));
        hikariConfig.setUsername(config.getUsername());
        hikariConfig.setPassword(config.getPassword());

        // Pool settings per HikariCP best practices
        hikariConfig.setMaximumPoolSize(config.getMaxPoolSize());
        hikariConfig.setMinimumIdle(config.getMinIdle());
        hikariConfig.setConnectionTimeout(config.getConnectionTimeout());
        hikariConfig.setIdleTimeout(config.getIdleTimeout());
        hikariConfig.setMaxLifetime(config.getMaxLifetime());

        // PostgreSQL-specific optimizations
        hikariConfig.addDataSourceProperty("cachePrepStmts", "true");
        hikariConfig.addDataSourceProperty("prepStmtCacheSize", "250");
        hikariConfig.addDataSourceProperty("prepStmtCacheSqlLimit", "2048");

        // Connection validation
        hikariConfig.setConnectionTestQuery("SELECT 1");
        hikariConfig.setPoolName("DragonRunPool");

        try {
            dataSource = new HikariDataSource(hikariConfig);
            // Test connection
            try (Connection conn = dataSource.getConnection()) {
                plugin.getLogger().info("Database connected successfully!");
                return true;
            }
        } catch (Exception e) {
            plugin.getLogger().severe("Database connection failed: " + e.getMessage());
            return false;
        }
    }

    public Connection getConnection() throws SQLException {
        return dataSource.getConnection();
    }

    public void initializeSchema() {
        try (InputStream is = plugin.getResource("schema.sql")) {
            if (is == null) {
                plugin.getLogger().warning("schema.sql not found in resources!");
                return;
            }
            String schema = new String(is.readAllBytes(), StandardCharsets.UTF_8);
            try (Connection conn = getConnection();
                 Statement stmt = conn.createStatement()) {
                // Execute each statement separated by semicolons
                for (String sql : schema.split(";")) {
                    String trimmed = sql.trim();
                    if (!trimmed.isEmpty()) {
                        stmt.execute(trimmed);
                    }
                }
                plugin.getLogger().info("Database schema initialized.");
            }
        } catch (Exception e) {
            plugin.getLogger().severe("Failed to initialize schema: " + e.getMessage());
        }

        // Run migrations
        runMigrations();
    }

    private void runMigrations() {
        // Migration 001: Add world columns
        try (InputStream is = plugin.getResource("migrations/001_add_world_columns.sql")) {
            if (is == null) {
                plugin.getLogger().warning("Migration 001 not found, skipping");
                return;
            }
            String migration = new String(is.readAllBytes(), StandardCharsets.UTF_8);
            try (Connection conn = getConnection();
                 Statement stmt = conn.createStatement()) {
                for (String sql : migration.split(";")) {
                    String trimmed = sql.trim();
                    if (!trimmed.isEmpty()) {
                        stmt.execute(trimmed);
                    }
                }
                plugin.getLogger().info("Database migration 001 applied successfully.");
            }
        } catch (Exception e) {
            plugin.getLogger().warning("Migration 001 failed (may already be applied): " + e.getMessage());
        }
    }

    public void close() {
        if (dataSource != null && !dataSource.isClosed()) {
            dataSource.close();
            plugin.getLogger().info("Database connections closed.");
        }
    }
}
