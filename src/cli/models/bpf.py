"""
BPF (Binary Profile Format) models.

Provides data models for compiled sing-box profiles, supporting
serialization and binary protocol message types.
"""

from enum import IntEnum, StrEnum

from pydantic import BaseModel


class ProfileType(IntEnum):
    """Enumeration of sing-box profile location types."""

    LOCAL = 0
    ICLOUD = 1
    REMOTE = 2


class ProfileTypeArg(StrEnum):
    """CLI argument mapping for profile location types."""

    LOCAL = "local"
    REMOTE = "remote"
    ICLOUD = "icloud"


class MessageType(IntEnum):
    """Enumeration of binary protocol message types."""

    PROFILE_CONTENT = 3


class ProfileContent(BaseModel):
    """
    Data model representing a compiled sing-box profile and its metadata.

    Attributes
    ----------
    name : str
        Human-readable display name.
    profile_type : ProfileType
        Location type (LOCAL, ICLOUD, REMOTE).
    config : str
        Raw JSON configuration string.
    remote_path : str
        URI for profile synchronization. Defaults to an empty string.
    auto_update : bool
        Enable automatic profile refresh. Defaults to False.
    auto_update_interval : int
        Refresh interval in seconds. Defaults to 3600.
    last_updated : float
        Timestamp of the last update. Defaults to 0.0.
    """

    name: str
    profile_type: ProfileType
    config: str
    remote_path: str = ""
    auto_update: bool = False
    auto_update_interval: int = 3600
    last_updated: float = 0.0
