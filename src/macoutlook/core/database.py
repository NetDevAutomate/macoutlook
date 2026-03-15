"""Database connection and management for macoutlook library."""

import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

from ..exceptions import (
    DatabaseConnectionError,
    DatabaseLockError,
    DatabaseNotFoundError,
)

logger = logging.getLogger(__name__)

# Known tables in the Outlook database (allowlist for table_info/row_count)
_KNOWN_TABLES = frozenset(
    {
        "Mail",
        "CalendarEvents",
        "Contacts",
        "Folders",
        "Calendars",
        "Conversations",
        "Files",
        "Notes",
        "Tasks",
        "Categories",
        "AccountsMail",
        "AccountsExchange",
        "Settings",
        "Signatures",
        "Rules",
        "Threads",
        "Main",
    }
)


class OutlookDatabase:
    """Manages connection to Microsoft Outlook SQLite database.

    Provides read-only access with retry logic for locked databases.
    """

    def __init__(self, db_path: Path | str | None = None, max_retries: int = 3) -> None:
        self.db_path: Path | None = Path(db_path) if db_path else None
        self.max_retries = max_retries
        self.conn: sqlite3.Connection | None = None
        self.is_connected = False

        logger.info("Initialized OutlookDatabase (db_path=%s)", self.db_path)

    def find_database_path(self) -> Path:
        """Find the Outlook SQLite database by searching common locations.

        Raises:
            DatabaseNotFoundError: If database cannot be found.
        """
        base_path = (
            Path.home()
            / "Library"
            / "Group Containers"
            / "UBF8T346G9.Office"
            / "Outlook"
        )

        searched_paths: list[str] = []

        profile_patterns = [
            "Outlook 15 Profiles/Main Profile/Data/Outlook.sqlite",
            "Outlook 16 Profiles/Main Profile/Data/Outlook.sqlite",
            "Outlook 17 Profiles/Main Profile/Data/Outlook.sqlite",
            "Outlook 18 Profiles/Main Profile/Data/Outlook.sqlite",
        ]

        for pattern in profile_patterns:
            full_path = base_path / pattern
            searched_paths.append(str(full_path))
            if full_path.exists():
                logger.info("Found Outlook database at %s", full_path)
                return full_path

        # Recursive search as fallback
        for match in base_path.rglob("Outlook.sqlite"):
            logger.info("Found Outlook database via recursive search: %s", match)
            return match

        logger.error(
            "Outlook database not found (searched %d paths)", len(searched_paths)
        )
        raise DatabaseNotFoundError(searched_paths)

    def connect(self) -> None:
        """Connect to the Outlook database with retry logic.

        Raises:
            DatabaseNotFoundError: If database file cannot be found.
            DatabaseLockError: If database is locked after all retries.
            DatabaseConnectionError: If connection fails.
        """
        if self.is_connected:
            return

        if not self.db_path:
            self.db_path = self.find_database_path()

        if not self.db_path.exists():
            raise DatabaseNotFoundError([str(self.db_path)])

        for attempt in range(self.max_retries):
            try:
                logger.info("Connecting to database (attempt %d)", attempt + 1)
                uri = f"file:{self.db_path}?mode=ro"
                self.conn = sqlite3.connect(uri, uri=True, timeout=30.0)
                self.conn.row_factory = sqlite3.Row

                cursor = self.conn.cursor()
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' LIMIT 1"
                )
                cursor.fetchone()
                cursor.close()

                self.is_connected = True
                logger.info("Connected to Outlook database")
                return

            except sqlite3.OperationalError as e:
                if "database is locked" in str(e).lower():
                    logger.warning(
                        "Database locked (attempt %d/%d)", attempt + 1, self.max_retries
                    )
                    if attempt < self.max_retries - 1:
                        time.sleep(2**attempt)
                        continue
                    raise DatabaseLockError(retry_count=attempt + 1) from e
                logger.error("Database operational error: %s", e)
                raise DatabaseConnectionError(str(self.db_path), e) from e

            except Exception as e:
                logger.error("Unexpected connection error: %s", e)
                raise DatabaseConnectionError(str(self.db_path), e) from e

    def disconnect(self) -> None:
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
            self.is_connected = False
            logger.info("Disconnected from database")

    def execute_query(
        self, query: str, params: tuple[Any, ...] | None = None
    ) -> list[sqlite3.Row]:
        """Execute a SELECT query and return results.

        Raises:
            DatabaseConnectionError: If not connected or query fails.
        """
        if not self.is_connected or not self.conn:
            raise DatabaseConnectionError("Not connected to database", None)

        try:
            cursor = self.conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            results = cursor.fetchall()
            cursor.close()
            return results

        except sqlite3.Error as e:
            logger.error("Query failed: %s", e)
            raise DatabaseConnectionError("Query failed", e) from e

    def get_table_names(self) -> list[str]:
        """Get list of all table names in the database."""
        query = "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        rows = self.execute_query(query)
        return [row["name"] for row in rows]

    def get_row_count(self, table_name: str) -> int:
        """Get the number of rows in a table (allowlisted names only)."""
        if table_name not in _KNOWN_TABLES:
            raise ValueError(f"Unknown table: {table_name}")

        query = f"SELECT COUNT(*) as count FROM {table_name}"  # noqa: S608  # nosec B608
        rows = self.execute_query(query)
        return rows[0]["count"] if rows else 0

    def __enter__(self) -> "OutlookDatabase":
        self.connect()
        return self

    def __exit__(
        self, exc_type: type | None, exc_val: Exception | None, exc_tb: object
    ) -> None:
        self.disconnect()
