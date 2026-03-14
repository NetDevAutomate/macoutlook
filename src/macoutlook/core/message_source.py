"""Message source file reader for macoutlook library.

Reads .olk15MsgSource files (RFC 2822 MIME format) from macOS Outlook's
data directory to extract full email content. These files contain the
complete email including body, headers, and attachments.

The .olk15MsgSource extraction approach was discovered by Jon Hammant
in the outlook-connector-package project.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from pathlib import Path

from ..models.email_message import AttachmentInfo

logger = logging.getLogger(__name__)

# Default location for .olk15MsgSource files
_DEFAULT_SOURCES_SUBPATH = (
    "Outlook 15 Profiles/Main Profile/Data/Message Sources"
)

# Cache location for persisted index
_CACHE_DIR = Path.home() / ".cache" / "macoutlook"
_INDEX_CACHE_FILE = _CACHE_DIR / "message_index.json"


@dataclass(frozen=True, slots=True)
class MimeContent:
    """Intermediate result from MIME parsing.

    Contains the extracted body parts and attachment metadata
    before enrichment processing.
    """

    body_text: str | None
    body_html: str | None
    attachments: tuple[AttachmentInfo, ...]
    defects: tuple[str, ...]


class MessageSourceReader:
    """Reads and indexes .olk15MsgSource files for full email content.

    Builds a Message-ID -> file path index lazily on first use,
    with disk persistence to avoid rebuilding on every CLI invocation.
    Uses regex-based Message-ID extraction for fast index building and
    BytesParser for full MIME parsing on demand.
    """

    # Regex to extract Message-ID from raw header bytes.
    # .olk15MsgSource files have a binary preamble before MIME headers,
    # and use \r (CR) line endings, not \r\n (CRLF).
    _MSG_ID_RE = re.compile(rb"Message-ID:\s*<?([^>\r\n]+)>?", re.IGNORECASE)

    def __init__(self, sources_dir: Path | str | None = None) -> None:
        self._sources_dir = Path(sources_dir) if sources_dir else self._default_sources_dir()
        self._index: dict[str, str] | None = None
        self._full_parser = BytesParser(policy=policy.default)

    @staticmethod
    def _default_sources_dir() -> Path:
        """Return default path to Outlook message sources directory."""
        return (
            Path.home()
            / "Library"
            / "Group Containers"
            / "UBF8T346G9.Office"
            / "Outlook"
            / _DEFAULT_SOURCES_SUBPATH
        )

    @property
    def sources_dir(self) -> Path:
        return self._sources_dir

    @property
    def index_size(self) -> int:
        """Number of indexed message source files."""
        if self._index is None:
            return 0
        return len(self._index)

    def build_index(
        self,
        force: bool = False,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> int:
        """Build or load the Message-ID -> file path index.

        Attempts to load from disk cache first. If cache is stale or
        missing, scans all .olk15MsgSource files (slow: ~12ms/file due
        to macOS Group Containers access latency).

        Args:
            force: Force a full rebuild, ignoring cache.
            progress_callback: Optional (current, total) callback for progress.

        Returns:
            Number of indexed files.
        """
        if self._index is not None and not force:
            return len(self._index)

        if not force:
            cached = self._load_cached_index()
            if cached is not None:
                self._index = cached
                logger.info("Loaded cached index (%d entries)", len(cached))
                return len(cached)

        # Full build from disk
        logger.info("Building message source index from %s", self._sources_dir)
        self._index = self._scan_source_files(progress_callback=progress_callback)
        logger.info("Indexed %d message source files", len(self._index))

        self._save_cached_index(self._index)
        return len(self._index)

    def get_source_path(self, message_id: str) -> str | None:
        """Look up the source file path for a given Message-ID.

        Lazily builds the index on first call.
        """
        if self._index is None:
            self.build_index()

        if self._index is None:
            return None
        return self._index.get(message_id)

    def get_content(self, message_id: str) -> MimeContent | None:
        """Parse full MIME content for a given Message-ID.

        Looks up the source file, parses the complete MIME message,
        and returns body parts + attachment metadata.

        Returns None if no source file is found.
        """
        source_path = self.get_source_path(message_id)
        if source_path is None:
            return None

        return self._parse_mime_file(source_path)

    def _scan_source_files(
        self,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> dict[str, str]:
        """Scan .olk15MsgSource files and extract Message-ID headers.

        Reads first 4KB of each file and extracts Message-ID via regex.
        Due to macOS Group Containers access latency (~12ms/file), a full
        scan of 50K+ files takes ~10 minutes. Use persistent caching to
        avoid repeated scans.

        Args:
            progress_callback: Optional (current, total) callback for progress.
        """
        if not self._sources_dir.exists():
            logger.warning("Message sources directory does not exist: %s", self._sources_dir)
            return {}

        entries = self._walk_source_files(self._sources_dir)
        file_count = len(entries)
        logger.info("Found %d .olk15MsgSource files, building index...", file_count)

        index: dict[str, str] = {}
        error_count = 0

        for i, entry in enumerate(entries):
            try:
                fd = os.open(entry.path, os.O_RDONLY)
                try:
                    data = os.read(fd, 4096)
                finally:
                    os.close(fd)

                m = self._MSG_ID_RE.search(data)
                if m:
                    msg_id = m.group(1).decode("ascii", errors="replace").strip()
                    if msg_id:
                        index[msg_id] = entry.path
                else:
                    error_count += 1
            except Exception:
                error_count += 1

            if progress_callback and (i + 1) % 1000 == 0:
                progress_callback(i + 1, file_count)

        logger.info(
            "Indexed %d Message-IDs from %d files (%d without Message-ID)",
            len(index), file_count, error_count,
        )
        return index

    @staticmethod
    def _walk_source_files(directory: Path) -> list[os.DirEntry[str]]:
        """Walk directory tree collecting .olk15MsgSource files using os.scandir."""
        entries: list[os.DirEntry[str]] = []

        def _recurse(path: str) -> None:
            try:
                with os.scandir(path) as it:
                    for entry in it:
                        if entry.is_dir(follow_symlinks=False):
                            _recurse(entry.path)
                        elif entry.name.endswith(".olk15MsgSource"):
                            entries.append(entry)
            except PermissionError:
                logger.warning("Permission denied: %s", path)

        _recurse(str(directory))
        return entries

    @staticmethod
    def _find_mime_start(data: bytes) -> int:
        """Find where RFC 2822 headers begin in an .olk15MsgSource file.

        These files have a binary preamble (typically 36-40 bytes) before
        the MIME content. We look for common RFC 2822 header patterns.
        """
        for pattern in (b"Date:", b"From:", b"Received:", b"MIME-Version:", b"Subject:"):
            idx = data.find(pattern)
            if idx != -1:
                return idx
        return 0

    def _parse_mime_file(self, file_path: str) -> MimeContent | None:
        """Parse a complete MIME message from a .olk15MsgSource file.

        Skips the binary preamble and uses BytesParser with policy.default.
        """
        try:
            with open(file_path, "rb") as f:
                raw = f.read()

            # Skip binary preamble to find MIME content
            mime_start = self._find_mime_start(raw)
            mime_bytes = raw[mime_start:]

            # .olk15MsgSource uses \r (CR) line endings — normalize to \r\n
            if b"\r\n" not in mime_bytes[:500] and b"\r" in mime_bytes[:500]:
                mime_bytes = mime_bytes.replace(b"\r", b"\r\n")

            msg = self._full_parser.parsebytes(mime_bytes)

            # Extract body parts using high-level API
            body_text = None
            body_html = None

            text_part = msg.get_body(preferencelist=("plain",))
            if text_part is not None:
                try:
                    body_text = text_part.get_content()
                except Exception as e:
                    logger.debug("Failed to decode text body: %s", e)

            html_part = msg.get_body(preferencelist=("html",))
            if html_part is not None:
                try:
                    body_html = html_part.get_content()
                except Exception as e:
                    logger.debug("Failed to decode HTML body: %s", e)

            # Extract attachment metadata
            attachments = self._extract_attachments(msg)

            # Collect any MIME defects
            defects = tuple(str(d) for d in msg.defects)

            return MimeContent(
                body_text=body_text,
                body_html=body_html,
                attachments=attachments,
                defects=defects,
            )

        except Exception as e:
            logger.warning("Failed to parse MIME file %s: %s", file_path, e)
            return None

    @staticmethod
    def _extract_attachments(msg: object) -> tuple[AttachmentInfo, ...]:
        """Extract attachment metadata from MIME message parts."""
        attachments: list[AttachmentInfo] = []

        try:
            for part in msg.iter_attachments():  # type: ignore[attr-defined]
                filename = part.get_filename()
                if not filename:
                    continue

                # Security: sanitize filename (strip path components)
                safe_filename = Path(filename).name
                if not safe_filename or safe_filename in (".", ".."):
                    continue

                content_type = part.get_content_type()
                content_id = part.get("Content-ID")

                # Get size by decoding content
                try:
                    content = part.get_content()
                    size = len(content) if isinstance(content, (bytes, str)) else None
                except Exception:
                    size = None

                attachments.append(AttachmentInfo(
                    filename=safe_filename,
                    size=size,
                    content_type=content_type,
                    content_id=content_id,
                ))
        except Exception as e:
            logger.debug("Failed to extract attachments: %s", e)

        return tuple(attachments)

    # --- Index persistence ---

    def _load_cached_index(self) -> dict[str, str] | None:
        """Load index from disk cache if it's still valid."""
        if not _INDEX_CACHE_FILE.exists():
            return None

        try:
            with open(_INDEX_CACHE_FILE) as f:
                data = json.load(f)

            meta = data.get("_meta", {})
            cached_mtime = meta.get("mtime", 0)
            cached_count = meta.get("count", 0)
            cached_sources_dir = meta.get("sources_dir", "")

            # Validate cache is for the same directory
            if cached_sources_dir != str(self._sources_dir):
                logger.debug("Cache sources_dir mismatch, rebuilding")
                return None

            # Check if sources directory has been modified
            if self._sources_dir.exists():
                current_mtime = self._sources_dir.stat().st_mtime
                if current_mtime != cached_mtime:
                    logger.debug(
                        "Sources dir mtime changed (%.0f -> %.0f), rebuilding",
                        cached_mtime, current_mtime,
                    )
                    return None

            # Remove meta key and return index
            index = {k: v for k, v in data.items() if k != "_meta"}

            if len(index) != cached_count:
                logger.debug("Cache count mismatch, rebuilding")
                return None

            return index

        except (json.JSONDecodeError, KeyError, OSError) as e:
            logger.debug("Failed to load cached index: %s", e)
            return None

    def _save_cached_index(self, index: dict[str, str]) -> None:
        """Persist index to disk cache."""
        try:
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)

            mtime = self._sources_dir.stat().st_mtime if self._sources_dir.exists() else 0

            data = dict(index)
            data["_meta"] = {  # type: ignore[assignment]
                "mtime": mtime,
                "count": len(index),
                "sources_dir": str(self._sources_dir),
            }

            with open(_INDEX_CACHE_FILE, "w") as f:
                json.dump(data, f)

            logger.info("Saved index cache (%d entries) to %s", len(index), _INDEX_CACHE_FILE)

        except OSError as e:
            logger.warning("Failed to save index cache: %s", e)
