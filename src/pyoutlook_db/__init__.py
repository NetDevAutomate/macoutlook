"""pyoutlook-db: Python library for accessing Microsoft Outlook SQLite database on macOS.

This library provides programmatic access to Microsoft Outlook's SQLite database,
enabling developers to read emails, calendar events, and other Outlook data with
automatic HTML/XML parsing and conversion to JSON/Markdown formats.
"""

__version__ = "0.1.0"
__author__ = "Amazon Q Developer"
__email__ = "noreply@amazon.com"

from .core.client import OutlookClient
from .core.exceptions import (
    ConnectionError,
    DatabaseLockError,
    DatabaseNotFoundError,
    OutlookDBError,
    ParseError,
)
from .models.calendar import Calendar, CalendarEvent
from .models.email import EmailMessage

__all__ = [
    "OutlookClient",
    "EmailMessage",
    "CalendarEvent",
    "Calendar",
    "OutlookDBError",
    "DatabaseNotFoundError",
    "DatabaseLockError",
    "ConnectionError",
    "ParseError",
]
