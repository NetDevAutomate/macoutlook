"""Unit tests for Pydantic models and enums."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from macoutlook.models.calendar import Calendar, CalendarEvent, EventStatus
from macoutlook.models.email_message import AttachmentInfo, EmailMessage
from macoutlook.models.enums import ContentSource, FlagStatus, Priority


class TestEmailMessage:
    def test_minimal_construction(self):
        email = EmailMessage(
            message_id="<test@example.com>",
            record_id=1,
            timestamp=datetime(2025, 1, 1),
        )
        assert email.message_id == "<test@example.com>"
        assert email.record_id == 1
        assert email.subject == ""
        assert email.content_source == ContentSource.PREVIEW_ONLY
        assert email.attachments == ()
        assert email.body_text is None

    def test_full_construction(self):
        att = AttachmentInfo(filename="doc.pdf", size=1024, content_type="application/pdf")
        email = EmailMessage(
            message_id="<full@example.com>",
            record_id=42,
            subject="Test Subject",
            sender="sender@example.com",
            sender_name="Test Sender",
            recipients=["a@example.com", "b@example.com"],
            cc_recipients=["c@example.com"],
            timestamp=datetime(2025, 6, 15, 10, 30),
            time_sent=datetime(2025, 6, 15, 10, 29),
            size=4096,
            is_read=True,
            is_outgoing=False,
            flag_status=FlagStatus.FLAGGED,
            priority=Priority.HIGH,
            folder_id=5,
            has_attachments=True,
            body_text="Hello world",
            body_html="<p>Hello world</p>",
            body_markdown="Hello world",
            preview="Hello...",
            attachments=(att,),
            content_source=ContentSource.MESSAGE_SOURCE,
        )
        assert email.subject == "Test Subject"
        assert len(email.recipients) == 2
        assert email.flag_status == FlagStatus.FLAGGED
        assert email.priority == Priority.HIGH
        assert email.content_source == ContentSource.MESSAGE_SOURCE
        assert email.attachments[0].filename == "doc.pdf"

    def test_frozen_model(self):
        email = EmailMessage(
            message_id="<frozen@example.com>",
            record_id=1,
            timestamp=datetime(2025, 1, 1),
        )
        with pytest.raises(ValidationError):
            email.subject = "mutated"  # type: ignore[misc]

    def test_datetime_from_timestamp(self):
        email = EmailMessage(
            message_id="<ts@example.com>",
            record_id=1,
            timestamp=1700000000,  # type: ignore[arg-type]
        )
        assert isinstance(email.timestamp, datetime)

    def test_datetime_from_iso_string(self):
        email = EmailMessage(
            message_id="<iso@example.com>",
            record_id=1,
            timestamp="2025-01-15T10:30:00",  # type: ignore[arg-type]
        )
        assert email.timestamp.year == 2025

    def test_serialization(self):
        email = EmailMessage(
            message_id="<ser@example.com>",
            record_id=1,
            timestamp=datetime(2025, 1, 1),
        )
        data = email.model_dump()
        assert data["message_id"] == "<ser@example.com>"
        assert isinstance(data["timestamp"], str)  # serialized via field_serializer

    def test_model_copy_for_enrichment(self):
        email = EmailMessage(
            message_id="<copy@example.com>",
            record_id=1,
            timestamp=datetime(2025, 1, 1),
            preview="short preview",
        )
        enriched = email.model_copy(update={
            "body_text": "Full body text here",
            "content_source": ContentSource.MESSAGE_SOURCE,
        })
        assert enriched.body_text == "Full body text here"
        assert enriched.content_source == ContentSource.MESSAGE_SOURCE
        assert enriched.preview == "short preview"  # preserved
        assert email.body_text is None  # original unchanged


class TestAttachmentInfo:
    def test_construction(self):
        att = AttachmentInfo(
            filename="report.pdf",
            size=2048,
            content_type="application/pdf",
            content_id="<img001>",
        )
        assert att.filename == "report.pdf"
        assert att.size == 2048

    def test_optional_size(self):
        att = AttachmentInfo(filename="unknown.bin", content_type="application/octet-stream")
        assert att.size is None

    def test_frozen(self):
        att = AttachmentInfo(filename="test.txt", content_type="text/plain")
        with pytest.raises(ValidationError):
            att.filename = "changed.txt"  # type: ignore[misc]


class TestCalendarEvent:
    def test_minimal_construction(self):
        event = CalendarEvent(
            event_id="ev1",
            calendar_id="cal1",
            start_time=datetime(2025, 6, 15, 14, 0),
            end_time=datetime(2025, 6, 15, 15, 0),
        )
        assert event.duration_minutes == 60
        assert event.status == EventStatus.BUSY

    def test_end_before_start_raises(self):
        with pytest.raises(ValidationError, match="end_time must be after start_time"):
            CalendarEvent(
                event_id="ev1",
                calendar_id="cal1",
                start_time=datetime(2025, 6, 15, 15, 0),
                end_time=datetime(2025, 6, 15, 14, 0),
            )

    def test_frozen(self):
        event = CalendarEvent(
            event_id="ev1",
            calendar_id="cal1",
            start_time=datetime(2025, 6, 15, 14, 0),
            end_time=datetime(2025, 6, 15, 15, 0),
        )
        with pytest.raises(ValidationError):
            event.title = "mutated"  # type: ignore[misc]


class TestCalendar:
    def test_construction(self):
        cal = Calendar(calendar_id="cal1", name="Work")
        assert cal.calendar_id == "cal1"
        assert cal.is_default is False


class TestEnums:
    def test_content_source_values(self):
        assert ContentSource.MESSAGE_SOURCE == "message_source"
        assert ContentSource.PREVIEW_ONLY == "preview_only"

    def test_flag_status_values(self):
        assert FlagStatus.NOT_FLAGGED == 0
        assert FlagStatus.FLAGGED == 1
        assert FlagStatus.COMPLETE == 2

    def test_priority_values(self):
        assert Priority.LOW == 1
        assert Priority.NORMAL == 3
        assert Priority.HIGH == 5

    def test_flag_status_from_int(self):
        assert FlagStatus(0) == FlagStatus.NOT_FLAGGED
        assert FlagStatus(1) == FlagStatus.FLAGGED

    def test_priority_from_int(self):
        assert Priority(3) == Priority.NORMAL
        assert Priority(5) == Priority.HIGH

    def test_content_source_is_str(self):
        assert isinstance(ContentSource.MESSAGE_SOURCE, str)
        assert f"source={ContentSource.MESSAGE_SOURCE}" == "source=message_source"
