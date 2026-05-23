"""
BCI Assistive Control — Configuration & Utility Functions
=========================================================
Central configuration paths and shared helper functions for Gaze Tracking and Voice Assistant.

Group No. 7 | 8th Semester Major Project
"""

import logging
import sys
from pathlib import Path

# ──────────────────────────────────────────────
# PATH CONFIGURATION
# ──────────────────────────────────────────────

# When frozen by PyInstaller, __file__ is inside _MEIPASS temp extraction.
# Use _MEIPASS as project root so all data paths resolve correctly.
if getattr(sys, 'frozen', False):
    PROJECT_ROOT = Path(sys._MEIPASS)
else:
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

