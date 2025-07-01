# PyOutlook-DB

[![Python Version](https://img.shields.io/badge/Python-3.12%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

A high-performance Python library for accessing Microsoft Outlook's SQLite database on macOS. Extract emails, calendar events, and contacts directly from Outlook's local database with full-text search, content parsing, and multiple export formats.

## 🚀 Features

- **📧 Email Access**: Retrieve 70,000+ emails with full metadata and content
- **📅 Calendar Integration**: Access both historical SQLite events and modern .ics files
- **🔍 Advanced Search**: Full-text search across subjects, content, and metadata
- **📊 Rich Content Parsing**: HTML to Markdown conversion with link/image extraction
- **⚡ High Performance**: Direct database access without API rate limits or timeouts
- **🎯 Multiple Formats**: Export to JSON, CSV, or structured Python objects
- **🛠️ CLI Interface**: Command-line tools for quick data access and analysis
- **📈 Analytics Ready**: Built-in statistics and aggregation capabilities

## 📋 Requirements

- **macOS**: Required (Windows/Linux not supported)
- **Python**: 3.12 or higher
- **Microsoft Outlook for Mac**: Must be installed with local data
- **Database Access**: Outlook should be closed or library uses read-only mode

## 🔧 Installation

### Using uv (Recommended)

```bash
uv add pyoutlook-db
```

### Using pip

```bash
pip install pyoutlook-db
```

### Development Installation

```bash
git clone https://github.com/your-username/pyoutlook-db.git
cd pyoutlook-db
uv sync --dev
```

## 🎯 Quick Start

### Command Line Interface

```bash
# Get database information
pyoutlook-db info

# List recent emails
pyoutlook-db emails --start-date 2024-01-01 --limit 10

# Search for specific emails
pyoutlook-db search --query "AWS" --type email --limit 5

# Export emails to JSON
pyoutlook-db emails --format json --start-date 2024-06-01 > emails.json

# List available calendars
pyoutlook-db calendars --format table

# Get calendar events
pyoutlook-db events --start-date 2024-01-01 --end-date 2024-12-31
```

### Python API

```python
from pyoutlook_db import OutlookClient
from datetime import datetime, timedelta

# Initialize client
client = OutlookClient()

# Get recent emails
recent_emails = client.get_emails_by_date_range(
    start_date=datetime.now() - timedelta(days=7),
    end_date=datetime.now(),
    limit=10
)

print(f"Found {len(recent_emails)} recent emails:")
for email in recent_emails:
    print(f"- {email.subject} (from: {email.sender_name})")
    print(f"  📅 {email.timestamp.strftime('%Y-%m-%d %H:%M')}")
    print(f"  📄 {len(email.content_text)} characters")
    print()

# Search emails
from pyoutlook_db.models.email import EmailSearchFilter

search_filter = EmailSearchFilter(
    query="AWS",
    start_date=datetime(2024, 1, 1),
    limit=5
)

aws_emails = client.search_emails(search_filter)
print(f"Found {len(aws_emails)} AWS-related emails")

# Get calendar events
events = client.get_calendar_events(
    start_date=datetime(2024, 1, 1),
    end_date=datetime(2024, 12, 31),
    limit=20
)

print(f"Found {len(events)} calendar events:")
for event in events:
    print(f"- {event.title}")
    print(f"  📅 {event.start_time.strftime('%Y-%m-%d %H:%M')}")
    if event.location:
        print(f"  📍 {event.location}")
    print()
```

## 📚 Comprehensive Examples

### Email Analytics

```python
from pyoutlook_db import OutlookClient
from collections import Counter
from datetime import datetime, timedelta

client = OutlookClient()

# Get last month's emails
start_date = datetime.now() - timedelta(days=30)
emails = client.get_emails_by_date_range(
    start_date=start_date,
    end_date=datetime.now(),
    limit=1000
)

# Analyze senders
senders = Counter(email.sender_name or email.sender for email in emails)
print("Top 10 senders:")
for sender, count in senders.most_common(10):
    print(f"  {sender}: {count} emails")

# Read/unread statistics
read_count = sum(1 for email in emails if email.is_read)
print(f"Read emails: {read_count}/{len(emails)} ({read_count/len(emails)*100:.1f}%)")
```

### Calendar Event Analysis

```python
from pyoutlook_db import OutlookClient
from datetime import datetime

# Access both historical and modern calendar data
client = OutlookClient()

# Historical events (SQLite database)
historical_events = client.get_calendar_events(
    start_date=datetime(2007, 1, 1),
    end_date=datetime(2008, 12, 31),
    limit=100
)

# Modern events (.ics files)
modern_client = OutlookClient(use_ics=True)
modern_events = modern_client.get_calendar_events(
    start_date=datetime(2024, 1, 1),
    end_date=datetime(2025, 12, 31)
)

print(f"Historical events: {len(historical_events)}")
print(f"Modern events: {len(modern_events)}")
```

### Data Export

```python
import json
from pyoutlook_db import OutlookClient
from datetime import datetime

client = OutlookClient()

# Export recent emails to JSON
emails = client.get_emails_by_date_range(
    start_date=datetime(2024, 6, 1),
    end_date=datetime(2024, 7, 1),
    include_content=True
)

# Convert to JSON-serializable format
emails_data = []
for email in emails:
    emails_data.append({
        'id': email.message_id,
        'subject': email.subject,
        'sender': email.sender,
        'timestamp': email.timestamp.isoformat(),
        'content_text': email.content_text,
        'recipients': email.recipients,
        'size': email.message_size
    })

# Save to file
with open('emails_export.json', 'w') as f:
    json.dump(emails_data, f, indent=2)

print(f"Exported {len(emails_data)} emails to emails_export.json")
```

## 📖 API Reference

### OutlookClient

The main client class for accessing Outlook data.

#### Constructor

```python
OutlookClient(
    db_path: str | None = None,
    auto_connect: bool = True,
    use_ics: bool = False
)
```

**Parameters:**
- `db_path`: Optional path to Outlook database file
- `auto_connect`: Whether to automatically connect to database
- `use_ics`: Whether to use .ics files for calendar data (modern events)

#### Methods

##### get_emails_by_date_range()

```python
get_emails_by_date_range(
    start_date: datetime,
    end_date: datetime,
    folders: list[str] | None = None,
    include_content: bool = True,
    limit: int = 1000
) -> list[EmailMessage]
```

Retrieve emails within a specific date range.

##### search_emails()

```python
search_emails(search_filter: EmailSearchFilter) -> list[EmailMessage]
```

Search emails using advanced filters.

##### get_calendar_events()

```python
get_calendar_events(
    calendar_id: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int = 1000
) -> list[CalendarEvent]
```

Get calendar events with optional filtering.

## 🧪 Testing

Run the test suite:

```bash
# Install development dependencies
uv sync --dev

# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src/pyoutlook_db

# Run specific test types
uv run pytest tests/unit/
uv run pytest tests/integration/
```

## 📝 Development

### Code Quality

```bash
# Format code
uv run ruff format .

# Lint code
uv run ruff check .

# Type checking
uv run mypy src/

# Security scan
uv run bandit -r src/
```

### Pre-commit Hooks

```bash
uv run pre-commit install
uv run pre-commit run --all-files
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass and code quality checks pass
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚠️ Disclaimer

This library accesses Microsoft Outlook's local SQLite database files. It is designed for personal use and data analysis. Always ensure you have backups of your data before using any database access tools.

## 🙏 Acknowledgments

- Microsoft Outlook team for the robust SQLite database structure
- The Python community for excellent libraries like Pydantic, Click, and BeautifulSoup
- Contributors and testers who helped improve this library

---

**Made with ❤️ for the Python and macOS communities**
