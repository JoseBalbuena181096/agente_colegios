"""
Structured logging configuration for the entire application.
Call setup_logging() once at startup (main.py).
"""

import logging
import sys


def setup_logging():
    """Configure structured logging to stdout for the 'app' namespace."""
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    handler.setFormatter(formatter)

    root = logging.getLogger("app")
    root.setLevel(logging.INFO)
    root.addHandler(handler)
