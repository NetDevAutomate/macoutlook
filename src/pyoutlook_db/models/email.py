"""Email data models for pyoutlook-db library.

This module defines Pydantic models for representing email messages and related data
structures with proper validation and serialization.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, validator


class EmailPriority(str, Enum):
    """Email priority levels."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class EmailMessage(BaseModel):
    """Represents an email message with all metadata and content.

    This model provides a structured representation of email data extracted
    from the Outlook SQLite database, with automatic content parsing and
    validation.
    """

    message_id: str = Field(..., description="Unique message identifier")
    subject: str = Field(default="", description="Email subject line")
    sender: str = Field(..., description="Sender email address")
    sender_name: str | None = Field(None, description="Sender display name")
    recipients: list[str] = Field(
        default_factory=list, description="List of recipient email addresses"
    )
    cc_recipients: list[str] = Field(
        default_factory=list, description="List of CC recipient email addresses"
    )
    bcc_recipients: list[str] = Field(
        default_factory=list, description="List of BCC recipient email addresses"
    )

    # Timestamps
    timestamp: datetime = Field(..., description="Email sent/received timestamp")
    received_time: datetime | None = Field(
        None, description="Time email was received"
    )

    # Content in various formats
    content_html: str = Field(default="", description="Original HTML content")
    content_text: str = Field(default="", description="Plain text content")
    content_markdown: str = Field(default="", description="Markdown formatted content")

    # Email metadata
    folder: str = Field(default="", description="Folder containing the email")
    is_read: bool = Field(default=False, description="Whether email has been read")
    is_flagged: bool = Field(default=False, description="Whether email is flagged")
    priority: EmailPriority = Field(
        default=EmailPriority.NORMAL, description="Email priority level"
    )

    # Attachments and categories
    attachments: list[str] = Field(
        default_factory=list, description="List of attachment filenames"
    )
    categories: list[str] = Field(
        default_factory=list, description="List of assigned categories"
    )

    # Additional metadata
    message_size: int | None = Field(None, description="Message size in bytes")
    conversation_id: str | None = Field(
        None, description="Conversation thread identifier"
    )

    class Config:
        """Pydantic configuration."""

        json_encoders = {datetime: lambda v: v.isoformat()}
        json_schema_extra = {
            "example": {
                "message_id": "AAMkAGE1M2IyZGNiLTI0NjYtNGIxYi05NTgxLTkwZjM4ZGY5OTk4MwBGAAAAAADUuTJK1K9TQoJ+1RLWA2cMBwD9RuUDxJWlRIJ+1RLWA2cMAAAAAAEMAAD9RuUDxJWlRIJ+1RLWA2cMAAAB4H+EAAA=",
                "subject": "Meeting Tomorrow",
                "sender": "john.doe@example.com",
                "sender_name": "John Doe",
                "recipients": ["jane.smith@example.com"],
                "timestamp": "2024-01-15T10:30:00",
                "content_text": "Hi Jane, let's meet tomorrow at 2 PM.",
                "content_markdown": "Hi Jane, let's meet tomorrow at 2 PM.",
                "folder": "Inbox",
                "is_read": False,
                "attachments": [],
                "categories": ["Work"],
            }
        }

    @validator("recipients", "cc_recipients", "bcc_recipients", pre=True)
    def parse_recipients(cls, v):
        """Parse recipients from various input formats."""
        if isinstance(v, str):
            # Handle semicolon or comma separated recipients
            return [
                email.strip()
                for email in v.replace(";", ",").split(",")
                if email.strip()
            ]
        elif isinstance(v, list):
            return v
        return []

    @validator("timestamp", "received_time", pre=True)
    def parse_datetime(cls, v):
        """Parse datetime from various input formats."""
        if isinstance(v, str):
            # Handle various datetime formats from Outlook database
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                # Try parsing as timestamp
                try:
                    return datetime.fromtimestamp(float(v))
                except (ValueError, TypeError):
                    raise ValueError(f"Unable to parse datetime: {v}")
        return v

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary with proper serialization."""
        return self.dict(by_alias=True)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return self.json(by_alias=True)

    def get_summary(self) -> str:
        """Get a brief summary of the email."""
        content_preview = (
            self.content_text[:100] + "..."
            if len(self.content_text) > 100
            else self.content_text
        )
        return f"From: {self.sender_name or self.sender}\nSubject: {self.subject}\nPreview: {content_preview}"


class EmailSearchFilter(BaseModel):
    """Filter criteria for email searches.

    This model defines the various filters that can be applied when searching
    for emails in the Outlook database.
    """

    query: str | None = Field(
        None, description="Text to search in subject and content"
    )
    sender: str | None = Field(None, description="Filter by sender email or name")
    subject: str | None = Field(None, description="Filter by subject text")
    folders: list[str] | None = Field(
        None, description="List of folders to search in"
    )

    # Status filters
    is_read: bool | None = Field(None, description="Filter by read status")
    is_flagged: bool | None = Field(None, description="Filter by flagged status")
    has_attachments: bool | None = Field(
        None, description="Filter by attachment presence"
    )

    # Date filters
    start_date: datetime | None = Field(
        None, description="Start date for date range filter"
    )
    end_date: datetime | None = Field(
        None, description="End date for date range filter"
    )

    # Category and priority filters
    categories: list[str] | None = Field(None, description="Filter by categories")
    priority: EmailPriority | None = Field(
        None, description="Filter by priority level"
    )

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


class EmailStats(BaseModel):
    """Statistics about email data.

    This model provides summary statistics for email collections,
    useful for analytics and reporting.
    """

    total_count: int = Field(..., description="Total number of emails")
    unread_count: int = Field(..., description="Number of unread emails")
    flagged_count: int = Field(..., description="Number of flagged emails")
    with_attachments_count: int = Field(
        ..., description="Number of emails with attachments"
    )

    # Date range
    earliest_date: datetime | None = Field(None, description="Earliest email date")
    latest_date: datetime | None = Field(None, description="Latest email date")

    # Size statistics
    total_size_bytes: int | None = Field(
        None, description="Total size of all emails in bytes"
    )
    average_size_bytes: float | None = Field(
        None, description="Average email size in bytes"
    )

    # Folder distribution
    folder_distribution: dict[str, int] = Field(
        default_factory=dict, description="Count of emails per folder"
    )

    # Top senders
    top_senders: dict[str, int] = Field(
        default_factory=dict, description="Top senders by email count"
    )

    def get_summary(self) -> str:
        """Get a text summary of the statistics."""
        summary_lines = [
            f"Total emails: {self.total_count:,}",
            f"Unread: {self.unread_count:,} ({self.unread_count / self.total_count * 100:.1f}%)"
            if self.total_count > 0
            else "Unread: 0",
            f"Flagged: {self.flagged_count:,}",
            f"With attachments: {self.with_attachments_count:,}",
        ]

        if self.earliest_date and self.latest_date:
            summary_lines.append(
                f"Date range: {self.earliest_date.date()} to {self.latest_date.date()}"
            )

        if self.total_size_bytes:
            size_mb = self.total_size_bytes / (1024 * 1024)
            summary_lines.append(f"Total size: {size_mb:.1f} MB")

        return "\n".join(summary_lines)
