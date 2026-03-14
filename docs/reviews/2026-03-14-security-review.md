# Security Review: macoutlook Full Content Extraction Plan

**Date**: 2026-03-14
**Reviewed by**: Application Security Audit (Claude Opus 4.6)
**Plan**: `docs/plans/2026-03-14-feat-macoutlook-full-content-extraction-plan.md`
**Sister project patterns**: `document_parsing/docs/mentoring/security-for-file-parsing.md`

---

## Executive Summary

The plan introduces significant new attack surface by moving from read-only SQLite queries to parsing untrusted MIME content from `.olk15MsgSource` files and writing attacker-controlled attachment data to disk. The existing codebase also has pre-existing SQL injection vulnerabilities that should be fixed during the redesign.

**Overall risk**: HIGH -- the new MIME parsing and file-write capabilities introduce multiple exploitable vectors if not mitigated. The existing codebase has MEDIUM risk from SQL injection via string interpolation.

### Severity Summary

| Severity | Count | Description |
|----------|-------|-------------|
| Critical | 2 | Path traversal in `save_attachment()`, SQL injection in existing code |
| High | 3 | MIME filename injection, HTML content (stored XSS), resource exhaustion |
| Medium | 3 | BeautifulSoup XXE-adjacent risks, error message information leakage, module name shadowing |
| Low | 2 | File permission scope, global singleton thread safety |

---

## Finding 1: SQL Injection via String Interpolation (CRITICAL)

### Existing Vulnerability -- Pre-dates This Plan

**Files**:
- `/Users/taylaand/code/personal/tools/pyoutlook-db/src/pyoutlook_db/core/database.py` (lines 252, 287-289)
- `/Users/taylaand/code/personal/tools/pyoutlook-db/src/pyoutlook_db/core/client.py` (lines 272, 482)

**Description**: The existing codebase has SQL injection vulnerabilities via f-string interpolation of user-controllable values directly into SQL statements.

In `database.py`, the `get_table_info()` method:
```python
query = f"PRAGMA table_info({table_name})"
```

In `database.py`, the `get_row_count()` method:
```python
query = f"SELECT COUNT(*) as count FROM {table_name}"
if where_clause:
    query += f" WHERE {where_clause}"
```

In `client.py`, the `search_emails()` method:
```python
query_parts.append(f"LIMIT {search_filter.limit} OFFSET {search_filter.offset}")
```

And in `get_calendar_events()`:
```python
query_parts.append(f"LIMIT {limit}")
```

**Impact**: While `limit` and `offset` are constrained by Pydantic validation (`ge=1, le=1000` and `ge=0`), the `table_name` and `where_clause` parameters in `database.py` have zero validation. `get_table_info()` is called from the CLI `info` command, and `get_row_count()` accepts an arbitrary `where_clause` string. If any code path allows user input to reach these methods, an attacker could execute arbitrary SQL.

**Exploitability**: MEDIUM for `table_name` (currently called with hardcoded table names from `info` command), but HIGH for `where_clause` (accepts raw SQL string with no sanitisation).

**Mitigation**:
1. Validate `table_name` against an allowlist of known table names before interpolation. PRAGMA statements do not accept parameterized values, so allowlisting is the only safe approach.
2. Remove the `where_clause` parameter entirely from `get_row_count()`. If filtering is needed, accept structured filter parameters and build parameterized queries internally.
3. For `LIMIT`/`OFFSET`, cast to `int` explicitly before interpolation as a defence-in-depth measure, even though Pydantic validates these fields.

```python
# Safe pattern for PRAGMA
ALLOWED_TABLES = {"Mail", "CalendarEvents", "Calendars", "Folders"}

def get_table_info(self, table_name: str) -> list[dict[str, Any]]:
    if table_name not in ALLOWED_TABLES:
        raise ValueError(f"Unknown table: {table_name}")
    query = f"PRAGMA table_info({table_name})"
    ...
```

---

## Finding 2: Path Traversal in Planned `save_attachment()` (CRITICAL)

### New Attack Surface from Plan Phase 2

**Planned file**: `src/macoutlook/core/message_source.py`

**Description**: The plan correctly identifies path traversal as a risk and mentions "Path validation: reject `..`, absolute paths, ensure dest is under target directory." However, the plan does not specify the implementation pattern, and the naive approach of string-checking for `..` is insufficient.

**Attack vectors**:
- MIME attachment filenames are entirely attacker-controlled via the `Content-Disposition` header
- Filenames can contain `../`, absolute paths (`/etc/cron.d/backdoor`), null bytes, or OS-specific sequences
- On macOS specifically, filenames can contain Unicode normalisation tricks (e.g., using fullwidth solidus U+FF0F that some filesystems interpret as a path separator)
- Symlink-following: the destination directory itself might contain symlinks that escape the intended target

**Mitigation**: Apply the exact pattern from the sister project's ZipSlip defence. The critical check is `Path.resolve()` followed by `is_relative_to()`:

```python
from pathlib import Path
import re

# Maximum allowed attachment size (50 MB)
MAX_ATTACHMENT_SIZE = 50 * 1024 * 1024

def _sanitize_filename(self, raw_filename: str) -> str:
    """Sanitize MIME attachment filename to a safe basename."""
    # Strip any directory components (forward slash, backslash)
    name = Path(raw_filename).name

    # Remove null bytes and control characters
    name = re.sub(r'[\x00-\x1f]', '', name)

    # Replace remaining path-separator-like Unicode chars
    name = name.replace('\uff0f', '_').replace('\uff3c', '_')

    # Reject empty or dot-only filenames
    if not name or name.strip('.') == '':
        name = "attachment"

    # Truncate to reasonable length
    if len(name) > 255:
        name = name[:255]

    return name

def save_attachment(self, message_id: str, filename: str, dest_dir: Path) -> Path:
    """Save an attachment to disk with path traversal protection."""
    dest_dir = dest_dir.resolve()

    safe_name = self._sanitize_filename(filename)
    target_path = (dest_dir / safe_name).resolve()

    # THE CRITICAL CHECK
    if not target_path.is_relative_to(dest_dir):
        raise ValueError(
            f"Path traversal detected: {filename!r} resolves to "
            f"{target_path} which is outside {dest_dir}"
        )

    # Check attachment size before writing
    if len(attachment_data) > MAX_ATTACHMENT_SIZE:
        raise ValueError(f"Attachment too large: {len(attachment_data)} bytes")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(attachment_data)
    return target_path
```

Both checks (filename sanitisation AND resolved path validation) are required. The filename sanitisation catches obvious cases with clear errors. The `is_relative_to` check catches anything the sanitisation misses, including edge cases from OS-level path normalisation.

---

## Finding 3: MIME Filename Injection (HIGH)

### New Attack Surface from Plan Phase 2

**Description**: Beyond path traversal, MIME filenames can be crafted to exploit downstream consumers of the `AttachmentInfo.filename` field. The plan stores the filename in a Pydantic model and exposes it via API and CLI.

**Attack vectors**:
- Shell metacharacters in filenames: if any downstream code passes the filename to `subprocess` or `os.system()`, an attacker gets command injection
- XSS via filenames: if the filename is rendered in a web UI or HTML report without escaping, an attacker gets script execution
- Filename collision: an attacker sends two attachments with the same sanitised name, causing one to overwrite the other

**Mitigation**:
1. Sanitise the filename at MIME parse time, before storing in `AttachmentInfo`. The model should never hold an unsanitised filename.
2. Add a Pydantic `field_validator` on `AttachmentInfo.filename` that enforces the sanitisation invariant.
3. For collision protection, append a short hash or counter when a duplicate filename is detected within the same message.

```python
class AttachmentInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    filename: str
    size: int
    content_type: str
    content_id: str | None = None

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        """Reject filenames with path components or control characters."""
        if '/' in v or '\\' in v or '\x00' in v or '..' in v:
            raise ValueError(f"Unsafe filename rejected: {v!r}")
        if not v or v.strip('.') == '':
            raise ValueError("Empty filename rejected")
        return v
```

---

## Finding 4: HTML Content -- Stored XSS Risk (HIGH)

### Existing + Amplified by Plan

**Files**:
- `/Users/taylaand/code/personal/tools/pyoutlook-db/src/pyoutlook_db/parsers/content.py`
- Planned: `body_html` field on `EmailMessage`

**Description**: The plan stores `body_html` directly from MIME `text/html` parts. Email HTML content is fully attacker-controlled and routinely contains JavaScript, event handlers, iframes, and tracking pixels. The existing `ContentParser._clean_html()` strips `<script>` and `<style>` tags, but does NOT strip:

- Event handler attributes: `<div onmouseover="alert(1)">`
- `javascript:` URLs in `href` attributes: `<a href="javascript:alert(1)">`
- `<iframe>`, `<object>`, `<embed>`, `<form>` tags
- `<svg>` tags with embedded script: `<svg onload="alert(1)">`
- `<meta http-equiv="refresh">` redirect tags
- CSS `url()` expressions that can trigger requests
- `data:` URIs that can embed executable content

**Impact**: If `body_html` is ever rendered in a browser context (web UI, Electron app, Jupyter notebook HTML display, or even a Markdown renderer that passes through HTML), the attacker's script executes.

**Mitigation**:
1. Add comprehensive HTML sanitisation. Use a dedicated sanitisation library like `bleach` (now `nh3` for the maintained Rust-based successor) or `lxml.html.clean` rather than hand-rolling tag stripping.
2. Strip ALL event handler attributes (`on*`).
3. Allowlist safe tags and attributes rather than blocklisting dangerous ones. Blocklists always miss something.
4. Strip `javascript:`, `vbscript:`, and `data:` URL schemes from all `href` and `src` attributes.
5. Add CSP-style metadata to the `EmailMessage` model indicating that `body_html` is untrusted and should not be rendered without sandboxing.

```python
# Recommended: allowlist approach
SAFE_TAGS = {
    'p', 'br', 'div', 'span', 'b', 'i', 'u', 'em', 'strong',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'ul', 'ol', 'li', 'a', 'blockquote', 'pre', 'code',
    'table', 'thead', 'tbody', 'tr', 'th', 'td',
    'img',  # if needed, with src validation
}

SAFE_ATTRS = {
    'a': {'href'},  # validate href scheme
    'img': {'src', 'alt', 'width', 'height'},  # validate src scheme
    'td': {'colspan', 'rowspan'},
    'th': {'colspan', 'rowspan'},
}
```

---

## Finding 5: Resource Exhaustion via MIME Parsing (HIGH)

### New Attack Surface from Plan Phase 2

**Description**: The plan calls for parsing 53,909 `.olk15MsgSource` files. Maliciously crafted MIME messages can cause resource exhaustion:

- **MIME bomb**: Deeply nested `multipart/*` structures that cause recursive parsing to exhaust stack/memory
- **Huge attachments**: A single MIME part declaring multi-GB content can exhaust memory when `email.message_from_string()` loads the entire file into memory
- **Encoded content expansion**: Base64-encoded content expands ~33% on decode. Quoted-printable can expand more with crafted input
- **Infinite-loop MIME boundaries**: Malformed boundary strings that cause the parser to loop

**Impact**: Denial of service -- the tool hangs or crashes, potentially filling disk or consuming all memory on the user's workstation.

**Mitigation**:
1. **File size limit**: Check `.olk15MsgSource` file size before reading. Reject files over a reasonable limit (e.g., 100 MB). Legitimate emails rarely exceed 25 MB.
2. **MIME depth limit**: Set `email.policy.default` with a `max_header_size` and use iterative (not recursive) MIME walking. Python's `email` module has a `max_count` parameter on header parsing.
3. **Attachment count limit**: Cap the number of attachments parsed per message (e.g., 200).
4. **Timeout**: Wrap MIME parsing in a timeout. If parsing a single file takes more than 10 seconds, skip it and log a warning.
5. **Memory-aware reading**: For the index-building phase (reading 53K files for Message-ID headers), read only the headers rather than the full file body. Use `email.parser.HeaderParser` instead of `email.message_from_string()`.

```python
from email.parser import HeaderParser
from email import policy

MAX_SOURCE_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
MAX_ATTACHMENTS_PER_MESSAGE = 200

def _parse_message_id_only(self, file_path: Path) -> str | None:
    """Parse only the Message-ID header without loading the full body."""
    if file_path.stat().st_size > MAX_SOURCE_FILE_SIZE:
        logger.warning("Source file too large, skipping", path=str(file_path))
        return None

    parser = HeaderParser(policy=policy.default)
    with open(file_path, 'r', errors='replace') as f:
        headers = parser.parse(f)
    return headers.get('Message-ID')
```

---

## Finding 6: BeautifulSoup and XML Parsing Risks (MEDIUM)

### Existing Vulnerability

**File**: `/Users/taylaand/code/personal/tools/pyoutlook-db/src/pyoutlook_db/parsers/content.py` (line 116)

**Description**: The `ContentParser` uses `BeautifulSoup(html_content, "html.parser")`. The `html.parser` backend is Python's stdlib HTML parser and is NOT vulnerable to XXE (it is an HTML parser, not an XML parser). However, the `_extract_html_from_xml()` method on line 72 is described as extracting "HTML from XML wrapper" and uses regex rather than an XML parser.

The risk here is low for the current code, but the plan's Phase 2 introduces processing of MIME parts that may contain XML content types (e.g., `application/xml`, `text/xml`). If any future code path uses Python's stdlib `xml.etree.ElementTree` or `lxml` to parse content from MIME parts, XXE becomes a real risk.

**Mitigation**:
1. Add `defusedxml` as a project dependency now, before any XML parsing is introduced.
2. Add a ruff rule or pre-commit hook that flags imports from `xml.etree` (the sister project has this exact pattern documented).
3. Document in the project's CLAUDE.md: "Never import from `xml.etree`, always from `defusedxml`."
4. For BeautifulSoup, if you ever switch to the `lxml` or `xml` parser backend, ensure you pass `features="lxml-xml"` and configure the parser to disable entity resolution.

```toml
# pyproject.toml addition
dependencies = [
    ...
    "defusedxml>=0.7.0",
]
```

---

## Finding 7: Error Messages Leak Sensitive Information (MEDIUM)

### Existing Vulnerability

**Files**:
- `/Users/taylaand/code/personal/tools/pyoutlook-db/src/pyoutlook_db/core/database.py` (line 241)
- `/Users/taylaand/code/personal/tools/pyoutlook-db/src/pyoutlook_db/core/exceptions.py` (line 75)
- `/Users/taylaand/code/personal/tools/pyoutlook-db/src/pyoutlook_db/cli/main.py` (lines 140-143)

**Description**: Error messages expose internal paths and database details:

In `database.py`:
```python
raise DBConnectionError(f"Query failed: {query[:50]}...", e) from e
```
This leaks the first 50 characters of the SQL query in the exception message.

In `exceptions.py`, `ConnectionError` includes the full database path:
```python
message = f"Failed to connect to database at {db_path}"
```

In `cli/main.py`, raw exceptions are printed to the user:
```python
click.echo(f"Unexpected error: {e}", err=True)
```

**Impact**: Exposes the full filesystem path to the Outlook database (which reveals the username and profile name), partial SQL queries (which reveal schema details), and raw Python exception traces.

**Mitigation**:
1. Log detailed error information (including query text and full paths) at DEBUG level only.
2. User-facing error messages should be generic: "Database connection failed. Run with --verbose for details."
3. Never include raw exception messages from sqlite3 in user-facing output -- these can reveal schema information.

---

## Finding 8: Module Name Shadowing Risk (MEDIUM)

### Applicable to Plan Phase 2

**Description**: The plan creates `src/macoutlook/models/email.py`. The Python stdlib has a module named `email`. If any import resolution quirk causes `email` to resolve to `macoutlook.models.email` instead of the stdlib `email` module, the MIME parsing in `message_source.py` (which uses `from email import ...`) will break silently or catastrophically.

The sister project's security document explicitly calls this out: "These stdlib module names are tempting to reuse" with `email.py` listed as a dangerous filename.

**Impact**: If shadowing occurs, `email.message_from_string()` would fail with an `AttributeError`, breaking the core MIME parsing functionality. Not a security vulnerability per se, but a reliability and correctness issue.

**Mitigation**: The current naming (`models/email.py`) is within a package, so relative imports within `macoutlook` use the package-qualified path. This is likely safe because `message_source.py` will use `import email` (stdlib) or `from email import ...` which resolves to stdlib. However, as defence-in-depth:

1. Rename `models/email.py` to `models/email_message.py` to eliminate any ambiguity.
2. Add a test that verifies `import email; assert 'message_from_string' in dir(email)` to catch shadowing during CI.

---

## Finding 9: File Permission Scope -- macOS Group Containers (LOW)

### Existing + Plan Context

**Description**: The library reads from `~/Library/Group Containers/UBF8T346G9.Office/Outlook/`. On macOS, accessing this directory requires Full Disk Access (FDA) entitlement. The plan adds reading of `.olk15MsgSource` files from this same directory tree, plus writing attachment files to user-specified paths.

**Risks**:
- If the library is used within a sandboxed macOS app, FDA access may not be available, leading to confusing `PermissionError` exceptions
- The `save_attachment()` method writes files -- if the destination is within a protected macOS directory, the write may silently fail or trigger a TCC prompt
- The database is opened with `?mode=ro` (good), but `.olk15MsgSource` files will be opened for reading with standard `open()` -- ensure read-only mode is explicit

**Mitigation**:
1. Document the FDA requirement prominently in README and CLI help.
2. When opening `.olk15MsgSource` files, use `open(path, 'r')` or `open(path, 'rb')` explicitly -- never write mode.
3. Add a startup check that tests read access to the Group Containers directory and gives a clear, actionable error message if access is denied.
4. For `save_attachment()`, verify the destination directory is writable before starting the extraction.

---

## Finding 10: Global Singleton Thread Safety (LOW)

### Existing Vulnerability

**Files**:
- `/Users/taylaand/code/personal/tools/pyoutlook-db/src/pyoutlook_db/core/database.py` (lines 309-327)
- `/Users/taylaand/code/personal/tools/pyoutlook-db/src/pyoutlook_db/parsers/content.py` (lines 347-362)

**Description**: The `get_database()` and `get_content_parser()` functions use global singletons without any thread safety. If the library is used in a multi-threaded context (e.g., a web server), concurrent access to the shared `sqlite3.Connection` will cause `ProgrammingError: SQLite objects created in a thread can only be used in that same thread`.

**Impact**: Low, because the plan explicitly calls for removing the global singleton pattern. Including here for completeness to ensure the replacement pattern is thread-safe.

**Mitigation**: The plan correctly identifies this and plans to remove singletons. When replacing, do NOT use a new global with a lock -- instead, make `OutlookClient` fully self-contained with its own database connection, and let the caller manage lifecycle (context manager pattern).

---

## Additional Recommendations for the Plan

### 1. Add `defusedxml` to dependencies immediately

Even though the current code does not parse XML directly, the plan adds MIME parsing which may encounter XML content types. Adding `defusedxml` now and establishing the "never import from `xml.etree`" convention prevents future mistakes.

### 2. Add security-focused ruff rules

The existing ruff config already includes `"S"` (bandit). Verify these specific bandit rules are active:
- `S608`: Hardcoded SQL expressions (will catch the f-string SQL injection)
- `S603`/`S607`: subprocess calls (relevant if any external tool invocation is added)
- `S314`: `xml.etree` usage (catches XXE-vulnerable imports)
- `S506`: unsafe YAML load (defence-in-depth)

### 3. Add security test suite (Phase 4 enhancement)

The plan mentions `test_attachment_security.py` for path traversal. Expand this to cover:
- MIME bomb (deeply nested multipart) handling
- Filenames with null bytes, Unicode path separators, and `..` sequences
- HTML content with `<script>`, `onload`, `javascript:` URIs -- verify sanitisation
- Oversized `.olk15MsgSource` files (>100 MB) -- verify rejection
- SQL injection attempts via search filter fields
- Malformed MIME that causes `email` module to raise exceptions

### 4. Add `nh3` (or equivalent) for HTML sanitisation

The current approach of stripping `<script>` and `<style>` with BeautifulSoup is a blocklist. Blocklists always miss vectors. Add a proper HTML sanitisation library:

```toml
dependencies = [
    ...
    "nh3>=0.2.0",  # Rust-based HTML sanitiser (successor to bleach)
]
```

### 5. Pin minimum dependency versions for security

The current `pyproject.toml` specifies minimum versions but no upper bounds. While upper bounds can cause dependency conflicts, ensure the minimum versions do not have known CVEs. Run `uv run safety check` regularly and add it to CI.

### 6. Do not log email content at INFO level

The existing code logs at INFO level with structlog. Ensure that when MIME parsing is added, email body content and attachment data are never logged -- even at DEBUG level, binary attachment content should be omitted. Log metadata (filename, size, content-type) only.

---

## Security Requirements Checklist for Implementation

- [ ] All SQL queries use parameterized statements (no f-string interpolation)
- [ ] `table_name` in PRAGMA calls validated against allowlist
- [ ] `where_clause` parameter removed from `get_row_count()`
- [ ] `save_attachment()` uses `Path.resolve()` + `is_relative_to()` for path traversal prevention
- [ ] MIME filenames sanitised at parse time (strip path components, control chars, null bytes)
- [ ] `AttachmentInfo.filename` has Pydantic validator rejecting unsafe patterns
- [ ] HTML content sanitised with allowlist approach (not blocklist)
- [ ] `defusedxml` added to dependencies
- [ ] `.olk15MsgSource` file size checked before reading (reject >100 MB)
- [ ] `HeaderParser` used for index building (headers only, not full body)
- [ ] Attachment count capped per message
- [ ] Error messages do not expose file paths, SQL queries, or internal details to users
- [ ] `models/email.py` renamed to `models/email_message.py` to avoid stdlib shadowing
- [ ] Security test suite covers: path traversal, MIME bombs, XSS vectors, SQL injection
- [ ] No email content logged at INFO level or above
- [ ] `nh3` or equivalent HTML sanitiser added to dependencies
- [ ] CI runs `safety check` and `bandit -r src/`

---

## Risk Matrix

```
                    LOW IMPACT          HIGH IMPACT
                +------------------+------------------+
  HIGH          |                  | F5: Resource     |
  LIKELIHOOD    |                  |   exhaustion     |
                |                  | F4: Stored XSS   |
                +------------------+------------------+
  MEDIUM        | F7: Error info   | F1: SQL injection|
  LIKELIHOOD    |   leakage        | F2: Path traversal|
                | F8: Module       | F3: Filename     |
                |   shadowing      |   injection      |
                +------------------+------------------+
  LOW           | F10: Thread      | F6: XXE (future) |
  LIKELIHOOD    |   safety         | F9: macOS perms  |
                +------------------+------------------+
```

Critical items to address before any code is written: F1 (existing SQL injection) and F2 (path traversal design). These are prerequisites, not post-implementation fixes.
