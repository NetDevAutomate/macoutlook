# Performance Review: Full Content Extraction Plan

**Date**: 2026-03-14
**Reviewer**: Performance Oracle
**Plan**: `docs/plans/2026-03-14-feat-macoutlook-full-content-extraction-plan.md`

---

## 1. Performance Summary

The plan introduces five performance-critical operations against a corpus of 53,909 `.olk15MsgSource` files and 32,560 SQLite records. The stated targets (index build <10s, single MIME parse <100ms) are achievable but only if the implementation avoids several traps that the plan does not address. The most dangerous gap is the **content enrichment loop**: iterating 32K DB records and performing per-record file I/O + MIME parsing + HTML-to-Markdown conversion is an O(n) pipeline where each step has high constant cost. Without batching, lazy evaluation, and I/O optimization, the wall-clock time for `get_emails()` with `enrich=True` will exceed 30 minutes on a cold run.

---

## 2. Critical Issues

### 2.1 Index Building: File I/O is the Bottleneck, Not Parsing

**Current plan**: Glob 53,909 files, then open each file and parse the `Message-ID` header.

**Problem**: This is 53,909 `open()` + `read()` syscalls. Python's `glob.glob()` with recursive patterns is itself slow at this scale on macOS APFS (no `d_type` optimization). Then reading even just the first few KB of each file to extract the Message-ID header means ~54K file opens.

**Projected impact**: On a cold filesystem cache (first run after reboot, or large enough working set to exceed unified buffer cache), this will take 20-40 seconds, not <10 seconds. On warm cache it may hit 8-12 seconds.

**Recommendations**:

1. **Use `os.scandir()` recursively instead of `glob.glob()`**. `scandir()` returns `DirEntry` objects with cached `stat` results and avoids the overhead of pattern matching. Build the file list with a simple recursive walk filtering on `.olk15MsgSource` suffix. This alone can be 2-3x faster than `glob.glob("**/*.olk15MsgSource", recursive=True)`.

2. **Read only the header portion of each file**. RFC 2822 headers end at the first blank line (`\r\n\r\n` or `\n\n`). Read a fixed buffer (e.g., 8KB) from each file rather than the entire file. Most Message-ID headers appear within the first 2KB. Use `open(path, 'rb').read(8192)` and search for `Message-ID:` with a byte-level find or a compiled regex on bytes.

3. **Use `os.read()` with file descriptors for minimal overhead**. Avoid Python's buffered I/O layer for the header scan:
   ```
   fd = os.open(path, os.O_RDONLY)
   chunk = os.read(fd, 8192)
   os.close(fd)
   ```
   This eliminates the Python `io.BufferedReader` object creation overhead per file.

4. **Persist the index to disk**. The plan says "cache index for session lifetime" but does not mention persistence. Serialize the `dict[str, Path]` index to a JSON or msgpack file alongside a manifest of file mtimes. On subsequent runs, only re-index files whose mtime changed. This turns a 10-second operation into a <1-second operation for typical use (few new emails between sessions). Use `pathlib.Path.stat().st_mtime_ns` for the manifest.

5. **Consider `concurrent.futures.ThreadPoolExecutor` for the header scan**. File I/O is not CPU-bound; it's syscall-bound. A thread pool with 8-16 workers can overlap the kernel I/O wait across files. Expected speedup: 3-5x on SSD. This brings cold-cache time under 10 seconds.

### 2.2 Content Enrichment Loop: O(n) with High Per-Item Cost

**Current plan**: For each DB record, look up source file by Message-ID, parse MIME, run ContentParser, build Pydantic model.

**Problem**: The plan's `get_emails()` flow (Phase 2, step 2-6) implies enriching ALL returned emails eagerly. If a user calls `get_emails(limit=1000)`, that means 1,000 sequential MIME parses + 1,000 HTML-to-Markdown conversions. At ~50ms per MIME parse and ~20ms per markdownify call, that is ~70 seconds for 1,000 emails. The default limit in the current code is 1,000.

**Recommendations**:

1. **Lazy enrichment via property or method**. Do NOT parse MIME in the `get_emails()` loop. Instead, store the source file path on the model and parse on first access:
   - Return `EmailMessage` objects with `content_source="pending"` and a private `_source_path` attribute
   - Make `body_text`, `body_html`, `body_markdown` computed on first access (use `@cached_property` or a `load_content()` method)
   - This turns a 70-second call into a <2-second call, with content loaded on demand

2. **If eager enrichment is needed, batch it**. Provide an explicit `client.enrich_emails(emails: list[EmailMessage])` method that processes a batch. Use `concurrent.futures.ThreadPoolExecutor` to parallelize file reads + MIME parsing. MIME parsing is CPU-bound (email.message_from_string), so for CPU-heavy workloads, `ProcessPoolExecutor` may be better, but the overhead of serializing email strings across processes likely makes threads preferable here.

3. **Skip HTML-to-Markdown conversion unless requested**. The ContentParser creates BeautifulSoup objects and runs markdownify on every email. This is expensive. Make markdown generation opt-in:
   - `get_emails(content_format="text")` -- only extract text/plain from MIME
   - `get_emails(content_format="markdown")` -- also run markdownify
   - `get_emails(content_format="all")` -- text + html + markdown
   - Default to `"text"` for performance

### 2.3 MIME Parsing: `email.message_from_string()` Allocates the Entire Message

**Current plan**: Use `email.message_from_string()` with `email.policy.default`.

**Problem**: `message_from_string()` reads the entire file into a string, then parses it into a tree of `Message` objects, decoding all MIME parts including attachments. For emails with large attachments (10MB+ PDFs, images), this means allocating 10MB+ of decoded attachment bytes in memory just to extract the text body.

**Recommendations**:

1. **Use `email.message_from_binary_file()` with `email.policy.default`** instead of reading the whole file into a string first. This avoids one copy of the data.

2. **For body extraction only, walk the MIME tree without decoding attachments**. After parsing, iterate `msg.walk()` and only call `part.get_content()` on `text/plain` and `text/html` parts. For attachment metadata, read only `Content-Type`, `Content-Disposition`, and `Content-Length` headers -- never call `get_payload(decode=True)` on attachment parts.

3. **For the `save_attachment()` method, stream rather than load**. The plan says "Re-parses source file, extracts matching MIME part, writes bytes to disk." This means the full MIME message is parsed twice (once for metadata, once for save). Instead, cache the parsed `email.message.Message` object (or at minimum the byte offsets of attachment boundaries) so re-parsing is avoided.

4. **Set a size threshold**. For source files >5MB, consider a streaming MIME parser or at minimum log a warning about memory usage. The stdlib `email` module is not streaming-capable, so for truly large messages, you may need `mailparser` or manual boundary scanning.

### 2.4 SQLite Query: Selecting 46 Columns Unnecessarily

**Current plan**: "Reading 32,560 email records with 46-column table."

**Problem**: The current queries `SELECT ... FROM Mail` explicitly name ~17 columns. The plan adds more fields but should never `SELECT *`. The real issue is that `Message_Preview` (up to 256 chars per row) is loaded for every email even when enrichment will replace it. For 32K rows, that is ~8MB of preview text loaded into Python memory that will be discarded.

**Recommendations**:

1. **Use two query tiers**:
   - **Metadata query** (fast): Select only indexed/small columns (record_id, message_id, subject, sender, timestamps, flags). No `Message_Preview`.
   - **Full query** (when `enrich=False`): Include `Message_Preview` as the content source.

2. **Verify indexes exist**. The plan assumes `Message_TimeReceived` is indexed for the `BETWEEN` clause, but does not verify. Run `PRAGMA index_list('Mail')` and `PRAGMA index_info(...)` to confirm. If `Message_TimeReceived` is not indexed, every date-range query is a full table scan of 32K rows. On the 46-column table, that is slow.

3. **Use `fetchmany()` instead of `fetchall()`**. The current `execute_query()` calls `cursor.fetchall()`, which materializes all rows into Python memory at once. For 32K rows with 17 columns each, this creates ~550K Python objects (sqlite3.Row wrappers). Use an iterator pattern:
   ```
   while rows := cursor.fetchmany(500):
       yield from rows
   ```
   This keeps peak memory bounded regardless of result set size.

### 2.5 Fuzzy Matching: SequenceMatcher is O(n*m) per Comparison

**Current plan**: Use `difflib.SequenceMatcher` for fuzzy sender matching.

**Problem**: `SequenceMatcher.ratio()` has time complexity O(n*m) where n and m are the lengths of the two strings. If fuzzy search scans all 32K sender addresses against a query, and average sender string length is ~30 chars, that is 32,000 * 30 * len(query) character comparisons. For a 12-char query, that is ~11.5 million comparisons. This will take 2-5 seconds in pure Python.

**Recommendations**:

1. **Pre-filter before fuzzy matching**. Use SQL `LIKE` to narrow candidates first:
   - Extract first/last name tokens from the query
   - Run `WHERE sender LIKE '%taylor%' OR sender_name LIKE '%taylor%'`
   - Apply SequenceMatcher only to the reduced candidate set (likely <500 rows)
   - This turns O(32K * n * m) into O(500 * n * m)

2. **Use `SequenceMatcher.quick_ratio()` as a fast pre-filter**. Call `quick_ratio()` first (O(n+m)), and only compute `ratio()` if `quick_ratio()` exceeds threshold - 0.1. This avoids the expensive O(n*m) computation for obvious non-matches.

3. **Consider `rapidfuzz` instead of `difflib`**. `rapidfuzz` is a C-extension library that provides the same SequenceMatcher API but 10-50x faster. It also provides `fuzz.token_sort_ratio` which handles word reordering ("Taylor Andrew" matching "Andrew Taylor") natively. This is a single `uv add rapidfuzz` away and eliminates the performance concern entirely.

4. **Cache the sender corpus**. Build a normalized sender list once (lowercase, stripped) and reuse it across searches within the same session. Do not re-query the database for each fuzzy search call.

---

## 3. Optimization Opportunities

### 3.1 Content Parsing Pipeline is Redundant for Enriched Emails

The current `ContentParser.parse_email_content()` runs BeautifulSoup twice (once in `_clean_html`, once in `_html_to_text`) plus markdownify. For enriched emails where MIME already provides `text/plain`, the text extraction step is unnecessary. Only run `_html_to_markdown()` when markdown output is explicitly requested, and skip `_html_to_text()` entirely when `text/plain` is already available from MIME.

### 3.2 Pydantic Model Construction Overhead

Creating 32K `EmailMessage` Pydantic models with validation is not free. Pydantic v2 is ~5x faster than v1, but model construction with field validators still costs ~10-50 microseconds per instance. For 32K instances, that is 0.3-1.6 seconds.

**Recommendation**: For bulk operations, consider using `model_construct()` (skips validation) when data comes from trusted sources (the SQLite database). Keep full validation for user-facing input and MIME-parsed data.

### 3.3 Index Data Structure Choice

The plan specifies `dict[str, Path]` for the Message-ID index. `Path` objects are heavy (~300 bytes each). For 53K entries, that is ~16MB just for Path objects. Use `dict[str, str]` instead and construct `Path` objects only when accessing specific files.

### 3.4 Streaming CLI Output

The CLI currently materializes all results, formats them, then prints. For large result sets (1,000+ emails), use streaming output -- print each email as it is processed rather than buffering all results in memory. For JSON output, use NDJSON (one JSON object per line) for streaming compatibility.

---

## 4. Scalability Assessment

### 4.1 Data Volume Projections

| Metric | Current | 10x | 100x |
|--------|---------|-----|------|
| DB records | 32K | 320K | 3.2M |
| Source files | 54K | 540K | 5.4M |
| Index build (cold, no optimization) | ~15s | ~150s | ~25min |
| Index build (with persistence + delta) | <1s | <2s | <10s |
| Eager enrichment (1K emails) | ~70s | same | same |
| Lazy enrichment (1K emails, 10 accessed) | <3s | same | same |
| Fuzzy search (no pre-filter) | ~3s | ~30s | ~300s |
| Fuzzy search (SQL pre-filter) | <0.5s | <1s | <5s |

### 4.2 Memory Usage Projections

| Operation | Current Plan | Optimized |
|-----------|-------------|-----------|
| Index in memory (54K entries) | ~20MB (Path objects) | ~8MB (str values) |
| 1K emails fully enriched | ~200MB (MIME + bodies + models) | ~50MB (lazy, only loaded bodies) |
| Full DB query result (32K rows) | ~100MB (fetchall) | ~5MB peak (fetchmany iterator) |

### 4.3 Concurrent User Analysis

Not applicable (single-user desktop library), but the global singleton pattern being removed in Phase 1 is the right call. The current `_db_instance` global would cause corruption under concurrent access.

---

## 5. Recommended Actions (Priority Order)

### P0 -- Must Do (blocks meeting performance targets)

1. **Implement lazy content enrichment**. Do not MIME-parse in the `get_emails()` loop. Store source paths, parse on demand. This is the single highest-impact change.

2. **Persist the file index to disk with delta updates**. Without this, every CLI invocation pays the full 10-second index build cost. Users will perceive the tool as slow.

3. **Read only headers (first 8KB) during index building**. Do not read entire source files just to extract Message-ID.

4. **Pre-filter fuzzy search candidates with SQL LIKE**. Without this, fuzzy search will be perceived as hanging for several seconds.

### P1 -- Should Do (significant performance improvement)

5. **Use `os.scandir()` recursive walk instead of `glob.glob()`** for file discovery.

6. **Use `cursor.fetchmany()` iterator pattern** instead of `fetchall()` in `execute_query()`.

7. **Make markdown conversion opt-in** rather than default. Most consumers want text or HTML, not markdown.

8. **Use `model_construct()` for bulk DB results** where data is trusted.

### P2 -- Nice to Have (polish and future-proofing)

9. **Add `rapidfuzz` as an optional dependency** for 10-50x faster fuzzy matching.

10. **Thread-pool the index build** for 3-5x speedup on cold cache.

11. **Use `dict[str, str]` instead of `dict[str, Path]`** for the index to reduce memory overhead.

12. **Verify SQLite indexes exist** on `Message_TimeReceived` and `Message_MessageID` columns.

---

## 6. Benchmarking Suggestions

Add these benchmarks to the test suite to track performance regressions:

```
# Benchmark 1: Index building
# Target: <10s cold, <1s warm (with persistence)
# Measure: time.perf_counter() around MessageSourceReader.build_index()
# Report: files/second throughput

# Benchmark 2: Single email MIME parse
# Target: <100ms for typical email, <500ms for 5MB email
# Measure: time.perf_counter() around email.message_from_binary_file()
# Report: p50, p95, p99 latencies across 100 sample files

# Benchmark 3: Bulk email retrieval
# Target: <2s for 1000 emails (metadata only), <5s with lazy enrichment setup
# Measure: time.perf_counter() around client.get_emails(limit=1000)
# Report: emails/second throughput, peak memory (tracemalloc)

# Benchmark 4: Fuzzy search
# Target: <1s for single query against full corpus
# Measure: time.perf_counter() around client.search_emails(query, fuzzy=True)
# Report: candidates scanned, matches found, wall-clock time

# Benchmark 5: Content parsing pipeline
# Target: <50ms per email for text extraction, <100ms with markdown
# Measure: time.perf_counter() around ContentParser.parse_email_content()
# Report: p50, p95 latencies, with and without markdown generation
```

Use `pytest-benchmark` for repeatable measurements and `tracemalloc` for memory profiling. Mark benchmarks with `@pytest.mark.benchmark` and exclude from default test runs.

---

## 7. Architecture Recommendation

The plan's current flow is:

```
DB Query --> Loop(Match --> MIME Parse --> Content Parse --> Model Build) --> Return List
```

The recommended flow is:

```
DB Query (metadata only, fetchmany iterator)
  --> Build lightweight EmailMessage with source_path
  --> Return iterator/list of lightweight models

On access (lazy):
  EmailMessage.body_text --> MIME parse source file --> cache result
  EmailMessage.body_markdown --> MIME parse + markdownify --> cache result

Explicit batch:
  client.enrich_emails(emails, format="text", workers=4)
  --> ThreadPoolExecutor: file read + MIME parse per email
  --> Populate body fields in-place
```

This gives users sub-second response for metadata browsing, with content loaded only when needed. The explicit batch method provides a controlled way to pre-load content for export scenarios.
