"""
Unit tests for OutlookClient class.
"""

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from pyoutlook_db.core.client import OutlookClient
from pyoutlook_db.core.exceptions import ValidationError
from pyoutlook_db.models.email import EmailMessage


class TestOutlookClient:
    """Test cases for OutlookClient class."""

    def test_init_with_auto_connect_false(self):
        """Test initialization without auto-connect."""
        with patch("pyoutlook_db.core.client.get_database") as mock_get_db:
            mock_db = Mock()
            mock_get_db.return_value = mock_db

            client = OutlookClient(auto_connect=False)

            assert client.db == mock_db
            assert not client._connected
            mock_db.connect.assert_not_called()

    def test_init_with_auto_connect_true(self):
        """Test initialization with auto-connect."""
        with patch("pyoutlook_db.core.client.get_database") as mock_get_db:
            mock_db = Mock()
            mock_get_db.return_value = mock_db

            client = OutlookClient(auto_connect=True)

            assert client.db == mock_db
            mock_db.connect.assert_called_once()

    def test_connect(self):
        """Test database connection."""
        with patch("pyoutlook_db.core.client.get_database") as mock_get_db:
            mock_db = Mock()
            mock_get_db.return_value = mock_db

            client = OutlookClient(auto_connect=False)
            client.connect()

            assert client._connected
            mock_db.connect.assert_called_once()

    def test_disconnect(self):
        """Test database disconnection."""
        with patch("pyoutlook_db.core.client.get_database") as mock_get_db:
            mock_db = Mock()
            mock_get_db.return_value = mock_db

            client = OutlookClient(auto_connect=True)
            client.disconnect()

            assert not client._connected
            mock_db.disconnect.assert_called_once()

    def test_get_emails_by_date_range_invalid_dates(self):
        """Test get_emails_by_date_range with invalid date range."""
        with patch("pyoutlook_db.core.client.get_database"):
            client = OutlookClient(auto_connect=False)

            start_date = datetime.now()
            end_date = start_date - timedelta(days=1)  # Invalid: end before start

            with pytest.raises(ValidationError) as exc_info:
                client.get_emails_by_date_range(start_date, end_date)

            assert "must be after start_date" in str(exc_info.value)

    def test_get_emails_by_date_range_success(self):
        """Test successful email retrieval by date range."""
        with patch("pyoutlook_db.core.client.get_database") as mock_get_db:
            # Mock database
            mock_db = Mock()
            mock_get_db.return_value = mock_db

            # Mock database row
            mock_row = {
                "message_id": "test-id-1",
                "subject": "Test Subject",
                "sender": "test@example.com",
                "sender_name": "Test Sender",
                "recipients": "recipient@example.com",
                "cc_recipients": None,
                "bcc_recipients": None,
                "timestamp": datetime.now().timestamp(),
                "received_time": datetime.now().timestamp(),
                "content_html": "<p>Test content</p>",
                "folder": "Inbox",
                "is_read": 1,
                "is_flagged": 0,
                "attachments": None,
                "categories": None,
                "message_size": 1024,
                "conversation_id": "conv-1",
            }

            mock_db.execute_query.return_value = [mock_row]

            # Mock content parser
            with patch("pyoutlook_db.core.client.get_content_parser") as mock_get_parser:
                mock_parser = Mock()
                mock_parser.parse_email_content.return_value = {
                    "html": "<p>Test content</p>",
                    "text": "Test content",
                    "markdown": "Test content"
                }
                mock_get_parser.return_value = mock_parser

                client = OutlookClient(auto_connect=False)

                start_date = datetime.now() - timedelta(days=7)
                end_date = datetime.now()

                emails = client.get_emails_by_date_range(start_date, end_date)

                assert len(emails) == 1
                assert isinstance(emails[0], EmailMessage)
                assert emails[0].subject == "Test Subject"
                assert emails[0].sender == "test@example.com"

    def test_parse_recipients(self):
        """Test recipient parsing."""
        with patch("pyoutlook_db.core.client.get_database"):
            client = OutlookClient(auto_connect=False)

            # Test None input
            assert client._parse_recipients(None) == []

            # Test empty string
            assert client._parse_recipients("") == []

            # Test single recipient
            assert client._parse_recipients("test@example.com") == ["test@example.com"]

            # Test multiple recipients with comma
            result = client._parse_recipients("test1@example.com, test2@example.com")
            assert result == ["test1@example.com", "test2@example.com"]

            # Test multiple recipients with semicolon
            result = client._parse_recipients("test1@example.com; test2@example.com")
            assert result == ["test1@example.com", "test2@example.com"]

    def test_context_manager(self):
        """Test context manager functionality."""
        with patch("pyoutlook_db.core.client.get_database") as mock_get_db:
            mock_db = Mock()
            mock_get_db.return_value = mock_db

            client = OutlookClient(auto_connect=False)

            with client:
                mock_db.connect.assert_called_once()

            mock_db.disconnect.assert_called_once()


class TestClientIntegration:
    """Integration-style tests that test multiple components together."""

    @pytest.mark.integration
    def test_full_email_retrieval_flow(self):
        """Test the complete flow of email retrieval."""
        # This would be an integration test that uses a real or mock database
        # For now, we'll skip it since we don't have a test database
        pytest.skip("Integration test requires test database")

    @pytest.mark.macos
    def test_database_discovery(self):
        """Test database path discovery on macOS."""
        # This test would only run on macOS with Outlook installed
        pytest.skip("Requires macOS with Outlook installed")
