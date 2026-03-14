"""Email data models for macoutlook library."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator

from .enums import ContentSource, FlagStatus, Priority


class AttachmentInfo(BaseModel):
    """Metadata for an email attachment extracted from MIME parts."""

    model_config = ConfigDict(frozen=True)

    filename: str
    size: int | None = None
    content_type: str
    content_id: str | None = None


class EmailMessage(BaseModel):
    """Represents an email message with metadata and content.

    Content fields (body_text, body_html, body_markdown) are populated
    lazily via EmailEnricher when .olk15MsgSource files are available.
    The preview field always comes from the database.
    """

    model_config = ConfigDict(frozen=True)

    # Identity
    message_id: str  # RFC 2822 Message-ID
    record_id: int  # Internal DB Record_RecordID

    # Metadata
    subject: str = ""
    sender: str = ""
    sender_name: str | None = None
    recipients: list[str] = []
    cc_recipients: list[str] = []
    timestamp: datetime  # TimeReceived
    time_sent: datetime | None = None
    size: int | None = None
    is_read: bool = False
    is_outgoing: bool = False
    flag_status: FlagStatus = FlagStatus.NOT_FLAGGED
    priority: Priority = Priority.NORMAL
    folder_id: int | None = None
    has_attachments: bool = False

    # Content (populated lazily via enrichment)
    body_text: str | None = None
    body_html: str | None = None
    body_markdown: str | None = None
    preview: str | None = None

    # Attachments (populated via enrichment)
    attachments: tuple[AttachmentInfo, ...] = ()

    # Provenance
    content_source: ContentSource = ContentSource.PREVIEW_ONLY

    @field_serializer("timestamp", "time_sent")
    @classmethod
    def serialize_datetime(cls, v: datetime | None) -> str | None:
        if v is None:
            return None
        return v.isoformat()

    @field_validator("timestamp", "time_sent", mode="before")
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
