# macoutlook

[![Python Version](https://img.shields.io/badge/Python-3.12%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Python library for extracting email and calendar data from Microsoft Outlook on macOS. Reads both the Outlook SQLite database and `.olk15MsgSource` files for full email content extraction with automatic HTML/XML parsing and Markdown conversion.

## Performance

| Metric | Database Only | With Message Sources |
|--------|--------------|---------------------|
| Content | Preview (~256 chars) | Full email body |
| Extraction ratio | 0.1% | 85%+ |
| Avg words/email | ~50 | 450+ |

## Requirements

- **macOS** (Windows/Linux not supported)
- **Python 3.12+**
- **Microsoft Outlook for Mac** installed with local data

## Installation

```bash
uv add macoutlook
```

```bash
pip install macoutlook
```

### Development

```bash
git clone https://github.com/taylaand/macoutlook.git
cd macoutlook
uv sync --dev
```

## Quick Start

### Python API

```python
from macoutlook import create_client

# Create client (auto-discovers Outlook database)
client = create_client()

# Get recent emails (metadata + preview, fast)
emails = client.get_emails(limit=10)
for email in emails:
    print(f"{email.subject} from {email.sender_name}")
    print(f"  Preview: {email.preview[:100]}")
    print(f"  Source: {email.content_source}")

# Enrich a single email with full content from .olk15MsgSource
enriched = client.enrich_email(emails[0])
print(f"Full body: {len(enriched.body_text or '')} chars")
print(f"Attachments: {len(enriched.attachments)}")

# Batch enrich (builds index on first call)
enriched_all = client.enrich_emails(emails)

# Search with fuzzy sender matching
results = client.search_emails(sender="Andy Taylor", fuzzy=True)
# Finds emails from "Andrew Taylor", "A. Taylor", etc.

# Calendar events
events = client.get_calendar_events(limit=20)
for event in events:
    print(f"{event.title} at {event.start_time}")
```

### CLI

```bash
# Database info
macoutlook info

# List recent emails
macoutlook emails --limit 10

# Search emails
macoutlook search --query "meeting" --sender "taylor" --fuzzy

# Calendar events
macoutlook events --start-date 2025-01-01

# Build message source index (one-time, ~10 min for large mailboxes)
macoutlook build-index
```

## Architecture

```
macoutlook/
├── core/
│   ├── client.py            # OutlookClient + create_client() factory
│   ├── database.py          # OutlookDatabase (SQLite, read-only)
│   ├── enricher.py          # EmailEnricher (never-raises pipeline)
│   └── message_source.py    # MessageSourceReader (.olk15MsgSource)
├── models/
│   ├── email_message.py     # EmailMessage, AttachmentInfo
│   ├── calendar.py          # CalendarEvent, Calendar
│   └── enums.py             # ContentSource, FlagStatus, Priority
├── parsers/
│   ├── content.py           # HTML -> text/markdown
│   └── icalendar.py         # .ics file parser
├── search.py                # FuzzyMatcher
├── cli/main.py              # Click CLI
└── exceptions.py            # Error hierarchy
```

### Key Design Patterns

- **Dependency Injection**: `OutlookClient` accepts components via constructor; `create_client()` for convenience
- **Lazy Enrichment**: `get_emails()` returns metadata fast; `enrich_email()` parses MIME on demand
- **Never-Raises Enrichment**: `EnrichmentResult` returns errors in the result, never raises exceptions
- **Persistent Index**: Message-ID to file path mapping cached at `~/.cache/macoutlook/`

### Content Sources

The library reads from two data sources:

1. **SQLite Database** (`Outlook.sqlite`): Email metadata, preview text (~256 chars), calendar events. Fast, always available.

2. **Message Source Files** (`.olk15MsgSource`): Full RFC 2822 MIME email content. Located in `~/Library/Group Containers/UBF8T346G9.Office/Outlook/.../Message Sources/`. Contains complete body text, HTML, and attachments. Requires building an index first (`build-index` command).

## API Reference

### create_client()

```python
from macoutlook import create_client

client = create_client(
    db_path=None,              # Auto-discovers Outlook database
    enable_enrichment=True,    # Set up .olk15MsgSource reader
)
```

### OutlookClient

```python
# Email retrieval
client.get_emails(start_date=None, end_date=None, limit=1000, enrich=False)
client.search_emails(query=None, sender=None, subject=None, fuzzy=False, limit=100)

# Enrichment (requires build_index first)
client.enrich_email(email, markdown=True)
client.enrich_emails(emails, markdown=True)
client.save_attachment(message_id, filename, dest_dir)

# Calendar
client.get_calendars()
client.get_calendar_events(calendar_id=None, start_date=None, end_date=None)

# Info
client.get_database_info()
```

### EmailMessage

```python
from macoutlook import EmailMessage, ContentSource

email.message_id        # RFC 2822 Message-ID
email.subject           # Email subject
email.sender            # Sender email address
email.sender_name       # Sender display name
email.recipients        # To recipients
email.cc_recipients     # CC recipients
email.timestamp         # Received time
email.preview           # Database preview (~256 chars)
email.body_text         # Full plain text (after enrichment)
email.body_html         # Full HTML (after enrichment)
email.body_markdown     # Markdown conversion (after enrichment)
email.attachments       # tuple[AttachmentInfo, ...]
email.content_source    # ContentSource.MESSAGE_SOURCE or PREVIEW_ONLY
email.is_read           # Read flag
email.priority          # Priority.LOW / NORMAL / HIGH
email.flag_status       # FlagStatus.NOT_FLAGGED / FLAGGED / COMPLETE
```

## Development

```bash
# Tests
uv run pytest tests/unit/ -v

# Lint
uv run ruff check .
uv run ruff format .

# Type check
uv run mypy src/

# Build
uv build
```

## Acknowledgements

- **Jon Hammant** -- Discovered the `.olk15MsgSource` extraction approach that enables full email content recovery (858x improvement over database preview). Also contributed fuzzing techniques and full-text search functionality that significantly improved library performance. See [CONTRIBUTORS.md](CONTRIBUTORS.md).

## License

MIT License. See [LICENSE](LICENSE) for details.
