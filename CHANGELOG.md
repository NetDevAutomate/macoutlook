# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-03-15

### Changed
- **Architecture**: Extracted `EmailRepository` and `CalendarRepository` from `OutlookClient`, reducing it from 524 to 288 lines
- **Protocols**: Added `DatabaseProtocol`, `EnricherProtocol`, `ContentParserProtocol` for structural typing and testability
- **CLI**: All commands now use `create_client()` factory instead of constructing `OutlookClient` directly
- SQL query construction moved from client layer to repository layer
- Core Foundation timestamp helpers moved to `CalendarRepository`

### Added
- `core/protocols.py` — Protocol definitions for dependency injection
- `core/email_repository.py` — Email queries, search, and row-to-model mapping
- `core/calendar_repository.py` — Calendar queries, ICS/DB branching, timestamp conversion
- 66 new repository tests across `test_email_repository.py` and `test_calendar_repository.py`

## [0.2.1] - 2026-03-15

### Fixed
- `save_attachment` now correctly skips binary preamble in `.olk15MsgSource` files
- `is_all_day` detection for calendar events (was always returning False)
- Double HTML parse eliminated in content pipeline (~50% CPU reduction)
- CI workflow: dev tools moved to `[dependency-groups]` so `uv sync --dev` installs them
- Pre-commit: replaced isolated `mirrors-mypy` with local `uv run mypy` hook
- Pre-commit: fixed bandit `pass_filenames` conflict with `-r src/`
- Type annotations: `Sequence[Any]` for list invariance, correct `type: ignore` codes

### Security
- Cache directory permissions hardened to 0o700, files to 0o600
- Added 100MB file size limit on MIME source file parsing

### Changed
- FuzzyMatcher reuses SequenceMatcher instance and caches compiled regex patterns
- Removed dead `sep` parameter from `_parse_delimited`
- Removed unused `is_today`/`is_upcoming` properties from CalendarEvent
- Removed unused `get_table_info` from OutlookDatabase
- Removed phantom `python-dateutil` dependency (was never imported)
- Updated CONTRIBUTING.md: renamed pyoutlook-db references, fixed project structure
- Added pre-commit git author identity check

## [0.1.0] - 2025-07-01

### Added
- **Core Functionality**
  - Direct SQLite database access to Microsoft Outlook on macOS
  - Email retrieval with full metadata and content parsing
  - Calendar event access (both SQLite and .ics file sources)
  - Contact information extraction

- **Email Features**
  - Retrieve emails by date range with filtering options
  - Advanced search functionality with multiple criteria
  - Full-text search across subjects and content
  - HTML to Markdown content conversion
  - Support for 70,000+ emails with high performance

- **Calendar Features**
  - Access to historical calendar events from SQLite database
  - Modern calendar event support via .ics file parsing
  - Calendar listing and metadata extraction
  - Event filtering by date range and calendar ID
  - Support for recurring events and all-day events

- **Content Processing**
  - HTML/XML email content parsing and cleaning
  - Automatic conversion to plain text and Markdown formats
  - Link and image extraction from email content
  - Proper handling of Outlook-specific HTML structures

- **CLI Interface**
  - Command-line tools for all major operations
  - Multiple output formats (JSON, CSV, table)
  - Email and calendar event listing and searching
  - Database information and statistics commands

- **Data Models**
  - Type-safe Pydantic models for all data structures
  - Comprehensive EmailMessage model with full metadata
  - CalendarEvent model with attendee and location support
  - Search filter models for advanced querying

- **Export and Integration**
  - JSON export functionality for all data types
  - CSV export support for spreadsheet integration
  - Python API for programmatic access
  - Analytics-ready data structures

- **Performance and Reliability**
  - Direct database access (no API rate limits)
  - Efficient SQLite query optimization
  - Automatic database discovery on macOS
  - Read-only database access for safety
  - Comprehensive error handling and logging

- **Development Features**
  - Full type hints throughout codebase
  - Comprehensive test suite with pytest
  - Code quality tools (ruff, mypy, bandit)
  - Pre-commit hooks for development
  - Structured logging with contextual information

### Technical Details
- **Python Support**: 3.12+
- **Platform Support**: macOS only
- **Database Support**: SQLite (Outlook 15+ format)
- **File Format Support**: .ics (iCalendar) files
- **Dependencies**: 6 runtime dependencies, 15+ development tools
- **Architecture**: Layered design with client, database, models, and parsers

### Performance Metrics
- **Email Processing**: 70,000+ emails processed efficiently
- **Calendar Events**: 6,000+ historical events supported
- **Search Performance**: Full-text search across large datasets
- **Memory Usage**: Optimized for large data volumes
- **Database Queries**: Optimized SQLite queries with proper indexing

### Known Limitations
- macOS only (Windows/Linux not supported)
- Requires Microsoft Outlook for Mac installation
- Historical calendar data limited to SQLite database timeframe
- Modern calendar events limited to .ics file availability
- Read-only access (no data modification capabilities)

## Security Considerations
- Read-only database access prevents data corruption
- No credential storage or transmission
- Local-only data processing (no network requests)
- Proper SQL injection prevention
- Safe HTML content parsing

## Migration Notes
- This is the initial release, no migration required
- Compatible with Outlook 15+ database format
- Backward compatible with older Outlook SQLite schemas
- Forward compatible with modern .ics file formats

---

**Note**: This changelog follows the [Keep a Changelog](https://keepachangelog.com/) format. Each version includes categorized changes (Added, Changed, Deprecated, Removed, Fixed, Security) with detailed descriptions for users and developers.
