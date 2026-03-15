"""Unit tests for EmailEnricher."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from macoutlook.core.enricher import EmailEnricher, EnrichmentResult
from macoutlook.core.message_source import MessageSourceReader, MimeContent
from macoutlook.models.email_message import AttachmentInfo
from macoutlook.models.enums import ContentSource


def _make_mime_content(
    body_text: str | None = "plain text",
    body_html: str | None = "<p>html</p>",
    attachments: tuple[AttachmentInfo, ...] = (),
) -> MimeContent:
    return MimeContent(
        body_text=body_text,
        body_html=body_html,
        attachments=attachments,
        defects=(),
    )


class TestEmailEnricher:
    def test_enrich_success(self):
        reader = Mock(spec=MessageSourceReader)
        reader.get_content.return_value = _make_mime_content()

        enricher = EmailEnricher(source_reader=reader)
        result = enricher.enrich("test@example.com")

        assert result.source == ContentSource.MESSAGE_SOURCE
        assert result.body_text == "plain text"
        assert result.body_html == "<p>html</p>"
        assert result.error is None

    def test_enrich_no_source_file(self):
        reader = Mock(spec=MessageSourceReader)
        reader.get_content.return_value = None

        enricher = EmailEnricher(source_reader=reader)
        result = enricher.enrich("missing@example.com")

        assert result.source == ContentSource.PREVIEW_ONLY
        assert result.error is not None
        assert "No source file" in result.error

    def test_enrich_never_raises(self):
        reader = Mock(spec=MessageSourceReader)
        reader.get_content.side_effect = RuntimeError("disk on fire")

        enricher = EmailEnricher(source_reader=reader)
        result = enricher.enrich("error@example.com")

        assert result.source == ContentSource.PREVIEW_ONLY
        assert result.error is not None
        assert "disk on fire" in result.error

    def test_enrich_with_attachments(self):
        attachment = AttachmentInfo(
            filename="report.pdf",
            size=1024,
            content_type="application/pdf",
        )
        reader = Mock(spec=MessageSourceReader)
        reader.get_content.return_value = _make_mime_content(attachments=(attachment,))

        enricher = EmailEnricher(source_reader=reader)
        result = enricher.enrich("attach@example.com")

        assert len(result.attachments) == 1
        assert result.attachments[0].filename == "report.pdf"

    def test_enrich_without_markdown(self):
        reader = Mock(spec=MessageSourceReader)
        reader.get_content.return_value = _make_mime_content()

        enricher = EmailEnricher(source_reader=reader)
        result = enricher.enrich("test@example.com", markdown=False)

        assert result.body_markdown is None
        assert result.body_text == "plain text"

    def test_enrich_with_markdown(self):
        reader = Mock(spec=MessageSourceReader)
        reader.get_content.return_value = _make_mime_content(
            body_html="<p><strong>bold</strong> text</p>"
        )

        enricher = EmailEnricher(source_reader=reader)
        result = enricher.enrich("test@example.com", markdown=True)

        assert result.body_markdown is not None
        assert "bold" in result.body_markdown

    def test_build_index_delegates_to_reader(self):
        reader = Mock(spec=MessageSourceReader)
        reader.build_index.return_value = 42

        enricher = EmailEnricher(source_reader=reader)
        count = enricher.build_index()

        assert count == 42
        reader.build_index.assert_called_once_with(force=False)


class TestSaveAttachment:
    """Tests for save_attachment with binary preamble handling."""

    # Minimal multipart MIME message with a text attachment.
    # Using CRLF line endings as per RFC 2822.
    _MIME_BODY = (
        b"From: sender@example.com\r\n"
        b"To: recipient@example.com\r\n"
        b"Subject: Test\r\n"
        b'Content-Type: multipart/mixed; boundary="BOUNDARY"\r\n'
        b"MIME-Version: 1.0\r\n"
        b"\r\n"
        b"--BOUNDARY\r\n"
        b"Content-Type: text/plain\r\n"
        b"\r\n"
        b"Body text here.\r\n"
        b"--BOUNDARY\r\n"
        b"Content-Type: application/octet-stream\r\n"
        b'Content-Disposition: attachment; filename="report.csv"\r\n'
        b"\r\n"
        b"col1,col2\r\nval1,val2\r\n"
        b"--BOUNDARY--\r\n"
    )

    # Binary preamble simulating what .olk15MsgSource files contain
    _PREAMBLE = b"\x00\x01\x02\x03" * 9  # 36 bytes of binary junk

    def _write_source_file(self, tmp_path: Path, *, with_preamble: bool) -> Path:
        """Write a .olk15MsgSource file with or without a binary preamble."""
        source_file = tmp_path / "test.olk15MsgSource"
        data = (self._PREAMBLE + self._MIME_BODY) if with_preamble else self._MIME_BODY
        source_file.write_bytes(data)
        return source_file

    def test_save_attachment_skips_preamble(self, tmp_path: Path):
        """save_attachment must skip the binary preamble before parsing MIME."""
        source_file = self._write_source_file(tmp_path, with_preamble=True)
        dest_dir = tmp_path / "output"
        dest_dir.mkdir()

        reader = Mock(spec=MessageSourceReader)
        reader.get_source_path.return_value = str(source_file)

        enricher = EmailEnricher(source_reader=reader)
        result_path = enricher.save_attachment(
            "test@example.com", "report.csv", dest_dir
        )

        assert result_path.exists()
        assert result_path.name == "report.csv"
        content = result_path.read_text()
        assert "col1,col2" in content

    def test_save_attachment_without_preamble(self, tmp_path: Path):
        """save_attachment works when there is no preamble (offset 0)."""
        source_file = self._write_source_file(tmp_path, with_preamble=False)
        dest_dir = tmp_path / "output"
        dest_dir.mkdir()

        reader = Mock(spec=MessageSourceReader)
        reader.get_source_path.return_value = str(source_file)

        enricher = EmailEnricher(source_reader=reader)
        result_path = enricher.save_attachment(
            "test@example.com", "report.csv", dest_dir
        )

        assert result_path.exists()
        content = result_path.read_text()
        assert "col1,col2" in content

    def test_save_attachment_bare_cr_line_endings(self, tmp_path: Path):
        """save_attachment normalizes bare CR line endings to CRLF."""
        # Replace CRLF with bare CR to simulate real .olk15MsgSource files
        bare_cr_mime = self._MIME_BODY.replace(b"\r\n", b"\r")
        source_file = tmp_path / "test.olk15MsgSource"
        source_file.write_bytes(self._PREAMBLE + bare_cr_mime)

        dest_dir = tmp_path / "output"
        dest_dir.mkdir()

        reader = Mock(spec=MessageSourceReader)
        reader.get_source_path.return_value = str(source_file)

        enricher = EmailEnricher(source_reader=reader)
        result_path = enricher.save_attachment(
            "test@example.com", "report.csv", dest_dir
        )

        assert result_path.exists()
        content = result_path.read_text()
        assert "col1,col2" in content

    def test_save_attachment_no_source_file(self, tmp_path: Path):
        """save_attachment raises FileNotFoundError when source is missing."""
        reader = Mock(spec=MessageSourceReader)
        reader.get_source_path.return_value = None

        enricher = EmailEnricher(source_reader=reader)
        with pytest.raises(FileNotFoundError, match="No source file"):
            enricher.save_attachment("missing@example.com", "file.txt", tmp_path)

    def test_save_attachment_missing_attachment(self, tmp_path: Path):
        """save_attachment raises FileNotFoundError for non-existent attachment."""
        source_file = self._write_source_file(tmp_path, with_preamble=True)
        dest_dir = tmp_path / "output"
        dest_dir.mkdir()

        reader = Mock(spec=MessageSourceReader)
        reader.get_source_path.return_value = str(source_file)

        enricher = EmailEnricher(source_reader=reader)
        with pytest.raises(FileNotFoundError, match="not found in message"):
            enricher.save_attachment("test@example.com", "nonexistent.pdf", dest_dir)

    def test_save_attachment_rejects_path_traversal(self, tmp_path: Path):
        """save_attachment rejects filenames with path traversal."""
        source_file = self._write_source_file(tmp_path, with_preamble=True)

        reader = Mock(spec=MessageSourceReader)
        reader.get_source_path.return_value = str(source_file)

        enricher = EmailEnricher(source_reader=reader)
        with pytest.raises(ValueError, match="Invalid attachment filename"):
            enricher.save_attachment("test@example.com", "..", tmp_path)


class TestEnrichmentResult:
    def test_default_values(self):
        result = EnrichmentResult()
        assert result.body_text is None
        assert result.body_html is None
        assert result.body_markdown is None
        assert result.attachments == ()
        assert result.source == ContentSource.PREVIEW_ONLY
        assert result.error is None

    def test_frozen(self):
        result = EnrichmentResult()
        with pytest.raises(AttributeError):
            result.body_text = "mutated"  # type: ignore[misc]
