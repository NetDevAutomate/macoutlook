"""Unit tests for MessageSourceReader."""

import os
import stat
from pathlib import Path

import pytest

from macoutlook.core.message_source import _MAX_SOURCE_FILE_SIZE, MessageSourceReader


def _write_mime_file(path: Path, message_id: str, body: str = "Hello world") -> None:
    """Write a minimal RFC 2822 MIME file."""
    content = (
        f"From: sender@example.com\r\n"
        f"To: recipient@example.com\r\n"
        f"Subject: Test Email\r\n"
        f"Message-ID: <{message_id}>\r\n"
        f"Content-Type: text/plain; charset=utf-8\r\n"
        f"\r\n"
        f"{body}\r\n"
    )
    path.write_bytes(content.encode("utf-8"))


def _write_multipart_file(
    path: Path, message_id: str, text_body: str, html_body: str
) -> None:
    """Write a multipart/alternative MIME file."""
    boundary = "----boundary123"
    content = (
        f"From: sender@example.com\r\n"
        f"To: recipient@example.com\r\n"
        f"Subject: Multipart Test\r\n"
        f"Message-ID: <{message_id}>\r\n"
        f'Content-Type: multipart/alternative; boundary="{boundary}"\r\n'
        f"\r\n"
        f"--{boundary}\r\n"
        f"Content-Type: text/plain; charset=utf-8\r\n"
        f"\r\n"
        f"{text_body}\r\n"
        f"--{boundary}\r\n"
        f"Content-Type: text/html; charset=utf-8\r\n"
        f"\r\n"
        f"{html_body}\r\n"
        f"--{boundary}--\r\n"
    )
    path.write_bytes(content.encode("utf-8"))


def _write_attachment_file(path: Path, message_id: str) -> None:
    """Write a multipart/mixed MIME file with an attachment."""
    boundary = "----mixedboundary"
    content = (
        f"From: sender@example.com\r\n"
        f"To: recipient@example.com\r\n"
        f"Subject: Attachment Test\r\n"
        f"Message-ID: <{message_id}>\r\n"
        f'Content-Type: multipart/mixed; boundary="{boundary}"\r\n'
        f"\r\n"
        f"--{boundary}\r\n"
        f"Content-Type: text/plain; charset=utf-8\r\n"
        f"\r\n"
        f"Email with attachment\r\n"
        f"--{boundary}\r\n"
        f'Content-Type: application/pdf; name="report.pdf"\r\n'
        f'Content-Disposition: attachment; filename="report.pdf"\r\n'
        f"Content-Transfer-Encoding: base64\r\n"
        f"\r\n"
        f"JVBERi0xLjQKMSAwIG9iago=\r\n"
        f"--{boundary}--\r\n"
    )
    path.write_bytes(content.encode("utf-8"))


class TestMessageSourceReader:
    def test_index_from_single_file(self, tmp_path: Path):
        msg_file = tmp_path / "test.olk15MsgSource"
        _write_mime_file(msg_file, "test123@example.com")

        reader = MessageSourceReader(sources_dir=tmp_path)
        count = reader.build_index(force=True)

        assert count == 1
        assert reader.get_source_path("test123@example.com") == str(msg_file)

    def test_index_from_multiple_files(self, tmp_path: Path):
        for i in range(5):
            msg_file = tmp_path / f"msg{i}.olk15MsgSource"
            _write_mime_file(msg_file, f"msg{i}@example.com")

        reader = MessageSourceReader(sources_dir=tmp_path)
        count = reader.build_index(force=True)

        assert count == 5
        for i in range(5):
            assert reader.get_source_path(f"msg{i}@example.com") is not None

    def test_index_returns_none_for_missing_id(self, tmp_path: Path):
        msg_file = tmp_path / "test.olk15MsgSource"
        _write_mime_file(msg_file, "exists@example.com")

        reader = MessageSourceReader(sources_dir=tmp_path)
        reader.build_index(force=True)

        assert reader.get_source_path("missing@example.com") is None

    def test_index_strips_angle_brackets(self, tmp_path: Path):
        msg_file = tmp_path / "test.olk15MsgSource"
        # Write with angle brackets in Message-ID header
        content = (
            "From: sender@example.com\r\n"
            "Message-ID: <bracketed@example.com>\r\n"
            "Content-Type: text/plain\r\n"
            "\r\n"
            "body\r\n"
        )
        msg_file.write_bytes(content.encode())

        reader = MessageSourceReader(sources_dir=tmp_path)
        reader.build_index(force=True)

        # Should be accessible without brackets
        assert reader.get_source_path("bracketed@example.com") is not None

    def test_index_skips_non_olk_files(self, tmp_path: Path):
        _write_mime_file(tmp_path / "good.olk15MsgSource", "good@example.com")
        (tmp_path / "bad.txt").write_text("not an email")
        (tmp_path / "bad.eml").write_text("also not right")

        reader = MessageSourceReader(sources_dir=tmp_path)
        count = reader.build_index(force=True)

        assert count == 1

    def test_index_handles_empty_directory(self, tmp_path: Path):
        reader = MessageSourceReader(sources_dir=tmp_path)
        count = reader.build_index(force=True)
        assert count == 0

    def test_index_handles_missing_directory(self, tmp_path: Path):
        reader = MessageSourceReader(sources_dir=tmp_path / "nonexistent")
        count = reader.build_index(force=True)
        assert count == 0

    def test_lazy_index_building(self, tmp_path: Path):
        _write_mime_file(tmp_path / "test.olk15MsgSource", "lazy@example.com")

        reader = MessageSourceReader(sources_dir=tmp_path)
        assert reader.index_size == 0

        # First access triggers index build
        result = reader.get_source_path("lazy@example.com")
        assert result is not None
        assert reader.index_size == 1

    def test_recursive_directory_scan(self, tmp_path: Path):
        subdir = tmp_path / "subdir1" / "subdir2"
        subdir.mkdir(parents=True)
        _write_mime_file(subdir / "deep.olk15MsgSource", "deep@example.com")

        reader = MessageSourceReader(sources_dir=tmp_path)
        reader.build_index(force=True)

        assert reader.get_source_path("deep@example.com") is not None


class TestMimeParsing:
    def test_parse_plain_text_email(self, tmp_path: Path):
        msg_file = tmp_path / "test.olk15MsgSource"
        _write_mime_file(msg_file, "plain@example.com", body="Hello plain text")

        reader = MessageSourceReader(sources_dir=tmp_path)
        reader.build_index(force=True)
        content = reader.get_content("plain@example.com")

        assert content is not None
        assert content.body_text is not None
        assert "Hello plain text" in content.body_text
        assert content.body_html is None
        assert content.attachments == ()

    def test_parse_multipart_email(self, tmp_path: Path):
        msg_file = tmp_path / "multi.olk15MsgSource"
        _write_multipart_file(
            msg_file,
            "multi@example.com",
            text_body="Plain version",
            html_body="<p>HTML version</p>",
        )

        reader = MessageSourceReader(sources_dir=tmp_path)
        reader.build_index(force=True)
        content = reader.get_content("multi@example.com")

        assert content is not None
        assert content.body_text is not None
        assert "Plain version" in content.body_text
        assert content.body_html is not None
        assert "<p>HTML version</p>" in content.body_html

    def test_parse_email_with_attachment(self, tmp_path: Path):
        msg_file = tmp_path / "attach.olk15MsgSource"
        _write_attachment_file(msg_file, "attach@example.com")

        reader = MessageSourceReader(sources_dir=tmp_path)
        reader.build_index(force=True)
        content = reader.get_content("attach@example.com")

        assert content is not None
        assert len(content.attachments) == 1
        assert content.attachments[0].filename == "report.pdf"
        assert content.attachments[0].content_type == "application/pdf"

    def test_get_content_returns_none_for_missing(self, tmp_path: Path):
        reader = MessageSourceReader(sources_dir=tmp_path)
        reader.build_index(force=True)

        content = reader.get_content("missing@example.com")
        assert content is None

    def test_mime_content_is_frozen(self, tmp_path: Path):
        msg_file = tmp_path / "test.olk15MsgSource"
        _write_mime_file(msg_file, "frozen@example.com")

        reader = MessageSourceReader(sources_dir=tmp_path)
        reader.build_index(force=True)
        content = reader.get_content("frozen@example.com")

        assert content is not None
        with pytest.raises(AttributeError):
            content.body_text = "mutated"  # type: ignore[misc]


class TestIndexPersistence:
    def test_save_and_load_index(self, tmp_path: Path, monkeypatch):
        cache_file = tmp_path / "cache" / "message_index.json"
        monkeypatch.setattr(
            "macoutlook.core.message_source._INDEX_CACHE_FILE", cache_file
        )
        monkeypatch.setattr(
            "macoutlook.core.message_source._CACHE_DIR", tmp_path / "cache"
        )

        sources = tmp_path / "sources"
        sources.mkdir()
        _write_mime_file(sources / "test.olk15MsgSource", "cached@example.com")

        # Build and save
        reader1 = MessageSourceReader(sources_dir=sources)
        reader1.build_index(force=True)
        assert cache_file.exists()

        # Load from cache
        reader2 = MessageSourceReader(sources_dir=sources)
        count = reader2.build_index()
        assert count == 1
        assert reader2.get_source_path("cached@example.com") is not None

    def test_cache_survives_dir_mtime_change(self, tmp_path: Path, monkeypatch):
        """Cache should NOT be invalidated by directory mtime changes.

        Outlook updates the Message Sources dir mtime on every sync,
        which would make the cache useless if we checked mtime.
        """
        cache_file = tmp_path / "cache" / "message_index.json"
        monkeypatch.setattr(
            "macoutlook.core.message_source._INDEX_CACHE_FILE", cache_file
        )
        monkeypatch.setattr(
            "macoutlook.core.message_source._CACHE_DIR", tmp_path / "cache"
        )

        sources = tmp_path / "sources"
        sources.mkdir()
        _write_mime_file(sources / "test.olk15MsgSource", "old@example.com")

        # Build and cache
        reader1 = MessageSourceReader(sources_dir=sources)
        reader1.build_index(force=True)
        assert cache_file.exists()

        # Modify directory mtime (simulating Outlook sync)
        os.utime(sources, None)

        # Cache should still be valid — loads instantly, same count
        reader2 = MessageSourceReader(sources_dir=sources)
        count = reader2.build_index()
        assert count == 1  # Loaded from cache, not rebuilt

    def test_force_rebuild_ignores_cache(self, tmp_path: Path, monkeypatch):
        cache_file = tmp_path / "cache" / "message_index.json"
        monkeypatch.setattr(
            "macoutlook.core.message_source._INDEX_CACHE_FILE", cache_file
        )
        monkeypatch.setattr(
            "macoutlook.core.message_source._CACHE_DIR", tmp_path / "cache"
        )

        sources = tmp_path / "sources"
        sources.mkdir()
        _write_mime_file(sources / "old.olk15MsgSource", "old@example.com")

        # Build and cache
        reader1 = MessageSourceReader(sources_dir=sources)
        reader1.build_index(force=True)

        # Add a new file
        _write_mime_file(sources / "new.olk15MsgSource", "new@example.com")

        # Normal build uses cache (still shows 1)
        reader2 = MessageSourceReader(sources_dir=sources)
        assert reader2.build_index() == 1

        # Force rebuild picks up the new file
        assert reader2.build_index(force=True) == 2
        assert reader2.get_source_path("new@example.com") is not None

    def test_cache_invalidated_on_different_sources_dir(
        self, tmp_path: Path, monkeypatch
    ):
        cache_file = tmp_path / "cache" / "message_index.json"
        monkeypatch.setattr(
            "macoutlook.core.message_source._INDEX_CACHE_FILE", cache_file
        )
        monkeypatch.setattr(
            "macoutlook.core.message_source._CACHE_DIR", tmp_path / "cache"
        )

        sources_a = tmp_path / "sources_a"
        sources_a.mkdir()
        _write_mime_file(sources_a / "a.olk15MsgSource", "a@example.com")

        sources_b = tmp_path / "sources_b"
        sources_b.mkdir()
        _write_mime_file(sources_b / "b.olk15MsgSource", "b@example.com")

        # Build cache for sources_a
        reader_a = MessageSourceReader(sources_dir=sources_a)
        reader_a.build_index(force=True)

        # Different sources_dir should not use that cache
        reader_b = MessageSourceReader(sources_dir=sources_b)
        count = reader_b.build_index()
        assert count == 1
        assert reader_b.get_source_path("b@example.com") is not None
        assert reader_b.get_source_path("a@example.com") is None


class TestCacheFilePermissions:
    """Security: cache directory and file must have restrictive permissions."""

    def test_cache_directory_created_with_mode_700(self, tmp_path: Path, monkeypatch):
        cache_dir = tmp_path / "secure_cache"
        cache_file = cache_dir / "message_index.json"
        monkeypatch.setattr(
            "macoutlook.core.message_source._INDEX_CACHE_FILE", cache_file
        )
        monkeypatch.setattr("macoutlook.core.message_source._CACHE_DIR", cache_dir)

        sources = tmp_path / "sources"
        sources.mkdir()
        _write_mime_file(sources / "test.olk15MsgSource", "perm@example.com")

        reader = MessageSourceReader(sources_dir=sources)
        reader.build_index(force=True)

        assert cache_dir.exists()
        dir_mode = cache_dir.stat().st_mode & 0o777
        assert dir_mode == 0o700, (
            f"Cache directory mode should be 0o700, got {oct(dir_mode)}"
        )

    def test_cache_file_written_with_mode_600(self, tmp_path: Path, monkeypatch):
        cache_dir = tmp_path / "secure_cache"
        cache_file = cache_dir / "message_index.json"
        monkeypatch.setattr(
            "macoutlook.core.message_source._INDEX_CACHE_FILE", cache_file
        )
        monkeypatch.setattr("macoutlook.core.message_source._CACHE_DIR", cache_dir)

        sources = tmp_path / "sources"
        sources.mkdir()
        _write_mime_file(sources / "test.olk15MsgSource", "perm@example.com")

        reader = MessageSourceReader(sources_dir=sources)
        reader.build_index(force=True)

        assert cache_file.exists()
        file_mode = cache_file.stat().st_mode & 0o777
        assert file_mode == 0o600, (
            f"Cache file mode should be 0o600, got {oct(file_mode)}"
        )

    def test_cache_file_not_world_readable(self, tmp_path: Path, monkeypatch):
        cache_dir = tmp_path / "secure_cache"
        cache_file = cache_dir / "message_index.json"
        monkeypatch.setattr(
            "macoutlook.core.message_source._INDEX_CACHE_FILE", cache_file
        )
        monkeypatch.setattr("macoutlook.core.message_source._CACHE_DIR", cache_dir)

        sources = tmp_path / "sources"
        sources.mkdir()
        _write_mime_file(sources / "test.olk15MsgSource", "perm@example.com")

        reader = MessageSourceReader(sources_dir=sources)
        reader.build_index(force=True)

        file_mode = cache_file.stat().st_mode
        # Neither group nor other should have any permissions
        assert not (file_mode & stat.S_IRGRP), "Cache file should not be group-readable"
        assert not (file_mode & stat.S_IROTH), "Cache file should not be world-readable"

    def test_cache_content_still_valid_after_permission_fix(
        self, tmp_path: Path, monkeypatch
    ):
        """Permissions fix must not break cache read/write functionality."""
        cache_dir = tmp_path / "secure_cache"
        cache_file = cache_dir / "message_index.json"
        monkeypatch.setattr(
            "macoutlook.core.message_source._INDEX_CACHE_FILE", cache_file
        )
        monkeypatch.setattr("macoutlook.core.message_source._CACHE_DIR", cache_dir)

        sources = tmp_path / "sources"
        sources.mkdir()
        _write_mime_file(sources / "test.olk15MsgSource", "valid@example.com")

        # Build and save to cache
        reader1 = MessageSourceReader(sources_dir=sources)
        reader1.build_index(force=True)

        # Load from restricted cache file -- must still work
        reader2 = MessageSourceReader(sources_dir=sources)
        count = reader2.build_index()
        assert count == 1
        assert reader2.get_source_path("valid@example.com") is not None


class TestMimeFileSizeLimit:
    """Security: oversized .olk15MsgSource files must be rejected."""

    def test_max_source_file_size_constant_is_100mb(self):
        assert _MAX_SOURCE_FILE_SIZE == 100 * 1024 * 1024

    def test_oversized_file_returns_none(self, tmp_path: Path, monkeypatch):
        """Files exceeding the size limit should be skipped, returning None."""
        # Use a tiny limit for testing (1 KB)
        monkeypatch.setattr(
            "macoutlook.core.message_source._MAX_SOURCE_FILE_SIZE", 1024
        )

        msg_file = tmp_path / "huge.olk15MsgSource"
        # Write a file that exceeds 1 KB
        body = "X" * 2048
        _write_mime_file(msg_file, "huge@example.com", body=body)
        assert msg_file.stat().st_size > 1024

        reader = MessageSourceReader(sources_dir=tmp_path)
        reader.build_index(force=True)
        content = reader.get_content("huge@example.com")

        assert content is None

    def test_file_at_exact_limit_is_accepted(self, tmp_path: Path, monkeypatch):
        """A file exactly at the size limit should be parsed normally."""
        msg_file = tmp_path / "exact.olk15MsgSource"
        _write_mime_file(msg_file, "exact@example.com", body="Small body")
        file_size = msg_file.stat().st_size

        # Set limit to exactly the file size
        monkeypatch.setattr(
            "macoutlook.core.message_source._MAX_SOURCE_FILE_SIZE", file_size
        )

        reader = MessageSourceReader(sources_dir=tmp_path)
        reader.build_index(force=True)
        content = reader.get_content("exact@example.com")

        assert content is not None
        assert content.body_text is not None

    def test_file_one_byte_over_limit_is_rejected(self, tmp_path: Path, monkeypatch):
        """A file one byte over the limit should be rejected."""
        msg_file = tmp_path / "over.olk15MsgSource"
        _write_mime_file(msg_file, "over@example.com", body="Small body")
        file_size = msg_file.stat().st_size

        # Set limit to one byte less than the file size
        monkeypatch.setattr(
            "macoutlook.core.message_source._MAX_SOURCE_FILE_SIZE", file_size - 1
        )

        reader = MessageSourceReader(sources_dir=tmp_path)
        reader.build_index(force=True)
        content = reader.get_content("over@example.com")

        assert content is None

    def test_oversized_file_logs_warning(self, tmp_path: Path, monkeypatch, caplog):
        """Skipping an oversized file should emit a warning log."""
        monkeypatch.setattr("macoutlook.core.message_source._MAX_SOURCE_FILE_SIZE", 100)

        msg_file = tmp_path / "big.olk15MsgSource"
        _write_mime_file(msg_file, "big@example.com", body="X" * 200)

        reader = MessageSourceReader(sources_dir=tmp_path)
        reader.build_index(force=True)

        import logging

        with caplog.at_level(logging.WARNING, logger="macoutlook.core.message_source"):
            content = reader.get_content("big@example.com")

        assert content is None
        assert "oversized" in caplog.text.lower() or "Skipping" in caplog.text

    def test_normal_file_under_limit_parses_successfully(self, tmp_path: Path):
        """Normal-sized files should parse without issue (regression guard)."""
        msg_file = tmp_path / "normal.olk15MsgSource"
        _write_mime_file(msg_file, "normal@example.com", body="Normal content")

        reader = MessageSourceReader(sources_dir=tmp_path)
        reader.build_index(force=True)
        content = reader.get_content("normal@example.com")

        assert content is not None
        assert "Normal content" in content.body_text
