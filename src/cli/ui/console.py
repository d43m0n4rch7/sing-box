"""
UI component configuration.

Provide a centralized Rich console instance configured with a custom
minimalist pastel palette for consistent CLI styling.
"""

from rich.console import Console
from rich.theme import Theme

custom_theme = Theme(
    {
        "primary": "#8aadf4",
        "secondary": "#c6a0f6",
        "accent": "#f5bde6",
        "success": "#a6da95",
        "warning": "#eed49f",
        "error": "#ed8796",
        "info": "#91d7e3",
        "muted": "#5b6078",
    }
)

console = Console(theme=custom_theme)
