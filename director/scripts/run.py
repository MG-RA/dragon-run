#!/usr/bin/env python3
"""Eris AI Director - Main entry point."""

import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

# Setup paths
BASE_DIR = Path(__file__).parent.parent
SRC_DIR = BASE_DIR / "src"
sys.path.insert(0, str(BASE_DIR))

# Override=True to ensure .env values take precedence over system env vars
# (Ollama sets OLLAMA_HOST=0.0.0.0 which we need to override)
load_dotenv(BASE_DIR / ".env", override=True)


def setup_logging(log_dir: Path, level: str = "INFO", json_mode: bool = False) -> None:
    """Configure application logging.

    Args:
        log_dir: Directory for log files.
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        json_mode: If True, output structured JSON logs.
    """
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "eris.log"

    handlers = [
        logging.StreamHandler(),
        logging.FileHandler(log_file, mode="a", encoding="utf-8"),
    ]

    if json_mode:
        # Structured JSON logging for production
        import json

        class JsonFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                log_entry = {
                    "timestamp": self.formatTime(record),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                }
                if record.exc_info:
                    log_entry["exception"] = self.formatException(record.exc_info)
                return json.dumps(log_entry)

        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
        )

    for handler in handlers:
        handler.setFormatter(formatter)

    logging.basicConfig(
        level=getattr(logging, level.upper()),
        handlers=handlers,
    )

    logger = logging.getLogger("eris")
    logger.info(f"Logging to: {log_file}")


async def main() -> None:
    """Main entry point for Eris AI Director."""
    from eris.config import ErisConfig
    from eris.application import ErisApplication

    # Load and validate configuration
    config_path = BASE_DIR / "config.yaml"
    try:
        config = ErisConfig.load(config_path)
    except Exception as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)

    # Setup logging from config
    setup_logging(
        log_dir=BASE_DIR / "logs",
        level=config.logging.level,
        json_mode=config.logging.json_mode,
    )

    logger = logging.getLogger("eris")
    logger.info("Eris AI Director starting...")

    # Create and run application
    app = ErisApplication(config, BASE_DIR)

    try:
        await app.initialize()
        await app.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
