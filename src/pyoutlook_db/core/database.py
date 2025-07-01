"""Database connection and management for pyoutlook-db library.

This module provides the core database connectivity functionality for accessing
Microsoft Outlook's SQLite database on macOS.
"""

import glob
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

import structlog

from ..core.exceptions import (
    ConnectionError as DBConnectionError,
)
from ..core.exceptions import (
    DatabaseLockError,
    DatabaseNotFoundError,
)

logger = structlog.get_logger(__name__)


class OutlookDatabase:
    """Manages connection to Microsoft Outlook SQLite database.

    This class handles database discovery, connection management, and provides
    read-only access to the Outlook database with proper error handling and
    retry mechanisms.
    """

    def __init__(self, db_path: str | None = None, max_retries: int = 3) -> None:
        """Initialize the database manager.

        Args:
            db_path: Optional explicit path to the database file
            max_retries: Maximum number of retry attempts for locked database
        """
        self.db_path = db_path
        self.max_retries = max_retries
        self.conn: sqlite3.Connection | None = None
        self.is_connected = False
        self.last_error: str | None = None

        logger.info(
            "Initialized OutlookDatabase", db_path=db_path, max_retries=max_retries
        )

    def find_database_path(self) -> str:
        """Find the Outlook SQLite database file by searching common locations.

        Returns:
            Path to the Outlook SQLite database file

        Raises:
            DatabaseNotFoundError: If database file cannot be found
        """
        logger.info("Searching for Outlook database")

        # Base path for Outlook data on macOS
        base_path = (
            Path.home()
            / "Library"
            / "Group Containers"
            / "UBF8T346G9.Office"
            / "Outlook"
        )

        searched_paths = []

        # Common profile paths to check
        profile_patterns = [
            "Outlook 15 Profiles/Main Profile/Data/Outlook.sqlite",
            "Outlook 16 Profiles/Main Profile/Data/Outlook.sqlite",
            "Outlook 17 Profiles/Main Profile/Data/Outlook.sqlite",
            "Outlook 18 Profiles/Main Profile/Data/Outlook.sqlite",
        ]

        # Try specific profile paths first
        for pattern in profile_patterns:
            full_path = base_path / pattern
            searched_paths.append(str(full_path))

            if full_path.exists():
                logger.info("Found Outlook database", path=str(full_path))
                return str(full_path)

        # If no specific path found, search recursively for any Outlook.sqlite file
        pattern = str(base_path / "**/Outlook.sqlite")
        matches = glob.glob(pattern, recursive=True)

        if matches:
            # Use the first match found
            db_path = matches[0]
            logger.info("Found Outlook database via recursive search", path=db_path)
            return db_path

        # Also check for alternative database names
        alt_patterns = [
            str(base_path / "**/outlook.sqlite"),
            str(base_path / "**/Outlook.db"),
            str(base_path / "**/outlook.db"),
        ]

        for pattern in alt_patterns:
            matches = glob.glob(pattern, recursive=True)
            searched_paths.extend(matches)
            if matches:
                db_path = matches[0]
                logger.info(
                    "Found Outlook database with alternative name", path=db_path
                )
                return db_path

        # Database not found
        logger.error("Outlook database not found", searched_paths=searched_paths)
        raise DatabaseNotFoundError(searched_paths)

    def connect(self) -> None:
        """Connect to the Outlook database with retry logic.

        Raises:
            DatabaseNotFoundError: If database file cannot be found
            DatabaseLockError: If database is locked after all retries
            DBConnectionError: If connection fails for other reasons
        """
        if self.is_connected:
            logger.debug("Already connected to database")
            return

        # Find database path if not provided
        if not self.db_path:
            self.db_path = self.find_database_path()

        # Verify database file exists
        if not os.path.exists(self.db_path):
            raise DatabaseNotFoundError([self.db_path])

        # Attempt connection with retries
        for attempt in range(self.max_retries):
            try:
                logger.info(
                    "Attempting database connection",
                    path=self.db_path,
                    attempt=attempt + 1,
                )

                # Connect in read-only mode with URI format
                uri = f"file:{self.db_path}?mode=ro"
                self.conn = sqlite3.connect(uri, uri=True, timeout=30.0)
                self.conn.row_factory = sqlite3.Row

                # Test the connection with a simple query
                cursor = self.conn.cursor()
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' LIMIT 1"
                )
                cursor.fetchone()
                cursor.close()

                self.is_connected = True
                logger.info("Successfully connected to Outlook database")
                return

            except sqlite3.OperationalError as e:
                error_msg = str(e).lower()

                if "database is locked" in error_msg:
                    logger.warning(
                        "Database is locked, retrying",
                        attempt=attempt + 1,
                        max_retries=self.max_retries,
                    )

                    if attempt < self.max_retries - 1:
                        # Exponential backoff: 1s, 2s, 4s
                        wait_time = 2**attempt
                        time.sleep(wait_time)
                        continue
                    else:
                        # Final attempt failed
                        raise DatabaseLockError(retry_count=attempt + 1) from e
                else:
                    # Other operational error
                    logger.error("Database operational error", error=str(e))
                    raise DBConnectionError(self.db_path, e) from e

            except Exception as e:
                logger.error("Unexpected database connection error", error=str(e))
                raise DBConnectionError(self.db_path, e) from e

    def disconnect(self) -> None:
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
            self.is_connected = False
            logger.info("Disconnected from database")

    def execute_query(
        self, query: str, params: tuple | None = None
    ) -> list[sqlite3.Row]:
        """Execute a SELECT query and return results.

        Args:
            query: SQL SELECT query to execute
            params: Optional query parameters

        Returns:
            List of query result rows

        Raises:
            DBConnectionError: If not connected or query fails
        """
        if not self.is_connected or not self.conn:
            raise DBConnectionError("Not connected to database", None)

        try:
            logger.debug(
                "Executing query",
                query=query[:100] + "..." if len(query) > 100 else query,
            )

            cursor = self.conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            results = cursor.fetchall()
            cursor.close()

            logger.debug("Query executed successfully", row_count=len(results))
            return results

        except sqlite3.Error as e:
            logger.error("Query execution failed", query=query, error=str(e))
            raise DBConnectionError(f"Query failed: {query[:50]}...", e) from e

    def get_table_info(self, table_name: str) -> list[dict[str, Any]]:
        """Get information about a database table.

        Args:
            table_name: Name of the table to inspect

        Returns:
            List of column information dictionaries
        """
        query = f"PRAGMA table_info({table_name})"
        rows = self.execute_query(query)

        return [
            {
                "cid": row["cid"],
                "name": row["name"],
                "type": row["type"],
                "notnull": bool(row["notnull"]),
                "dflt_value": row["dflt_value"],
                "pk": bool(row["pk"]),
            }
            for row in rows
        ]

    def get_table_names(self) -> list[str]:
        """Get list of all table names in the database.

        Returns:
            List of table names
        """
        query = "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        rows = self.execute_query(query)
        return [row["name"] for row in rows]

    def get_row_count(self, table_name: str, where_clause: str = "") -> int:
        """Get the number of rows in a table.

        Args:
            table_name: Name of the table
            where_clause: Optional WHERE clause (without the WHERE keyword)

        Returns:
            Number of rows
        """
        query = f"SELECT COUNT(*) as count FROM {table_name}"
        if where_clause:
            query += f" WHERE {where_clause}"

        rows = self.execute_query(query)
        return rows[0]["count"] if rows else 0

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()

    def __del__(self):
        """Cleanup on object destruction."""
        if self.is_connected:
            self.disconnect()


# Global database instance for reuse
_db_instance: OutlookDatabase | None = None


def get_database(db_path: str | None = None) -> OutlookDatabase:
    """Get a shared database instance.

    Args:
        db_path: Optional explicit database path

    Returns:
        OutlookDatabase instance
    """
    global _db_instance

    if _db_instance is None or (db_path and _db_instance.db_path != db_path):
        _db_instance = OutlookDatabase(db_path)

    return _db_instance
