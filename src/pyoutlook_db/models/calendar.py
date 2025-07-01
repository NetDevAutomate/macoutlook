"""Calendar data models for pyoutlook-db library.

This module defines Pydantic models for representing calendar events, calendars,
and related data structures with proper validation and serialization.
"""

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, validator


class EventStatus(str, Enum):
    """Calendar event status."""

    FREE = "free"
    TENTATIVE = "tentative"
    BUSY = "busy"
    OUT_OF_OFFICE = "out_of_office"


class ResponseStatus(str, Enum):
    """Response status for calendar events."""

    NONE = "none"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    TENTATIVE = "tentative"


class RecurrenceType(str, Enum):
    """Recurrence pattern types."""

    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class Calendar(BaseModel):
    """Represents a calendar container.

    This model represents an Outlook calendar that contains events.
    """

    calendar_id: str = Field(..., description="Unique calendar identifier")
    name: str = Field(..., description="Calendar display name")
    color: str | None = Field(None, description="Calendar color")
    is_default: bool = Field(
        default=False, description="Whether this is the default calendar"
    )
    is_shared: bool = Field(
        default=False, description="Whether this calendar is shared"
    )
    owner: str | None = Field(None, description="Calendar owner email address")

    class Config:
        """Pydantic configuration."""

        json_schema_extra = {
            "example": {
                "calendar_id": "AAMkAGE1M2IyZGNiLTI0NjYtNGIxYi05NTgxLTkwZjM4ZGY5OTk4MwBGAAAAAADUuTJK1K9TQoJ+1RLWA2cM",
                "name": "Calendar",
                "color": "#1F497D",
                "is_default": True,
                "is_shared": False,
                "owner": "user@example.com",
            }
        }


class CalendarEvent(BaseModel):
    """Represents a calendar event with all metadata and details.

    This model provides a structured representation of calendar event data
    extracted from the Outlook SQLite database.
    """

    event_id: str = Field(..., description="Unique event identifier")
    calendar_id: str = Field(..., description="Parent calendar identifier")
    calendar_name: str | None = Field(None, description="Parent calendar name")

    # Basic event information
    title: str = Field(default="", description="Event title/subject")
    description: str = Field(default="", description="Event description/body")
    location: str = Field(default="", description="Event location")

    # Timing information
    start_time: datetime = Field(..., description="Event start time")
    end_time: datetime = Field(..., description="Event end time")
    is_all_day: bool = Field(default=False, description="Whether event is all-day")

    # Status and response
    status: EventStatus = Field(default=EventStatus.BUSY, description="Event status")
    my_response: ResponseStatus = Field(
        default=ResponseStatus.NONE, description="User's response to the event"
    )

    # Organizer and attendees
    organizer: str | None = Field(None, description="Event organizer email")
    organizer_name: str | None = Field(
        None, description="Event organizer display name"
    )
    attendees: list[str] = Field(
        default_factory=list, description="List of attendee email addresses"
    )
    required_attendees: list[str] = Field(
        default_factory=list, description="List of required attendees"
    )
    optional_attendees: list[str] = Field(
        default_factory=list, description="List of optional attendees"
    )

    # Recurrence information
    is_recurring: bool = Field(default=False, description="Whether event is recurring")
    recurrence_type: RecurrenceType = Field(
        default=RecurrenceType.NONE, description="Recurrence pattern"
    )
    recurrence_end_date: datetime | None = Field(
        None, description="End date for recurring events"
    )

    # Additional metadata
    categories: list[str] = Field(
        default_factory=list, description="List of assigned categories"
    )
    is_private: bool = Field(
        default=False, description="Whether event is marked as private"
    )
    reminder_minutes: int | None = Field(
        None, description="Reminder time in minutes before event"
    )

    # Creation and modification timestamps
    created_time: datetime | None = Field(
        None, description="Event creation timestamp"
    )
    modified_time: datetime | None = Field(
        None, description="Last modification timestamp"
    )

    class Config:
        """Pydantic configuration."""

        json_encoders = {datetime: lambda v: v.isoformat()}
        json_schema_extra = {
            "example": {
                "event_id": "AAMkAGE1M2IyZGNiLTI0NjYtNGIxYi05NTgxLTkwZjM4ZGY5OTk4MwBGAAAAAADUuTJK1K9TQoJ+1RLWA2cMBwD9RuUDxJWlRIJ+1RLWA2cMAAAAAAENAAD9RuUDxJWlRIJ+1RLWA2cMAAAB4H+FAAA=",
                "calendar_id": "AAMkAGE1M2IyZGNiLTI0NjYtNGIxYi05NTgxLTkwZjM4ZGY5OTk4MwBGAAAAAADUuTJK1K9TQoJ+1RLWA2cM",
                "title": "Team Meeting",
                "description": "Weekly team sync meeting",
                "location": "Conference Room A",
                "start_time": "2024-01-15T14:00:00",
                "end_time": "2024-01-15T15:00:00",
                "is_all_day": False,
                "organizer": "manager@example.com",
                "attendees": ["team1@example.com", "team2@example.com"],
                "status": "busy",
            }
        }

    @validator("attendees", "required_attendees", "optional_attendees", pre=True)
    def parse_attendees(cls, v):
        """Parse attendees from various input formats."""
        if isinstance(v, str):
            # Handle semicolon or comma separated attendees
            return [
                email.strip()
                for email in v.replace(";", ",").split(",")
                if email.strip()
            ]
        elif isinstance(v, list):
            return v
        return []

    @validator("end_time")
    def validate_end_time(cls, v, values):
        """Validate that end_time is after start_time."""
        if "start_time" in values and values["start_time"]:
            if v <= values["start_time"]:
                raise ValueError("end_time must be after start_time")
        return v

    @validator(
        "start_time",
        "end_time",
        "created_time",
        "modified_time",
        "recurrence_end_date",
        pre=True,
    )
    def parse_datetime(cls, v):
        """Parse datetime from various input formats."""
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                try:
                    return datetime.fromtimestamp(float(v))
                except (ValueError, TypeError):
                    raise ValueError(f"Unable to parse datetime: {v}")
        return v

    @property
    def duration_minutes(self) -> int:
        """Calculate event duration in minutes."""
        return int((self.end_time - self.start_time).total_seconds() / 60)

    @property
    def is_today(self) -> bool:
        """Check if event is today."""
        today = date.today()
        return self.start_time.date() == today

    @property
    def is_upcoming(self) -> bool:
        """Check if event is in the future."""
        return self.start_time > datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary with proper serialization."""
        return self.dict(by_alias=True)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return self.json(by_alias=True)

    def get_summary(self) -> str:
        """Get a brief summary of the event."""
        time_str = f"{self.start_time.strftime('%Y-%m-%d %H:%M')} - {self.end_time.strftime('%H:%M')}"
        if self.is_all_day:
            time_str = f"{self.start_time.strftime('%Y-%m-%d')} (All Day)"

        summary_lines = [
            f"Title: {self.title}",
            f"Time: {time_str}",
        ]

        if self.location:
            summary_lines.append(f"Location: {self.location}")

        if self.organizer:
            summary_lines.append(f"Organizer: {self.organizer_name or self.organizer}")

        if self.attendees:
            summary_lines.append(f"Attendees: {len(self.attendees)}")

        return "\n".join(summary_lines)


class CalendarEventFilter(BaseModel):
    """Filter criteria for calendar event searches.

    This model defines the various filters that can be applied when searching
    for calendar events in the Outlook database.
    """

    query: str | None = Field(
        None, description="Text to search in title and description"
    )
    calendar_ids: list[str] | None = Field(
        None, description="List of calendar IDs to search in"
    )

    # Date filters
    start_date: datetime | None = Field(
        None, description="Start date for date range filter"
    )
    end_date: datetime | None = Field(
        None, description="End date for date range filter"
    )

    # Status filters
    status: EventStatus | None = Field(None, description="Filter by event status")
    my_response: ResponseStatus | None = Field(
        None, description="Filter by user's response"
    )
    is_all_day: bool | None = Field(None, description="Filter by all-day events")
    is_recurring: bool | None = Field(None, description="Filter by recurring events")

    # Organizer and attendee filters
    organizer: str | None = Field(None, description="Filter by organizer email")
    attendee: str | None = Field(None, description="Filter by attendee email")

    # Category filters
    categories: list[str] | None = Field(None, description="Filter by categories")

    # Pagination
    limit: int = Field(
        default=100, ge=1, le=1000, description="Maximum number of results"
    )
    offset: int = Field(default=0, ge=0, description="Number of results to skip")

    @validator("end_date")
    def validate_date_range(cls, v, values):
        """Validate that end_date is after start_date."""
        if v and "start_date" in values and values["start_date"]:
            if v <= values["start_date"]:
                raise ValueError("end_date must be after start_date")
        return v


class CalendarStats(BaseModel):
    """Statistics about calendar data.

    This model provides summary statistics for calendar events,
    useful for analytics and reporting.
    """

    total_events: int = Field(..., description="Total number of events")
    upcoming_events: int = Field(..., description="Number of upcoming events")
    all_day_events: int = Field(..., description="Number of all-day events")
    recurring_events: int = Field(..., description="Number of recurring events")

    # Date range
    earliest_event: datetime | None = Field(None, description="Earliest event date")
    latest_event: datetime | None = Field(None, description="Latest event date")

    # Calendar distribution
    calendar_distribution: dict[str, int] = Field(
        default_factory=dict, description="Count of events per calendar"
    )

    # Status distribution
    status_distribution: dict[str, int] = Field(
        default_factory=dict, description="Count of events by status"
    )

    # Top organizers
    top_organizers: dict[str, int] = Field(
        default_factory=dict, description="Top organizers by event count"
    )

    def get_summary(self) -> str:
        """Get a text summary of the statistics."""
        summary_lines = [
            f"Total events: {self.total_events:,}",
            f"Upcoming: {self.upcoming_events:,}",
            f"All-day: {self.all_day_events:,}",
            f"Recurring: {self.recurring_events:,}",
        ]

        if self.earliest_event and self.latest_event:
            summary_lines.append(
                f"Date range: {self.earliest_event.date()} to {self.latest_event.date()}"
            )

        return "\n".join(summary_lines)
