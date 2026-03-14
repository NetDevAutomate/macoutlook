---
date: 2026-03-14
topic: full-content-extraction
attribution: Jon Hammant - .olk15MsgSource discovery and extraction approach
---

# Full Email Content Extraction via .olk15MsgSource Integration

## What We're Building

Integrate full email content extraction into pyoutlook-db by reading `.olk15MsgSource` files
(RFC 2822 MIME format) from macOS Outlook's data directory. This replaces the current
`Message_Preview` limitation (~256 chars, 0.1% extraction ratio) with complete email bodies
(85.8%+ extraction ratio, 858x improvement).

The enhancement originated from Jon Hammant's work in the `outlook-connector-package`
(`getEmails_FULL_ENHANCED.py`), which demonstrated that `.olk15MsgSource` files in
`~/Library/Group Containers/UBF8T346G9.Office/Outlook/Outlook 15 Profiles/Main Profile/Data/Message Sources/`
contain full RFC 2822 MIME email content.

This is a **clean redesign** — backward compatibility with the current API is not required.

## Why This Approach

**Approaches considered:**

1. **Port script as utility** — Rejected. The standalone script architecture doesn't fit the
   library's layered design and would create a second code path.
2. **Hybrid enrichment layer** — Rejected. Optional enrichment adds complexity without benefit
   since full content is always preferable when available.
3. **Full library integration** — **Chosen.** Add a `MessageSourceReader` to the core layer so
   `OutlookClient` transparently enriches emails with full content. All consumers (CLI, API)
   get full bodies automatically.

## Key Decisions

### 1. MIME Parsing: Python stdlib `email` module
- **Rationale**: `email.message_from_string()` with `email.policy.default` handles all MIME
  edge cases — multipart boundaries, encodings (quoted-printable, base64), content type
  negotiation. Far more robust than the regex-based 3-method cascade in the original script.

### 2. DB-to-File Matching: Multi-strategy cascade
- **Strategy**: Message-ID header match first → subject+date+sender match → fuzzy subject match
- **Rationale**: Message-ID is the canonical email identifier and should achieve near-100% match.
  Fallback strategies catch edge cases where Message-ID is missing or malformed. This should
  push extraction well above the original 85.8%.

### 3. Indexing: Lazy with caching
- **Rationale**: Build the .olk15MsgSource file index on first email content request, cache for
  the session. Avoids startup cost when user only wants calendar data or metadata. Can be
  pre-warmed explicitly via API if needed.

### 4. EmailMessage Model: Clean redesign
```python
class EmailMessage(BaseModel):
    # Metadata (from DB)
    message_id: str
    subject: str
    sender: str
    sender_name: str | None
    recipients: list[str]
    cc_recipients: list[str]
    timestamp: datetime
    has_attachments: bool

    # Content (richest available)
    body_text: str | None       # Plain text (from MIME text/plain or converted)
    body_html: str | None       # Full HTML (from MIME text/html)
    body_markdown: str | None   # Generated via ContentParser from HTML
    preview: str | None         # DB preview snippet (useful for list views)

    # Attachments
    attachments: list[AttachmentInfo]  # Metadata extracted from MIME parts

    # Provenance
    content_source: str         # "message_source" | "database" | "preview_only"
```

- **Rationale**: Separates preview (always available) from body_* fields (full content when
  .olk15MsgSource exists). `content_source` provides transparency about data quality.
  All three body formats (text, html, markdown) available simultaneously — consumers pick
  what they need.

### 5. Attachments: Metadata + save-to-disk method
- **Model**: `AttachmentInfo` with filename, size, content_type fields
- **Method**: `save_attachment(email, attachment_name, dest_path)` on client
- **Rationale**: Maintains clean separation with the `docextract` package. pyoutlook-db
  extracts and saves attachment files; docextract handles parsing them to text. No coupling
  between the two libraries.

### 6. Fuzzy Matching: Integrated into search API
- **Rationale**: Word-boundary-aware fuzzy matching (from Jon's script) is valuable for
  sender/recipient search — finding "Andy Taylor" when DB has "Andrew Taylor". Integrated
  as a search option rather than external concern.

### 7. Attribution: Jon Hammant
- README acknowledgements section
- Module docstring in the message source reader
- CONTRIBUTORS.md file

### 8. Package Rename: pyoutlook-db -> macoutlook
- **PyPI name**: `macoutlook` (confirmed available on PyPI)
- **Import**: `from macoutlook import OutlookClient`
- **CLI**: `macoutlook` (replaces `pyoutlook-db`)
- **Rationale**: Signals macOS-only scope upfront. The old name "pyoutlook-db" is misleading
  since the library now reads both the SQLite database AND .olk15MsgSource files directly.

### 9. PyPI Publishing: GitHub Actions with manual trigger
- **CI**: Auto-run tests, ruff, mypy on every PR
- **Publish**: Manual `workflow_dispatch` trigger with version input
- **Auth**: PyPI Trusted Publishers (OIDC) — no API tokens needed, GitHub Actions authenticates
  directly with PyPI via OpenID Connect
- **Rationale**: Maximum control over releases. Tests gate quality automatically; human decides
  when to publish. OIDC is the most secure auth method — no secrets to rotate or leak.

## Architecture

```
OutlookClient
├── OutlookDatabase          (SQLite: metadata + preview)
├── MessageSourceReader      (NEW: .olk15MsgSource files)
│   ├── File discovery       (glob for *.olk15MsgSource)
│   ├── MIME parsing         (stdlib email module)
│   ├── Index building       (lazy, cached: Message-ID → file path)
│   └── Content extraction   (text/plain, text/html, attachments)
├── ContentParser            (HTML → text/markdown conversion)
└── FuzzyMatcher             (NEW: word-boundary + SequenceMatcher search)
```

**Flow**: DB query → get metadata + preview → match to .olk15MsgSource via Message-ID →
parse MIME → populate body_text/body_html → run ContentParser for body_markdown → return
enriched EmailMessage.

## Open Questions

- **Message-ID availability**: Does the Outlook SQLite DB store Message-ID headers? If not,
  we'll need to extract it from .olk15MsgSource files and use subject+date+sender as the
  primary matching strategy against DB records.
- **Performance at scale**: How many .olk15MsgSource files exist in a typical mailbox? Index
  building time for 50K+ files needs benchmarking.
- **File format stability**: Are .olk15MsgSource files always RFC 2822 MIME, or do some use
  a different format? Need to test with a variety of email types (calendar invites, encrypted,
  S/MIME signed).
- **PyPI Trusted Publisher setup**: Requires configuring the publisher on PyPI before the first
  publish. Need to set up the GitHub repo as a trusted publisher in PyPI account settings.

## Next Steps

-> `/workflows:plan` for implementation details
