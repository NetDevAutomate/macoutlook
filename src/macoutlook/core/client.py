"""Main client class for macoutlook library.

Coordinates database access, content parsing, and data model creation.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path

from ..models.calendar import Calendar, CalendarEvent
from ..models.email_message import EmailMessage
from ..models.enums import ContentSource, FlagStatus, Priority
from ..parsers.content import ContentParser
from ..parsers.icalendar import ICalendarParser
from .database import OutlookDatabase
from .enricher import EmailEnricher
from .message_source import MessageSourceReader

logger = logging.getLogger(__name__)

# Apple Core Foundation epoch starts from 2001-01-01
CF_EPOCH = datetime(2001, 1, 1)


def cf_timestamp_to_datetime(cf_timestamp: float) -> datetime:
    """Convert Core Foundation timestamp to datetime."""
    if not cf_timestamp or cf_timestamp <= 0:
        return datetime.fromtimestamp(0)
    return CF_EPOCH + timedelta(seconds=cf_timestamp)


def datetime_to_cf_timestamp(dt: datetime) -> float:
    """Convert datetime to Core Foundation timestamp."""
    return (dt - CF_EPOCH).total_seconds()


# SQL query for email retrieval with all needed columns
_EMAIL_QUERY_COLUMNS = """
    Record_RecordID,
    Message_MessageID,
    Message_NormalizedSubject,
    Message_SenderAddressList,
    Message_SenderList,
    Message_ToRecipientAddressList,
    Message_CCRecipientAddressList,
    Message_TimeReceived,
    Message_TimeSent,
    Message_Preview,
    Message_ReadFlag,
    Message_IsOutgoingMessage,
    Record_FlagStatus,
    Record_Priority,
    Record_FolderID,
    Message_HasAttachment,
    Message_Size
"""


class OutlookClient:
    """Main client for accessing Microsoft Outlook data.

    Accepts dependencies via constructor for testability and composability.
    Use create_client() for the common case.
    """

    def __init__(
        self,
        database: OutlookDatabase | None = None,
        enricher: EmailEnricher | None = None,
        content_parser: ContentParser | None = None,
        ics_parser: ICalendarParser | None = None,
        db_path: Path | str | None = None,
    ) -> None:
        self.db = database or OutlookDatabase(db_path)
        self.enricher = enricher
        self.parser = content_parser or ContentParser()
        self.ics_parser = ics_parser
        self._connected = False

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

        query_parts = [f"SELECT {_EMAIL_QUERY_COLUMNS} FROM Mail WHERE 1=1"]  # noqa: S608  # nosec B608
        params: list[object] = []

        if start_date:
            query_parts.append("AND Message_TimeReceived >= ?")
            params.append(start_date.timestamp())

        if end_date:
            query_parts.append("AND Message_TimeReceived <= ?")
            params.append(end_date.timestamp())

        query_parts.append("ORDER BY Message_TimeReceived DESC LIMIT ?")
        params.append(limit)

        query = " ".join(query_parts)
        rows = self.db.execute_query(query, tuple(params))

        emails = []
        for row in rows:
            try:
                email = self._row_to_email(row)
                emails.append(email)
            except (ValueError, KeyError) as e:
                logger.warning("Failed to parse email row: %s", e)
                continue

        logger.info("Retrieved %d emails", len(emails))

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

        query_parts = [f"SELECT {_EMAIL_QUERY_COLUMNS} FROM Mail WHERE 1=1"]  # noqa: S608  # nosec B608
        params: list[object] = []

        if query:
            query_parts.append(
                "AND (Message_NormalizedSubject LIKE ? OR Message_Preview LIKE ?)"
            )
            term = f"%{query}%"
            params.extend([term, term])

        if sender:
            if fuzzy:
                # Pre-filter: SQL LIKE on first token to reduce candidate set
                tokens = sender.split()
                for token in tokens[:2]:
                    query_parts.append(
                        "AND (Message_SenderAddressList LIKE ? OR Message_SenderList LIKE ?)"
                    )
                    params.extend([f"%{token}%", f"%{token}%"])
            else:
                query_parts.append("AND Message_SenderAddressList LIKE ?")
                params.append(f"%{sender}%")

        if subject:
            query_parts.append("AND Message_NormalizedSubject LIKE ?")
            params.append(f"%{subject}%")

        if is_read is not None:
            query_parts.append("AND Message_ReadFlag = ?")
            params.append(1 if is_read else 0)

        if start_date:
            query_parts.append("AND Message_TimeReceived >= ?")
            params.append(start_date.timestamp())

        if end_date:
            query_parts.append("AND Message_TimeReceived <= ?")
            params.append(end_date.timestamp())

        query_parts.append("ORDER BY Message_TimeReceived DESC LIMIT ? OFFSET ?")
        params.extend([limit, offset])

        sql = " ".join(query_parts)
        rows = self.db.execute_query(sql, tuple(params))

        emails = []
        for row in rows:
            try:
                email = self._row_to_email(row)
                emails.append(email)
            except (ValueError, KeyError) as e:
                logger.warning("Failed to parse email row: %s", e)
                continue

        # Apply fuzzy matching post-filter on sender
        if fuzzy and sender:
            from ..search import FuzzyMatcher

            matcher = FuzzyMatcher()
            emails = [
                e
                for e in emails
                if matcher.is_match(sender, e.sender_name or "")
                or matcher.is_match(sender, e.sender)
            ]

        logger.info("Search returned %d emails", len(emails))
        return emails

    def get_calendars(self) -> list[Calendar]:
        """Get list of all available calendars."""
        if self.ics_parser:
            calendar_data = self.ics_parser.get_calendars()
            return [
                Calendar(
                    calendar_id=d["calendar_id"],
                    name=d["name"],
                    color=d.get("color"),
                    is_default=d.get("is_default", False),
                    is_shared=d.get("is_shared", False),
                    owner=d.get("owner"),
                )
                for d in calendar_data
            ]

        self.connect()

        query = """
            SELECT DISTINCT
                Record_FolderID as calendar_id,
                'Calendar' as name
            FROM CalendarEvents
            ORDER BY Record_FolderID
        """
        rows = self.db.execute_query(query)

        return [
            Calendar(
                calendar_id=str(row["calendar_id"] or ""),
                name=row["name"] or "Calendar",
            )
            for row in rows
        ]

    def get_calendar_events(
        self,
        calendar_id: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 1000,
    ) -> list[CalendarEvent]:
        """Get calendar events with optional filtering."""
        if self.ics_parser:
            events = self.ics_parser.get_all_events(
                start_date=start_date,
                end_date=end_date,
                calendar_id=calendar_id,
            )
            return events[:limit] if len(events) > limit else events

        self.connect()

        query_parts = [
            """
            SELECT
                Record_RecordID as event_id,
                Record_FolderID as calendar_id,
                Calendar_UID as title,
                Calendar_StartDateUTC as start_time,
                Calendar_EndDateUTC as end_time,
                Calendar_IsRecurring as is_recurring,
                Record_ModDate as modified_time
            FROM CalendarEvents
            WHERE 1=1
        """
        ]
        params: list[object] = []

        if calendar_id:
            query_parts.append("AND Record_FolderID = ?")
            params.append(calendar_id)

        if start_date:
            query_parts.append("AND Calendar_StartDateUTC >= ?")
            params.append(datetime_to_cf_timestamp(start_date))

        if end_date:
            query_parts.append("AND Calendar_EndDateUTC <= ?")
            params.append(datetime_to_cf_timestamp(end_date))

        query_parts.append("ORDER BY Calendar_StartDateUTC ASC LIMIT ?")
        params.append(limit)

        query = " ".join(query_parts)
        rows = self.db.execute_query(query, tuple(params))

        events = []
        for row in rows:
            try:
                event = CalendarEvent(
                    event_id=str(row["event_id"] or ""),
                    calendar_id=str(row["calendar_id"] or ""),
                    title=row["title"] or "Calendar Event",
                    start_time=cf_timestamp_to_datetime(row["start_time"] or 0),
                    end_time=cf_timestamp_to_datetime(row["end_time"] or 0),
                    is_recurring=bool(row["is_recurring"]),
                    modified_time=cf_timestamp_to_datetime(row["modified_time"])
                    if row["modified_time"]
                    else None,
                )
                events.append(event)
            except (ValueError, KeyError) as e:
                logger.warning("Failed to parse event row: %s", e)
                continue

        logger.info("Retrieved %d calendar events", len(events))
        return events

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

    def _row_to_email(self, row: object) -> EmailMessage:
        """Convert a database row to an EmailMessage."""
        r = dict(row)  # type: ignore[call-overload]

        # Parse recipients from semicolon-separated strings
        recipients = _parse_delimited(r.get("Message_ToRecipientAddressList"))
        cc_recipients = _parse_delimited(r.get("Message_CCRecipientAddressList"))

        # Parse preview content
        preview = str(r.get("Message_Preview") or "")

        # Parse timestamp
        raw_ts = r.get("Message_TimeReceived") or 0
        timestamp = (
            datetime.fromtimestamp(float(raw_ts))
            if raw_ts
            else datetime.fromtimestamp(0)
        )

        raw_sent = r.get("Message_TimeSent")
        time_sent = datetime.fromtimestamp(float(raw_sent)) if raw_sent else None

        return EmailMessage(
            message_id=str(r.get("Message_MessageID") or ""),
            record_id=int(r.get("Record_RecordID") or 0),
            subject=str(r.get("Message_NormalizedSubject") or ""),
            sender=str(r.get("Message_SenderAddressList") or ""),
            sender_name=str(r.get("Message_SenderList") or "") or None,
            recipients=recipients,
            cc_recipients=cc_recipients,
            timestamp=timestamp,
            time_sent=time_sent,
            size=r.get("Message_Size"),
            is_read=bool(r.get("Message_ReadFlag")),
            is_outgoing=bool(r.get("Message_IsOutgoingMessage")),
            flag_status=FlagStatus(r.get("Record_FlagStatus") or 0)
            if r.get("Record_FlagStatus") in (0, 1, 2)
            else FlagStatus.NOT_FLAGGED,
            priority=Priority(r.get("Record_Priority") or 3)
            if r.get("Record_Priority") in (1, 3, 5)
            else Priority.NORMAL,
            folder_id=r.get("Record_FolderID"),
            has_attachments=bool(r.get("Message_HasAttachment")),
            preview=preview,
            content_source=ContentSource.PREVIEW_ONLY,
        )

    def __enter__(self) -> "OutlookClient":
        self.connect()
        return self

    def __exit__(
        self, exc_type: type | None, exc_val: Exception | None, exc_tb: object
    ) -> None:
        self.disconnect()


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


def _parse_delimited(value: str | None, sep: str = ";") -> list[str]:
    """Parse a delimited string into a list of trimmed, non-empty strings."""
    if not value:
        return []
    return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]
