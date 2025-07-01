# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

pyoutlook-db is a Python library that provides programmatic access to Microsoft Outlook's SQLite database on macOS. It extracts emails, calendar events, and other Outlook data directly from the database, with automatic content parsing and conversion to JSON/Markdown formats for LLM processing.

### Core Architecture

The library follows a layered architecture:

- **Client Layer** (`core/client.py`): High-level `OutlookClient` class that orchestrates database access and content parsing
- **Database Layer** (`core/database.py`): `OutlookDatabase` class for SQLite connection management with automatic database discovery
- **Models Layer** (`models/`): Pydantic models for emails and calendar events with validation
- **Parsers Layer** (`parsers/`): Content parsing for HTML/XML to text and Markdown conversion
- **CLI Layer** (`cli/main.py`): Command-line interface using Click framework

### Key Design Patterns

- **Context Managers**: Database connections support `with` statements for automatic cleanup
- **Factory Pattern**: `get_database()` function provides shared database instances
- **Content Strategy**: Pluggable content parsers via `get_content_parser()`
- **Auto-Discovery**: Database path finding uses macOS-specific search patterns in `~/Library/Group Containers/UBF8T346G9.Office/Outlook/`

## Development Commands

### Environment Setup
```bash
# Install dependencies and dev tools
uv sync --dev

# Install pre-commit hooks
uv run pre-commit install
```

### Code Quality
```bash
# Run all linting and formatting
uv run ruff check .
uv run ruff format .
uv run mypy src/

# Security scanning
uv run bandit -r src/
uv run safety check
```

### Testing
```bash
# Run all tests with coverage
uv run pytest

# Run specific test types
uv run pytest tests/unit/ -v
uv run pytest tests/integration/ -v

# Run tests excluding slow ones
uv run pytest -m "not slow"

# Run tests for macOS-specific functionality
uv run pytest -m macos
```

### CLI Testing
```bash
# Test CLI commands (requires Outlook database)
uv run pyoutlook-db info
uv run pyoutlook-db emails --start-date 2024-01-01 --limit 5
uv run pyoutlook-db calendars --format json
```

### Build and Package
```bash
# Build wheel
uv build

# Install locally for testing
uv pip install -e .
```

## Database Schema Knowledge

The library expects Outlook SQLite database with these key tables:
- `Messages`: Email data with fields like `RecordID`, `Subject`, `SenderEmailAddress`, `Body`, `DateReceived`
- `Events`: Calendar events with `EventID`, `CalendarID`, `Subject`, `StartTime`, `EndTime`
- `Calendars`: Calendar metadata with `CalendarID`, `CalendarName`, `IsDefault`

## Platform-Specific Considerations

### macOS Requirements
- Only works on macOS (Windows/Linux not supported)
- Requires Microsoft Outlook for Mac to be installed
- Database access requires Outlook to be closed or uses read-only mode
- Uses macOS-specific Group Container paths for database discovery

### Error Handling Patterns
- `DatabaseNotFoundError`: When Outlook database cannot be located
- `DatabaseLockError`: When database is locked by Outlook application
- `ValidationError`: For invalid date ranges or parameters
- Retry logic with exponential backoff for database lock scenarios

## Testing Strategy

### Unit Tests
- Mock database connections for isolated testing
- Test content parsing with sample HTML/XML data
- Validate Pydantic model validation rules

### Integration Tests
- Require actual Outlook database for end-to-end testing
- Test database discovery and connection logic
- Validate SQL query generation and result parsing

### Markers
- `@pytest.mark.slow`: For tests that take significant time
- `@pytest.mark.integration`: For tests requiring database access
- `@pytest.mark.macos`: For macOS-specific functionality

## Content Parsing Pipeline

The library uses a multi-stage content parsing approach:
1. Extract HTML/XML from Outlook database
2. Clean and sanitize content using BeautifulSoup
3. Convert to plain text for searchability
4. Generate Markdown format for LLM consumption
5. Preserve original HTML for full fidelity when needed

## CLI Usage Patterns

The CLI supports multiple output formats (JSON, CSV, table) and common operations:
- Date-based email retrieval with folder filtering
- Calendar event listing and searching
- Full-text search across emails and events
- Database inspection and statistics