"""Unit tests for exception classes."""

from macoutlook.exceptions import (
    DatabaseConnectionError,
    DatabaseLockError,
    DatabaseNotFoundError,
    MessageSourceError,
    OutlookDBError,
    ParseError,
)


class TestExceptions:
    def test_base_error(self):
        err = OutlookDBError("test message")
        assert str(err) == "test message"
        assert err.details is None

    def test_base_error_with_details(self):
        err = OutlookDBError("message", "extra details")
        assert str(err) == "message: extra details"
        assert err.details == "extra details"

    def test_database_not_found(self):
        err = DatabaseNotFoundError(["/path/a", "/path/b"])
        assert "not found" in str(err)
        assert err.searched_paths == ["/path/a", "/path/b"]

    def test_database_not_found_no_paths(self):
        err = DatabaseNotFoundError()
        assert err.searched_paths == []

    def test_database_lock_error(self):
        err = DatabaseLockError(retry_count=3)
        assert "locked" in str(err)
        assert err.retry_count == 3

    def test_database_connection_error(self):
        original = RuntimeError("connection refused")
        err = DatabaseConnectionError("/path/to/db", original)
        assert "/path/to/db" in str(err)
        assert err.original_error is original

    def test_parse_error(self):
        err = ParseError("HTML", ValueError("bad html"))
        assert "HTML" in str(err)
        assert err.content_type == "HTML"

    def test_message_source_error(self):
        err = MessageSourceError("MIME parse failed", OSError("disk error"))
        assert "MIME parse failed" in str(err)
        assert err.original_error is not None

    def test_inheritance(self):
        """All exceptions inherit from OutlookDBError."""
        assert issubclass(DatabaseNotFoundError, OutlookDBError)
        assert issubclass(DatabaseLockError, OutlookDBError)
        assert issubclass(DatabaseConnectionError, OutlookDBError)
        assert issubclass(ParseError, OutlookDBError)
        assert issubclass(MessageSourceError, OutlookDBError)

    def test_catchable_as_base(self):
        """Can catch all library errors with OutlookDBError."""
        with_types = [
            DatabaseNotFoundError(),
            DatabaseLockError(),
            DatabaseConnectionError("path", None),
            ParseError("HTML"),
            MessageSourceError("msg"),
        ]
        for err in with_types:
            try:
                raise err
            except OutlookDBError:
                pass  # Should be caught
