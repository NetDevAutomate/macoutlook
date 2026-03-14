"""Exception classes for macoutlook library."""


class OutlookDBError(Exception):
    """Base exception for all macoutlook errors."""

    def __init__(self, message: str, details: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def __str__(self) -> str:
        if self.details:
            return f"{self.message}: {self.details}"
        return self.message


class DatabaseNotFoundError(OutlookDBError):
    """Raised when the Outlook SQLite database cannot be found."""

    def __init__(self, searched_paths: list[str] | None = None) -> None:
        message = "Outlook SQLite database not found"
        details = None
        if searched_paths:
            details = f"Searched paths: {', '.join(searched_paths)}"
        super().__init__(message, details)
        self.searched_paths = searched_paths or []


class DatabaseLockError(OutlookDBError):
    """Raised when the database is locked by another process."""

    def __init__(self, retry_count: int = 0) -> None:
        message = "Database is locked by another process"
        details = f"Retries attempted: {retry_count}"
        super().__init__(message, details)
        self.retry_count = retry_count


class DatabaseConnectionError(OutlookDBError):
    """Raised when database connection fails."""

    def __init__(
        self, db_path: str, original_error: Exception | None = None
    ) -> None:
        message = f"Failed to connect to database at {db_path}"
        details = str(original_error) if original_error else None
        super().__init__(message, details)
        self.db_path = db_path
        self.original_error = original_error


class ParseError(OutlookDBError):
    """Raised when content parsing fails."""

    def __init__(
        self, content_type: str, original_error: Exception | None = None
    ) -> None:
        message = f"Failed to parse {content_type} content"
        details = str(original_error) if original_error else None
        super().__init__(message, details)
        self.content_type = content_type
        self.original_error = original_error


class MessageSourceError(OutlookDBError):
    """Raised when .olk15MsgSource file operations fail."""

    def __init__(
        self, message: str, original_error: Exception | None = None
    ) -> None:
        details = str(original_error) if original_error else None
        super().__init__(message, details)
        self.original_error = original_error
