# Repository Research: pyoutlook-db Refactor to macoutlook

Date: 2026-03-14
Purpose: Comprehensive project analysis for package rename and .olk15MsgSource integration

---

## 1. Current Project Structure

```
pyoutlook-db/
├── pyproject.toml
├── CLAUDE.md
├── CONTRIBUTING.md
├── CHANGELOG.md
├── README.md
├── LICENSE (MIT)
├── MANIFEST.in
├── .pre-commit-config.yaml
├── .gitignore
├── example_usage.py
├── docs/
│   └── brainstorms/
│       └── 2026-03-14-full-content-extraction-brainstorm.md
├── src/
│   └── pyoutlook_db/
│       ├── __init__.py              # Public API, version "0.1.0"
│       ├── core/
│       │   ├── __init__.py          # Empty
│       │   ├── client.py            # OutlookClient (main orchestrator)
│       │   ├── database.py          # OutlookDatabase + get_database() factory
│       │   └── exceptions.py        # Exception hierarchy
│       ├── models/
│       │   ├── __init__.py          # Empty
│       │   ├── email.py             # EmailMessage, EmailSearchFilter, EmailStats, EmailPriority
│       │   └── calendar.py          # CalendarEvent, Calendar, EventStatus, ResponseStatus, RecurrenceType
│       ├── parsers/
│       │   ├── __init__.py          # Empty
│       │   ├── content.py           # ContentParser + get_content_parser() factory
│       │   └── icalendar.py         # ICalendarParser (.ics file reader)
│       └── cli/
│           ├── __init__.py          # Empty
│           └── main.py              # Click CLI (cli group + subcommands)
└── tests/
    ├── __init__.py                  # Empty
    └── unit/
        ├── __init__.py              # Empty
        ├── test_client.py           # 8 tests using unittest.mock
        └── test_content_parser.py   # 8 tests using setup_method pattern
```

No `tests/integration/` directory exists yet (referenced in CLAUDE.md but not created).

---

## 2. pyproject.toml Configuration

### Build System
- **Backend**: hatchling (`hatch.build`)
- **Version**: Dynamic, sourced from `src/pyoutlook_db/__init__.py` line 8: `__version__ = "0.1.0"`
- **Wheel packages**: `["src/pyoutlook_db"]`

### Package Identity
- **Name**: `pyoutlook-db` (line 6)
- **Python**: `>=3.12` (line 10)
- **License**: MIT (line 11)
- **Author**: Amazon Q Developer / noreply@amazon.com (line 12-13) -- needs updating for macoutlook
- **URLs**: All point to `github.com/amazon-q-developer/pyoutlook-db` -- needs updating

### Dependencies (line 28-36)
```
beautifulsoup4>=4.12.0
markdownify>=0.11.0
click>=8.1.0
pydantic>=2.0.0
python-dateutil>=2.8.0
structlog>=23.0.0
icalendar>=5.0.0
```

### Optional Dependencies
- **dev**: pytest, pytest-cov, pytest-asyncio, ruff, mypy, bandit, safety, pre-commit
- **analytics**: pandas, numpy

### Entry Point (line 61)
```
pyoutlook-db = "pyoutlook_db.cli.main:cli"
```

### Tool Configuration
- **ruff**: line-length 88, target py312, Google docstring convention, extensive rule set (E, W, F, I, B, C4, UP, SIM, S, N, D)
- **ruff ignores**: E501, D100, D104; `__init__.py` allows F401; `tests/*` allows S101 and skips D
- **mypy**: strict mode (line 102-120), relaxed for tests
- **pytest**: testpaths=["tests"], strict markers, cov>=80%, markers: slow, integration, unit, macos
- **coverage**: omit tests/* and __init__.py, branch coverage enabled

---

## 3. Existing Test Structure and Patterns

### test_client.py (8 tests)
- **File**: `/Users/taylaand/code/personal/tools/pyoutlook-db/tests/unit/test_client.py`
- **Pattern**: Class-based (`TestOutlookClient`), uses `unittest.mock.patch` and `unittest.mock.Mock`
- **Imports**: `from pyoutlook_db.core.client import OutlookClient`
- **Mocking strategy**: Patches `pyoutlook_db.core.client.get_database` and `pyoutlook_db.core.client.get_content_parser`
- **Key tests**: init with/without auto_connect, connect, disconnect, invalid date range validation, get_emails_by_date_range with mocked DB rows
- **No conftest.py** exists at any level
- **No fixtures** -- each test creates its own mocks inline

### test_content_parser.py (8+ tests)
- **File**: `/Users/taylaand/code/personal/tools/pyoutlook-db/tests/unit/test_content_parser.py`
- **Pattern**: Class-based (`TestContentParser`), uses `setup_method` for fixture creation
- **Direct instantiation**: `self.parser = ContentParser()` (no mocking needed)
- **Tests**: empty content, plain text, simple HTML, whitespace cleaning, HTML tag stripping, link extraction, image extraction

### Observations
- Tests use bare `assert` (ruff S101 suppressed for tests/)
- No parametrize usage found
- No conftest.py with shared fixtures
- No integration test files exist
- pytest markers defined (slow, integration, unit, macos) but no tests use them

---

## 4. Current Models

### EmailMessage (lines 22-143 of email.py)
**Fields:**
| Field | Type | Required | Default |
|-------|------|----------|---------|
| message_id | str | Yes (Field(...)) | - |
| subject | str | No | "" |
| sender | str | Yes (Field(...)) | - |
| sender_name | str \| None | No | None |
| recipients | list[str] | No | [] |
| cc_recipients | list[str] | No | [] |
| bcc_recipients | list[str] | No | [] |
| timestamp | datetime | Yes (Field(...)) | - |
| received_time | datetime \| None | No | None |
| content_html | str | No | "" |
| content_text | str | No | "" |
| content_markdown | str | No | "" |
| folder | str | No | "" |
| is_read | bool | No | False |
| is_flagged | bool | No | False |
| priority | EmailPriority | No | NORMAL |
| attachments | list[str] | No | [] |
| categories | list[str] | No | [] |
| message_size | int \| None | No | None |
| conversation_id | str \| None | No | None |

**Validators** (Pydantic v1-style `@validator`):
- `parse_recipients` (pre=True): Handles str (semicolon/comma separated) or list input for recipients/cc/bcc
- `parse_datetime` (pre=True): Handles ISO format strings and Unix timestamps

**Methods:**
- `to_dict()` -> dict (uses deprecated `.dict(by_alias=True)`)
- `to_json()` -> str (uses deprecated `.json(by_alias=True)`)
- `get_summary()` -> str (From/Subject/Preview format)

**Config class** (Pydantic v1-style):
- `json_encoders` with datetime lambda
- `json_schema_extra` with example data

**IMPORTANT**: Uses Pydantic v1 API patterns (`@validator`, `Config` class, `.dict()`, `.json()`) despite requiring pydantic>=2.0.0. These need migration to v2 patterns (`@field_validator`, `model_config`, `.model_dump()`, `.model_dump_json()`).

### EmailSearchFilter (lines 145-194 of email.py)
- query, sender, subject, folders, is_read, is_flagged, has_attachments
- start_date, end_date (with date range validator)
- categories, priority
- limit (1-1000, default 100), offset (>=0, default 0)

### EmailStats (lines 197-253 of email.py)
- Aggregate statistics model with total_count, unread_count, flagged_count, etc.
- folder_distribution, top_senders as dict[str, int]
- `get_summary()` method

### CalendarEvent (lines 74-180+ of calendar.py)
- event_id, calendar_id, calendar_name
- title, description, location
- start_time, end_time (both required datetime)
- is_all_day, is_recurring
- organizer (str | None), attendees (list[str])
- status (EventStatus enum), response_status (ResponseStatus enum)
- recurrence_type (RecurrenceType enum)
- Also uses v1-style Config and validators

### Calendar (lines 42-71 of calendar.py)
- calendar_id, name, color, is_default, is_shared, owner

### Supporting Enums
- EmailPriority: low, normal, high
- EventStatus: free, tentative, busy, out_of_office
- ResponseStatus: none, accepted, declined, tentative
- RecurrenceType: none, daily, weekly, monthly, yearly

---

## 5. Database Layer

### OutlookDatabase class (database.py, 328 lines)

**Constructor** (line 35):
```python
def __init__(self, db_path: str | None = None, max_retries: int = 3) -> None
```
- Stores db_path, max_retries, conn (sqlite3.Connection | None), is_connected (bool), last_error

**Database Discovery** (`find_database_path`, line 52):
- Base path: `~/Library/Group Containers/UBF8T346G9.Office/Outlook/`
- Tries profile versions 15-18 explicitly
- Falls back to recursive glob for `**/Outlook.sqlite`
- Then tries alternative names: `outlook.sqlite`, `Outlook.db`, `outlook.db`
- Raises `DatabaseNotFoundError` with searched paths list

**Connection** (`connect`, line 122):
- Read-only mode via URI: `file:{path}?mode=ro`
- Sets `row_factory = sqlite3.Row` for dict-like access
- Tests connection with `SELECT name FROM sqlite_master WHERE type='table' LIMIT 1`
- Exponential backoff on lock: 1s, 2s, 4s (2^attempt)
- Raises DatabaseLockError after max_retries exhausted

**Query Execution** (`execute_query`, line 203):
- Takes query string + optional params tuple
- Returns `list[sqlite3.Row]`
- Logs truncated query for debugging

**Utility Methods:**
- `get_table_info(table_name)` -- PRAGMA table_info
- `get_table_names()` -- SELECT from sqlite_master
- `get_row_count(table_name, where_clause="")` -- COUNT with optional WHERE

**Context Manager** (lines 294-301):
- `__enter__`: calls connect(), returns self
- `__exit__`: calls disconnect()
- `__del__`: cleanup guard

**Factory Function** (`get_database`, line 313):
- Module-level singleton pattern via `_db_instance` global
- Creates new instance if None or db_path changed
- NOTE: This is a simple singleton, not thread-safe

### SQL Column Names Used in client.py Queries
The actual Outlook DB column names (from client.py line 122+):
- `Record_RecordID` as message_id
- `Message_NormalizedSubject` as subject
- `Message_SenderAddressList` as sender
- `Message_SenderList` as sender_name
- `Message_ToRecipientAddressList` as recipients
- `Message_CCRecipientAddressList` as cc_recipients
- `Message_TimeReceived` as timestamp
- `Message_TimeSent`
- `Message_Preview` as preview (current content source -- ~256 chars only)
- `Message_ReadFlag` as is_read
- `Message_HasAttachment` as has_attachments
- `Record_Categories` as categories
- `Conversation_ConversationID` as conversation_id

---

## 6. Content Parser

### ContentParser class (content.py)

**Factory**: `get_content_parser()` -- module-level singleton pattern (same as database)

**Main method**: `parse_email_content(raw_content: str) -> dict[str, str]`
- Returns `{"html": ..., "text": ..., "markdown": ...}`
- Pipeline: extract HTML from XML wrapper -> clean HTML -> convert to text + markdown
- Fallback: returns raw content with tags stripped on any exception

**Internal methods:**
- `_extract_html_from_xml(content)` -- Handles Outlook's XML-wrapped HTML
- `_clean_html(html_content)` -- BeautifulSoup cleaning, removes scripts/styles
- `_html_to_text(html)` -- BeautifulSoup get_text() with whitespace normalization
- `_html_to_markdown(html)` -- Uses `markdownify` library
- `_clean_whitespace(text)` -- Collapses multiple spaces/newlines
- `_strip_html_tags(content)` -- Regex fallback for tag removal

**Utility methods:**
- `extract_links(html_content)` -> list[dict] with url, text, type
- `extract_images(html_content)` -> list[dict] with src, alt

**Dependencies**: beautifulsoup4, markdownify

---

## 7. CLI Structure

### Click Group (cli/main.py)

**Entry point**: `cli` group with `--db-path`, `--format` (json/csv/table, default json), `--verbose` options

**Commands:**
1. **`info`** -- Database information (tables, row counts, table schema)
2. **`emails`** -- Email retrieval with `--start-date`, `--end-date`, `--folder`, `--limit`, `--include-content/--no-content`
3. **`calendars`** -- Calendar listing and event retrieval with `--start-date`, `--end-date`, `--calendar-id`, `--limit`, `--use-ics` flag
4. **`search`** -- Email search with `--query`, `--sender`, `--subject`, `--folder`, `--limit`

**Output formatting**: `format_output()` function handles json (via json.dumps), csv (via csv.DictWriter), and table (via get_summary() or dict key-value pairs)

**Logging**: Configures structlog with JSON renderer at module level

---

## 8. GitHub Actions Workflows

**None exist.** The `.github/` directory does not exist at all. The brainstorm doc (decision #9) specifies the planned approach:
- CI: Auto-run tests, ruff, mypy on every PR
- Publish: Manual `workflow_dispatch` with version input
- Auth: PyPI Trusted Publishers (OIDC)

---

## 9. Public API (__init__.py Exports)

**File**: `/Users/taylaand/code/personal/tools/pyoutlook-db/src/pyoutlook_db/__init__.py`

```python
__version__ = "0.1.0"
__author__ = "Amazon Q Developer"
__email__ = "noreply@amazon.com"

__all__ = [
    "OutlookClient",
    "EmailMessage",
    "CalendarEvent",
    "Calendar",
    "OutlookDBError",
    "DatabaseNotFoundError",
    "DatabaseLockError",
    "ConnectionError",
    "ParseError",
]
```

**Not exported but exist**: EmailSearchFilter, EmailStats, EmailPriority, EventStatus, ResponseStatus, RecurrenceType, ContentParser, ICalendarParser, OutlookDatabase

---

## 10. CLAUDE.md Conventions

Key conventions established in the project CLAUDE.md:
- Layered architecture: Client -> Database/Models/Parsers
- Context managers for database connections
- Factory pattern for shared instances (get_database, get_content_parser)
- Auto-discovery for macOS-specific paths
- Google-style docstrings (enforced via ruff)
- Type hints required (mypy strict mode)
- 80% minimum test coverage
- `uv` for all package management
- Pre-commit hooks: trailing-whitespace, ruff, ruff-format, mypy (strict), bandit, pytest

---

## 11. Key Observations for the Refactor

### Things That Must Change
1. **Package name**: `pyoutlook-db` -> `macoutlook` in pyproject.toml, `src/pyoutlook_db/` -> `src/macoutlook/`
2. **Entry point**: `pyoutlook-db = "pyoutlook_db.cli.main:cli"` -> `macoutlook = "macoutlook.cli.main:cli"`
3. **All imports**: Every file uses `from pyoutlook_db.` or `from ..` (relative imports are fine)
4. **Test imports**: `from pyoutlook_db.core.client import OutlookClient` etc.
5. **Hatch version path**: `src/pyoutlook_db/__init__.py` -> `src/macoutlook/__init__.py`
6. **Hatch build packages**: `["src/pyoutlook_db"]` -> `["src/macoutlook"]`
7. **Author metadata**: Update from Amazon Q Developer
8. **Project URLs**: Update GitHub repository references

### Things That Should Change (Technical Debt)
1. **Pydantic v1 patterns**: All models use deprecated `@validator`, `Config` class, `.dict()`, `.json()` -- should migrate to v2 patterns (`@field_validator`, `model_config`, `.model_dump()`)
2. **Global singleton factories**: `get_database()` and `get_content_parser()` use module-level globals -- not thread-safe, hard to test
3. **No conftest.py**: Tests would benefit from shared fixtures
4. **Missing integration test directory**: Referenced in CLAUDE.md but does not exist
5. **No pytest markers used**: Markers defined but no tests tagged with them
6. **Client has SQL embedded**: SQL queries are inline in client.py rather than in the database layer

### New Components Needed (from brainstorm)
1. **MessageSourceReader** (core/message_source.py): .olk15MsgSource file discovery, MIME parsing, lazy index building
2. **FuzzyMatcher** (core/fuzzy.py or matching/fuzzy.py): Word-boundary-aware matching for search
3. **AttachmentInfo model**: New Pydantic model for attachment metadata
4. **Redesigned EmailMessage**: New fields (body_text, body_html, body_markdown, preview, content_source, attachments as list[AttachmentInfo])
5. **GitHub Actions**: `.github/workflows/ci.yml` and `.github/workflows/publish.yml`

### Patterns to Preserve
- Layered architecture (core/models/parsers/cli)
- Context manager support on database
- structlog for all logging
- Click for CLI
- Pydantic for all data models (but upgrade to v2 patterns)
- Read-only database access
- Auto-discovery of macOS paths
- Google-style docstrings
- The existing ContentParser pipeline (HTML -> text/markdown) will be reused for .olk15MsgSource HTML content
