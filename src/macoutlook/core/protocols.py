"""Protocol definitions for dependency injection in macoutlook.

These Protocols define the structural contracts that concrete classes
must satisfy. Using Protocol (PEP 544) enables structural subtyping —
existing classes satisfy protocols without inheritance changes.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DatabaseProtocol(Protocol):
    """Protocol for database access."""

    is_connected: bool
    db_path: Path | None

    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def execute_query(
        self, query: str, params: tuple[Any, ...] | None = None
    ) -> list[sqlite3.Row]: ...

    def get_table_names(self) -> list[str]: ...

    def get_row_count(self, table_name: str) -> int: ...


@runtime_checkable
class EnricherProtocol(Protocol):
    """Protocol for email enrichment pipeline."""

    @property
    def index_size(self) -> int: ...

    def build_index(self, force: bool = False) -> int: ...

    def enrich(self, message_id: str, markdown: bool = True) -> Any: ...

    def save_attachment(
        self, message_id: str, attachment_filename: str, dest_dir: Path
    ) -> Path: ...


@runtime_checkable
class ContentParserProtocol(Protocol):
    """Protocol for content parsing."""

    def parse_email_content(self, raw_content: str) -> dict[str, str]: ...
