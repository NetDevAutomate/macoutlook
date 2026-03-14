# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

macoutlook is a Python library for extracting email and calendar data from macOS Outlook. It reads both the Outlook SQLite database (metadata + preview) and `.olk15MsgSource` files (full RFC 2822 MIME content) for complete email extraction.

**Attribution**: The `.olk15MsgSource` extraction approach was discovered by Jon Hammant.

### Core Architecture

Layered architecture with dependency injection:

- **Client Layer** (`core/client.py`): `OutlookClient` orchestrator, `create_client()` factory
- **Database Layer** (`core/database.py`): `OutlookDatabase` for SQLite with read-only access
- **Models Layer** (`models/`): Pydantic v2 models with `ConfigDict(frozen=True)`
  - `models/email_message.py`: `EmailMessage`, `AttachmentInfo`
  - `models/calendar.py`: `CalendarEvent`, `Calendar`
  - `models/enums.py`: `ContentSource`, `FlagStatus`, `Priority` (StrEnum/IntEnum)
- **Parsers Layer** (`parsers/`): Content parsing (HTML -> text/markdown)
- **CLI Layer** (`cli/main.py`): Click-based CLI (`macoutlook` command)
- **Exceptions** (`exceptions.py`): `OutlookDBError` hierarchy at package root

### Key Design Patterns

- **Dependency Injection**: `OutlookClient.__init__` accepts `database`, `enricher`, etc.
- **Context Managers**: Database and client support `with` statements
- **Lazy Enrichment**: Emails return metadata-only by default; full content on demand
- **Never-Raises Enrichment**: `EnrichmentResult` returns errors, never raises exceptions
- **Typed Enums**: `ContentSource(StrEnum)`, `FlagStatus(IntEnum)`, `Priority(IntEnum)`

### Key Conventions

- **stdlib `logging`** throughout (NOT structlog — this is a library)
- **`pathlib.Path`** exclusively (no `os.path`, no `import glob`)
- **Pydantic v2 API**: `ConfigDict`, `@field_validator`, `@model_validator`, `.model_dump()`
- **Parameterized SQL**: No f-string interpolation. Table names allowlisted.

## Development Commands

```bash
# Install dependencies
uv sync --dev

# Run tests
uv run pytest tests/unit/ -v

# Lint and format
uv run ruff check .
uv run ruff format .
uv run mypy src/

# Build wheel
uv build

# CLI
uv run macoutlook info
uv run macoutlook emails --limit 5
uv run macoutlook search --query "meeting"
```

## Database Schema

The `Mail` table has 46 columns. Key fields:

| Column | Usage |
|--------|-------|
| `Record_RecordID` | Internal DB ID (`record_id` on model) |
| `Message_MessageID` | RFC 2822 Message-ID (`message_id` on model, 100% coverage) |
| `Message_Preview` | Preview snippet (~256 chars, `preview` field) |
| `Message_NormalizedSubject` | Email subject |
| `Message_SenderAddressList` | Sender email |
| `Message_TimeReceived` | Timestamp (Unix epoch) |
| `Message_TimeSent` | Sent timestamp |
| `Message_Size` | Message size in bytes |
| `Message_ReadFlag` | Read status |
| `Record_FlagStatus` | Flag status (0=none, 1=flagged, 2=complete) |
| `Record_Priority` | Priority (1=low, 3=normal, 5=high) |

Source files: `~/Library/Group Containers/UBF8T346G9.Office/Outlook/Outlook 15 Profiles/Main Profile/Data/Message Sources/*.olk15MsgSource`

## Error Handling

- `DatabaseNotFoundError`: Outlook database not found
- `DatabaseLockError`: Database locked by Outlook
- `DatabaseConnectionError`: Connection failures (renamed from `ConnectionError` to avoid builtin shadow)
- `ParseError`: Content parsing failures
- `MessageSourceError`: .olk15MsgSource file operations

## Testing Strategy

- Unit tests mock `OutlookDatabase` via DI (no singletons to patch)
- Content parser tests use inline HTML fixtures
- Catch `ValueError | KeyError` in row parsing (not bare `Exception`)
- Markers: `@pytest.mark.integration`, `@pytest.mark.macos`, `@pytest.mark.slow`
