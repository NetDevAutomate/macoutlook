# Python Library Best Practices Research (2024-2026)

Researched: 2026-03-14
Sources: Python 3.14 stdlib docs, Pydantic official docs, uv official docs (astral.sh), PyPI official docs, Context7

---

## 1. Python stdlib `email` Module: MIME/RFC 2822 Parsing

### Critical: Always Use the Modern Policy API

The biggest pitfall is using the legacy API. The default `email.message_from_string()` and
`email.message_from_bytes()` use `policy=compat32`, which returns the legacy `Message` class
with known bugs preserved for backward compatibility.

**Must do:**

- **Always pass `policy=email.policy.default`** (or `email.policy.SMTP` / `email.policy.SMTPUTF8`
  for sending). The Python docs explicitly warn: "The policy keyword should always be specified;
  The default will change to `email.policy.default` in a future version of Python."
- Use `email.message.EmailMessage` (modern) instead of `email.message.Message` (legacy).
  The legacy `Message` docs say: "If you are going to use another policy [other than compat32],
  you should be using the `EmailMessage` class instead."
- Use `BytesParser` for raw email bytes (most common case), `Parser` only for already-decoded
  strings.

**Parsing pattern:**

```python
from email import policy
from email.parser import BytesParser

parser = BytesParser(policy=policy.default)
msg = parser.parsebytes(raw_bytes)
# Returns EmailMessage, not legacy Message
```

**Multipart handling with modern API:**

```python
# Modern API provides high-level methods on EmailMessage:
body = msg.get_body(preferencelist=('plain', 'html'))  # auto-finds best body
text = body.get_content()  # auto-decodes charset

# Iterate MIME parts:
for part in msg.iter_parts():       # direct children only
    print(part.get_content_type())

for part in msg.walk():              # recursive traversal
    if part.get_content_maintype() == 'multipart':
        continue
    # process leaf parts
```

**Encoding detection:**

- `EmailMessage.get_content()` handles charset decoding automatically with the modern policy.
- For `compat32`, you must manually call `get_payload(decode=True)` and decode bytes yourself.
- The modern policy uses `utf-8` as the default charset with surrogateescape error handling
  for undecodable bytes.

**Common pitfalls:**

1. **Not passing `policy=`** -- silently gets legacy behavior with different header handling.
2. **Using `get_payload()` instead of `get_content()`** -- `get_payload()` is the legacy API.
   `get_content()` on `EmailMessage` auto-decodes and returns the right type.
3. **Assuming single-part** -- always check `is_multipart()` or use `get_body()` which
   handles both cases.
4. **Header access** -- modern policy returns structured `Address` objects:
   `msg['from'].addresses[0].addr_spec` vs legacy string splitting.

**Source:** Python 3.14 docs: email.parser, email.policy, email.message

---

## 2. PyPI Trusted Publishers (OIDC)

### Setup Guide (GitHub Actions to PyPI)

Trusted Publishing eliminates long-lived API tokens entirely. Uses OIDC to mint 15-minute
short-lived tokens.

**Step 1: Configure on PyPI**

1. Go to https://pypi.org/manage/projects/ -> "Manage" -> "Publishing"
2. Add GitHub Actions publisher with:
   - **Owner**: your GitHub username/org
   - **Repository**: the repo name
   - **Workflow filename**: e.g., `publish.yml` (just the filename, not full path)
   - **Environment** (optional but **strongly recommended**): e.g., `pypi`

For new packages that do not exist on PyPI yet, you can use "pending publishers" to register
the publisher *before* the first upload at https://pypi.org/manage/account/publishing/.

**Step 2: GitHub Actions Workflow**

```yaml
name: Publish to PyPI
on:
  release:
    types: [published]

jobs:
  publish:
    runs-on: ubuntu-latest
    environment: pypi                    # Must match PyPI config
    permissions:
      id-token: write                    # MANDATORY for OIDC
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v7
      - run: uv build
      - uses: pypa/gh-action-pypi-publish@release/v1
        # No username/password/token needed
```

**Gotchas:**

1. **`id-token: write` is mandatory** -- set at **job level** (not workflow level) to minimize
   credential exposure. Without it, the action silently fails to authenticate.
2. **Environment name must match exactly** between GitHub and PyPI configuration.
3. **`pypa/gh-action-pypi-publish@release/v1`** is the standard action. Pin to `release/v1`
   (not a specific SHA) for automatic security patches.
4. For TestPyPI, add `repository-url: https://test.pypi.org/legacy/` and configure a
   separate trusted publisher on TestPyPI.
5. **uv publish alternative**: `uv publish` also supports trusted publishing natively --
   it can mint OIDC tokens. But `pypa/gh-action-pypi-publish` is more widely documented.

**Source:** https://docs.pypi.org/trusted-publishers/, PyPI official docs

---

## 3. Pydantic v2 Patterns

### Model Configuration (v2 Style)

```python
from pydantic import BaseModel, ConfigDict

class MyModel(BaseModel):
    model_config = ConfigDict(
        frozen=True,              # Immutable instances (replaces allow_mutation=False)
        strict=False,             # Whether to enable strict mode (no coercion)
        from_attributes=True,     # Enable ORM mode (replaces orm_mode=True)
        populate_by_name=True,    # Allow population by field name AND alias
        str_strip_whitespace=True,
        str_to_lower=False,
        use_enum_values=True,     # Use enum .value instead of enum instance
    )
```

**Key v1 -> v2 migration changes:**

| v1 Pattern | v2 Pattern |
|---|---|
| `class Config:` inner class | `model_config = ConfigDict(...)` |
| `@validator('field')` | `@field_validator('field')` |
| `@root_validator` | `@model_validator(mode='before'\|'after')` |
| `.dict()` | `.model_dump()` |
| `.json()` | `.model_dump_json()` |
| `Optional[X]` | `X \| None` (PEP 604) |
| `orm_mode = True` | `from_attributes = True` |
| `allow_mutation = False` | `frozen = True` |
| `schema_extra` | `json_schema_extra` |

### Frozen Models

- Set `frozen=True` in `ConfigDict` for immutable data objects.
- Attempting to set attributes raises `ValidationError`.
- **Caveat**: Python does not enforce deep immutability -- mutable nested objects (dicts, lists)
  inside a frozen model can still be mutated. For true immutability, use frozen models with
  `tuple` instead of `list` and `frozenset` instead of `set`.

### Field Validators

```python
from pydantic import BaseModel, field_validator, ValidationInfo

class Email(BaseModel):
    subject: str

    @field_validator('subject')
    @classmethod
    def clean_subject(cls, v: str, info: ValidationInfo) -> str:
        # info.config, info.field_name available
        return v.strip()
```

- `@field_validator` replaces `@validator`. Must be a `@classmethod`.
- Access config via `info.config`, field metadata via `cls.model_fields[info.field_name]`.
- `mode='before'` runs before Pydantic's own validation; default `mode='after'` runs after.

### Model Validators

```python
from pydantic import BaseModel, model_validator
from typing import Self

class DateRange(BaseModel):
    start: datetime
    end: datetime

    @model_validator(mode='after')
    def check_dates(self) -> Self:
        if self.end <= self.start:
            raise ValueError('end must be after start')
        return self
```

### Serialization

```python
model.model_dump()                          # -> dict
model.model_dump(exclude_none=True)         # skip None fields
model.model_dump(include={'subject', 'sender'})  # whitelist
model.model_dump_json(indent=2)             # -> JSON string
model.model_dump(mode='json')               # dict with JSON-compatible types
```

- Use `model_dump(mode='json')` when you need JSON-safe types (datetimes as ISO strings)
  but want a dict, not a JSON string.

**Source:** https://docs.pydantic.dev/latest/migration/, Pydantic official docs

---

## 4. Python Library Packaging with uv

### Recommended pyproject.toml Structure

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "your-package"
dynamic = ["version"]                    # Or set version = "0.1.0" statically
description = "One-line description"
readme = "README.md"
requires-python = ">=3.10"
license = {text = "MIT"}
authors = [{name = "You", email = "you@example.com"}]
keywords = ["relevant", "keywords"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Programming Language :: Python :: 3",
]
dependencies = [
    "pydantic>=2.0",
    "click>=8.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "ruff>=0.4",
    "mypy>=1.10",
]

[project.urls]
Homepage = "https://github.com/you/pkg"
Repository = "https://github.com/you/pkg"
Issues = "https://github.com/you/pkg/issues"

[project.scripts]
your-cli = "your_package.cli:main"

[tool.hatch.version]
path = "src/your_package/__init__.py"

[tool.hatch.build.targets.wheel]
packages = ["src/your_package"]
```

### Build System Choice

- **hatchling** (recommended): Modern, fast, good `src/` layout support, native dynamic
  versioning from `__init__.py`. This is what uv scaffolds by default with `uv init --lib`.
- **setuptools**: Legacy but functional. Use only if you have existing setuptools config.
- **flit-core**: Minimal alternative, good for pure-Python packages.

### Version Management

Two approaches:

1. **Dynamic versioning (recommended with hatchling)**:
   - Set `dynamic = ["version"]` in `[project]`
   - Configure `[tool.hatch.version] path = "src/pkg/__init__.py"`
   - Define `__version__ = "0.1.0"` in `__init__.py`
   - Use `uv version --bump minor` to update

2. **Static versioning**:
   - Set `version = "0.1.0"` directly in `[project]`
   - Update manually or with `uv version` command

### Build and Publish

```bash
uv build                          # Creates dist/*.whl and dist/*.tar.gz
uv build --no-sources             # Verify it builds without tool.uv.sources
uv publish                        # Upload to PyPI (supports OIDC)
uv publish --index testpypi       # Upload to TestPyPI
```

**Best practice**: Always run `uv build --no-sources` before publishing to catch
dependency resolution issues that `tool.uv.sources` masks during development.

### Preventing Accidental Publish

For private/internal packages:
```toml
classifiers = ["Private :: Do Not Upload"]  # PyPI rejects uploads with this
```

**Source:** https://docs.astral.sh/uv/guides/package/, uv official docs

---

## 5. GitHub Actions CI for Python Libraries

### Optimal Workflow Template

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true
      - run: uv sync --locked --dev
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run mypy src/

  test:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12", "3.13"]
        os: [ubuntu-latest, macos-latest]
      fail-fast: false
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v7
        with:
          python-version: ${{ matrix.python-version }}
          enable-cache: true
      - run: uv sync --locked --dev
      - run: uv run pytest tests/ -v --tb=short

  publish:
    needs: [lint, test]
    if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v7
      - run: uv build
      - uses: pypa/gh-action-pypi-publish@release/v1
```

### Key Practices

1. **Pin uv version** in CI: `with: version: "0.10.9"` for reproducibility. Or omit for
   latest (convenient but less reproducible).

2. **Use `--locked`**: `uv sync --locked` ensures the lockfile is up-to-date and fails if
   it is stale. This catches lockfile drift.

3. **Enable built-in caching**: `enable-cache: true` in `setup-uv` action. This caches the
   uv package cache (not the venv) using `uv.lock` as the cache key.

4. **Manual cache management** (advanced): If you need tighter control, use `actions/cache`
   with `UV_CACHE_DIR` and run `uv cache prune --ci` as the last step.

5. **Matrix testing**: Test across Python versions and OS. Use `fail-fast: false` so one
   failing combination does not cancel others.

6. **Separate lint and test jobs**: Lint runs once (fast), tests run in matrix (thorough).
   Publish depends on both passing.

7. **Current action versions** (as of 2026):
   - `actions/checkout@v6`
   - `astral-sh/setup-uv@v7`
   - `actions/setup-python@v6` (if needed instead of uv's Python management)
   - `pypa/gh-action-pypi-publish@release/v1`

8. **For macOS-only libraries** (like pyoutlook-db): Use `runs-on: macos-latest` for
   integration tests, but `ubuntu-latest` for lint/type-check (faster, cheaper).

**Source:** https://docs.astral.sh/uv/guides/integration/github/, uv official docs

---

## Cross-Cutting Recommendations for pyoutlook-db

Based on this research, specific to this project:

1. **Email parsing**: When parsing `.olk15MsgSource` MIME content, always use
   `BytesParser(policy=policy.default)` to get `EmailMessage` objects with proper charset
   handling and structured header access.

2. **Pydantic models**: Your existing `ConfigDict(frozen=True)` pattern is correct. Complete
   the v1->v2 migration checklist: `@validator` -> `@field_validator`, `.dict()` ->
   `.model_dump()`, `class Config` -> `model_config`.

3. **Packaging**: Your `pyproject.toml` is already well-structured with hatchling. Add
   `uv build --no-sources` to CI to validate packaging.

4. **CI**: Update action versions to v6/v7 generation. Add `enable-cache: true`. Use
   `--locked` flag.

5. **Publishing**: Set up Trusted Publishers on PyPI before first release -- zero secrets
   management.
