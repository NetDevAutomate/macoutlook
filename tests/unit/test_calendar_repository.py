"""Unit tests for CalendarRepository class."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import Mock

from macoutlook.core.calendar_repository import (
    CF_EPOCH,
    CalendarRepository,
    cf_timestamp_to_datetime,
    datetime_to_cf_timestamp,
)
from macoutlook.core.protocols import DatabaseProtocol
from macoutlook.models.calendar import Calendar, CalendarEvent
from macoutlook.parsers.icalendar import ICalendarParser

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _mock_db() -> Mock:
    """Create a mock satisfying DatabaseProtocol."""
    return Mock(spec=DatabaseProtocol)


def _mock_ics_parser() -> Mock:
    """Create a mock ICalendarParser."""
    return Mock(spec=ICalendarParser)


def _make_event_row(
    event_id: int = 1,
    calendar_id: int = 100,
    title: str = "Team Standup",
    start_offset_seconds: float = 700_000_000.0,
    duration_minutes: int = 30,
    is_recurring: bool = False,
    modified_offset_seconds: float | None = 700_000_100.0,
) -> dict:
    """Build a fake DB row dict for a CalendarEvent.

    Offsets are seconds from the Core Foundation epoch (2001-01-01).
    """
    end_offset = start_offset_seconds + (duration_minutes * 60)
    return {
        "event_id": event_id,
        "calendar_id": calendar_id,
        "title": title,
        "start_time": start_offset_seconds,
        "end_time": end_offset,
        "is_recurring": int(is_recurring),
        "modified_time": modified_offset_seconds,
    }


# ---------------------------------------------------------------------------
# Core Foundation timestamp helpers
# ---------------------------------------------------------------------------


class TestCFTimestampToDatetime:
    def test_known_value(self):
        """1 second after CF epoch should be 2001-01-01 00:00:01."""
        result = cf_timestamp_to_datetime(1.0)
        assert result == CF_EPOCH + timedelta(seconds=1)

    def test_zero_returns_unix_epoch(self):
        result = cf_timestamp_to_datetime(0)
        assert result == datetime.fromtimestamp(0)

    def test_negative_returns_unix_epoch(self):
        result = cf_timestamp_to_datetime(-100.0)
        assert result == datetime.fromtimestamp(0)

    def test_large_value(self):
        """700 million seconds ~ roughly mid-2023."""
        result = cf_timestamp_to_datetime(700_000_000.0)
        expected = CF_EPOCH + timedelta(seconds=700_000_000.0)
        assert result == expected

    def test_none_treated_as_falsy(self):
        """None coerces to falsy, should return unix epoch."""
        result = cf_timestamp_to_datetime(None)  # type: ignore[arg-type]
        assert result == datetime.fromtimestamp(0)


class TestDatetimeToCFTimestamp:
    def test_cf_epoch_returns_zero(self):
        assert datetime_to_cf_timestamp(CF_EPOCH) == 0.0

    def test_roundtrip(self):
        """Converting to CF and back should yield the same datetime."""
        original = datetime(2024, 6, 15, 12, 0, 0)
        cf_ts = datetime_to_cf_timestamp(original)
        roundtripped = cf_timestamp_to_datetime(cf_ts)
        assert roundtripped == original

    def test_before_cf_epoch_is_negative(self):
        dt = datetime(2000, 1, 1)
        result = datetime_to_cf_timestamp(dt)
        assert result < 0


# ---------------------------------------------------------------------------
# CalendarRepository.get_calendars()
# ---------------------------------------------------------------------------


class TestGetCalendars:
    def test_get_calendars_from_db(self):
        db = _mock_db()
        db.execute_query.return_value = [
            {"calendar_id": "1", "name": "Calendar"},
            {"calendar_id": "2", "name": "Work"},
        ]
        repo = CalendarRepository(db=db)

        calendars = repo.get_calendars()

        assert len(calendars) == 2
        assert all(isinstance(c, Calendar) for c in calendars)
        assert calendars[0].calendar_id == "1"
        assert calendars[0].name == "Calendar"
        assert calendars[1].calendar_id == "2"
        assert calendars[1].name == "Work"
        db.execute_query.assert_called_once()

    def test_get_calendars_from_db_null_name_defaults(self):
        db = _mock_db()
        db.execute_query.return_value = [
            {"calendar_id": "1", "name": None},
        ]
        repo = CalendarRepository(db=db)

        calendars = repo.get_calendars()

        assert calendars[0].name == "Calendar"

    def test_get_calendars_from_db_null_id_defaults_to_empty(self):
        db = _mock_db()
        db.execute_query.return_value = [
            {"calendar_id": None, "name": "Test"},
        ]
        repo = CalendarRepository(db=db)

        calendars = repo.get_calendars()

        assert calendars[0].calendar_id == ""

    def test_get_calendars_from_db_empty_result(self):
        db = _mock_db()
        db.execute_query.return_value = []
        repo = CalendarRepository(db=db)

        calendars = repo.get_calendars()

        assert calendars == []

    def test_get_calendars_from_ics_parser(self):
        db = _mock_db()
        ics = _mock_ics_parser()
        ics.get_calendars.return_value = [
            {
                "calendar_id": "ics-1",
                "name": "My Calendar",
                "color": "#FF0000",
                "is_default": True,
                "is_shared": False,
                "owner": "user@example.com",
            },
        ]
        repo = CalendarRepository(db=db, ics_parser=ics)

        calendars = repo.get_calendars()

        assert len(calendars) == 1
        assert calendars[0].calendar_id == "ics-1"
        assert calendars[0].name == "My Calendar"
        assert calendars[0].color == "#FF0000"
        assert calendars[0].is_default is True
        assert calendars[0].owner == "user@example.com"
        # DB should NOT be touched when ICS parser is available
        db.execute_query.assert_not_called()

    def test_get_calendars_ics_with_minimal_data(self):
        """ICS dict may lack optional keys -- defaults should apply."""
        db = _mock_db()
        ics = _mock_ics_parser()
        ics.get_calendars.return_value = [
            {"calendar_id": "ics-2", "name": "Sparse"},
        ]
        repo = CalendarRepository(db=db, ics_parser=ics)

        calendars = repo.get_calendars()

        assert calendars[0].color is None
        assert calendars[0].is_default is False
        assert calendars[0].is_shared is False
        assert calendars[0].owner is None


# ---------------------------------------------------------------------------
# CalendarRepository.get_calendar_events()
# ---------------------------------------------------------------------------


class TestGetCalendarEvents:
    def test_get_events_from_db_basic(self):
        db = _mock_db()
        db.execute_query.return_value = [_make_event_row()]
        repo = CalendarRepository(db=db)

        events = repo.get_calendar_events()

        assert len(events) == 1
        event = events[0]
        assert isinstance(event, CalendarEvent)
        assert event.event_id == "1"
        assert event.calendar_id == "100"
        assert event.title == "Team Standup"
        assert event.is_recurring is False
        assert event.modified_time is not None
        db.execute_query.assert_called_once()

    def test_get_events_from_db_with_calendar_id_filter(self):
        db = _mock_db()
        db.execute_query.return_value = []
        repo = CalendarRepository(db=db)

        repo.get_calendar_events(calendar_id="42")

        sql_called = db.execute_query.call_args[0][0]
        params_called = db.execute_query.call_args[0][1]
        assert "AND Record_FolderID = ?" in sql_called
        assert "42" in params_called

    def test_get_events_from_db_with_date_range(self):
        db = _mock_db()
        db.execute_query.return_value = []
        repo = CalendarRepository(db=db)

        start = datetime(2024, 1, 1)
        end = datetime(2024, 12, 31)
        repo.get_calendar_events(start_date=start, end_date=end)

        sql_called = db.execute_query.call_args[0][0]
        params_called = db.execute_query.call_args[0][1]
        assert "AND Calendar_StartDateUTC >= ?" in sql_called
        assert "AND Calendar_EndDateUTC <= ?" in sql_called
        # Params should be CF timestamps, not Unix timestamps
        expected_start_cf = datetime_to_cf_timestamp(start)
        expected_end_cf = datetime_to_cf_timestamp(end)
        assert expected_start_cf in params_called
        assert expected_end_cf in params_called

    def test_get_events_from_db_with_limit(self):
        db = _mock_db()
        db.execute_query.return_value = []
        repo = CalendarRepository(db=db)

        repo.get_calendar_events(limit=50)

        params_called = db.execute_query.call_args[0][1]
        assert 50 in params_called

    def test_get_events_from_db_skips_bad_rows(self):
        """Rows that fail parsing should be skipped, not blow up."""
        db = _mock_db()
        good_row = _make_event_row(event_id=1)
        # Bad row: start_time == end_time triggers Pydantic validation error
        bad_row = _make_event_row(
            event_id=2, start_offset_seconds=100.0, duration_minutes=0
        )
        db.execute_query.return_value = [good_row, bad_row]
        repo = CalendarRepository(db=db)

        events = repo.get_calendar_events()

        assert len(events) == 1
        assert events[0].event_id == "1"

    def test_get_events_from_db_null_modified_time(self):
        db = _mock_db()
        row = _make_event_row(modified_offset_seconds=None)
        db.execute_query.return_value = [row]
        repo = CalendarRepository(db=db)

        events = repo.get_calendar_events()

        assert events[0].modified_time is None

    def test_get_events_from_ics_parser(self):
        db = _mock_db()
        ics = _mock_ics_parser()
        mock_event = CalendarEvent(
            event_id="ics-evt-1",
            calendar_id="ics-cal-1",
            title="ICS Meeting",
            start_time=datetime(2024, 6, 15, 10, 0),
            end_time=datetime(2024, 6, 15, 11, 0),
        )
        ics.get_all_events.return_value = [mock_event]
        repo = CalendarRepository(db=db, ics_parser=ics)

        events = repo.get_calendar_events(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31),
            calendar_id="ics-cal-1",
        )

        assert len(events) == 1
        assert events[0].title == "ICS Meeting"
        ics.get_all_events.assert_called_once_with(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31),
            calendar_id="ics-cal-1",
        )
        db.execute_query.assert_not_called()

    def test_get_events_from_ics_parser_respects_limit(self):
        db = _mock_db()
        ics = _mock_ics_parser()
        mock_events = [
            CalendarEvent(
                event_id=f"evt-{i}",
                calendar_id="cal-1",
                title=f"Event {i}",
                start_time=datetime(2024, 6, 15, 10 + i, 0),
                end_time=datetime(2024, 6, 15, 11 + i, 0),
            )
            for i in range(5)
        ]
        ics.get_all_events.return_value = mock_events
        repo = CalendarRepository(db=db, ics_parser=ics)

        events = repo.get_calendar_events(limit=3)

        assert len(events) == 3

    def test_get_events_from_ics_parser_no_truncation_when_under_limit(self):
        db = _mock_db()
        ics = _mock_ics_parser()
        ics.get_all_events.return_value = [
            CalendarEvent(
                event_id="evt-1",
                calendar_id="cal-1",
                title="Only One",
                start_time=datetime(2024, 6, 15, 10, 0),
                end_time=datetime(2024, 6, 15, 11, 0),
            )
        ]
        repo = CalendarRepository(db=db, ics_parser=ics)

        events = repo.get_calendar_events(limit=100)

        assert len(events) == 1


# ---------------------------------------------------------------------------
# Row-to-model mapping
# ---------------------------------------------------------------------------


class TestRowToCalendarEvent:
    def test_maps_all_fields(self):
        row = _make_event_row(
            event_id=42,
            calendar_id=7,
            title="Design Review",
            is_recurring=True,
        )
        event = CalendarRepository._row_to_calendar_event(row)

        assert event.event_id == "42"
        assert event.calendar_id == "7"
        assert event.title == "Design Review"
        assert event.is_recurring is True
        assert isinstance(event.start_time, datetime)
        assert isinstance(event.end_time, datetime)
        assert event.end_time > event.start_time

    def test_null_title_defaults_to_calendar_event(self):
        row = _make_event_row(title=None)  # type: ignore[arg-type]
        row["title"] = None
        event = CalendarRepository._row_to_calendar_event(row)
        assert event.title == "Calendar Event"

    def test_null_event_id_defaults_to_empty(self):
        row = _make_event_row()
        row["event_id"] = None
        event = CalendarRepository._row_to_calendar_event(row)
        assert event.event_id == ""

    def test_null_calendar_id_defaults_to_empty(self):
        row = _make_event_row()
        row["calendar_id"] = None
        event = CalendarRepository._row_to_calendar_event(row)
        assert event.calendar_id == ""

    def test_start_time_uses_cf_conversion(self):
        cf_seconds = 700_000_000.0
        row = _make_event_row(start_offset_seconds=cf_seconds)
        event = CalendarRepository._row_to_calendar_event(row)

        expected = CF_EPOCH + timedelta(seconds=cf_seconds)
        assert event.start_time == expected
