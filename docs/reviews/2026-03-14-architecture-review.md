# Architecture Review: macoutlook Redesign Plan

**Date**: 2026-03-14
**Reviewer**: System Architecture Analysis
**Plan**: `docs/plans/2026-03-14-feat-macoutlook-full-content-extraction-plan.md`

---

## 1. Architecture Overview

### Current State

The existing `pyoutlook-db` is a layered library with four tiers:

```
CLI (Click) --> Client (OutlookClient) --> Database (OutlookDatabase) + Parser (ContentParser)
                                       --> Models (Pydantic v1-style)
```

Key characteristics of the current codebase:
- Global singletons for `OutlookDatabase` and `ContentParser`
- Pydantic v1 API used despite requiring pydantic>=2.0
- Raw SQL strings embedded directly in `OutlookClient`
- `OutlookClient.__init__` calls `get_database()` and `get_content_parser()` internally
- Massive row-to-model mapping duplicated across `get_emails_by_date_range` and `search_emails`
- Dead code: `_row_to_email()` method references column names that do not match any query

### Proposed State

The plan adds two new components and restructures the package:

```
CLI --> OutlookClient --> OutlookDatabase (SQLite metadata)
                     --> MessageSourceReader (.olk15MsgSource MIME files)
                     --> ContentParser (HTML --> markdown)
                     --> FuzzyMatcher (sender search)
                     --> Models (Pydantic v2, redesigned)
```

---

## 2. Change Assessment: Question-by-Question Analysis

### Q1: Is the layered architecture (client --> database + message_source + parser + fuzzy) well-structured?

**Verdict: Mostly sound, with one structural concern.**

The plan correctly keeps `OutlookClient` as an orchestrator that composes four collaborators. This respects Single Responsibility -- each component does one thing:
- `OutlookDatabase`: SQLite queries
- `MessageSourceReader`: file I/O + MIME parsing
- `ContentParser`: HTML transformation
- `FuzzyMatcher`: search scoring

The structural concern is that `MessageSourceReader` as described in the plan does two distinct things: (a) builds/maintains a file index (glob + header parsing), and (b) parses MIME content from matched files. These are separable responsibilities. However, given the library's scope and the tight coupling between "find the file" and "parse the file," keeping them together is a pragmatic choice. Splitting into `MessageSourceIndex` and `MimeParser` would be over-engineering at this scale. The plan is correct to combine them.

The `search/fuzzy.py` module being in its own `search/` package is slightly premature -- it is a single module. A flat `fuzzy.py` alongside `core/` would be simpler. But if you anticipate adding more search strategies (e.g., full-text indexing), the package structure is justified as forward planning.

### Q2: Are the component boundaries clean? Is there appropriate coupling/decoupling?

**Verdict: Mostly clean. One coupling risk identified.**

**Good boundaries:**
- `OutlookDatabase` has no knowledge of models or content parsing
- `ContentParser` is stateless and model-agnostic
- `FuzzyMatcher` takes strings in, returns scores out -- pure function territory
- Models are plain data containers (Pydantic) with no business logic

**Coupling risk -- the enrichment join:**

The plan describes the enrichment flow as:
1. Query DB for metadata + Message_MessageID
2. Build MessageSourceReader index (Message-ID --> file path)
3. Match each email's Message-ID to source file
4. Parse MIME content
5. Run ContentParser on HTML --> markdown

Steps 2-5 execute inside `OutlookClient.get_emails()`. This means `OutlookClient` must understand the matching strategy, the index structure, and the enrichment assembly. This is acceptable for an orchestrator, but the plan should be explicit that the matching logic (Message-ID lookup, fallback to subject+date+sender) lives inside `MessageSourceReader.find_source(message_id, subject, sender, date)` -- not in the client.

**Recommendation**: `MessageSourceReader` should expose a single method like `get_content(message_id: str, fallback_key: tuple[str, str, str] | None = None) -> MimeContent | None` that encapsulates the entire lookup + parse cycle. The client should not reach into the index dict directly.

### Q3: Is the lazy indexing approach (build on first use, cache for session) the right pattern?

**Verdict: Correct pattern, needs explicit lifecycle management.**

Lazy initialization is the right call for a library where:
- Not every caller needs enrichment (the `enrich=False` path)
- Index building is expensive (53K file glob + header parse)
- The index does not change during a session (Outlook files are stable)

However, the plan does not specify where the index lives or how its lifecycle is managed. The index should be:
- A private attribute of `MessageSourceReader` (e.g., `self._index: dict[str, Path] | None = None`)
- Built on first call to any method that requires it
- Invalidated only by explicit `rebuild_index()` or new `MessageSourceReader` instance

The `<10 second` target for 53K files needs validation. Parsing the Message-ID header from each file requires reading the first few KB of each file. At 53K files, this is I/O-bound. Consider:
- Reading only the first N bytes (Message-ID is always in the first 4KB of RFC 2822 headers)
- Using `os.scandir()` instead of `glob.glob()` for the initial file listing
- Optional: `concurrent.futures.ThreadPoolExecutor` for parallel header reads (I/O-bound work parallelizes well with threads)

The plan mentions "consider parallel file reading" in risk analysis but should promote this to a Phase 2 implementation detail.

### Q4: Should MessageSourceReader be injected into OutlookClient or created internally?

**Verdict: Inject it. This is the most important architectural decision in the plan.**

The current code creates dependencies internally:
```python
self.db = get_database(db_path)      # internal creation via singleton
self.parser = get_content_parser()   # internal creation via singleton
```

The plan correctly removes the singletons. But it does not specify how `OutlookClient` gets its collaborators. There are two options:

**Option A -- Constructor Injection (Recommended):**
```python
class OutlookClient:
    def __init__(
        self,
        database: OutlookDatabase,
        message_source: MessageSourceReader | None = None,
        content_parser: ContentParser | None = None,
    ): ...
```

**Option B -- Internal Creation with Config:**
```python
class OutlookClient:
    def __init__(self, db_path: str | None = None, enrich: bool = True): ...
        # Creates OutlookDatabase, MessageSourceReader internally
```

Constructor injection (Option A) is strongly preferred because:

1. **Testability**: The Outlook MCP server and tests can inject mocks without monkey-patching
2. **Composability**: The MCP server likely needs to control database lifecycle (keep connection open across requests) rather than letting `OutlookClient` manage it
3. **Ecosystem fit**: Since this pairs with docextract and an MCP server, the server needs to configure components once and reuse them

To avoid forcing users to assemble the object graph manually, provide a factory function:
```python
def create_client(
    db_path: str | None = None,
    enrich: bool = True,
    outlook_data_path: Path | None = None,
) -> OutlookClient:
    """Convenience factory -- builds an OutlookClient with default collaborators."""
```

This gives you both: clean DI for the MCP server and ergonomic creation for CLI/scripting use.

### Q5: Is the enrichment flow (DB query --> match --> MIME parse --> model) well-designed?

**Verdict: Well-designed. Two refinements needed.**

The flow is sound: query structured metadata from SQLite (fast, indexed), then selectively enrich with MIME content from files (I/O heavy). This is a classic "read-through enrichment" pattern.

**Refinement 1 -- Batch vs. per-email enrichment:**

The plan implies enrichment happens per-email in a loop. For 100 emails, that means 100 file reads. This is fine, but the index should be built once before the loop, not lazily on first email. The plan's "build on first use, cache for session" handles this correctly.

However, consider whether `get_emails()` should accept a batch of Message-IDs and return enriched content in one pass. This matters for the MCP server, which may request emails in batches. The current design (iterate + enrich each) is fine for v1; just ensure the API does not preclude batch optimization later.

**Refinement 2 -- The `content_source` provenance field:**

The plan defines `content_source: str = "preview_only" | "message_source"`. This is good practice for downstream consumers (LLMs need to know content quality). Consider making this a `Literal` type or an enum rather than a bare string, for type safety:

```python
content_source: Literal["preview_only", "message_source"] = "preview_only"
```

### Q6: Are there missing abstractions or unnecessary ones?

**Missing abstractions:**

1. **No data path abstraction.** Both `OutlookDatabase` and `MessageSourceReader` need to find paths under `~/Library/Group Containers/UBF8T346G9.Office/Outlook/`. This path logic is duplicated. Extract an `OutlookDataPath` or `OutlookProfile` class that resolves the base directory, profile name, and provides paths to both the SQLite file and the source files directory. This also makes testing easier (inject a temp directory).

2. **No result type for enrichment.** The plan merges everything into `EmailMessage`. Consider whether `MimeContent` (body_text, body_html, attachments) should be a separate intermediate type returned by `MessageSourceReader`, which `OutlookClient` then merges into `EmailMessage`. This keeps `MessageSourceReader` independent of the Pydantic model.

3. **No protocol/interface for the database layer.** If you ever want to support a different backend (e.g., reading from an exported mailbox), having `OutlookDatabase` implement a `Protocol` would help. Low priority for now, but worth noting.

**Unnecessary abstractions:**

1. **`EmailSearchFilter` as a Pydantic model.** The current code uses `EmailSearchFilter` as a structured input to `search_emails()`. The plan's `search_emails(query, fuzzy=False)` simplifies this. Good -- the filter model added complexity without value (the client immediately destructured it into SQL params).

2. **`EmailStats`, `CalendarStats`, `CalendarEventFilter`** in the current code are never used by any caller. The plan implicitly drops them, which is correct.

### Q7: How does this compare to standard Python library architecture patterns?

The proposed architecture follows established patterns well:

- **Repository Pattern**: `OutlookDatabase` acts as a repository (data access abstraction)
- **Facade Pattern**: `OutlookClient` is a facade over multiple subsystems
- **Strategy Pattern**: `ContentParser` and `FuzzyMatcher` are pluggable strategies
- **Lazy Initialization**: Index building deferred to first use

This is comparable to libraries like `python-docx` (document reading), `openpyxl` (Excel reading), and `mailbox` (stdlib). All follow the pattern of: file/source reader --> structured model --> optional formatting.

One area where the plan could improve is the **public API surface**. The `__init__.py` should export a minimal set:
- `OutlookClient` (primary entry point)
- `create_client()` (convenience factory)
- `EmailMessage`, `AttachmentInfo`, `CalendarEvent` (data models)
- Exception classes

Internal components (`OutlookDatabase`, `MessageSourceReader`, `ContentParser`, `FuzzyMatcher`) should be importable but not in `__all__`. This follows the "narrow API, wide internals" principle.

### Q8: The plan removes global singletons -- is the proposed replacement sound?

**Verdict: Removing singletons is correct. The replacement is under-specified.**

The current singletons are problematic:
- `_db_instance` in `database.py` is module-level mutable state
- `_parser_instance` in `content.py` is the same
- Neither is thread-safe
- Both make testing require careful teardown

The plan says "Remove global singleton pattern from `get_database()` / `get_content_parser()`" but does not specify the replacement. The replacement should be:

1. **`ContentParser`**: Make it stateless (it already is) and just instantiate it directly. No factory needed. `ContentParser()` is cheap.

2. **`OutlookDatabase`**: Pass as constructor argument to `OutlookClient`. The factory function (`create_client()`) handles default construction.

3. **`MessageSourceReader`**: Same as database -- inject or create in factory.

Do NOT replace singletons with a service locator or registry. Direct constructor injection with an optional factory function is the cleanest pattern.

---

## 3. Compliance Check

| Principle | Status | Notes |
|-----------|--------|-------|
| **Single Responsibility** | PASS | Each component has one job. `OutlookClient` is an orchestrator, not a god class. |
| **Open/Closed** | PASS | New enrichment added via new `MessageSourceReader` class, not by modifying `OutlookDatabase`. |
| **Liskov Substitution** | N/A | No inheritance hierarchies. Composition-based design. |
| **Interface Segregation** | PARTIAL | `OutlookClient` exposes emails + calendars + search. The MCP server may only need emails. Consider whether `OutlookClient` should be split, or whether the current surface is small enough. Verdict: small enough. |
| **Dependency Inversion** | NEEDS WORK | Plan does not specify injection. High-level `OutlookClient` should depend on abstractions (or at minimum, accept instances), not create its own dependencies. |
| **No Circular Dependencies** | PASS | Clean DAG: CLI --> Client --> {Database, MessageSource, Parser, Fuzzy} --> Models. |
| **Pydantic v2 Migration** | PASS | Plan correctly identifies all v1 patterns to migrate. |

---

## 4. Risk Analysis

### Architectural Risks

**Risk 1 -- Index memory footprint (Low likelihood, Medium impact)**
53K entries of `{message_id: Path}` is approximately 5-10 MB in memory. Acceptable. The secondary index `{subject+sender+date: Path}` doubles this. Still fine.

**Risk 2 -- MIME parsing robustness (Medium likelihood, Medium impact)**
Python's `email` module handles RFC 2822 well but can be slow on large MIME messages (e.g., emails with large base64 attachments). Since `save_attachment()` re-parses the source file on each call, consider caching parsed `email.message.Message` objects or at least the attachment metadata index.

**Risk 3 -- Path coupling to macOS Outlook internals (High likelihood on Outlook updates, High impact)**
The entire library depends on Outlook's undocumented file layout. The `OutlookProfile` / data path abstraction recommended above would at least centralize this coupling.

**Risk 4 -- `save_attachment()` security surface**
The plan correctly identifies path traversal risks. The implementation must also consider:
- Filename length limits (macOS: 255 bytes)
- Null bytes in filenames
- Unicode normalization (macOS uses NFD)
- Symlink following in the destination path

### Technical Debt Identified in Current Code

1. **Duplicated row-to-model mapping** in `get_emails_by_date_range` and `search_emails` (70+ identical lines)
2. **Dead `_row_to_email` method** references columns (`RecordID`, `Subject`, `SenderEmailAddress`) that do not match any query in the codebase
3. **SQL injection surface** in `get_row_count` -- `where_clause` parameter is string-interpolated, not parameterized
4. **`ConnectionError` shadows builtin** -- custom exception name conflicts with Python's `builtins.ConnectionError`
5. **`search_filter.dict()`** on line 211 of `client.py` uses Pydantic v1 API

---

## 5. Recommendations

### Critical (Must Address Before Implementation)

1. **Specify dependency injection for `OutlookClient`.** The plan must define how collaborators are provided. Recommend constructor injection with a `create_client()` factory function.

2. **Extract a shared `OutlookProfile` path resolver.** Both database discovery and source file discovery need the same base path logic. Centralizing this eliminates duplication and makes the library testable with a synthetic data directory.

3. **Define `MessageSourceReader.get_content()` as the single public enrichment method.** Do not expose the raw index to `OutlookClient`. The matching strategy (Message-ID primary, subject+date+sender fallback) is an internal concern of `MessageSourceReader`.

### Important (Should Address)

4. **Use `Literal["preview_only", "message_source"]` for `content_source`** instead of bare `str`. Better type safety, autocomplete, and documentation.

5. **Fix `get_row_count` SQL injection** during the redesign. Use parameterized queries or at minimum validate `table_name` against `get_table_names()`.

6. **Rename `ConnectionError`** to `DatabaseConnectionError` to avoid shadowing the Python builtin. The current code already aliases it as `DBConnectionError` in imports, which shows the name collision is already causing friction.

7. **Add a `MimeContent` intermediate type** returned by `MessageSourceReader`, keeping it independent of the `EmailMessage` Pydantic model. This improves separation of concerns and makes `MessageSourceReader` reusable outside the client context.

### Nice to Have

8. **Consider `os.scandir()` + partial file reads** for index building performance. Reading only the first 4KB of each file for the Message-ID header would significantly reduce I/O.

9. **Provide a `rebuild_index()` method** on `MessageSourceReader` for long-running processes (like the MCP server) that may need to pick up new emails.

10. **Add a `__repr__` to `OutlookClient`** showing configuration (db_path, enrichment enabled, index size). Useful for debugging in MCP server logs.

---

## 6. Ecosystem Fit Assessment

The plan positions `macoutlook` as a composable building block alongside `docextract` and the Outlook MCP server. For this to work well:

- **MCP server integration**: The server needs to control component lifecycle (keep DB connection open, build index once, reuse across requests). Constructor injection is essential for this. The current `auto_connect=True` default fights against server-managed lifecycle.

- **docextract compatibility**: If `docextract` also produces Markdown from documents, ensure the `ContentParser` output format is consistent (same heading style, link format, etc.). Consider whether `ContentParser` should be shared between the two libraries or kept independent.

- **LLM consumption**: The `body_markdown` field with `content_source` provenance is well-designed for LLM consumption. The MCP server can use `content_source` to decide whether to include content or flag it as "preview only" in tool responses.

---

## Summary Verdict

The plan is architecturally sound. The layered design, the enrichment pattern, the singleton removal, and the Pydantic v2 migration are all correct decisions. The main gap is under-specification of dependency management -- how components are created, injected, and their lifecycles managed. Addressing the three critical recommendations (DI specification, shared path resolver, encapsulated enrichment method) will produce a clean, composable library that serves well as a foundation for the MCP server.
