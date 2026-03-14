"""Unit tests for OutlookClient class."""

from datetime import datetime
from unittest.mock import Mock

from macoutlook.core.client import OutlookClient, _parse_delimited
from macoutlook.core.database import OutlookDatabase
from macoutlook.core.enricher import EmailEnricher, EnrichmentResult
from macoutlook.models.email_message import AttachmentInfo, EmailMessage
from macoutlook.models.enums import ContentSource


class TestOutlookClient:
    def _make_client(self, mock_db: Mock | None = None) -> OutlookClient:
        """Create a client with a mock database (DI, no auto-connect)."""
        db = mock_db or Mock(spec=OutlookDatabase)
        return OutlookClient(database=db)

    def test_init_does_not_auto_connect(self):
        mock_db = Mock(spec=OutlookDatabase)
        client = OutlookClient(database=mock_db)
        assert not client._connected
        mock_db.connect.assert_not_called()

    def test_connect(self):
        mock_db = Mock(spec=OutlookDatabase)
        client = self._make_client(mock_db)
        client.connect()
        assert client._connected
        mock_db.connect.assert_called_once()

    def test_disconnect(self):
        mock_db = Mock(spec=OutlookDatabase)
        client = self._make_client(mock_db)
        client.connect()
        client.disconnect()
        assert not client._connected
        mock_db.disconnect.assert_called_once()

    def test_context_manager(self):
        mock_db = Mock(spec=OutlookDatabase)
        client = self._make_client(mock_db)
        with client:
            mock_db.connect.assert_called_once()
        mock_db.disconnect.assert_called_once()

    def test_get_emails_returns_email_messages(self):
        mock_db = Mock(spec=OutlookDatabase)
        mock_db.is_connected = True
        mock_db.conn = Mock()

        mock_row = {
            "Record_RecordID": 1,
            "Message_MessageID": "<test@example.com>",
            "Message_NormalizedSubject": "Test Subject",
            "Message_SenderAddressList": "sender@example.com",
            "Message_SenderList": "Test Sender",
            "Message_ToRecipientAddressList": "recipient@example.com",
            "Message_CCRecipientAddressList": None,
            "Message_TimeReceived": datetime.now().timestamp(),
            "Message_TimeSent": datetime.now().timestamp(),
            "Message_Preview": "Preview text",
            "Message_ReadFlag": 1,
            "Message_IsOutgoingMessage": 0,
            "Record_FlagStatus": 0,
            "Record_Priority": 3,
            "Record_FolderID": 1,
            "Message_HasAttachment": 0,
            "Message_Size": 1024,
        }
        mock_db.execute_query.return_value = [mock_row]

        client = self._make_client(mock_db)
        client._connected = True

        emails = client.get_emails(limit=10)
        assert len(emails) == 1
        assert isinstance(emails[0], EmailMessage)
        assert emails[0].subject == "Test Subject"
        assert emails[0].sender == "sender@example.com"
        assert emails[0].message_id == "<test@example.com>"
        assert emails[0].content_source == ContentSource.PREVIEW_ONLY
        assert emails[0].preview == "Preview text"

    def test_get_emails_empty_result(self):
        mock_db = Mock(spec=OutlookDatabase)
        mock_db.is_connected = True
        mock_db.conn = Mock()
        mock_db.execute_query.return_value = []

        client = self._make_client(mock_db)
        client._connected = True

        emails = client.get_emails()
        assert emails == []


class TestOutlookClientEnrichment:
    def _make_email(self, message_id: str = "<test@example.com>") -> EmailMessage:
        return EmailMessage(
            message_id=message_id,
            record_id=1,
            subject="Test",
            sender="sender@example.com",
            timestamp=datetime.now(),
            preview="short preview",
            content_source=ContentSource.PREVIEW_ONLY,
        )

    def test_enrich_email_without_enricher(self):
        client = OutlookClient(database=Mock(spec=OutlookDatabase))
        email = self._make_email()
        result = client.enrich_email(email)
        assert result is email  # unchanged

    def test_enrich_email_with_enricher(self):
        mock_enricher = Mock(spec=EmailEnricher)
        mock_enricher.enrich.return_value = EnrichmentResult(
            body_text="Full body text",
            body_html="<p>Full body</p>",
            body_markdown="Full body",
            attachments=(
                AttachmentInfo(filename="doc.pdf", content_type="application/pdf"),
            ),
            source=ContentSource.MESSAGE_SOURCE,
        )

        client = OutlookClient(
            database=Mock(spec=OutlookDatabase),
            enricher=mock_enricher,
        )
        email = self._make_email()
        enriched = client.enrich_email(email)

        assert enriched.body_text == "Full body text"
        assert enriched.content_source == ContentSource.MESSAGE_SOURCE
        assert enriched.preview == "short preview"  # preserved
        assert len(enriched.attachments) == 1

    def test_enrich_email_returns_original_on_failure(self):
        mock_enricher = Mock(spec=EmailEnricher)
        mock_enricher.enrich.return_value = EnrichmentResult(
            source=ContentSource.PREVIEW_ONLY,
            error="not found",
        )

        client = OutlookClient(
            database=Mock(spec=OutlookDatabase),
            enricher=mock_enricher,
        )
        email = self._make_email()
        result = client.enrich_email(email)
        assert result is email  # unchanged

    def test_enrich_emails_batch(self):
        mock_enricher = Mock(spec=EmailEnricher)
        mock_enricher.build_index.return_value = 100
        mock_enricher.enrich.return_value = EnrichmentResult(
            body_text="enriched",
            source=ContentSource.MESSAGE_SOURCE,
        )

        client = OutlookClient(
            database=Mock(spec=OutlookDatabase),
            enricher=mock_enricher,
        )
        emails = [self._make_email(f"<msg{i}@example.com>") for i in range(3)]
        results = client.enrich_emails(emails)

        assert len(results) == 3
        assert all(e.body_text == "enriched" for e in results)
        mock_enricher.build_index.assert_called_once()

    def test_get_emails_with_enrich_flag(self):
        mock_db = Mock(spec=OutlookDatabase)
        mock_db.is_connected = True
        mock_db.conn = Mock()
        mock_db.execute_query.return_value = [
            {
                "Record_RecordID": 1,
                "Message_MessageID": "<t@x.com>",
                "Message_NormalizedSubject": "Test",
                "Message_SenderAddressList": "s@x.com",
                "Message_SenderList": "Sender",
                "Message_ToRecipientAddressList": None,
                "Message_CCRecipientAddressList": None,
                "Message_TimeReceived": datetime.now().timestamp(),
                "Message_TimeSent": None,
                "Message_Preview": "preview",
                "Message_ReadFlag": 0,
                "Message_IsOutgoingMessage": 0,
                "Record_FlagStatus": 0,
                "Record_Priority": 3,
                "Record_FolderID": 1,
                "Message_HasAttachment": 0,
                "Message_Size": 100,
            }
        ]

        mock_enricher = Mock(spec=EmailEnricher)
        mock_enricher.build_index.return_value = 10
        mock_enricher.enrich.return_value = EnrichmentResult(
            body_text="full body",
            source=ContentSource.MESSAGE_SOURCE,
        )

        client = OutlookClient(database=mock_db, enricher=mock_enricher)
        client._connected = True

        emails = client.get_emails(limit=1, enrich=True)
        assert len(emails) == 1
        assert emails[0].body_text == "full body"


class TestOutlookClientSearch:
    def _mock_client(self):
        mock_db = Mock(spec=OutlookDatabase)
        mock_db.is_connected = True
        mock_db.conn = Mock()
        mock_db.execute_query.return_value = [
            {
                "Record_RecordID": 1,
                "Message_MessageID": "<s@x.com>",
                "Message_NormalizedSubject": "Search Result",
                "Message_SenderAddressList": "sender@example.com",
                "Message_SenderList": "Andy Taylor",
                "Message_ToRecipientAddressList": None,
                "Message_CCRecipientAddressList": None,
                "Message_TimeReceived": datetime.now().timestamp(),
                "Message_TimeSent": None,
                "Message_Preview": "preview",
                "Message_ReadFlag": 1,
                "Message_IsOutgoingMessage": 0,
                "Record_FlagStatus": 0,
                "Record_Priority": 3,
                "Record_FolderID": 1,
                "Message_HasAttachment": 0,
                "Message_Size": 200,
            }
        ]
        client = OutlookClient(database=mock_db)
        client._connected = True
        return client

    def test_search_by_query(self):
        client = self._mock_client()
        results = client.search_emails(query="meeting")
        assert len(results) == 1
        assert results[0].subject == "Search Result"

    def test_search_by_sender(self):
        client = self._mock_client()
        results = client.search_emails(sender="sender@example.com")
        assert len(results) == 1

    def test_search_fuzzy_sender(self):
        client = self._mock_client()
        results = client.search_emails(sender="Andy Taylor", fuzzy=True)
        assert len(results) == 1  # "Andy Taylor" matches exactly

    def test_search_with_date_range(self):
        client = self._mock_client()
        results = client.search_emails(
            query="test",
            start_date=datetime(2020, 1, 1),
            end_date=datetime(2030, 1, 1),
        )
        assert len(results) == 1


class TestOutlookClientCalendar:
    def test_get_calendars_from_db(self):
        mock_db = Mock(spec=OutlookDatabase)
        mock_db.is_connected = True
        mock_db.conn = Mock()
        mock_db.execute_query.return_value = [
            {"calendar_id": "1", "name": "Calendar"},
        ]

        client = OutlookClient(database=mock_db)
        client._connected = True
        calendars = client.get_calendars()
        assert len(calendars) == 1
        assert calendars[0].name == "Calendar"

    def test_get_database_info(self):
        mock_db = Mock(spec=OutlookDatabase)
        mock_db.is_connected = True
        mock_db.conn = Mock()
        mock_db.db_path = "/fake/path"
        mock_db.get_table_names.return_value = ["Mail", "CalendarEvents"]
        mock_db.get_row_count.side_effect = lambda t: {
            "Mail": 100,
            "CalendarEvents": 50,
        }[t]

        client = OutlookClient(database=mock_db)
        client._connected = True
        info = client.get_database_info()

        assert info["db_path"] == "/fake/path"
        assert info["mail_count"] == 100
        assert info["calendarevents_count"] == 50


class TestParseDelimited:
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

    def test_strips_whitespace(self):
        result = _parse_delimited("  a@example.com ;  b@example.com  ")
        assert result == ["a@example.com", "b@example.com"]

    def test_filters_empty_values(self):
        result = _parse_delimited("a@example.com;;; b@example.com")
        assert result == ["a@example.com", "b@example.com"]
