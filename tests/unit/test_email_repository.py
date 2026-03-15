"""Unit tests for EmailRepository class."""

from datetime import datetime
from unittest.mock import Mock

from macoutlook.core.email_repository import (
    EmailRepository,
    _parse_delimited,
)
from macoutlook.core.protocols import DatabaseProtocol
from macoutlook.models.email_message import EmailMessage
from macoutlook.models.enums import ContentSource, FlagStatus, Priority


def _make_mock_db(rows: list[dict] | None = None) -> Mock:
    """Create a mock DatabaseProtocol with execute_query returning rows."""
    db = Mock(spec=DatabaseProtocol)
    db.is_connected = True
    db.execute_query.return_value = rows if rows is not None else []
    return db


def _make_email_row(
    record_id: int = 1,
    message_id: str = "<test@example.com>",
    subject: str = "Test Subject",
    sender: str = "sender@example.com",
    sender_name: str = "Test Sender",
    recipients: str | None = "recipient@example.com",
    cc_recipients: str | None = None,
    preview: str = "Preview text",
    is_read: int = 1,
    is_outgoing: int = 0,
    flag_status: int = 0,
    priority: int = 3,
    folder_id: int = 1,
    has_attachment: int = 0,
    size: int = 1024,
    time_received: float | None = None,
    time_sent: float | None = None,
) -> dict:
    """Build a realistic email row dict matching the SQL column names."""
    now_ts = datetime.now().timestamp()
    return {
        "Record_RecordID": record_id,
        "Message_MessageID": message_id,
        "Message_NormalizedSubject": subject,
        "Message_SenderAddressList": sender,
        "Message_SenderList": sender_name,
        "Message_ToRecipientAddressList": recipients,
        "Message_CCRecipientAddressList": cc_recipients,
        "Message_TimeReceived": time_received if time_received is not None else now_ts,
        "Message_TimeSent": time_sent if time_sent is not None else now_ts,
        "Message_Preview": preview,
        "Message_ReadFlag": is_read,
        "Message_IsOutgoingMessage": is_outgoing,
        "Record_FlagStatus": flag_status,
        "Record_Priority": priority,
        "Record_FolderID": folder_id,
        "Message_HasAttachment": has_attachment,
        "Message_Size": size,
    }


class TestEmailRepositoryGetEmails:
    """Tests for EmailRepository.get_emails()."""

    def test_returns_email_messages(self):
        row = _make_email_row()
        db = _make_mock_db([row])
        repo = EmailRepository(db)

        emails = repo.get_emails(limit=10)

        assert len(emails) == 1
        assert isinstance(emails[0], EmailMessage)
        assert emails[0].subject == "Test Subject"
        assert emails[0].sender == "sender@example.com"
        assert emails[0].message_id == "<test@example.com>"
        assert emails[0].content_source == ContentSource.PREVIEW_ONLY

    def test_empty_result(self):
        db = _make_mock_db([])
        repo = EmailRepository(db)

        emails = repo.get_emails()
        assert emails == []

    def test_calls_execute_query_with_limit(self):
        db = _make_mock_db([])
        repo = EmailRepository(db)

        repo.get_emails(limit=42)

        db.execute_query.assert_called_once()
        call_args = db.execute_query.call_args
        sql = call_args[0][0]
        params = call_args[0][1]

        assert "LIMIT ?" in sql
        assert params[-1] == 42

    def test_date_filtering(self):
        db = _make_mock_db([])
        repo = EmailRepository(db)
        start = datetime(2024, 1, 1)
        end = datetime(2024, 12, 31)

        repo.get_emails(start_date=start, end_date=end, limit=10)

        call_args = db.execute_query.call_args
        sql = call_args[0][0]
        params = call_args[0][1]

        assert "Message_TimeReceived >= ?" in sql
        assert "Message_TimeReceived <= ?" in sql
        assert params[0] == start.timestamp()
        assert params[1] == end.timestamp()
        assert params[2] == 10  # limit

    def test_skips_unparseable_rows(self):
        """Rows that raise ValueError/KeyError are skipped, not fatal."""
        good_row = _make_email_row(record_id=1)
        # A row where dict() will work but timestamp parsing will fail
        bad_row = _make_email_row(record_id=2)
        bad_row["Message_TimeReceived"] = "not-a-timestamp"

        db = _make_mock_db([bad_row, good_row])
        repo = EmailRepository(db)

        emails = repo.get_emails()
        # The bad row is skipped; the good row is returned
        assert len(emails) == 1
        assert emails[0].record_id == 1

    def test_does_not_call_connect(self):
        """Repository must never call db.connect() — that's the client's job."""
        db = _make_mock_db([])
        repo = EmailRepository(db)

        repo.get_emails()

        db.connect.assert_not_called()

    def test_multiple_rows(self):
        rows = [
            _make_email_row(record_id=i, message_id=f"<msg{i}@example.com>")
            for i in range(5)
        ]
        db = _make_mock_db(rows)
        repo = EmailRepository(db)

        emails = repo.get_emails(limit=100)
        assert len(emails) == 5
        assert [e.record_id for e in emails] == [0, 1, 2, 3, 4]


class TestEmailRepositorySearchEmails:
    """Tests for EmailRepository.search_emails()."""

    def test_search_by_query(self):
        row = _make_email_row(subject="Meeting notes")
        db = _make_mock_db([row])
        repo = EmailRepository(db)

        results = repo.search_emails(query="meeting")

        assert len(results) == 1
        assert results[0].subject == "Meeting notes"

        # Verify LIKE terms in SQL
        call_args = db.execute_query.call_args
        sql = call_args[0][0]
        params = call_args[0][1]
        assert "Message_NormalizedSubject LIKE ?" in sql
        assert "Message_Preview LIKE ?" in sql
        assert "%meeting%" in params

    def test_search_by_sender(self):
        row = _make_email_row(sender="alice@example.com")
        db = _make_mock_db([row])
        repo = EmailRepository(db)

        results = repo.search_emails(sender="alice@example.com")

        assert len(results) == 1
        call_args = db.execute_query.call_args
        sql = call_args[0][0]
        assert "Message_SenderAddressList LIKE ?" in sql

    def test_search_by_subject(self):
        row = _make_email_row(subject="Quarterly Report")
        db = _make_mock_db([row])
        repo = EmailRepository(db)

        results = repo.search_emails(subject="Quarterly")
        assert len(results) == 1

    def test_search_by_read_status(self):
        db = _make_mock_db([])
        repo = EmailRepository(db)

        repo.search_emails(is_read=True)

        call_args = db.execute_query.call_args
        sql = call_args[0][0]
        params = call_args[0][1]
        assert "Message_ReadFlag = ?" in sql
        assert 1 in params

    def test_search_unread(self):
        db = _make_mock_db([])
        repo = EmailRepository(db)

        repo.search_emails(is_read=False)

        call_args = db.execute_query.call_args
        params = call_args[0][1]
        assert 0 in params

    def test_search_with_date_range(self):
        row = _make_email_row()
        db = _make_mock_db([row])
        repo = EmailRepository(db)
        start = datetime(2024, 1, 1)
        end = datetime(2024, 12, 31)

        repo.search_emails(query="test", start_date=start, end_date=end)

        call_args = db.execute_query.call_args
        sql = call_args[0][0]
        assert "Message_TimeReceived >= ?" in sql
        assert "Message_TimeReceived <= ?" in sql

    def test_search_with_offset(self):
        db = _make_mock_db([])
        repo = EmailRepository(db)

        repo.search_emails(limit=50, offset=10)

        call_args = db.execute_query.call_args
        sql = call_args[0][0]
        params = call_args[0][1]
        assert "LIMIT ? OFFSET ?" in sql
        assert params[-2] == 50
        assert params[-1] == 10

    def test_search_fuzzy_sender(self):
        """Fuzzy search pre-filters with LIKE on tokens, then post-filters."""
        row = _make_email_row(
            sender="andrew.taylor@example.com",
            sender_name="Andy Taylor",
        )
        db = _make_mock_db([row])
        repo = EmailRepository(db)

        results = repo.search_emails(sender="Andy Taylor", fuzzy=True)

        # "Andy Taylor" matches sender_name "Andy Taylor" exactly
        assert len(results) == 1

        # Verify SQL used token-based LIKE for pre-filtering
        call_args = db.execute_query.call_args
        sql = call_args[0][0]
        assert "Message_SenderList LIKE ?" in sql

    def test_search_fuzzy_no_match(self):
        """Fuzzy post-filter rejects non-matching candidates."""
        row = _make_email_row(
            sender="bob.smith@example.com",
            sender_name="Bob Smith",
        )
        db = _make_mock_db([row])
        repo = EmailRepository(db)

        results = repo.search_emails(sender="Andy Taylor", fuzzy=True)
        assert len(results) == 0

    def test_search_empty_result(self):
        db = _make_mock_db([])
        repo = EmailRepository(db)

        results = repo.search_emails(query="nonexistent")
        assert results == []

    def test_search_does_not_call_connect(self):
        db = _make_mock_db([])
        repo = EmailRepository(db)

        repo.search_emails(query="test")
        db.connect.assert_not_called()

    def test_search_combines_multiple_filters(self):
        """Multiple filters are combined with AND logic."""
        db = _make_mock_db([])
        repo = EmailRepository(db)

        repo.search_emails(
            query="meeting",
            sender="alice",
            subject="standup",
            is_read=True,
        )

        call_args = db.execute_query.call_args
        sql = call_args[0][0]
        assert sql.count("AND") == 4  # query(1) + sender(1) + subject(1) + is_read(1)


class TestRowToEmail:
    """Tests for EmailRepository._row_to_email() conversion."""

    def test_basic_conversion(self):
        row = _make_email_row()
        db = _make_mock_db()
        repo = EmailRepository(db)

        email = repo._row_to_email(row)

        assert isinstance(email, EmailMessage)
        assert email.message_id == "<test@example.com>"
        assert email.record_id == 1
        assert email.subject == "Test Subject"
        assert email.sender == "sender@example.com"
        assert email.sender_name == "Test Sender"
        assert email.recipients == ["recipient@example.com"]
        assert email.cc_recipients == []
        assert email.preview == "Preview text"
        assert email.is_read is True
        assert email.is_outgoing is False
        assert email.content_source == ContentSource.PREVIEW_ONLY

    def test_flag_status_mapping(self):
        db = _make_mock_db()
        repo = EmailRepository(db)

        for value, expected in [
            (0, FlagStatus.NOT_FLAGGED),
            (1, FlagStatus.FLAGGED),
            (2, FlagStatus.COMPLETE),
        ]:
            row = _make_email_row(flag_status=value)
            email = repo._row_to_email(row)
            assert email.flag_status == expected

    def test_flag_status_unknown_defaults_to_not_flagged(self):
        db = _make_mock_db()
        repo = EmailRepository(db)

        row = _make_email_row(flag_status=99)
        email = repo._row_to_email(row)
        assert email.flag_status == FlagStatus.NOT_FLAGGED

    def test_priority_mapping(self):
        db = _make_mock_db()
        repo = EmailRepository(db)

        for value, expected in [
            (1, Priority.LOW),
            (3, Priority.NORMAL),
            (5, Priority.HIGH),
        ]:
            row = _make_email_row(priority=value)
            email = repo._row_to_email(row)
            assert email.priority == expected

    def test_priority_unknown_defaults_to_normal(self):
        db = _make_mock_db()
        repo = EmailRepository(db)

        row = _make_email_row(priority=99)
        email = repo._row_to_email(row)
        assert email.priority == Priority.NORMAL

    def test_null_optional_fields(self):
        """Null/missing optional fields are handled gracefully."""
        row = _make_email_row(
            sender_name="",
            recipients=None,
            cc_recipients=None,
            preview="",
        )
        row["Message_TimeSent"] = None
        row["Message_Size"] = None

        db = _make_mock_db()
        repo = EmailRepository(db)
        email = repo._row_to_email(row)

        assert email.sender_name is None
        assert email.recipients == []
        assert email.cc_recipients == []
        assert email.time_sent is None
        assert email.size is None
        assert email.preview == ""

    def test_timestamp_zero_fallback(self):
        """Zero/null timestamp falls back to epoch."""
        row = _make_email_row()
        row["Message_TimeReceived"] = 0

        db = _make_mock_db()
        repo = EmailRepository(db)
        email = repo._row_to_email(row)

        assert email.timestamp == datetime.fromtimestamp(0)

    def test_has_attachments_true(self):
        row = _make_email_row(has_attachment=1)
        db = _make_mock_db()
        repo = EmailRepository(db)

        email = repo._row_to_email(row)
        assert email.has_attachments is True

    def test_semicolon_separated_recipients(self):
        row = _make_email_row(
            recipients="a@x.com; b@x.com; c@x.com",
            cc_recipients="d@x.com, e@x.com",
        )
        db = _make_mock_db()
        repo = EmailRepository(db)

        email = repo._row_to_email(row)
        assert email.recipients == ["a@x.com", "b@x.com", "c@x.com"]
        assert email.cc_recipients == ["d@x.com", "e@x.com"]


class TestParseDelimited:
    """Tests for the _parse_delimited() helper function."""

    def test_none_returns_empty(self):
        assert _parse_delimited(None) == []

    def test_empty_string_returns_empty(self):
        assert _parse_delimited("") == []

    def test_single_value(self):
        assert _parse_delimited("test@example.com") == ["test@example.com"]

    def test_comma_separated(self):
        result = _parse_delimited("a@example.com, b@example.com")
        assert result == ["a@example.com", "b@example.com"]

    def test_semicolon_separated(self):
        result = _parse_delimited("a@example.com; b@example.com")
        assert result == ["a@example.com", "b@example.com"]

    def test_mixed_delimiters(self):
        result = _parse_delimited("a@x.com; b@x.com, c@x.com")
        assert result == ["a@x.com", "b@x.com", "c@x.com"]

    def test_strips_whitespace(self):
        result = _parse_delimited("  a@example.com ;  b@example.com  ")
        assert result == ["a@example.com", "b@example.com"]

    def test_filters_empty_values(self):
        result = _parse_delimited("a@example.com;;; b@example.com")
        assert result == ["a@example.com", "b@example.com"]

    def test_whitespace_only_returns_empty(self):
        assert _parse_delimited("   ") == []

    def test_only_delimiters_returns_empty(self):
        assert _parse_delimited(";;;,,,") == []
