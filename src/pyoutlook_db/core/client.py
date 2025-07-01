"""Main client class for pyoutlook-db library.

This module provides the primary interface for accessing Outlook data through
the OutlookClient class, which coordinates database access, content parsing,
and data model creation.
"""

from datetime import datetime, timedelta
from typing import Any

import structlog

from ..models.calendar import (
    Calendar,
    CalendarEvent,
)
from ..models.email import EmailMessage, EmailSearchFilter
from ..parsers.content import get_content_parser
from ..parsers.icalendar import ICalendarParser
from .database import get_database
from .exceptions import OutlookDBError, ValidationError

logger = structlog.get_logger(__name__)

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


class OutlookClient:
    """Main client for accessing Microsoft Outlook SQLite database.

    This class provides high-level methods for retrieving emails, calendar events,
    and other Outlook data with automatic content parsing and data validation.
    """

    def __init__(self, db_path: str | None = None, auto_connect: bool = True, use_ics: bool = False) -> None:
        """Initialize the Outlook client.

        Args:
            db_path: Optional explicit path to the Outlook database
            auto_connect: Whether to automatically connect to the database
            use_ics: Whether to use .ics files for calendar data (default: False, use SQLite)
        """
        self.db = get_database(db_path)
        self.parser = get_content_parser()
        self.ics_parser = ICalendarParser() if use_ics else None
        self.use_ics = use_ics
        self._connected = False

        logger.info("Initialized OutlookClient",
                   db_path=db_path,
                   auto_connect=auto_connect,
                   use_ics=use_ics)

        if auto_connect:
            self.connect()

    def connect(self) -> None:
        """Connect to the Outlook database."""
        if not self._connected:
            self.db.connect()
            self._connected = True
            logger.info("Connected to Outlook database")

    def disconnect(self) -> None:
        """Disconnect from the Outlook database."""
        if self._connected:
            self.db.disconnect()
            self._connected = False
            logger.info("Disconnected from Outlook database")

    def get_emails_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        folders: list[str] | None = None,
        include_content: bool = True,
        limit: int = 1000,
    ) -> list[EmailMessage]:
        """Get emails within a specific date range.

        Args:
            start_date: Start date for the range
            end_date: End date for the range
            folders: Optional list of folder names to search in
            include_content: Whether to include full email content
            limit: Maximum number of emails to return

        Returns:
            List of EmailMessage objects

        Raises:
            ValidationError: If date range is invalid
            OutlookDBError: If database operation fails
        """
        if end_date <= start_date:
            raise ValidationError("end_date", str(end_date), "must be after start_date")

        logger.info(
            "Getting emails by date range",
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            folders=folders,
            limit=limit,
        )

        try:
            self.connect()

            # Build the query using actual Mail table structure
            query = """
                SELECT 
                    Record_RecordID as message_id,
                    Message_NormalizedSubject as subject,
                    Message_SenderAddressList as sender,
                    Message_SenderList as sender_name,
                    Message_ToRecipientAddressList as recipients,
                    Message_CCRecipientAddressList as cc_recipients,
                    '' as bcc_recipients,
                    Message_TimeReceived as timestamp,
                    Message_TimeSent as received_time,
                    Message_Preview as content_html,
                    '' as folder,
                    Message_ReadFlag as is_read,
                    0 as is_flagged,
                    Message_HasAttachment as attachments,
                    Record_Categories as categories,
                    Message_Size as message_size,
                    Conversation_ConversationID as conversation_id
                FROM Mail 
                WHERE Message_TimeReceived BETWEEN ? AND ?
            """

            params = [start_date.timestamp(), end_date.timestamp()]

            # Add folder filter if specified
            if folders:
                folder_placeholders = ",".join("?" * len(folders))
                query += f" AND FolderName IN ({folder_placeholders})"
                params.extend(folders)

            query += " ORDER BY Message_TimeReceived DESC LIMIT ?"
            params.append(limit)

            rows = self.db.execute_query(query, tuple(params))

            emails = []
            for row in rows:
                try:
                    # Parse content if requested
                    content_data = {"html": "", "text": "", "markdown": ""}
                    if include_content and row["content_html"]:
                        content_data = self.parser.parse_email_content(row["content_html"])

                    # Create EmailMessage object with proper handling of nullable fields
                    email = EmailMessage(
                        message_id=str(row["message_id"] or ""),
                        subject=str(row["subject"] or ""),
                        sender=str(row["sender"] or ""),
                        sender_name=str(row["sender_name"] or ""),
                        recipients=self._parse_recipients(row["recipients"]) if row["recipients"] else [],
                        cc_recipients=self._parse_recipients(row["cc_recipients"]) if row["cc_recipients"] else [],
                        bcc_recipients=[],
                        timestamp=datetime.fromtimestamp(row["timestamp"] or 0),
                        received_time=datetime.fromtimestamp(row["received_time"] or 0)
                        if row["received_time"]
                        else None,
                        content_html=content_data["html"],
                        content_text=content_data["text"],
                        content_markdown=content_data["markdown"],
                        folder="",
                        is_read=bool(row["is_read"]),
                        is_flagged=False,
                        attachments=[],
                        categories=[],
                        message_size=row["message_size"] or 0,
                        conversation_id=str(row["conversation_id"] or ""),
                    )
                    emails.append(email)

                except Exception as e:
                    logger.warning("Failed to parse email row", error=str(e), row_id=row["message_id"] if "message_id" in row.keys() else "unknown")
                    continue

            logger.info("Retrieved emails", count=len(emails))
            return emails

        except Exception as e:
            logger.error("Failed to get emails by date range", error=str(e))
            raise OutlookDBError("Failed to retrieve emails", str(e)) from e

    def search_emails(self, search_filter: EmailSearchFilter) -> list[EmailMessage]:
        """Search for emails using advanced filters.

        Args:
            search_filter: EmailSearchFilter object with search criteria

        Returns:
            List of matching EmailMessage objects
        """
        logger.info("Searching emails", filter=search_filter.dict())

        try:
            self.connect()

            # Build dynamic query based on filters using actual Mail table
            query_parts = ["""
                SELECT 
                    Record_RecordID as message_id,
                    Message_NormalizedSubject as subject,
                    Message_SenderAddressList as sender,
                    Message_SenderList as sender_name,
                    Message_ToRecipientAddressList as recipients,
                    Message_CCRecipientAddressList as cc_recipients,
                    '' as bcc_recipients,
                    Message_TimeReceived as timestamp,
                    Message_TimeSent as received_time,
                    Message_Preview as content_html,
                    '' as folder,
                    Message_ReadFlag as is_read,
                    0 as is_flagged,
                    Message_HasAttachment as attachments,
                    Record_Categories as categories,
                    Message_Size as message_size,
                    Conversation_ConversationID as conversation_id
                FROM Mail WHERE 1=1
            """]
            params = []

            # Text search
            if search_filter.query:
                query_parts.append("AND (Message_NormalizedSubject LIKE ? OR Message_Preview LIKE ?)")
                search_term = f"%{search_filter.query}%"
                params.extend([search_term, search_term])

            # Sender filter
            if search_filter.sender:
                query_parts.append("AND Message_SenderAddressList LIKE ?")
                params.append(f"%{search_filter.sender}%")

            # Subject filter
            if search_filter.subject:
                query_parts.append("AND Message_NormalizedSubject LIKE ?")
                params.append(f"%{search_filter.subject}%")

            # Status filters
            if search_filter.is_read is not None:
                query_parts.append("AND Message_ReadFlag = ?")
                params.append(1 if search_filter.is_read else 0)

            # Date range
            if search_filter.start_date:
                query_parts.append("AND Message_TimeReceived >= ?")
                params.append(search_filter.start_date.timestamp())

            if search_filter.end_date:
                query_parts.append("AND Message_TimeReceived <= ?")
                params.append(search_filter.end_date.timestamp())

            # Add ordering and limits
            query_parts.append("ORDER BY Message_TimeReceived DESC")
            query_parts.append(f"LIMIT {search_filter.limit} OFFSET {search_filter.offset}")

            query = " ".join(query_parts)
            rows = self.db.execute_query(query, tuple(params))

            # Convert rows to EmailMessage objects
            emails = []
            for row in rows:
                try:
                    # Parse content if requested
                    content_data = {"html": "", "text": "", "markdown": ""}
                    if row["content_html"]:
                        content_data = self.parser.parse_email_content(row["content_html"])

                    # Create EmailMessage object with proper handling of nullable fields
                    email = EmailMessage(
                        message_id=str(row["message_id"] or ""),
                        subject=str(row["subject"] or ""),
                        sender=str(row["sender"] or ""),
                        sender_name=str(row["sender_name"] or ""),
                        recipients=self._parse_recipients(row["recipients"]) if row["recipients"] else [],
                        cc_recipients=self._parse_recipients(row["cc_recipients"]) if row["cc_recipients"] else [],
                        bcc_recipients=[],
                        timestamp=datetime.fromtimestamp(row["timestamp"] or 0),
                        received_time=datetime.fromtimestamp(row["received_time"] or 0)
                        if row["received_time"]
                        else None,
                        content_html=content_data["html"],
                        content_text=content_data["text"],
                        content_markdown=content_data["markdown"],
                        folder="",
                        is_read=bool(row["is_read"]),
                        is_flagged=False,
                        attachments=[],
                        categories=[],
                        message_size=row["message_size"] or 0,
                        conversation_id=str(row["conversation_id"] or ""),
                    )
                    emails.append(email)
                except Exception as e:
                    logger.warning("Failed to parse email row", error=str(e))
                    continue

            logger.info("Search completed", results_count=len(emails))
            return emails

        except Exception as e:
            logger.error("Email search failed", error=str(e))
            raise OutlookDBError("Email search failed", str(e)) from e

    def get_calendars(self) -> list[Calendar]:
        """Get list of all available calendars.

        Returns:
            List of Calendar objects
        """
        logger.info("Getting calendars", use_ics=self.use_ics)

        try:
            # Use .ics files if enabled (modern Outlook)
            if self.use_ics and self.ics_parser:
                calendar_data = self.ics_parser.get_calendars()
                calendars = []

                for cal_data in calendar_data:
                    calendar = Calendar(
                        calendar_id=cal_data["calendar_id"],
                        name=cal_data["name"],
                        color=cal_data["color"],
                        is_default=cal_data["is_default"],
                        is_shared=cal_data["is_shared"],
                        owner=cal_data["owner"],
                    )
                    calendars.append(calendar)

                logger.info("Retrieved calendars from .ics files", count=len(calendars))
                return calendars

            # Fallback to SQLite database (legacy Outlook)
            self.connect()

            query = """
                SELECT DISTINCT
                    Record_FolderID as calendar_id,
                    'Calendar' as name,
                    NULL as color,
                    0 as is_default,
                    0 as is_shared,
                    NULL as owner
                FROM CalendarEvents
                ORDER BY Record_FolderID
            """

            rows = self.db.execute_query(query)

            calendars = []
            for row in rows:
                try:
                    calendar = Calendar(
                        calendar_id=str(row["calendar_id"] or ""),
                        name=row["name"] or "Calendar",
                        color=row["color"],
                        is_default=bool(row["is_default"]),
                        is_shared=bool(row["is_shared"]),
                        owner=row["owner"],
                    )
                    calendars.append(calendar)
                except Exception as e:
                    logger.warning("Failed to parse calendar row", error=str(e))
                    continue

            logger.info("Retrieved calendars from SQLite", count=len(calendars))
            return calendars

        except Exception as e:
            logger.error("Failed to get calendars", error=str(e))
            raise OutlookDBError("Failed to retrieve calendars", str(e)) from e

    def get_calendar_events(
        self,
        calendar_id: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 1000,
    ) -> list[CalendarEvent]:
        """Get calendar events with optional filtering.

        Args:
            calendar_id: Optional calendar ID to filter by
            start_date: Optional start date for filtering
            end_date: Optional end date for filtering
            limit: Maximum number of events to return

        Returns:
            List of CalendarEvent objects
        """
        logger.info(
            "Getting calendar events",
            calendar_id=calendar_id,
            start_date=start_date.isoformat() if start_date else None,
            end_date=end_date.isoformat() if end_date else None,
            limit=limit,
            use_ics=self.use_ics
        )

        try:
            # Use .ics files if enabled (modern Outlook)
            if self.use_ics and self.ics_parser:
                events = self.ics_parser.get_all_events(
                    start_date=start_date,
                    end_date=end_date,
                    calendar_id=calendar_id
                )

                # Apply limit
                if limit and len(events) > limit:
                    events = events[:limit]

                logger.info("Retrieved calendar events from .ics files", count=len(events))
                return events

            # Fallback to SQLite database (legacy Outlook)
            self.connect()

            query_parts = [
                """
                SELECT 
                    Record_RecordID as event_id,
                    Record_FolderID as calendar_id,
                    'Event' as calendar_name,
                    Calendar_UID as title,
                    '' as description,
                    '' as location,
                    Calendar_StartDateUTC as start_time,
                    Calendar_EndDateUTC as end_time,
                    0 as is_all_day,
                    'busy' as status,
                    'none' as my_response,
                    '' as organizer,
                    '' as organizer_name,
                    '' as attendees,
                    '' as required_attendees,
                    '' as optional_attendees,
                    Calendar_IsRecurring as is_recurring,
                    'none' as recurrence_type,
                    '' as categories,
                    0 as is_private,
                    NULL as reminder_minutes,
                    NULL as created_time,
                    Record_ModDate as modified_time
                FROM CalendarEvents
                WHERE 1=1
                """
            ]
            params = []

            # Add filters
            if calendar_id:
                query_parts.append("AND Record_FolderID = ?")
                params.append(calendar_id)

            if start_date:
                query_parts.append("AND Calendar_StartDateUTC >= ?")
                params.append(datetime_to_cf_timestamp(start_date))

            if end_date:
                query_parts.append("AND Calendar_EndDateUTC <= ?")
                params.append(datetime_to_cf_timestamp(end_date))

            query_parts.append("ORDER BY Calendar_StartDateUTC ASC")
            query_parts.append(f"LIMIT {limit}")

            query = " ".join(query_parts)
            rows = self.db.execute_query(query, tuple(params))

            events = []
            for row in rows:
                try:
                    event = CalendarEvent(
                        event_id=str(row["event_id"] or ""),
                        calendar_id=str(row["calendar_id"] or ""),
                        calendar_name=row["calendar_name"],
                        title=row["title"] or "Calendar Event",
                        description=row["description"] or "",
                        location=row["location"] or "",
                        start_time=cf_timestamp_to_datetime(row["start_time"] or 0),
                        end_time=cf_timestamp_to_datetime(row["end_time"] or 0),
                        is_all_day=bool(row["is_all_day"]),
                        organizer=row["organizer"],
                        organizer_name=row["organizer_name"],
                        attendees=self._parse_recipients(row["attendees"]),
                        required_attendees=self._parse_recipients(row["required_attendees"]),
                        optional_attendees=self._parse_recipients(row["optional_attendees"]),
                        is_recurring=bool(row["is_recurring"]),
                        categories=self._parse_categories(row["categories"]),
                        is_private=bool(row["is_private"]),
                        reminder_minutes=row["reminder_minutes"],
                        created_time=cf_timestamp_to_datetime(row["created_time"])
                        if row["created_time"]
                        else None,
                        modified_time=cf_timestamp_to_datetime(row["modified_time"])
                        if row["modified_time"]
                        else None,
                    )
                    events.append(event)
                except Exception as e:
                    logger.warning("Failed to parse event row", error=str(e))
                    continue

            logger.info("Retrieved calendar events from SQLite", count=len(events))
            return events

        except Exception as e:
            logger.error("Failed to get calendar events", error=str(e))
            raise OutlookDBError("Failed to retrieve calendar events", str(e)) from e

    def _parse_recipients(self, recipients_str: str | None) -> list[str]:
        """Parse recipients string into list of email addresses."""
        if not recipients_str:
            return []

        # Handle various separator formats
        recipients = recipients_str.replace(";", ",").split(",")
        return [email.strip() for email in recipients if email.strip()]

    def _parse_attachments(self, attachments_str: str | None) -> list[str]:
        """Parse attachments string into list of filenames."""
        if not attachments_str:
            return []

        # Simple parsing - may need enhancement based on actual format
        attachments = attachments_str.split(";")
        return [att.strip() for att in attachments if att.strip()]

    def _parse_categories(self, categories_str: str | None) -> list[str]:
        """Parse categories string into list of category names."""
        if not categories_str:
            return []

        categories = categories_str.split(";")
        return [cat.strip() for cat in categories if cat.strip()]

    def _row_to_email(self, row: dict[str, Any], content_data: dict[str, str]) -> EmailMessage:
        """Convert database row to EmailMessage object."""
        return EmailMessage(
            message_id=row["RecordID"] or "",
            subject=row["Subject"] or "",
            sender=row["SenderEmailAddress"] or "",
            sender_name=row["SenderName"],
            recipients=self._parse_recipients(row["Recipients"]),
            cc_recipients=self._parse_recipients(row["CCRecipients"]),
            bcc_recipients=self._parse_recipients(row["BCCRecipients"]),
            timestamp=datetime.fromtimestamp(row["DateReceived"] or 0),
            received_time=datetime.fromtimestamp(row["DateSent"]) if row["DateSent"] else None,
            content_html=content_data["html"],
            content_text=content_data["text"],
            content_markdown=content_data["markdown"],
            folder=row["FolderName"] or "",
            is_read=bool(row["IsRead"]),
            is_flagged=bool(row["IsFlagged"]),
            attachments=self._parse_attachments(row["Attachments"]),
            categories=self._parse_categories(row["Categories"]),
            message_size=row["MessageSize"],
            conversation_id=row["ConversationID"],
        )

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()

    def __del__(self):
        """Cleanup on object destruction."""
        if self._connected:
            self.disconnect()
