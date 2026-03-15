"""Main client class for macoutlook library.

Orchestrates database connections, repository delegation, and enrichment.
Domain-specific query logic lives in EmailRepository and CalendarRepository.
"""

import logging
from datetime import datetime
from pathlib import Path

from ..models.calendar import Calendar, CalendarEvent
from ..models.email_message import EmailMessage
from ..models.enums import ContentSource
from ..parsers.icalendar import ICalendarParser
from .calendar_repository import CalendarRepository
from .database import OutlookDatabase
from .email_repository import EmailRepository
from .enricher import EmailEnricher
from .message_source import MessageSourceReader
from .protocols import DatabaseProtocol, EnricherProtocol

logger = logging.getLogger(__name__)


class OutlookClient:
    """Main client for accessing Microsoft Outlook data.

    Accepts dependencies via constructor for testability and composability.
    Use create_client() for the common case.

    This class is a thin orchestrator: it manages database connection
    lifecycle and delegates query logic to EmailRepository and
    CalendarRepository.
    """

    def __init__(
        self,
        database: DatabaseProtocol | None = None,
        enricher: EnricherProtocol | None = None,
        db_path: Path | str | None = None,
        ics_parser: ICalendarParser | None = None,
    ) -> None:
        self.db: DatabaseProtocol = database or OutlookDatabase(db_path)
        self.enricher = enricher
        self._connected = False

        # Build repositories using the shared database handle
        self._email_repo = EmailRepository(self.db)
        self._calendar_repo = CalendarRepository(self.db, ics_parser)

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Connect to the Outlook database."""
        if not self._connected:
            self.db.connect()
            self._connected = True

    def disconnect(self) -> None:
        """Disconnect from the Outlook database."""
        if self._connected:
            self.db.disconnect()
            self._connected = False

    def __enter__(self) -> "OutlookClient":
        self.connect()
        return self

    def __exit__(
        self, exc_type: type | None, exc_val: Exception | None, exc_tb: object
    ) -> None:
        self.disconnect()

    # ------------------------------------------------------------------
    # Email operations (delegated to EmailRepository)
    # ------------------------------------------------------------------

    def get_emails(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 1000,
        enrich: bool = False,
    ) -> list[EmailMessage]:
        """Get emails with optional date filtering.

        Args:
            start_date: Start date for filtering.
            end_date: End date for filtering.
            limit: Maximum number of emails to return.
            enrich: Whether to enrich with full content from .olk15MsgSource
                files. When False (default), returns metadata + preview only.

        Returns:
            List of EmailMessage objects.
        """
        self.connect()
        emails = self._email_repo.get_emails(start_date, end_date, limit)

        if enrich and self.enricher is not None:
            emails = self.enrich_emails(emails)

        return emails

    def search_emails(
        self,
        query: str | None = None,
        sender: str | None = None,
        subject: str | None = None,
        is_read: bool | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        fuzzy: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EmailMessage]:
        """Search for emails using filters.

        All filter parameters are optional and combined with AND logic.

        Args:
            fuzzy: When True and sender is specified, pre-filter with SQL LIKE
                then apply FuzzyMatcher for word-boundary-aware matching.
                Finds "Andy Taylor" when DB has "Andrew Taylor".
        """
        self.connect()
        return self._email_repo.search_emails(
            query=query,
            sender=sender,
            subject=subject,
            is_read=is_read,
            start_date=start_date,
            end_date=end_date,
            fuzzy=fuzzy,
            limit=limit,
            offset=offset,
        )

    # ------------------------------------------------------------------
    # Calendar operations (delegated to CalendarRepository)
    # ------------------------------------------------------------------

    def get_calendars(self) -> list[Calendar]:
        """Get list of all available calendars."""
        self.connect()
        return self._calendar_repo.get_calendars()

    def get_calendar_events(
        self,
        calendar_id: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 1000,
    ) -> list[CalendarEvent]:
        """Get calendar events with optional filtering."""
        self.connect()
        return self._calendar_repo.get_calendar_events(
            calendar_id=calendar_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

    # ------------------------------------------------------------------
    # Enrichment (cross-cutting orchestration, stays in client)
    # ------------------------------------------------------------------

    def enrich_email(self, email: EmailMessage, markdown: bool = True) -> EmailMessage:
        """Enrich an email with full content from its .olk15MsgSource file.

        Returns a new EmailMessage instance with body_text, body_html,
        body_markdown, and attachments populated from the MIME source.
        If enrichment fails, returns the original email unchanged.

        Args:
            email: EmailMessage to enrich.
            markdown: Whether to generate markdown from HTML.
        """
        if self.enricher is None:
            logger.debug("No enricher configured, returning email as-is")
            return email

        result = self.enricher.enrich(email.message_id, markdown=markdown)

        if result.source == ContentSource.PREVIEW_ONLY:
            return email

        # Create new frozen instance with enriched content
        return email.model_copy(
            update={
                "body_text": result.body_text,
                "body_html": result.body_html,
                "body_markdown": result.body_markdown,
                "attachments": result.attachments,
                "content_source": result.source,
            }
        )

    def enrich_emails(
        self,
        emails: list[EmailMessage],
        markdown: bool = True,
    ) -> list[EmailMessage]:
        """Batch-enrich a list of emails.

        Builds the index once, then enriches each email.
        """
        if self.enricher is None:
            return emails

        self.enricher.build_index()

        return [self.enrich_email(e, markdown=markdown) for e in emails]

    def save_attachment(
        self,
        message_id: str,
        attachment_filename: str,
        dest_dir: Path | str,
    ) -> Path:
        """Save an email attachment to disk.

        Args:
            message_id: RFC 2822 Message-ID of the email.
            attachment_filename: Name of the attachment to save.
            dest_dir: Directory to save the attachment to.

        Returns:
            Path to the saved file.

        Raises:
            RuntimeError: If no enricher is configured.
            FileNotFoundError: If source file or attachment not found.
            ValueError: If path validation fails.
        """
        if self.enricher is None:
            raise RuntimeError("No enricher configured — cannot save attachments")

        return self.enricher.save_attachment(
            message_id=message_id,
            attachment_filename=attachment_filename,
            dest_dir=Path(dest_dir),
        )

    # ------------------------------------------------------------------
    # Database info (cross-cutting, stays in client)
    # ------------------------------------------------------------------

    def get_database_info(self) -> dict[str, object]:
        """Get information about the connected database."""
        self.connect()

        tables = self.db.get_table_names()
        info: dict[str, object] = {
            "db_path": str(self.db.db_path),
            "tables": tables,
            "table_count": len(tables),
        }

        for table in ["Mail", "CalendarEvents", "Contacts"]:
            if table in tables:
                try:
                    info[f"{table.lower()}_count"] = self.db.get_row_count(table)
                except Exception:
                    logger.debug("Could not get row count for %s", table)

        return info


def create_client(
    db_path: Path | str | None = None,
    enable_enrichment: bool = True,
) -> OutlookClient:
    """Factory for creating an OutlookClient with default dependencies.

    Args:
        db_path: Optional explicit database path.
        enable_enrichment: Whether to set up the enricher for reading
            .olk15MsgSource files. Set False for metadata-only access.
    """
    enricher = None
    if enable_enrichment:
        reader = MessageSourceReader()
        enricher = EmailEnricher(reader)

    return OutlookClient(db_path=db_path, enricher=enricher)
