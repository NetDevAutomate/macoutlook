"""macoutlook: Python library for extracting email and calendar data from macOS Outlook.

Reads both the Outlook SQLite database and .olk15MsgSource files for full
email content extraction with automatic HTML/XML parsing and Markdown conversion.

Attribution: The .olk15MsgSource extraction approach was discovered by Jon Hammant.
"""

__version__ = "0.2.1"

from .core.client import OutlookClient, create_client
from .core.enricher import EmailEnricher, EnrichmentResult
from .core.message_source import MessageSourceReader, MimeContent
from .exceptions import (
    DatabaseConnectionError,
    DatabaseLockError,
    DatabaseNotFoundError,
    MessageSourceError,
    OutlookDBError,
    ParseError,
)
from .models.calendar import Calendar, CalendarEvent
from .models.email_message import AttachmentInfo, EmailMessage
from .models.enums import ContentSource, FlagStatus, Priority

__all__ = [
    "OutlookClient",
    "create_client",
    "EmailMessage",
    "AttachmentInfo",
    "CalendarEvent",
    "Calendar",
    "ContentSource",
    "FlagStatus",
    "Priority",
    "OutlookDBError",
    "DatabaseNotFoundError",
    "DatabaseLockError",
    "DatabaseConnectionError",
    "MessageSourceError",
    "ParseError",
    "EmailEnricher",
    "EnrichmentResult",
    "MessageSourceReader",
    "MimeContent",
]
