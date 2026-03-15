"""Calendar repository for macoutlook library.

Owns all calendar-related SQL queries and row-to-model mapping.
Extracts calendar domain logic from OutlookClient for single-responsibility.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from ..models.calendar import Calendar, CalendarEvent
from ..parsers.icalendar import ICalendarParser
from .protocols import DatabaseProtocol

logger = logging.getLogger(__name__)

# Apple Core Foundation epoch starts from 2001-01-01
CF_EPOCH = datetime(2001, 1, 1)


def cf_timestamp_to_datetime(cf_timestamp: float) -> datetime:
    """Convert Core Foundation timestamp to datetime.

    macOS stores calendar timestamps as seconds since 2001-01-01 (the Core
    Foundation / Cocoa epoch), not the Unix epoch of 1970-01-01.

    Args:
        cf_timestamp: Seconds since 2001-01-01T00:00:00.

    Returns:
        Equivalent Python datetime.
    """
    if not cf_timestamp or cf_timestamp <= 0:
        return datetime.fromtimestamp(0)
    return CF_EPOCH + timedelta(seconds=cf_timestamp)


def datetime_to_cf_timestamp(dt: datetime) -> float:
    """Convert datetime to Core Foundation timestamp.

    Args:
        dt: Python datetime to convert.

    Returns:
        Seconds since 2001-01-01T00:00:00.
    """
    return (dt - CF_EPOCH).total_seconds()


class CalendarRepository:
    """Repository for calendar data access.

    Encapsulates all calendar-related SQL queries and row-to-model mapping.
    Supports both direct database access and ICS file parsing via the
    injected ICalendarParser.

    The repository calls ``db.execute_query()`` to run SQL -- it does NOT
    manage database connections (no ``connect()`` / ``disconnect()`` calls).
    Connection lifecycle is the caller's responsibility.
    """

    def __init__(
        self,
        db: DatabaseProtocol,
        ics_parser: ICalendarParser | None = None,
    ) -> None:
        self._db = db
        self._ics_parser = ics_parser

    def get_calendars(self) -> list[Calendar]:
        """Get list of all available calendars.

        When an ICS parser is configured, calendars are read from .ics file
        directories. Otherwise, distinct calendar containers are queried from
        the Outlook SQLite database.

        Returns:
            List of Calendar model instances.
        """
        if self._ics_parser:
            calendar_data = self._ics_parser.get_calendars()
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

        query = """
            SELECT DISTINCT
                Record_FolderID as calendar_id,
                'Calendar' as name
            FROM CalendarEvents
            ORDER BY Record_FolderID
        """
        rows = self._db.execute_query(query)

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
        """Get calendar events with optional filtering.

        When an ICS parser is configured, events are read from .ics files.
        Otherwise, events are queried from the Outlook SQLite database using
        Core Foundation timestamp conversion for date filtering.

        Args:
            calendar_id: Optional calendar ID to filter by.
            start_date: Optional start date for filtering.
            end_date: Optional end date for filtering.
            limit: Maximum number of events to return.

        Returns:
            List of CalendarEvent model instances.
        """
        if self._ics_parser:
            events = self._ics_parser.get_all_events(
                start_date=start_date,
                end_date=end_date,
                calendar_id=calendar_id,
            )
            return events[:limit] if len(events) > limit else events

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
        rows = self._db.execute_query(query, tuple(params))

        events = []
        for row in rows:
            try:
                event = self._row_to_calendar_event(row)
                events.append(event)
            except (ValueError, KeyError) as e:
                logger.warning("Failed to parse event row: %s", e)
                continue

        logger.info("Retrieved %d calendar events", len(events))
        return events

    @staticmethod
    def _row_to_calendar_event(row: object) -> CalendarEvent:
        """Convert a database row to a CalendarEvent model.

        Args:
            row: A sqlite3.Row or dict-like object from execute_query.

        Returns:
            CalendarEvent with fields mapped from the database row.

        Raises:
            ValueError: If required fields are missing or invalid.
            KeyError: If expected columns are not present.
        """
        r = dict(row)  # type: ignore[call-overload]
        return CalendarEvent(
            event_id=str(r["event_id"] or ""),
            calendar_id=str(r["calendar_id"] or ""),
            title=r["title"] or "Calendar Event",
            start_time=cf_timestamp_to_datetime(r["start_time"] or 0),
            end_time=cf_timestamp_to_datetime(r["end_time"] or 0),
            is_recurring=bool(r["is_recurring"]),
            modified_time=cf_timestamp_to_datetime(r["modified_time"])
            if r["modified_time"]
            else None,
        )
