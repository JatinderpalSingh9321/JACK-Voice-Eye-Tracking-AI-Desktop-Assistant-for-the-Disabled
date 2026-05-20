"""
BCI Assistive Control — Configuration & Utility Functions
=========================================================
Central configuration paths and shared helper functions for Gaze Tracking and Voice Assistant.

Group No. 7 | 8th Semester Major Project
"""

import logging
from pathlib import Path

# ──────────────────────────────────────────────
# PATH CONFIGURATION
# ──────────────────────────────────────────────

# Project root directory (one level up from src/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Data directory
DATA_DIR = PROJECT_ROOT / "data"

# ──────────────────────────────────────────────
# LOGGING SETUP
# ──────────────────────────────────────────────

def setup_logger(name, level=logging.INFO):
    """Create a logger with a consistent format for all modules."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        fmt = logging.Formatter(
            "%(asctime)s | %(name)-20s | %(levelname)-7s | %(message)s",
            datefmt="%H:%M:%S"
        )
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger

