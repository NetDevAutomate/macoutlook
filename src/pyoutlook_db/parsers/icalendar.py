"""iCalendar (.ics) file parser for modern Outlook calendar data.

This module provides functionality to parse .ics files from the modern Outlook
data structure (Omc directories) and convert them to CalendarEvent objects.
"""

import glob
from datetime import datetime
from pathlib import Path

import structlog
from icalendar import Calendar

from ..models.calendar import CalendarEvent

logger = structlog.get_logger(__name__)


class ICalendarParser:
    """Parser for .ics files containing calendar events."""

    def __init__(self, outlook_profile_path: str | None = None) -> None:
        """Initialize the iCalendar parser.

        Args:
            outlook_profile_path: Optional path to Outlook profile directory
        """
        self.outlook_profile_path = outlook_profile_path
        logger.info("Initialized ICalendarParser", profile_path=outlook_profile_path)

    def find_ics_files(self) -> list[str]:
        """Find all .ics files in the Outlook profile directory.

        Returns:
            List of paths to .ics files
        """
        if self.outlook_profile_path:
            base_path = Path(self.outlook_profile_path)
        else:
            # Default path to Outlook profile
            base_path = (
                Path.home()
                / "Library"
                / "Group Containers"
                / "UBF8T346G9.Office"
                / "Outlook"
                / "Outlook 15 Profiles"
                / "Main Profile"
            )

        # Search for .ics files in the Omc calendar directories
        search_pattern = str(base_path / "Omc" / "*" / "calendar" / "*" / "*.ics")
        ics_files = glob.glob(search_pattern)

        logger.info("Found .ics files", count=len(ics_files), pattern=search_pattern)
        return ics_files

    def parse_ics_file(self, file_path: str) -> list[CalendarEvent]:
        """Parse a single .ics file and extract calendar events.

        Args:
            file_path: Path to the .ics file

        Returns:
            List of CalendarEvent objects
        """
        events = []

        try:
            with open(file_path, 'rb') as f:
                calendar = Calendar.from_ical(f.read())

            for component in calendar.walk():
                if component.name == "VEVENT":
                    try:
                        event = self._parse_vevent(component, file_path)
                        if event:
                            events.append(event)
                    except Exception as e:
                        logger.warning(
                            "Failed to parse event in .ics file",
                            file=file_path,
                            error=str(e)
                        )
                        continue

        except Exception as e:
            logger.error(
                "Failed to parse .ics file",
                file=file_path,
                error=str(e)
            )

        logger.debug("Parsed .ics file", file=file_path, events_count=len(events))
        return events

    def _parse_vevent(self, vevent, file_path: str) -> CalendarEvent | None:
        """Parse a VEVENT component into a CalendarEvent.

        Args:
            vevent: iCalendar VEVENT component
            file_path: Path to the source .ics file

        Returns:
            CalendarEvent object or None if parsing fails
        """
        try:
            # Extract basic event information
            uid = str(vevent.get('UID', ''))
            summary = str(vevent.get('SUMMARY', ''))
            description = str(vevent.get('DESCRIPTION', ''))
            location = str(vevent.get('LOCATION', ''))

            # Extract dates
            dtstart = vevent.get('DTSTART')
            dtend = vevent.get('DTEND')

            if not dtstart or not dtend:
                logger.warning("Event missing start or end time", uid=uid)
                return None

            # Convert to datetime objects
            start_time = self._convert_to_datetime(dtstart.dt)
            end_time = self._convert_to_datetime(dtend.dt)

            if not start_time or not end_time:
                logger.warning("Failed to parse event times", uid=uid)
                return None

            # Extract additional properties
            is_all_day = hasattr(dtstart.dt, 'date') and not hasattr(dtstart.dt, 'hour')
            is_recurring = bool(vevent.get('RRULE'))

            # Extract organizer
            organizer = vevent.get('ORGANIZER')
            organizer_email = ''
            organizer_name = ''
            if organizer:
                organizer_email = str(organizer).replace('mailto:', '')
                organizer_name = str(organizer.params.get('CN', ''))

            # Extract attendees
            attendees = []
            for attendee in vevent.get('ATTENDEE', []):
                if isinstance(attendee, list):
                    attendees.extend([str(a).replace('mailto:', '') for a in attendee])
                else:
                    attendees.append(str(attendee).replace('mailto:', ''))

            # Extract categories
            categories = []
            cats = vevent.get('CATEGORIES')
            if cats:
                if isinstance(cats, list):
                    categories = [str(c) for c in cats]
                else:
                    categories = [str(cats)]

            # Extract timestamps
            created_time = None
            modified_time = None

            created = vevent.get('CREATED')
            if created:
                created_time = self._convert_to_datetime(created.dt)

            dtstamp = vevent.get('DTSTAMP')
            if dtstamp:
                modified_time = self._convert_to_datetime(dtstamp.dt)

            # Create CalendarEvent object
            event = CalendarEvent(
                event_id=uid,
                calendar_id=self._extract_calendar_id_from_path(file_path),
                calendar_name="Calendar",
                title=summary or "Untitled Event",
                description=description,
                location=location,
                start_time=start_time,
                end_time=end_time,
                is_all_day=is_all_day,
                organizer=organizer_email,
                organizer_name=organizer_name,
                attendees=attendees,
                required_attendees=attendees,  # iCal doesn't distinguish required/optional
                optional_attendees=[],
                is_recurring=is_recurring,
                categories=categories,
                is_private=False,  # Would need to check CLASS property
                reminder_minutes=None,  # Could extract from VALARM
                created_time=created_time,
                modified_time=modified_time,
            )

            return event

        except Exception as e:
            logger.error("Failed to parse VEVENT", error=str(e), uid=vevent.get('UID'))
            return None

    def _convert_to_datetime(self, dt) -> datetime | None:
        """Convert various datetime formats to Python datetime.

        Args:
            dt: Date/time value from iCalendar

        Returns:
            datetime object or None if conversion fails
        """
        if isinstance(dt, datetime):
            # Remove timezone info to make it naive for comparison
            return dt.replace(tzinfo=None)
        elif hasattr(dt, 'datetime'):
            return dt.datetime().replace(tzinfo=None)
        elif hasattr(dt, 'date'):
            # Convert date to datetime at midnight
            return datetime.combine(dt.date(), datetime.min.time())
        else:
            try:
                dt_obj = datetime.fromisoformat(str(dt))
                return dt_obj.replace(tzinfo=None)
            except (ValueError, TypeError):
                logger.warning("Could not convert to datetime", value=str(dt))
                return None

    def _extract_calendar_id_from_path(self, file_path: str) -> str:
        """Extract calendar ID from the .ics file path.

        Args:
            file_path: Path to the .ics file

        Returns:
            Calendar ID string
        """
        # Extract the calendar directory name from the path
        # Format: .../calendar/CALENDAR_ID/FILE.ics
        path = Path(file_path)
        if 'calendar' in path.parts:
            calendar_idx = path.parts.index('calendar')
            if calendar_idx + 1 < len(path.parts):
                return path.parts[calendar_idx + 1]

        return "unknown"

    def get_all_events(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        calendar_id: str | None = None
    ) -> list[CalendarEvent]:
        """Get all calendar events from .ics files with optional filtering.

        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter
            calendar_id: Optional calendar ID filter

        Returns:
            List of CalendarEvent objects
        """
        all_events = []
        ics_files = self.find_ics_files()

        for ics_file in ics_files:
            if calendar_id and calendar_id not in ics_file:
                continue

            events = self.parse_ics_file(ics_file)
            all_events.extend(events)

        # Apply date filters
        if start_date or end_date:
            filtered_events = []
            for event in all_events:
                if start_date and event.start_time < start_date:
                    continue
                if end_date and event.end_time > end_date:
                    continue
                filtered_events.append(event)
            all_events = filtered_events

        # Sort by start time
        all_events.sort(key=lambda e: e.start_time)

        logger.info(
            "Retrieved calendar events from .ics files",
            total_events=len(all_events),
            start_date=start_date,
            end_date=end_date,
            calendar_id=calendar_id
        )

        return all_events

    def get_calendars(self) -> list[dict]:
        """Get list of available calendars from .ics file directories.

        Returns:
            List of calendar information dictionaries
        """
        ics_files = self.find_ics_files()
        calendar_ids = set()

        for ics_file in ics_files:
            calendar_id = self._extract_calendar_id_from_path(ics_file)
            calendar_ids.add(calendar_id)

        calendars = []
        for i, calendar_id in enumerate(sorted(calendar_ids)):
            calendars.append({
                'calendar_id': calendar_id,
                'name': f'Calendar {calendar_id}',
                'color': None,
                'is_default': i == 0,  # First one is default
                'is_shared': False,
                'owner': None,
            })

        logger.info("Retrieved calendars from .ics files", count=len(calendars))
        return calendars
