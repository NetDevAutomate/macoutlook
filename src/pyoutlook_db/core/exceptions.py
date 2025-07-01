"""Exception classes for pyoutlook-db library.

This module defines custom exceptions used throughout the library to provide
clear error handling and debugging information.
"""



class OutlookDBError(Exception):
    """Base exception for all pyoutlook-db errors."""

    def __init__(self, message: str, details: str | None = None) -> None:
        """Initialize the exception with message and optional details.

        Args:
            message: The main error message
            details: Optional additional details about the error
        """
        super().__init__(message)
        self.message = message
        self.details = details

    def __str__(self) -> str:
        """Return string representation of the error."""
        if self.details:
            return f"{self.message}: {self.details}"
        return self.message


class DatabaseNotFoundError(OutlookDBError):
    """Raised when the Outlook SQLite database cannot be found."""

    def __init__(self, searched_paths: list[str] | None = None) -> None:
        """Initialize with optional list of searched paths.

        Args:
            searched_paths: List of paths that were searched for the database
        """
        message = "Outlook SQLite database not found"
        details = None
        if searched_paths:
            details = f"Searched paths: {', '.join(searched_paths)}"
        super().__init__(message, details)
        self.searched_paths = searched_paths or []


class DatabaseLockError(OutlookDBError):
    """Raised when the database is locked by another process (usually Outlook)."""

    def __init__(self, retry_count: int = 0) -> None:
        """Initialize with retry count information.

        Args:
            retry_count: Number of retry attempts made
        """
        message = "Database is locked by another process"
        details = f"Retries attempted: {retry_count}"
        super().__init__(message, details)
        self.retry_count = retry_count


class ConnectionError(OutlookDBError):
    """Raised when database connection fails."""

    def __init__(
        self, db_path: str, original_error: Exception | None = None
    ) -> None:
        """Initialize with database path and original error.

        Args:
            db_path: Path to the database that failed to connect
            original_error: The original exception that caused the connection failure
        """
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
        """Initialize with content type and original error.

        Args:
            content_type: Type of content that failed to parse (e.g., 'HTML', 'XML')
            original_error: The original exception that caused the parsing failure
        """
        message = f"Failed to parse {content_type} content"
        details = str(original_error) if original_error else None
        super().__init__(message, details)
        self.content_type = content_type
        self.original_error = original_error


class ValidationError(OutlookDBError):
    """Raised when input validation fails."""

    def __init__(self, field: str, value: str, reason: str) -> None:
        """Initialize with validation details.

        Args:
            field: Name of the field that failed validation
            value: The invalid value
            reason: Reason why the validation failed
        """
        message = f"Validation failed for field '{field}'"
        details = f"Value: {value}, Reason: {reason}"
        super().__init__(message, details)
        self.field = field
        self.value = value
        self.reason = reason
