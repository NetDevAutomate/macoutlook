"""Email enrichment pipeline for macoutlook library.

Enriches email metadata from the database with full content from
.olk15MsgSource files. Never raises exceptions — returns EnrichmentResult
with error details on failure.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from ..models.email_message import AttachmentInfo
from ..models.enums import ContentSource
from ..parsers.content import ContentParser
from .message_source import MessageSourceReader, MimeContent

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EnrichmentResult:
    """Result of enriching an email with full content.

    Never-raises contract: failures produce a result with
    source=PREVIEW_ONLY and error set, rather than raising.
    """

    body_text: str | None = None
    body_html: str | None = None
    body_markdown: str | None = None
    attachments: tuple[AttachmentInfo, ...] = ()
    source: ContentSource = ContentSource.PREVIEW_ONLY
    error: str | None = None


class EmailEnricher:
    """Enrichment pipeline: source file lookup -> MIME parse -> content convert.

    Accepts a MessageSourceReader and ContentParser, uses them to enrich
    emails with full body content and attachment metadata.
    """

    def __init__(
        self,
        source_reader: MessageSourceReader,
        content_parser: ContentParser | None = None,
    ) -> None:
        self._reader = source_reader
        self._parser = content_parser or ContentParser()

    @property
    def index_size(self) -> int:
        """Number of indexed source files."""
        return self._reader.index_size

    def build_index(self, force: bool = False) -> int:
        """Build or load the message source index.

        Returns number of indexed files.
        """
        return self._reader.build_index(force=force)

    def enrich(self, message_id: str, markdown: bool = True) -> EnrichmentResult:
        """Enrich an email with full content from its .olk15MsgSource file.

        Args:
            message_id: RFC 2822 Message-ID to look up.
            markdown: Whether to generate markdown from HTML (slower).

        Returns:
            EnrichmentResult with body content and attachments.
            On failure, returns result with source=PREVIEW_ONLY and error set.
        """
        try:
            mime_content = self._reader.get_content(message_id)

            if mime_content is None:
                return EnrichmentResult(
                    source=ContentSource.PREVIEW_ONLY,
                    error=f"No source file found for Message-ID: {message_id}",
                )

            return self._process_mime_content(mime_content, markdown=markdown)

        except Exception as e:
            logger.warning("Enrichment failed for %s: %s", message_id, e)
            return EnrichmentResult(
                source=ContentSource.PREVIEW_ONLY,
                error=str(e),
            )

    def _process_mime_content(
        self, content: MimeContent, markdown: bool = True
    ) -> EnrichmentResult:
        """Convert MimeContent into an EnrichmentResult."""
        body_markdown = None

        if markdown and content.body_html:
            try:
                parsed = self._parser.parse_email_content(content.body_html)
                body_markdown = parsed.get("markdown")
            except Exception as e:
                logger.debug("Markdown conversion failed: %s", e)

        return EnrichmentResult(
            body_text=content.body_text,
            body_html=content.body_html,
            body_markdown=body_markdown,
            attachments=content.attachments,
            source=ContentSource.MESSAGE_SOURCE,
        )

    def save_attachment(
        self,
        message_id: str,
        attachment_filename: str,
        dest_dir: Path,
    ) -> Path:
        """Save an attachment from a source file to disk.

        Args:
            message_id: RFC 2822 Message-ID of the email.
            attachment_filename: Name of the attachment to save.
            dest_dir: Directory to save the attachment to.

        Returns:
            Path to the saved file.

        Raises:
            FileNotFoundError: If source file or attachment not found.
            ValueError: If path validation fails.
        """
        source_path = self._reader.get_source_path(message_id)
        if source_path is None:
            raise FileNotFoundError(f"No source file for Message-ID: {message_id}")

        # Re-parse the full MIME message to get attachment content
        from email import policy as _policy
        from email.parser import BytesParser

        with open(source_path, "rb") as f:
            msg = BytesParser(policy=_policy.default).parse(f)

        # Find the matching attachment
        safe_target = Path(attachment_filename).name
        if not safe_target or safe_target in (".", ".."):
            raise ValueError(f"Invalid attachment filename: {attachment_filename}")

        for part in msg.iter_attachments():
            filename = part.get_filename()
            if not filename:
                continue

            safe_name = Path(filename).name
            if safe_name == safe_target:
                content = part.get_content()

                # Path validation: ensure dest is under target directory
                dest_path = (dest_dir / safe_name).resolve()
                if not dest_path.is_relative_to(dest_dir.resolve()):
                    raise ValueError(f"Path traversal detected: {safe_name}")

                # Write content
                mode = "wb" if isinstance(content, bytes) else "w"
                with open(dest_path, mode) as out:
                    out.write(content)

                logger.info("Saved attachment %s to %s", safe_name, dest_path)
                return dest_path

        raise FileNotFoundError(
            f"Attachment '{attachment_filename}' not found in message {message_id}"
        )
