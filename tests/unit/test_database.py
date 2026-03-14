"""Unit tests for OutlookDatabase."""

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from macoutlook.core.database import OutlookDatabase, _KNOWN_TABLES
from macoutlook.exceptions import DatabaseConnectionError, DatabaseNotFoundError


class TestOutlookDatabase:
    def test_init_with_path(self, tmp_path: Path):
        db = OutlookDatabase(db_path=tmp_path / "test.sqlite")
        assert db.db_path == tmp_path / "test.sqlite"
        assert not db.is_connected

    def test_init_without_path(self):
        db = OutlookDatabase()
        assert db.db_path is None

    def test_connect_to_real_sqlite(self, tmp_path: Path):
        db_file = tmp_path / "test.sqlite"
        conn = sqlite3.connect(str(db_file))
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO test VALUES (1, 'hello')")
        conn.commit()
        conn.close()

        db = OutlookDatabase(db_path=db_file)
        db.connect()
        assert db.is_connected

        rows = db.execute_query("SELECT name FROM test WHERE id = ?", (1,))
        assert rows[0]["name"] == "hello"

        db.disconnect()
        assert not db.is_connected

    def test_connect_nonexistent_raises(self, tmp_path: Path):
        db = OutlookDatabase(db_path=tmp_path / "nonexistent.sqlite")
        with pytest.raises(DatabaseNotFoundError):
            db.connect()

    def test_context_manager(self, tmp_path: Path):
        db_file = tmp_path / "test.sqlite"
        sqlite3.connect(str(db_file)).close()

        with OutlookDatabase(db_path=db_file) as db:
            assert db.is_connected
        assert not db.is_connected

    def test_execute_query_not_connected(self, tmp_path: Path):
        db = OutlookDatabase(db_path=tmp_path / "test.sqlite")
        with pytest.raises(DatabaseConnectionError):
            db.execute_query("SELECT 1")

    def test_get_table_names(self, tmp_path: Path):
        db_file = tmp_path / "test.sqlite"
        conn = sqlite3.connect(str(db_file))
        conn.execute("CREATE TABLE alpha (id INTEGER)")
        conn.execute("CREATE TABLE beta (id INTEGER)")
        conn.commit()
        conn.close()

        with OutlookDatabase(db_path=db_file) as db:
            tables = db.get_table_names()
            assert "alpha" in tables
            assert "beta" in tables

    def test_get_table_info_allowlist(self, tmp_path: Path):
        db = OutlookDatabase(db_path=tmp_path / "test.sqlite")
        with pytest.raises(ValueError, match="Unknown table"):
            db.get_table_info("'; DROP TABLE users; --")

    def test_get_row_count_allowlist(self, tmp_path: Path):
        db = OutlookDatabase(db_path=tmp_path / "test.sqlite")
        with pytest.raises(ValueError, match="Unknown table"):
            db.get_row_count("injected_table")

    def test_known_tables_includes_mail(self):
        assert "Mail" in _KNOWN_TABLES
        assert "CalendarEvents" in _KNOWN_TABLES

    def test_double_connect_is_idempotent(self, tmp_path: Path):
        db_file = tmp_path / "test.sqlite"
        sqlite3.connect(str(db_file)).close()

        db = OutlookDatabase(db_path=db_file)
        db.connect()
        db.connect()  # Should not raise
        assert db.is_connected
        db.disconnect()

    def test_disconnect_when_not_connected(self):
        db = OutlookDatabase()
        db.disconnect()  # Should not raise


class TestDatabaseDiscovery:
    def test_find_database_path_missing(self):
        db = OutlookDatabase()
        with patch.object(Path, "exists", return_value=False):
            with patch.object(Path, "rglob", return_value=iter([])):
                with pytest.raises(DatabaseNotFoundError):
                    db.find_database_path()
