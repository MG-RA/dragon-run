"""Configuration models with validation for Eris AI Director."""

from pathlib import Path

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings


class WebSocketConfig(BaseModel):
    """WebSocket connection settings."""

    uri: str = "ws://localhost:8765"
    # Reconnection settings (exponential backoff)
    reconnect_base_delay: float = Field(default=1.0, ge=0.5, le=10.0)
    reconnect_max_delay: float = Field(default=30.0, ge=5.0, le=300.0)
    reconnect_jitter: float = Field(default=0.1, ge=0.0, le=0.5)
    # Heartbeat settings (ping/pong for dead connection detection)
    ping_interval: float = Field(default=10.0, ge=5.0, le=60.0)
    ping_timeout: float = Field(default=5.0, ge=2.0, le=30.0)
    # Command queue settings
    command_queue_max_size: int = Field(default=100, ge=10, le=1000)
    command_timeout: float = Field(default=10.0, ge=2.0, le=60.0)


class DatabaseConfig(BaseModel):
    """PostgreSQL database settings."""

    host: str = "localhost"
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = "dragonrun"
    user: str = "postgres"
    password: str = "postgres"
    pool_min: int = Field(default=1, ge=1, le=10)
    pool_max: int = Field(default=5, ge=1, le=20)
    connect_timeout: float = Field(default=10.0, ge=1.0, le=60.0)


class OllamaConfig(BaseModel):
    """Ollama LLM settings."""

    host: str = "http://localhost:11434"
    model: str = "ministral-3:14b"
    temperature: float = Field(default=0.15, ge=0.0, le=2.0)
    keep_alive: str = "30m"
    context_window: int = Field(default=32768, ge=2048, le=131072)
    timeout: float = Field(default=30.0, ge=5.0, le=120.0)


class DebounceConfig(BaseModel):
    """Event debouncing settings."""

    state: float = Field(default=15.0, ge=1.0, le=60.0)
    player_damaged: float = Field(default=5.0, ge=1.0, le=30.0)
    resource_milestone: float = Field(default=3.0, ge=1.0, le=30.0)


class EventProcessorConfig(BaseModel):
    """Event processing settings."""

    debounce: DebounceConfig = Field(default_factory=DebounceConfig)
    queue_max_size: int = Field(default=1000, ge=100, le=10000)


class MemoryConfig(BaseModel):
    """Memory management settings."""

    short_term_max_tokens: int = Field(default=25000, ge=1000, le=100000)
    chat_buffer_size: int = Field(default=50, ge=10, le=200)
    max_events_in_context: int = Field(default=30, ge=5, le=100)


class ErisBehaviorConfig(BaseModel):
    """Eris personality and behavior settings."""

    mask_stability: float = Field(default=0.7, ge=0.0, le=1.0)
    mask_stability_decay: float = Field(default=0.05, ge=0.0, le=0.5)
    min_stability: float = Field(default=0.3, ge=0.0, le=1.0)
    speech_cooldown: float = Field(default=5.0, ge=0.0, le=60.0)
    idle_check_interval: float = Field(default=45.0, ge=10.0, le=300.0)
    min_idle_time: float = Field(default=90.0, ge=30.0, le=600.0)


class GraphConfig(BaseModel):
    """LangGraph execution settings."""

    invoke_timeout: float = Field(default=60.0, ge=10.0, le=300.0)
    max_retries: int = Field(default=2, ge=0, le=5)


class LoggingConfig(BaseModel):
    """Logging settings."""

    level: str = Field(default="INFO")
    format: str = Field(default="%(asctime)s | %(name)s | %(levelname)s | %(message)s")
    json_mode: bool = Field(default=False)

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid}")
        return v.upper()


class ErisConfig(BaseSettings):
    """Root configuration for Eris AI Director.

    Loads from config.yaml with environment variable overrides.
    Environment variables use ERIS_ prefix (e.g., ERIS_DATABASE__HOST).
    """

    websocket: WebSocketConfig = Field(default_factory=WebSocketConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    event_processor: EventProcessorConfig = Field(default_factory=EventProcessorConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    eris: ErisBehaviorConfig = Field(default_factory=ErisBehaviorConfig)
    graph: GraphConfig = Field(default_factory=GraphConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    model_config = {
        "env_prefix": "ERIS_",
        "env_nested_delimiter": "__",
    }

    @classmethod
    def load(cls, config_path: Path | None = None) -> "ErisConfig":
        """Load configuration from YAML file with env overrides.

        Args:
            config_path: Path to config.yaml. If None, uses defaults.

        Returns:
            Validated ErisConfig instance.
        """
        import os

        import yaml

        config_data = {}

        if config_path and config_path.exists():
            with open(config_path) as f:
                config_data = yaml.safe_load(f) or {}

        # Apply environment variable overrides for database
        if os.getenv("DB_HOST"):
            config_data.setdefault("database", {})["host"] = os.getenv("DB_HOST")
        if os.getenv("DB_PORT"):
            config_data.setdefault("database", {})["port"] = int(os.getenv("DB_PORT"))
        if os.getenv("DB_NAME"):
            config_data.setdefault("database", {})["database"] = os.getenv("DB_NAME")
        if os.getenv("DB_USER"):
            config_data.setdefault("database", {})["user"] = os.getenv("DB_USER")
        if os.getenv("DB_PASSWORD"):
            config_data.setdefault("database", {})["password"] = os.getenv("DB_PASSWORD")

        # Apply environment variable overrides for Ollama
        if os.getenv("OLLAMA_HOST"):
            config_data.setdefault("ollama", {})["host"] = os.getenv("OLLAMA_HOST")
        if os.getenv("OLLAMA_MODEL"):
            config_data.setdefault("ollama", {})["model"] = os.getenv("OLLAMA_MODEL")

        return cls(**config_data)
