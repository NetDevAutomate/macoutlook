"""Calendar data models for macoutlook library."""

from datetime import datetime
from enum import StrEnum

from pydantic import (
    BaseModel,
    ConfigDict,
    field_serializer,
    field_validator,
    model_validator,
)


class EventStatus(StrEnum):
    """Calendar event status."""

    FREE = "free"
    TENTATIVE = "tentative"
    BUSY = "busy"
    OUT_OF_OFFICE = "out_of_office"


class ResponseStatus(StrEnum):
    """Response status for calendar events."""

    NONE = "none"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    TENTATIVE = "tentative"


class RecurrenceType(StrEnum):
    """Recurrence pattern types."""

    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class Calendar(BaseModel):
    """Represents a calendar container."""

    model_config = ConfigDict(frozen=True)

    calendar_id: str
    name: str
    color: str | None = None
    is_default: bool = False
    is_shared: bool = False
    owner: str | None = None


class CalendarEvent(BaseModel):
    """Represents a calendar event with metadata."""

    model_config = ConfigDict(frozen=True)

    event_id: str
    calendar_id: str
    calendar_name: str | None = None

    title: str = ""
    description: str = ""
    location: str = ""

    start_time: datetime
    end_time: datetime
    is_all_day: bool = False

    status: EventStatus = EventStatus.BUSY
    my_response: ResponseStatus = ResponseStatus.NONE

    organizer: str | None = None
    organizer_name: str | None = None
    attendees: list[str] = []
    required_attendees: list[str] = []
    optional_attendees: list[str] = []

    is_recurring: bool = False
    recurrence_type: RecurrenceType = RecurrenceType.NONE
    recurrence_end_date: datetime | None = None

    categories: list[str] = []
    is_private: bool = False
    reminder_minutes: int | None = None

    created_time: datetime | None = None
    modified_time: datetime | None = None

    @field_serializer(
        "start_time", "end_time", "created_time", "modified_time", "recurrence_end_date"
    )
    @classmethod
    def serialize_datetime(cls, v: datetime | None) -> str | None:
        if v is None:
            return None
        return v.isoformat()

    @field_validator(
        "start_time",
        "end_time",
        "created_time",
        "modified_time",
        "recurrence_end_date",
        mode="before",
    )
    @classmethod
    def parse_datetime(cls, v: object) -> object:
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                try:
                    return datetime.fromtimestamp(float(v))
                except (ValueError, TypeError) as e:
                    raise ValueError(f"Unable to parse datetime: {v}") from e
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return datetime.fromtimestamp(v)
        return v

    @model_validator(mode="after")
    def validate_end_after_start(self) -> "CalendarEvent":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self

    @property
    def duration_minutes(self) -> int:
        return int((self.end_time - self.start_time).total_seconds() / 60)
