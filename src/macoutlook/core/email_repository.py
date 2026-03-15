"""Repository for email-related database queries and row-to-model mapping.

Owns all email SQL queries and the conversion from database rows to
EmailMessage domain objects. Does NOT manage database connections —
the caller (OutlookClient) is responsible for calling db.connect().
"""

from __future__ import annotations

import logging
from datetime import datetime

from ..models.email_message import EmailMessage
from ..models.enums import ContentSource, FlagStatus, Priority
from .protocols import DatabaseProtocol

logger = logging.getLogger(__name__)

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


def _parse_delimited(value: str | None) -> list[str]:
    """Parse a semicolon/comma-delimited string into trimmed, non-empty strings."""
    if not value:
        return []
    return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]


class EmailRepository:
    """Repository for email query execution and row-to-model mapping.

    Accepts a DatabaseProtocol via constructor injection. The database
    must already be connected before calling query methods — this class
    never calls ``db.connect()`` or ``db.disconnect()``.
    """

    def __init__(self, db: DatabaseProtocol) -> None:
        self._db = db

    def get_emails(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 1000,
    ) -> list[EmailMessage]:
        """Get emails with optional date filtering.

        Args:
            start_date: Start date for filtering (inclusive).
            end_date: End date for filtering (inclusive).
            limit: Maximum number of emails to return.

        Returns:
            List of EmailMessage objects, newest first.
        """
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
        rows = self._db.execute_query(query, tuple(params))

        emails: list[EmailMessage] = []
        for row in rows:
            try:
                email = self._row_to_email(row)
                emails.append(email)
            except (ValueError, KeyError) as e:
                logger.warning("Failed to parse email row: %s", e)
                continue

        logger.info("Retrieved %d emails", len(emails))
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
            query: Free-text search across subject and preview.
            sender: Sender email or name filter.
            subject: Subject line filter.
            is_read: Filter by read status.
            start_date: Start date for filtering (inclusive).
            end_date: End date for filtering (inclusive).
            fuzzy: When True and sender is specified, pre-filter with SQL LIKE
                then apply FuzzyMatcher for word-boundary-aware matching.
                Finds "Andy Taylor" when DB has "Andrew Taylor".
            limit: Maximum number of results.
            offset: Number of results to skip (for pagination).

        Returns:
            List of matching EmailMessage objects, newest first.
        """
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
        rows = self._db.execute_query(sql, tuple(params))

        emails: list[EmailMessage] = []
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

    def _row_to_email(self, row: object) -> EmailMessage:
        """Convert a database row to an EmailMessage.

        Args:
            row: A sqlite3.Row or dict-like object from execute_query.

        Returns:
            Parsed EmailMessage with content_source=PREVIEW_ONLY.

        Raises:
            ValueError: If required fields are missing or unparseable.
            KeyError: If expected columns are absent from the row.
        """
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
