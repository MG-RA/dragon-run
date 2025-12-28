"""Logfire tracing initialization and utilities for Eris AI Director."""

import contextvars
import logging
import os
import uuid
from contextvars import Token

logger = logging.getLogger(__name__)

_initialized = False


def init_tracing() -> bool:
    """Initialize Logfire tracing from environment.

    Returns:
        True if tracing was successfully initialized, False otherwise.
    """
    global _initialized
    if _initialized:
        return True

    token = os.getenv("LOGFIRE_TOKEN")
    if not token:
        logger.debug("LOGFIRE_TOKEN not set, tracing disabled")
        return False

    try:
        import logfire

        logfire.configure(
            token=token,
            service_name="eris-director",
            service_version="1.3",
        )

        # Enable asyncpg (PostgreSQL) instrumentation for detailed query tracing
        try:
            logfire.instrument_asyncpg()
            logger.info("PostgreSQL (asyncpg) instrumentation enabled")
        except Exception as e:
            logger.warning(f"Failed to instrument asyncpg: {e}")

        _initialized = True
        logger.info("Logfire tracing initialized")
        return True
    except ImportError:
        logger.warning("logfire package not installed, tracing disabled")
        return False
    except Exception as e:
        logger.warning(f"Failed to initialize Logfire: {e}")
        return False


def generate_trace_id() -> str:
    """Generate a unique trace ID for event correlation.

    Returns:
        12-character hex string (e.g., "a1b2c3d4e5f6")
    """
    return uuid.uuid4().hex[:12]


def generate_root_trace_id() -> str:
    """Generate a unique root trace ID for scenario-level correlation.

    Root trace IDs are longer (24 chars) to distinguish from per-event trace IDs (12 chars).
    Used to track an entire scenario through generation, validation, and execution.

    Returns:
        24-character hex string (e.g., "a1b2c3d4e5f6a1b2c3d4e5f6")
    """
    return uuid.uuid4().hex[:24]


# Context variable for root trace ID propagation
_root_trace_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "root_trace_id", default=None
)


def set_root_trace_id(trace_id: str) -> Token:
    """Set the root trace ID for the current async context.

    Args:
        trace_id: Root trace ID to set

    Returns:
        Token that can be used to reset the context
    """
    return _root_trace_context.set(trace_id)


def get_root_trace_id() -> str | None:
    """Get the current root trace ID, if set.

    Returns:
        Root trace ID or None if not in a traced context
    """
    return _root_trace_context.get()


def reset_root_trace_id(token: Token) -> None:
    """Reset the root trace ID context using a token.

    Args:
        token: Token from set_root_trace_id()
    """
    _root_trace_context.reset(token)


def is_tracing_enabled() -> bool:
    """Check if tracing is currently enabled."""
    return _initialized


# Context manager for optional tracing spans
class TracingSpan:
    """Context manager that wraps logfire.span when tracing is enabled.

    Falls back to a no-op when tracing is disabled.
    Automatically injects root_trace_id from context if available.
    """

    def __init__(self, name: str, **attributes):
        self.name = name
        self.attributes = attributes
        self._span = None
        self._logfire_span = None

        # Auto-inject root_trace_id from context if not explicitly provided
        root_id = get_root_trace_id()
        if root_id and "root_trace_id" not in self.attributes:
            self.attributes["root_trace_id"] = root_id

    def set_attribute(self, key: str, value) -> None:
        """Set an attribute on the span after creation."""
        if self._logfire_span is not None:
            try:
                self._logfire_span.set_attribute(key, value)
            except Exception:
                pass

    def set_attributes(self, **attributes) -> None:
        """Set multiple attributes on the span after creation."""
        for key, value in attributes.items():
            self.set_attribute(key, value)

    def __enter__(self):
        if _initialized:
            try:
                import logfire

                self._logfire_span = logfire.span(self.name, **self.attributes)
                self._span = self._logfire_span.__enter__()
                return self
            except Exception:
                pass
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._logfire_span is not None:
            return self._logfire_span.__exit__(exc_type, exc_val, exc_tb)
        return False

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return self.__exit__(exc_type, exc_val, exc_tb)


def span(name: str, **attributes) -> TracingSpan:
    """Create a tracing span that works whether or not tracing is enabled.

    Args:
        name: Span name (e.g., "llm.invoke", "tool.execute")
        **attributes: Key-value attributes to attach to the span

    Returns:
        TracingSpan context manager
    """
    return TracingSpan(name, **attributes)
