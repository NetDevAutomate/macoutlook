"""Unit tests for ICalendarParser."""

from datetime import datetime
from pathlib import Path

import pytest

from macoutlook.parsers.icalendar import ICalendarParser


# Minimal valid .ics file content
_SIMPLE_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-uid-001@example.com
SUMMARY:Team Standup
DTSTART:20250615T090000Z
DTEND:20250615T091500Z
LOCATION:Room 42
ORGANIZER;CN=Alice Smith:mailto:alice@example.com
ATTENDEE;CN=Bob Jones:mailto:bob@example.com
CATEGORIES:Work
DESCRIPTION:Daily standup meeting
CREATED:20250101T120000Z
DTSTAMP:20250601T080000Z
END:VEVENT
END:VCALENDAR
"""

_MULTI_EVENT_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:event-1@example.com
SUMMARY:Morning Meeting
DTSTART:20250615T090000Z
DTEND:20250615T100000Z
END:VEVENT
BEGIN:VEVENT
UID:event-2@example.com
SUMMARY:Lunch
DTSTART:20250615T120000Z
DTEND:20250615T130000Z
END:VEVENT
BEGIN:VEVENT
UID:event-3@example.com
SUMMARY:Afternoon Review
DTSTART:20250615T150000Z
DTEND:20250615T160000Z
END:VEVENT
END:VCALENDAR
"""

_RECURRING_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:recurring-001@example.com
SUMMARY:Weekly Sync
DTSTART:20250615T140000Z
DTEND:20250615T150000Z
RRULE:FREQ=WEEKLY;BYDAY=MO
END:VEVENT
END:VCALENDAR
"""

_MISSING_TIMES_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:no-times@example.com
SUMMARY:Broken Event
END:VEVENT
END:VCALENDAR
"""


def _write_ics(path: Path, content: str) -> Path:
    path.write_text(content)
    return path


class TestICalendarParser:
    def test_init(self):
        parser = ICalendarParser()
        assert parser.outlook_profile_path is None

    def test_init_with_path(self, tmp_path: Path):
        parser = ICalendarParser(outlook_profile_path=str(tmp_path))
        assert parser.outlook_profile_path == str(tmp_path)

    def test_find_ics_files_empty(self, tmp_path: Path):
        parser = ICalendarParser(outlook_profile_path=str(tmp_path))
        files = parser.find_ics_files()
        assert files == []

    def test_find_ics_files_in_omc(self, tmp_path: Path):
        omc_dir = tmp_path / "Omc" / "acct1" / "calendar" / "cal1"
        omc_dir.mkdir(parents=True)
        _write_ics(omc_dir / "event1.ics", _SIMPLE_ICS)
        _write_ics(omc_dir / "event2.ics", _SIMPLE_ICS)

        parser = ICalendarParser(outlook_profile_path=str(tmp_path))
        files = parser.find_ics_files()
        assert len(files) == 2


class TestParseIcsFile:
    def test_parse_single_event(self, tmp_path: Path):
        ics_file = _write_ics(tmp_path / "test.ics", _SIMPLE_ICS)

        parser = ICalendarParser()
        events = parser.parse_ics_file(str(ics_file))

        assert len(events) == 1
        event = events[0]
        assert event.event_id == "test-uid-001@example.com"
        assert event.title == "Team Standup"
        assert event.location == "Room 42"
        assert event.description == "Daily standup meeting"
        assert isinstance(event.start_time, datetime)
        assert isinstance(event.end_time, datetime)
        assert event.duration_minutes == 15

    def test_parse_organizer(self, tmp_path: Path):
        ics_file = _write_ics(tmp_path / "test.ics", _SIMPLE_ICS)

        parser = ICalendarParser()
        events = parser.parse_ics_file(str(ics_file))

        event = events[0]
        assert "alice@example.com" in event.organizer
        assert event.organizer_name == "Alice Smith"

    def test_parse_attendees(self, tmp_path: Path):
        ics_file = _write_ics(tmp_path / "test.ics", _SIMPLE_ICS)

        parser = ICalendarParser()
        events = parser.parse_ics_file(str(ics_file))

        event = events[0]
        assert len(event.attendees) == 1
        assert "bob@example.com" in event.attendees[0]

    def test_parse_categories(self, tmp_path: Path):
        ics_file = _write_ics(tmp_path / "test.ics", _SIMPLE_ICS)

        parser = ICalendarParser()
        events = parser.parse_ics_file(str(ics_file))

        event = events[0]
        assert len(event.categories) >= 1

    def test_parse_timestamps(self, tmp_path: Path):
        ics_file = _write_ics(tmp_path / "test.ics", _SIMPLE_ICS)

        parser = ICalendarParser()
        events = parser.parse_ics_file(str(ics_file))

        event = events[0]
        assert event.created_time is not None
        assert event.modified_time is not None

    def test_parse_multiple_events(self, tmp_path: Path):
        ics_file = _write_ics(tmp_path / "multi.ics", _MULTI_EVENT_ICS)

        parser = ICalendarParser()
        events = parser.parse_ics_file(str(ics_file))

        assert len(events) == 3
        titles = {e.title for e in events}
        assert "Morning Meeting" in titles
        assert "Lunch" in titles
        assert "Afternoon Review" in titles

    def test_parse_recurring_event(self, tmp_path: Path):
        ics_file = _write_ics(tmp_path / "recurring.ics", _RECURRING_ICS)

        parser = ICalendarParser()
        events = parser.parse_ics_file(str(ics_file))

        assert len(events) == 1
        assert events[0].is_recurring is True

    def test_parse_event_missing_times(self, tmp_path: Path):
        ics_file = _write_ics(tmp_path / "broken.ics", _MISSING_TIMES_ICS)

        parser = ICalendarParser()
        events = parser.parse_ics_file(str(ics_file))

        # Event with missing times should be skipped gracefully
        assert len(events) == 0

    def test_parse_nonexistent_file(self):
        parser = ICalendarParser()
        events = parser.parse_ics_file("/nonexistent/path.ics")
        assert events == []

    def test_parse_invalid_file(self, tmp_path: Path):
        bad_file = tmp_path / "bad.ics"
        bad_file.write_text("this is not ics content")

        parser = ICalendarParser()
        events = parser.parse_ics_file(str(bad_file))
        assert events == []


class TestConvertToDatetime:
    def test_from_datetime(self):
        parser = ICalendarParser()
        dt = datetime(2025, 6, 15, 10, 30)
        result = parser._convert_to_datetime(dt)
        assert result == datetime(2025, 6, 15, 10, 30)

    def test_from_none_like(self):
        parser = ICalendarParser()
        result = parser._convert_to_datetime(None)
        assert result is None

    def test_from_string(self):
        parser = ICalendarParser()
        result = parser._convert_to_datetime("2025-06-15T10:30:00")
        assert result is not None
        assert result.year == 2025


class TestExtractCalendarId:
    def test_extract_from_path(self):
        parser = ICalendarParser()
        result = parser._extract_calendar_id_from_path(
            "/path/to/Omc/acct1/calendar/cal123/event.ics"
        )
        assert result == "cal123"

    def test_extract_no_calendar_in_path(self):
        parser = ICalendarParser()
        result = parser._extract_calendar_id_from_path("/path/to/event.ics")
        assert result == "unknown"


class TestGetAllEvents:
    def _setup_ics_dir(self, tmp_path: Path) -> ICalendarParser:
        omc_dir = tmp_path / "Omc" / "acct" / "calendar" / "cal1"
        omc_dir.mkdir(parents=True)
        _write_ics(omc_dir / "multi.ics", _MULTI_EVENT_ICS)
        return ICalendarParser(outlook_profile_path=str(tmp_path))

    def test_get_all_events(self, tmp_path: Path):
        parser = self._setup_ics_dir(tmp_path)
        events = parser.get_all_events()
        assert len(events) == 3

    def test_get_all_events_sorted_by_start(self, tmp_path: Path):
        parser = self._setup_ics_dir(tmp_path)
        events = parser.get_all_events()
        for i in range(len(events) - 1):
            assert events[i].start_time <= events[i + 1].start_time

    def test_get_all_events_date_filter(self, tmp_path: Path):
        parser = self._setup_ics_dir(tmp_path)
        # Filter to only afternoon events (after 14:00)
        events = parser.get_all_events(
            start_date=datetime(2025, 6, 15, 14, 0),
        )
        assert len(events) == 1
        assert events[0].title == "Afternoon Review"

    def test_get_all_events_no_files(self, tmp_path: Path):
        parser = ICalendarParser(outlook_profile_path=str(tmp_path))
        events = parser.get_all_events()
        assert events == []


class TestGetCalendars:
    def test_get_calendars(self, tmp_path: Path):
        omc_dir = tmp_path / "Omc" / "acct" / "calendar" / "cal1"
        omc_dir.mkdir(parents=True)
        _write_ics(omc_dir / "event.ics", _SIMPLE_ICS)

        parser = ICalendarParser(outlook_profile_path=str(tmp_path))
        calendars = parser.get_calendars()

        assert len(calendars) >= 1
        assert calendars[0]["calendar_id"] is not None

    def test_get_calendars_empty(self, tmp_path: Path):
        parser = ICalendarParser(outlook_profile_path=str(tmp_path))
        calendars = parser.get_calendars()
        assert calendars == []
