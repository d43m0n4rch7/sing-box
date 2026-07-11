"""
Commands package for sing-box.

This package encapsulates the primary CLI functionality for sing-box.
"""

from cli.commands.converter import app as converter_app
from cli.commands.fetcher import app as fetcher_app
from cli.commands.generate import app as generate_app

__all__ = [
    "converter_app",
    "fetcher_app",
    "generate_app",
]
