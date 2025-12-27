"""Logfire tracing initialization and utilities for Eris AI Director."""

import os
import uuid
import logging
from typing import Optional

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


def is_tracing_enabled() -> bool:
    """Check if tracing is currently enabled."""
    return _initialized


# Context manager for optional tracing spans
class TracingSpan:
    """Context manager that wraps logfire.span when tracing is enabled.

    Falls back to a no-op when tracing is disabled.
    """

    def __init__(self, name: str, **attributes):
        self.name = name
        self.attributes = attributes
        self._span = None
        self._logfire_span = None

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
