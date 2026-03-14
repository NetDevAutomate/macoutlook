"""Enumeration types for macoutlook models."""

from enum import IntEnum, StrEnum


class ContentSource(StrEnum):
    """Tracks where email content was sourced from."""

    MESSAGE_SOURCE = "message_source"
    PREVIEW_ONLY = "preview_only"


class FlagStatus(IntEnum):
    """Email flag status from Outlook database."""

    NOT_FLAGGED = 0
    FLAGGED = 1
    COMPLETE = 2


class Priority(IntEnum):
    """Email priority levels from Outlook database."""

    LOW = 1
    NORMAL = 3
    HIGH = 5
