"""Logging configuration."""
import logging
import sys
import os

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()


def setup_logger(name: str = "ultra_hunter") -> logging.Logger:
    """Set up and return a logger instance."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    log_dir = os.environ.get("LOG_DIR", "/data/logs")
    os.makedirs(log_dir, exist_ok=True)
    file_handler = logging.FileHandler(os.path.join(log_dir, "ultra_hunter.log"))
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


logger = setup_logger()
