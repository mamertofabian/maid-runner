"""Logging utilities for MAID Agents."""

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """Setup logging configuration for MAID Agents.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Convert string level to logging constant
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Configure root logger
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Get logger for maid_agents
    logger = logging.getLogger("maid_agents")
    logger.setLevel(numeric_level)

    logger.info(f"Logging configured at {level} level")


def get_logger(name: str) -> logging.Logger:
    """Get logger for specific module.

    Args:
        name: Module name

    Returns:
        Configured logger instance
    """
    return logging.getLogger(f"maid_agents.{name}")
