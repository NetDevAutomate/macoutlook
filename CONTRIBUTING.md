# Contributing to macoutlook

Thank you for your interest in contributing to macoutlook! This document provides guidelines and information for contributors.

## How to Contribute

### Reporting Issues

Before creating an issue, please:

1. **Search existing issues** to avoid duplicates
2. **Use the latest version** to ensure the issue hasn't been fixed
3. **Provide detailed information** including:
   - Your operating system (macOS version)
   - Python version
   - Outlook version
   - Complete error messages and stack traces
   - Steps to reproduce the issue

### Suggesting Enhancements

Enhancement suggestions are welcome! Please:

1. **Check existing issues** and discussions first
2. **Provide a clear use case** explaining why the enhancement would be valuable
3. **Consider the scope** - focus on features that benefit most users
4. **Include implementation ideas** if you have them

### Pull Requests

We love pull requests! Here's how to contribute code:

#### 1. Fork and Clone

```bash
# Fork the repository on GitHub, then:
git clone https://github.com/your-username/macoutlook.git
cd macoutlook
```

#### 2. Set Up Development Environment

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync --dev

# Install pre-commit hooks
uv run pre-commit install
```

#### 3. Create a Feature Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/issue-description
```

#### 4. Make Your Changes

- Follow the [coding standards](#coding-standards) below
- Add tests for new functionality
- Update documentation as needed
- Ensure all tests pass

#### 5. Test Your Changes

```bash
# Run all tests
uv run pytest tests/unit/ -v

# Run with coverage
uv run pytest --cov=src/macoutlook

# Check code quality
uv run ruff check .
uv run ruff format .
uv run mypy src/
```

#### 6. Commit Your Changes

```bash
# Stage your changes
git add .

# Commit with a descriptive message
git commit -m "feat: brief description of what you added"

# Or for bug fixes:
git commit -m "fix: brief description of what you fixed"
```

#### 7. Push and Create Pull Request

```bash
git push origin feature/your-feature-name
```

Then create a pull request on GitHub with:
- **Clear title** describing the change
- **Detailed description** explaining what and why
- **Reference to issues** if applicable (e.g., "Fixes #123")
- **Screenshots or examples** if UI/output changes

## Coding Standards

### Python Code Style

We follow PEP 8 with these specific requirements:

- **Line length**: 88 characters maximum
- **Python version**: 3.12+ target
- **Type hints**: Required for all function signatures
- **Docstrings**: Google format for all public functions/classes
- **Imports**: Organized in three groups (standard library, third-party, local)
- **Logging**: stdlib `logging` throughout (NOT structlog)
- **Paths**: `pathlib.Path` exclusively (no `os.path`)

### Code Quality Tools

All code must pass these checks:

```bash
# Formatting
uv run ruff format .

# Linting
uv run ruff check .

# Type checking
uv run mypy src/

# Or run everything via pre-commit
uv run pre-commit run --all-files
```

### Testing

- **Test coverage**: Maintain minimum 80% coverage
- **Test types**: Write unit tests for all new functions
- **Test naming**: Use descriptive names explaining the scenario
- **Fixtures**: Use pytest fixtures for common test setup
- **Mocking**: Mock `OutlookDatabase` via DI (no singletons to patch)

Example test structure:
```python
def test_should_return_emails_when_valid_date_range_provided():
    # Arrange
    client = OutlookClient()
    start_date = datetime(2024, 1, 1)
    end_date = datetime(2024, 1, 31)

    # Act
    emails = client.get_emails_by_date_range(start_date, end_date)

    # Assert
    assert isinstance(emails, list)
    assert len(emails) >= 0
```

## Project Structure

```
macoutlook/
├── src/macoutlook/                # Main package
│   ├── core/                      # Core functionality
│   │   ├── client.py              # Main OutlookClient class
│   │   ├── database.py            # Database connection handling
│   │   ├── enricher.py            # Email content enrichment
│   │   └── message_source.py      # .olk15MsgSource file reader
│   ├── models/                    # Pydantic v2 data models
│   │   ├── email_message.py       # EmailMessage, AttachmentInfo
│   │   ├── calendar.py            # CalendarEvent, Calendar
│   │   └── enums.py               # ContentSource, FlagStatus, Priority
│   ├── parsers/                   # Content parsing
│   │   ├── content.py             # HTML → text/markdown
│   │   └── icalendar.py           # .ics file parsing
│   ├── cli/                       # Command line interface
│   │   └── main.py                # Click-based CLI commands
│   └── exceptions.py              # OutlookDBError hierarchy
├── tests/                         # Test suite
│   └── unit/                      # Unit tests
├── scripts/                       # Utility scripts
└── docs/                          # Documentation
```

## Development Tips

### Local Testing

```bash
# Test with your local Outlook database
uv run macoutlook info
uv run macoutlook emails --limit 5
uv run macoutlook search --query "meeting"
```

### Common Issues

1. **Database not found**: Ensure Outlook for Mac is installed and has data
2. **Permission errors**: Close Outlook while testing
3. **Import errors**: Check that you're using the development installation
4. **Test failures**: Ensure you have test data or mock appropriately

### Debugging

```python
import logging

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger("macoutlook")
logger.setLevel(logging.DEBUG)
```

## Commit Message Guidelines

Use [Conventional Commits](https://www.conventionalcommits.org/) format:

```
type: brief description

Longer explanation if needed, explaining what and why,
not how (the code explains how).

- Bullet points are okay
- Reference issues: Fixes #123, Closes #456
```

### Types
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks
- `ci`: CI/CD changes

## Release Process

For maintainers preparing releases:

1. **Update version** in `src/macoutlook/__init__.py`
2. **Update CHANGELOG.md** with new version
3. **Run full test suite** and ensure all passes
4. **Trigger publish workflow** from GitHub Actions (workflow_dispatch)

## Getting Help

If you need help:

1. **Check existing issues** and discussions
2. **Read the documentation** thoroughly
3. **Ask questions** in GitHub discussions

## License

By contributing to macoutlook, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to macoutlook!
