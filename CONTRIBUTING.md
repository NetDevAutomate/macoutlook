# Contributing to PyOutlook-DB

Thank you for your interest in contributing to PyOutlook-DB! This document provides guidelines and information for contributors.

## 🤝 How to Contribute

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
git clone https://github.com/your-username/pyoutlook-db.git
cd pyoutlook-db
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
uv run pytest

# Run with coverage
uv run pytest --cov=src/pyoutlook_db

# Run specific test types
uv run pytest tests/unit/
uv run pytest tests/integration/

# Check code quality
uv run ruff check .
uv run ruff format .
uv run mypy src/
uv run bandit -r src/
```

#### 6. Commit Your Changes

```bash
# Stage your changes
git add .

# Commit with a descriptive message
git commit -m "Add feature: brief description of what you added"

# Or for bug fixes:
git commit -m "Fix: brief description of what you fixed"
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

## 📋 Coding Standards

### Python Code Style

We follow PEP 8 with these specific requirements:

- **Line length**: 88 characters maximum
- **Python version**: 3.12+ target
- **Type hints**: Required for all function signatures
- **Docstrings**: Google format for all public functions/classes
- **Imports**: Organized in three groups (standard library, third-party, local)

### Code Quality Tools

All code must pass these checks:

```bash
# Formatting
uv run ruff format .

# Linting
uv run ruff check .

# Type checking
uv run mypy src/

# Security scanning
uv run bandit -r src/
```

### Documentation

- **Docstrings**: Use Google format for all public APIs
- **Type hints**: Include comprehensive type annotations
- **Comments**: Explain complex logic, not obvious code
- **README updates**: Update examples if you change public APIs

### Testing

- **Test coverage**: Maintain minimum 80% coverage
- **Test types**: Write unit tests for all new functions
- **Test naming**: Use descriptive names explaining the scenario
- **Fixtures**: Use pytest fixtures for common test setup

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

## 🏗️ Project Structure

Understanding the codebase structure:

```
pyoutlook-db/
├── src/pyoutlook_db/           # Main package
│   ├── core/                   # Core functionality
│   │   ├── client.py          # Main OutlookClient class
│   │   ├── database.py        # Database connection handling
│   │   └── exceptions.py      # Custom exceptions
│   ├── models/                 # Data models
│   │   ├── email.py           # Email message models
│   │   └── calendar.py        # Calendar event models
│   ├── parsers/                # Content parsing
│   │   ├── content.py         # HTML/text parsing
│   │   └── icalendar.py       # .ics file parsing
│   └── cli/                    # Command line interface
│       └── main.py            # CLI commands
├── tests/                      # Test suite
│   ├── unit/                  # Unit tests
│   ├── integration/           # Integration tests
│   └── fixtures/              # Test data
└── docs/                      # Documentation
```

## 🐛 Development Tips

### Local Testing

```bash
# Test with your local Outlook database
uv run python -c "
from pyoutlook_db import OutlookClient
client = OutlookClient()
print(f'Connected to database with {len(client.get_emails_by_date_range(...))} emails')
"

# Test CLI commands
uv run pyoutlook-db info
uv run pyoutlook-db emails --limit 5
```

### Common Issues

1. **Database not found**: Ensure Outlook for Mac is installed and has data
2. **Permission errors**: Close Outlook while testing
3. **Import errors**: Check that you're using the development installation
4. **Test failures**: Ensure you have test data or mock appropriately

### Debugging

```python
import structlog
import logging

# Enable debug logging
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG)
)

# Use the logger in your code
logger = structlog.get_logger(__name__)
logger.debug("Debug information", extra_data="value")
```

## 📝 Commit Message Guidelines

Use clear, descriptive commit messages:

### Format
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

### Examples
```
feat: add support for calendar filtering by organizer

Add new search parameter to filter calendar events by organizer
email address, supporting both exact matches and partial matches.

Fixes #45
```

```
fix: handle null timestamp values in email parsing

Email parsing was failing when timestamp fields contained null
values. Added proper null checking and default values.

Closes #67
```

## 🚀 Release Process

For maintainers preparing releases:

1. **Update version** in `pyproject.toml`
2. **Update CHANGELOG.md** with new version
3. **Run full test suite** and ensure all passes
4. **Create GitHub release** with changelog notes
5. **Build and test package** locally before publishing

## 📞 Getting Help

If you need help:

1. **Check existing issues** and discussions
2. **Read the documentation** thoroughly
3. **Ask questions** in GitHub discussions
4. **Be patient and respectful** - this is maintained by volunteers

## 📄 License

By contributing to PyOutlook-DB, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to PyOutlook-DB! Your efforts help make this library better for everyone. 🎉
