# Design Pattern Analysis: pyoutlook-db and macoutlook Plan

**Date**: 2026-03-14
**Scope**: Current `pyoutlook-db` source, proposed `macoutlook` plan, cross-reference with `docextract` sister project

---

## 1. Design Patterns Currently Used

### 1.1 Facade Pattern -- OutlookClient (client.py, 590 lines)

`OutlookClient` is the primary Facade. It hides `OutlookDatabase`, `ContentParser`, and
`ICalendarParser` behind a single interface (`get_emails()`, `get_calendars()`, etc.).

**Assessment**: Correct pattern choice. However, at 590 lines with ~20 methods including private
helpers for SQL construction, row-to-model conversion, recipient parsing, timestamp conversion,
and content orchestration, it is drifting toward God Class territory (see Anti-Patterns below).

### 1.2 Context Manager Protocol -- OutlookDatabase and OutlookClient

Both classes implement `__enter__`/`__exit__` for resource cleanup. `OutlookDatabase` also has
`__del__` as a safety net.

**Assessment**: Good Pythonic pattern. The `__del__` fallback is defensive but acceptable for
database connections. The plan retains this pattern, which is correct.

### 1.3 Module-Level Singleton -- get_database() and get_content_parser()

Global mutable state (`_db_instance`, `_parser_instance`) with factory functions that
lazily instantiate and cache a single instance.

**Assessment**: This is an anti-pattern, not a proper Singleton. See section 2.1 below.

### 1.4 Template Method (informal) -- ContentParser

`ContentParser` has `parse_content()` which dispatches to `_html_to_text()`,
`_html_to_markdown()`, `_clean_whitespace()` in a fixed pipeline sequence. Not a formal
Template Method (no abstract base class) but follows the structural intent.

**Assessment**: Functional but not extensible. The plan does not propose changing this, which is
a missed opportunity (see section 5).

### 1.5 Value Objects -- Pydantic Models

`EmailMessage`, `CalendarEvent`, `Calendar`, filter models, and stats models are all Pydantic
`BaseModel` subclasses serving as rich value objects with validation.

**Assessment**: Correct pattern. The Pydantic v1 API debt is a known issue the plan addresses.

---

## 2. Anti-Patterns in Current Code That the Plan Addresses

### 2.1 Global Mutable Singletons (Severity: HIGH)

**Location**: `database.py:310-327`, `parsers/content.py:348-362`

```python
_db_instance: OutlookDatabase | None = None

def get_database(db_path: str | None = None) -> OutlookDatabase:
    global _db_instance
    if _db_instance is None or (db_path and _db_instance.db_path != db_path):
        _db_instance = OutlookDatabase(db_path)
    return _db_instance
```

**Problems**: Not thread-safe. Untestable without monkeypatching globals. Silently replaces the
instance if a different `db_path` is passed, breaking any existing references. Makes dependency
injection impossible.

**Plan fix**: Phase 1 explicitly removes these. Good.

### 2.2 Pydantic v1 API Debt (Severity: MEDIUM)

**Locations**: 18 occurrences across `models/email.py`, `models/calendar.py`, `cli/main.py`

- `@validator` instead of `@field_validator`
- `class Config:` instead of `model_config = ConfigDict(...)`
- `.dict()` instead of `.model_dump()`
- `json_encoders` instead of custom serializers

**Plan fix**: Phase 1 migrates all to Pydantic v2 API. Good.

### 2.3 Preview-Only Content (Severity: HIGH -- functional limitation)

**Location**: `client.py` SQL queries only read `Message_Preview` (~256 chars)

**Plan fix**: Phase 2 introduces `MessageSourceReader` to read full MIME content from
`.olk15MsgSource` files. This is the core feature of the plan.

### 2.4 Wrong Identifier Used as message_id (Severity: HIGH)

**Location**: `client.py` -- uses `Record_RecordID` (internal DB integer) as `message_id`

The RFC 2822 `Message-ID` header is the canonical email identifier. Using the DB's internal
row ID prevents cross-system correlation and makes the Message-ID-based matching in Phase 2
impossible.

**Plan fix**: Phase 1 switches to `Message_MessageID` from the DB, keeps `record_id` as a
separate field. Good.

---

## 3. Anti-Patterns the Plan Might Introduce

### 3.1 God Class Risk -- OutlookClient Growing (Severity: MEDIUM-HIGH)

The plan adds to `OutlookClient`:
- `MessageSourceReader` orchestration (build index, match, enrich)
- `save_attachment()` method (file I/O with security validation)
- `FuzzyMatcher` integration
- `enrich: bool` parameter threading through all email methods

At 590 lines today, the client will likely exceed 800-900 lines post-plan. The Mermaid diagram
in the plan shows OutlookClient with arrows to 4 collaborators -- this is the textbook sign of a
Mediator pattern being used where delegation and decomposition would be healthier.

**Recommendation**: Extract an `EmailEnricher` class that owns the enrichment pipeline
(MessageSourceReader + ContentParser + matching strategy). OutlookClient delegates to it.
This mirrors how docextract's `ParserRouter` owns the parsing pipeline rather than putting
it in a top-level client.

### 3.2 No Result Type for Enrichment Operations (Severity: MEDIUM)

The plan specifies `content_source: str = "preview_only"` as a string literal on `EmailMessage`.
This is a stringly-typed provenance field. If MIME parsing fails, it silently degrades. There is
no structured record of what was attempted, what failed, and why -- unlike docextract's
`ParseResult` with its `AttemptRecord` cascade trace.

For a library that will routinely encounter corrupt MIME files, missing source files, and
encoding edge cases, this is insufficient for debugging.

**Recommendation**: Adopt a structured enrichment result (see section 5).

### 3.3 Matching Strategy Embedded in Procedural Code (Severity: LOW-MEDIUM)

The plan describes a 3-tier matching cascade (Message-ID -> subject+date+sender -> fuzzy subject)
but implements it as procedural logic inside `MessageSourceReader`. This works for the current
scope but is not extensible.

**Recommendation**: At minimum, make the matching strategy a method chain with clear separation.
A full Strategy pattern with a `Matcher` protocol is overkill for 3 strategies but would be
warranted if more matching heuristics are added later.

### 3.4 content_source as Bare String (Severity: LOW)

Using `str` for `content_source` with magic values `"preview_only"` and `"message_source"`
invites typos and makes exhaustive matching impossible.

**Recommendation**: Use a `StrEnum`:

```python
class ContentSource(str, Enum):
    PREVIEW_ONLY = "preview_only"
    MESSAGE_SOURCE = "message_source"
```

---

## 4. Pattern Consistency Across the Codebase

### 4.1 Naming Conventions -- Consistent

- Classes: PascalCase throughout (OutlookClient, OutlookDatabase, ContentParser, EmailMessage)
- Methods/functions: snake_case throughout
- Constants: UPPER_SNAKE_CASE (CF_EPOCH)
- Private methods: single underscore prefix (_parse_recipients, _row_to_email)
- Module-level private globals: single underscore (_db_instance, _parser_instance)

No naming inconsistencies found.

### 4.2 Error Handling -- Inconsistent

The exception hierarchy in `core/exceptions.py` is well-designed (OutlookDBError base, specific
subclasses with structured fields). However:

- `OutlookDatabase` raises exceptions properly (DatabaseNotFoundError, DatabaseLockError)
- `ContentParser` silently swallows errors and returns empty strings
- `OutlookClient` has mixed behavior -- some methods raise, some log and continue

There is no consistent contract about what raises and what degrades gracefully.

### 4.3 Dependency Direction -- Clean

The layering is correct: CLI -> Client -> Database/Parsers -> Models. No circular imports.
Models have no upward dependencies. This is good and the plan preserves it.

### 4.4 Pydantic Usage -- Internally Consistent (but v1 API)

All models use the same patterns: BaseModel, Field with descriptions, validators, Config class.
The consistency is good; the API version is the issue.

---

## 5. Should macoutlook Adopt docextract Patterns?

### 5.1 DocumentParser Protocol -- YES, Adapted

docextract defines:

```python
@runtime_checkable
class DocumentParser(Protocol):
    @property
    def name(self) -> str: ...
    def can_handle(self, mime_type: str) -> bool: ...
    def parse(self, file_path: Path) -> ParseResult: ...
```

macoutlook does not need this exact interface (it parses MIME email, not arbitrary documents),
but the `MessageSourceReader` would benefit from a similar protocol for its matching strategies:

```python
class MessageMatcher(Protocol):
    @property
    def name(self) -> str: ...
    def match(self, email_metadata: EmailMetadata, index: SourceIndex) -> Path | None: ...
```

**Verdict**: Adopt the Protocol pattern for matching strategies if the matching logic is expected
to grow. For the initial 3-strategy cascade, a simpler method chain is sufficient but should be
designed to be extractable later.

### 5.2 ParserRouter Dispatch -- YES, for Enrichment Pipeline

docextract's `ParserRouter` is the key architectural insight: a single class owns the dispatch
table and orchestrates the cascade. macoutlook's equivalent is the enrichment pipeline
(find source file -> parse MIME -> extract content -> convert to markdown).

Instead of embedding this in `OutlookClient`, extract an `EmailEnricher` class that:
- Owns the `MessageSourceReader`
- Owns the `ContentParser`
- Orchestrates the match-parse-convert pipeline
- Returns a structured result

This directly parallels `ParserRouter.parse()` -> `ParseResult`.

**Verdict**: Strongly recommended. This is the single highest-impact pattern adoption.

### 5.3 ParseResult with Cascade Trace -- YES, Adapted

docextract's `ParseResult` is a frozen dataclass with:
- `text: str | None` -- the output
- `source_parser: str` -- which parser produced it
- `attempts: tuple[AttemptRecord, ...]` -- full cascade trace
- `error: str | None` -- final error if failed
- `success: bool` property

macoutlook should adopt an `EnrichmentResult`:

```
EnrichmentResult (frozen dataclass):
    content_source: ContentSource (enum)
    body_text: str | None
    body_html: str | None
    body_markdown: str | None
    attachments: list[AttachmentInfo]
    match_method: str | None  -- "message_id", "subject_date_sender", "fuzzy"
    error: str | None
    success: bool (property)
```

This separates the enrichment outcome from the `EmailMessage` model, which should only hold
the final composed data. The provenance metadata can be attached or logged separately.

**Verdict**: Strongly recommended. The plan's `content_source` string field is a minimal version
of this; the full result type adds debuggability at near-zero cost.

### 5.4 Never-Raises Philosophy -- YES, for MessageSourceReader

docextract's contract is "parse() NEVER raises -- always returns ParseResult." This is critical
for batch processing where one corrupt file should not abort the entire run.

macoutlook's `MessageSourceReader` should follow the same contract:
- If the source file is missing: return result with `content_source=PREVIEW_ONLY`
- If MIME parsing fails: return result with error, fall back to preview
- Never raise from enrichment operations

The plan already describes this behavior informally ("graceful fallback") but does not codify
it as a contract. Making it explicit via the return type is the docextract way.

**Verdict**: Adopt. The plan's intent aligns; formalize the contract.

### 5.5 Dataclass vs Pydantic for Internal Results -- ADOPT DATACLASS

docextract uses `@dataclass(frozen=True, slots=True)` for `ParseResult` and `AttemptRecord`.
This is deliberate: these are internal value types that do not need validation, serialization,
or schema generation. Pydantic would add overhead for no benefit.

macoutlook should follow this split:
- **Pydantic BaseModel**: For public API models (`EmailMessage`, `CalendarEvent`) that need
  validation, JSON serialization, and schema documentation
- **Frozen dataclass**: For internal pipeline results (`EnrichmentResult`, `MatchResult`) that
  are pure value carriers

**Verdict**: Adopt. This is a meaningful Python pattern distinction that the plan does not
currently address.

---

## 6. Summary of Recommendations

| # | Finding | Severity | Recommendation |
|---|---------|----------|----------------|
| 1 | OutlookClient God Class risk | HIGH | Extract EmailEnricher class to own enrichment pipeline |
| 2 | No structured enrichment result | MEDIUM | Adopt EnrichmentResult frozen dataclass (a la ParseResult) |
| 3 | content_source as bare string | LOW | Use StrEnum for type safety |
| 4 | Matching strategies as procedural code | LOW-MED | Design for extractability; full Protocol if scope grows |
| 5 | Never-raises contract informal | MEDIUM | Formalize via return type on MessageSourceReader |
| 6 | Dataclass vs Pydantic not distinguished | LOW | Use frozen dataclass for internal results, Pydantic for API |
| 7 | ContentParser not extensible | LOW | Consider strategy interface if output formats grow |
| 8 | Error handling inconsistency | MEDIUM | Establish clear contract per layer (raises vs degrades) |

### Pattern Adoption Priority from docextract

1. **ParserRouter -> EmailEnricher** (architectural, prevents God Class)
2. **ParseResult -> EnrichmentResult** (debuggability, batch safety)
3. **Never-raises contract** (operational robustness)
4. **DocumentParser Protocol -> MessageMatcher Protocol** (future extensibility, defer if scope is fixed)
5. **Frozen dataclass for internal types** (performance, correctness)
