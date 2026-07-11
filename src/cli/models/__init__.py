"""
Models package for sing-box.

This package provides a centralized definition of data structures used
across the application. It includes models for:
    - BPF (Binary Profile Format) serialization and metadata.
    - VLESS connection parameters for proxy configuration.
"""

from cli.models.bpf import MessageType, ProfileContent, ProfileType, ProfileTypeArg
from cli.models.vless import VlessParams

__all__ = [
    "MessageType",
    "ProfileContent",
    "ProfileType",
    "ProfileTypeArg",
    "VlessParams",
]
