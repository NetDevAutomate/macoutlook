"""Unit tests for EmailEnricher."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from macoutlook.core.enricher import EmailEnricher, EnrichmentResult
from macoutlook.core.message_source import MessageSourceReader, MimeContent
from macoutlook.models.email_message import AttachmentInfo, EmailMessage
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
        reader.get_content.return_value = _make_mime_content(
            attachments=(attachment,)
        )

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
