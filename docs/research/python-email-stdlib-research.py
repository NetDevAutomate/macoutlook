"""
Python stdlib `email` Package -- Comprehensive Research Findings
================================================================

Research conducted: 2026-03-14
Sources: Python 3.14 official docs (Context7), CPython source

Context: Parsing .olk15MsgSource files (RFC 2822 MIME format) from Outlook
for Mac to extract email bodies, HTML content, and attachments.

This file is executable pseudocode / reference patterns. Run sections
individually or use as a copy-paste reference.
"""

# =============================================================================
# 1. PARSING: message_from_string() vs message_from_bytes()
# =============================================================================
#
# RECOMMENDATION: Use BytesParser / message_from_bytes() with policy=email.policy.default
#
# WHY:
# - .olk15MsgSource files are RFC 2822 MIME, which is fundamentally a *bytes*
#   format (headers are ASCII, body can be any charset via Content-Transfer-Encoding)
# - message_from_string() / Parser requires text-mode input. If the file contains
#   non-ASCII bytes in the body (common with quoted-printable/base64), reading as
#   text with the wrong encoding silently corrupts data.
# - message_from_bytes() / BytesParser handles the raw bytes correctly, letting the
#   email package decode each part according to its declared charset.
#
# CRITICAL: Both convenience functions default to policy=compat32 (returns legacy
# Message objects). You MUST pass policy=email.policy.default to get EmailMessage.

from email import policy
from email.parser import BytesParser

def parse_olk15_file(file_path: str):
    """Parse an .olk15MsgSource file into an EmailMessage object."""
    with open(file_path, 'rb') as fp:
        msg = BytesParser(policy=policy.default).parse(fp)
    return msg

# Equivalent convenience function form:
import email
def parse_olk15_bytes(raw_bytes: bytes):
    """Parse raw bytes into an EmailMessage."""
    return email.message_from_bytes(raw_bytes, policy=policy.default)

# IF you truly have a string (already decoded text), use Parser/message_from_string:
from email.parser import Parser
def parse_from_string(text: str):
    """Only use if data is genuinely a Python str, not bytes read from disk."""
    return Parser(policy=policy.default).parsestr(text)

# NOTE: If .olk15MsgSource files are UTF-8 text files (not raw MIME bytes),
# then reading as text and using Parser is acceptable. But MIME files from
# Outlook are almost certainly raw bytes -- use BytesParser.


# =============================================================================
# 2. POLICIES: email.policy.default vs email.policy.compat32
# =============================================================================
#
# ALWAYS USE policy.default FOR NEW CODE.
#
# Key differences:
#
# | Aspect                  | compat32 (legacy)              | default (modern)                |
# |-------------------------|--------------------------------|---------------------------------|
# | Message class           | email.message.Message          | email.message.EmailMessage      |
# | Header access           | Returns raw strings            | Returns parsed header objects   |
# | Unicode handling        | Manual decode_header() needed  | Automatic unicode conversion    |
# | get_body()              | NOT AVAILABLE                  | Available (finds best body)     |
# | iter_parts()            | NOT AVAILABLE                  | Available (iterate sub-parts)   |
# | iter_attachments()      | NOT AVAILABLE                  | Available (skip body parts)     |
# | get_content()           | NOT AVAILABLE                  | Available (auto-decodes text)   |
# | Content-Transfer-Enc    | Manual get_payload(decode=True) | Automatic via get_content()    |
# | Charset handling        | Manual                         | Automatic                       |
# | Default behavior        | Bug-compatible with Python 2   | RFC-compliant, modern           |
#
# The modern API (EmailMessage + policy.default) provides:
# - get_body(preferencelist=('related', 'html', 'plain')) -- find the "main" content
# - iter_parts() -- iterate immediate children of multipart
# - iter_attachments() -- skip body parts, return only attachments
# - get_content() -- auto-decode content (text -> str, binary -> bytes)
# - is_attachment() -- check Content-Disposition
#
# Pre-defined policy instances:
#   policy.default    -- EmailPolicy with standard defaults
#   policy.SMTP       -- linesep='\r\n' (for sending)
#   policy.SMTPUTF8   -- SMTP + utf8=True
#   policy.HTTP       -- max_line_length=None
#   policy.strict     -- default + raise_on_defect=True
#   policy.compat32   -- legacy Compat32 policy (AVOID)


# =============================================================================
# 3. WALKING MULTIPART MESSAGES
# =============================================================================
#
# Three approaches, from most to least automated:
#
# APPROACH A (BEST): Use get_body() + iter_attachments() [EmailMessage only]
# APPROACH B: Use walk() for full tree traversal
# APPROACH C: Use iter_parts() for one level at a time

# --- APPROACH A: High-level API (recommended for most use cases) ---

def extract_content_modern(msg):
    """
    Extract text body, HTML body, and attachments using the modern API.
    Requires parsing with policy=email.policy.default.
    """
    # Get the "best" body part -- tries related, then html, then plain
    # For just text: get_body(preferencelist=('plain',))
    # For just HTML: get_body(preferencelist=('html',))
    body_plain = msg.get_body(preferencelist=('plain',))
    body_html = msg.get_body(preferencelist=('html',))

    text_content = None
    html_content = None

    if body_plain:
        # get_content() auto-decodes: handles charset + transfer encoding
        # For text parts, returns a unicode str
        text_content = body_plain.get_content()

    if body_html:
        html_content = body_html.get_content()

    # Get all attachments (skips body parts automatically)
    attachments = []
    # iter_attachments() only works on multipart messages
    if msg.is_multipart():
        for part in msg.iter_attachments():
            attachments.append({
                'filename': part.get_filename(),
                'content_type': part.get_content_type(),
                'size': len(part.get_content()),  # decoded content
                'data': part.get_content(),  # bytes for non-text, str for text
            })

    return text_content, html_content, attachments


# --- APPROACH B: walk() for full tree traversal ---

def extract_content_walk(msg):
    """
    Walk the full MIME tree. Works with both Message and EmailMessage.
    walk() is depth-first, visiting every part including containers.
    """
    text_parts = []
    html_parts = []
    attachments = []

    for part in msg.walk():
        content_type = part.get_content_type()
        content_disposition = part.get_content_disposition()

        # Skip multipart containers -- they're just wrappers
        if part.get_content_maintype() == 'multipart':
            continue

        # Check if it's an attachment
        if content_disposition == 'attachment':
            # get_payload(decode=True) returns bytes, handling base64/QP decoding
            data = part.get_payload(decode=True)
            attachments.append({
                'filename': part.get_filename(),
                'content_type': content_type,
                'size': len(data) if data else 0,
                'data': data,
            })
            continue

        # Inline or no disposition -- treat as body content
        if content_type == 'text/plain':
            payload = part.get_payload(decode=True)
            charset = part.get_content_charset() or 'utf-8'
            text_parts.append(payload.decode(charset, errors='replace'))

        elif content_type == 'text/html':
            payload = part.get_payload(decode=True)
            charset = part.get_content_charset() or 'utf-8'
            html_parts.append(payload.decode(charset, errors='replace'))

        else:
            # Other inline content (images, etc.) -- treat as attachment
            data = part.get_payload(decode=True)
            if data:
                attachments.append({
                    'filename': part.get_filename(),
                    'content_type': content_type,
                    'size': len(data),
                    'data': data,
                })

    return '\n'.join(text_parts), '\n'.join(html_parts), attachments


# --- APPROACH C: iter_parts() for one-level traversal ---
# Useful when you need to handle multipart/alternative vs multipart/mixed
# differently (e.g., pick the best alternative rather than collecting all)

def extract_content_structured(msg):
    """Handle multipart/alternative and multipart/mixed correctly."""
    if not msg.is_multipart():
        # Simple message, single part
        ct = msg.get_content_type()
        content = msg.get_content()  # auto-decoded (requires policy.default)
        return content if ct == 'text/plain' else None, \
               content if ct == 'text/html' else None, []

    maintype = msg.get_content_type()

    if maintype == 'multipart/alternative':
        # Pick the best alternative (last one is usually richest)
        # Or use get_body() which handles this automatically
        text = html = None
        for part in msg.iter_parts():
            if part.get_content_type() == 'text/plain':
                text = part.get_content()
            elif part.get_content_type() == 'text/html':
                html = part.get_content()
        return text, html, []

    elif maintype == 'multipart/mixed':
        # First part(s) are body, rest are attachments
        text = html = None
        attachments = []
        for part in msg.iter_parts():
            if part.get_content_type() == 'multipart/alternative':
                # Recurse into alternative
                t, h, _ = extract_content_structured(part)
                text = text or t
                html = html or h
            elif part.is_attachment():
                attachments.append(part)
            elif part.get_content_type() == 'text/plain' and text is None:
                text = part.get_content()
            elif part.get_content_type() == 'text/html' and html is None:
                html = part.get_content()
            else:
                attachments.append(part)
        return text, html, attachments

    # Fallback: walk everything
    return extract_content_walk(msg)


# =============================================================================
# 4. CONTENT DECODING
# =============================================================================
#
# The email package handles Content-Transfer-Encoding automatically in two ways:
#
# METHOD 1 (Modern API -- preferred):
#   part.get_content()
#   - For text/* parts: returns str (unicode), auto-decodes charset + CTE
#   - For other parts: returns bytes, auto-decodes CTE (base64/QP)
#   - Uses the policy's content_manager (raw_data_manager by default)
#   - Errors parameter: get_content(errors='replace') -- default is 'replace'
#
# METHOD 2 (Legacy API -- still works):
#   part.get_payload(decode=True)
#   - Returns bytes after decoding Content-Transfer-Encoding
#   - Handles: quoted-printable, base64 (anything else returns raw payload)
#   - You must then decode charset yourself:
#       charset = part.get_content_charset() or 'utf-8'
#       text = payload.decode(charset, errors='replace')
#
# CHARSET DETECTION:
#   part.get_content_charset()  -> returns charset param from Content-Type header
#   part.get_charsets()         -> list of charsets for all parts (multipart)
#   If None, common fallbacks: 'utf-8', 'ascii', 'latin-1'
#
# CONTENT-TRANSFER-ENCODING VALUES HANDLED:
#   - 'base64'           -> decoded automatically
#   - 'quoted-printable' -> decoded automatically
#   - '7bit', '8bit'     -> returned as-is (already readable)
#   - 'binary'           -> returned as-is
#   - Missing header     -> returned as-is

def decode_part_safely(part) -> str:
    """Robustly decode a text MIME part to a Python string."""
    # Modern API (requires policy.default):
    try:
        return part.get_content()  # Returns str for text parts
    except (KeyError, LookupError, UnicodeDecodeError):
        pass

    # Fallback: legacy API
    payload = part.get_payload(decode=True)
    if payload is None:
        return ''

    # Try declared charset first
    charset = part.get_content_charset()
    if charset:
        try:
            return payload.decode(charset, errors='replace')
        except (LookupError, UnicodeDecodeError):
            pass

    # Fallback charset chain
    for enc in ('utf-8', 'latin-1', 'ascii'):
        try:
            return payload.decode(enc, errors='replace')
        except (LookupError, UnicodeDecodeError):
            continue

    # Nuclear option: latin-1 never fails (all byte values are valid)
    return payload.decode('latin-1', errors='replace')


# =============================================================================
# 5. ATTACHMENT EXTRACTION
# =============================================================================
#
# Key methods for attachment metadata:
#
#   part.get_filename(failobj=None)
#     - Returns filename from Content-Disposition header's 'filename' param
#     - Falls back to Content-Type header's 'name' param
#     - Returns failobj if neither found
#     - WARNING: Filenames from emails are UNTRUSTED INPUT -- sanitize!
#
#   part.get_content_type()
#     - Returns 'maintype/subtype' string, always lowercase
#     - Defaults to 'text/plain' if missing
#
#   part.is_attachment()
#     - True if Content-Disposition value is 'attachment'
#     - False for 'inline' or missing header
#
#   part.get_content_disposition()
#     - Returns 'inline', 'attachment', or None
#
#   len(part.get_payload(decode=True))  or  len(part.get_content())
#     - Size of decoded content in bytes/chars

import os
import re

def sanitize_filename(filename: str | None) -> str:
    """Sanitize a filename from an email attachment."""
    if not filename:
        return 'unnamed_attachment'

    # Remove path separators to prevent directory traversal
    filename = os.path.basename(filename)

    # Remove null bytes and other control characters
    filename = re.sub(r'[\x00-\x1f\x7f]', '', filename)

    # Replace potentially dangerous characters
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)

    # Limit length
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:255 - len(ext)] + ext

    return filename or 'unnamed_attachment'


def extract_attachments(msg):
    """Extract all attachments from an EmailMessage with full metadata."""
    attachments = []

    if not msg.is_multipart():
        return attachments

    for part in msg.iter_attachments():
        content = part.get_content()  # bytes for non-text, str for text

        attachment = {
            'filename': sanitize_filename(part.get_filename()),
            'content_type': part.get_content_type(),
            'disposition': part.get_content_disposition(),
            'charset': part.get_content_charset(),
            'size': len(content) if content else 0,
            'data': content,
        }
        attachments.append(attachment)

    return attachments


# Using walk() approach (works with compat32 Message too):
def extract_attachments_walk(msg):
    """Extract attachments using walk() -- works with any policy."""
    attachments = []

    for part in msg.walk():
        if part.get_content_maintype() == 'multipart':
            continue

        disposition = part.get_content_disposition()
        if disposition != 'attachment':
            # Also catch inline non-text content as de facto attachments
            if disposition == 'inline' and part.get_content_maintype() != 'text':
                pass  # treat as attachment
            else:
                continue

        data = part.get_payload(decode=True)
        if data is None:
            continue

        attachments.append({
            'filename': sanitize_filename(part.get_filename()),
            'content_type': part.get_content_type(),
            'size': len(data),
            'data': data,
        })

    return attachments


# =============================================================================
# 6. ERROR HANDLING
# =============================================================================
#
# The email package is LENIENT BY DEFAULT. It almost never raises exceptions
# during parsing. Instead, it records "defects" on message objects.
#
# === Exceptions (rarely raised during parsing) ===
#
# email.errors.MessageError          -- base class for all email exceptions
# email.errors.MessageParseError     -- base for parser exceptions
# email.errors.HeaderParseError      -- malformed headers (set_boundary on unknown CT)
# email.errors.MultipartConversionError -- misuse of attach() on non-multipart
# email.errors.HeaderWriteError      -- serialization issues (non-ASCII in compat32)
#
# === Defects (recorded on message objects, not raised) ===
#
# These are found on msg.defects (a list). Each is a MessageDefect subclass:
#
# NoBoundaryInMultipartDefect     -- multipart with no boundary parameter
# StartBoundaryNotFoundDefect     -- declared boundary never found
# CloseBoundaryNotFoundDefect     -- start found but no end boundary
# FirstHeaderLineIsContinuationDefect -- first header is a continuation line
# MisplacedEnvelopeHeaderDefect   -- envelope header in wrong position
# MissingHeaderBodySeparatorDefect -- no blank line between headers and body
# MultipartInvariantViolationDefect -- multipart but is_multipart() is False
# InvalidMultipartContentTransferEncodingDefect -- bad CTE on multipart
# UndecodableBytesDefect          -- bytes that can't be decoded
# InvalidBase64PaddingDefect      -- wrong base64 padding (padding added to fix)
# InvalidBase64CharactersDefect   -- non-base64 chars (chars ignored)
# InvalidBase64LengthDefect       -- bad base64 block length (kept as-is!)
#
# === Policy control ===
#
# raise_on_defect=False (default): defects silently recorded on msg.defects
# raise_on_defect=True:  defects raised as exceptions immediately
#
# policy.strict = policy.default + raise_on_defect=True
# You can combine: my_policy = policy.default + policy.strict

from email import errors as email_errors

def parse_email_robust(file_path: str):
    """Parse an email file with comprehensive error handling."""
    try:
        with open(file_path, 'rb') as fp:
            msg = BytesParser(policy=policy.default).parse(fp)
    except email_errors.MessageParseError as e:
        # Extremely rare -- parser is very lenient
        raise ValueError(f"Failed to parse email: {e}") from e
    except (OSError, IOError) as e:
        raise FileNotFoundError(f"Cannot read file: {e}") from e

    # Check for defects (malformed email that was parsed leniently)
    if msg.defects:
        # Log defects but don't fail -- the parser recovered from them
        for defect in msg.defects:
            print(f"WARNING: Email defect: {type(defect).__name__}: {defect}")

    # Also check sub-parts for defects
    for part in msg.walk():
        if part.defects:
            for defect in part.defects:
                print(f"WARNING: Part defect ({part.get_content_type()}): "
                      f"{type(defect).__name__}: {defect}")

    return msg


# For STRICT parsing (reject malformed emails):
def parse_email_strict(file_path: str):
    """Parse with strict policy -- raises on any defect."""
    strict_policy = policy.default + policy.strict  # raise_on_defect=True
    try:
        with open(file_path, 'rb') as fp:
            msg = BytesParser(policy=strict_policy).parse(fp)
        return msg
    except email_errors.MessageDefect as e:
        raise ValueError(f"Malformed email: {type(e).__name__}: {e}") from e


# === Common exception patterns you'll encounter ===

def safe_get_content(part) -> str | bytes | None:
    """Safely extract content from a MIME part."""
    try:
        return part.get_content()
    except KeyError:
        # Raised when content type has no registered handler
        # (e.g., calling get_content() on a multipart container)
        return None
    except LookupError:
        # Unknown charset in Content-Type header
        # Fall back to raw bytes
        return part.get_payload(decode=True)
    except UnicodeDecodeError:
        # Charset declared but content doesn't match
        payload = part.get_payload(decode=True)
        if payload:
            return payload.decode('utf-8', errors='replace')
        return None


# =============================================================================
# 7. COMPLETE ROBUST PARSER (recommended pattern for pyoutlook-db)
# =============================================================================

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ParsedEmail:
    """Structured representation of a parsed email."""
    subject: str = ''
    from_addr: str = ''
    to_addrs: list[str] = field(default_factory=list)
    cc_addrs: list[str] = field(default_factory=list)
    date: str = ''
    message_id: str = ''
    text_body: str | None = None
    html_body: str | None = None
    attachments: list[dict] = field(default_factory=list)
    defects: list[str] = field(default_factory=list)


def parse_olk15_message(file_path: str | Path) -> ParsedEmail:
    """
    Parse an .olk15MsgSource file into a structured ParsedEmail.

    Uses BytesParser with modern policy for robust RFC 2822 MIME parsing.
    """
    result = ParsedEmail()
    file_path = Path(file_path)

    # Parse the raw MIME bytes
    try:
        with open(file_path, 'rb') as fp:
            msg = BytesParser(policy=policy.default).parse(fp)
    except email_errors.MessageParseError as e:
        result.defects.append(f"Parse error: {e}")
        return result
    except OSError as e:
        result.defects.append(f"File error: {e}")
        return result

    # Record any defects from lenient parsing
    for defect in msg.defects:
        result.defects.append(f"{type(defect).__name__}: {defect}")

    # Extract headers (modern policy returns proper unicode automatically)
    result.subject = str(msg.get('Subject', ''))
    result.from_addr = str(msg.get('From', ''))
    result.message_id = str(msg.get('Message-ID', ''))
    result.date = str(msg.get('Date', ''))

    # To and CC can have multiple addresses
    to_header = msg.get('To', '')
    if to_header:
        # With policy.default, this is a parsed header object
        result.to_addrs = [str(addr).strip() for addr in str(to_header).split(',')]

    cc_header = msg.get('Cc', '')
    if cc_header:
        result.cc_addrs = [str(addr).strip() for addr in str(cc_header).split(',')]

    # Extract body content using the high-level API
    if not msg.is_multipart():
        # Simple single-part message
        ct = msg.get_content_type()
        content = safe_get_content(msg)
        if content is not None:
            if ct == 'text/html':
                result.html_body = str(content)
            else:
                result.text_body = str(content)
    else:
        # Multipart -- use get_body() for the main content
        plain_part = msg.get_body(preferencelist=('plain',))
        if plain_part:
            content = safe_get_content(plain_part)
            if content is not None:
                result.text_body = str(content)

        html_part = msg.get_body(preferencelist=('html',))
        if html_part:
            content = safe_get_content(html_part)
            if content is not None:
                result.html_body = str(content)

        # Extract attachments
        try:
            for part in msg.iter_attachments():
                data = safe_get_content(part)
                if data is not None:
                    result.attachments.append({
                        'filename': sanitize_filename(part.get_filename()),
                        'content_type': part.get_content_type(),
                        'size': len(data) if data else 0,
                    })
        except TypeError:
            # iter_attachments() can raise TypeError on malformed multipart
            result.defects.append("Failed to iterate attachments")

    return result


# =============================================================================
# 8. COMMON MIME STRUCTURES (reference)
# =============================================================================
#
# Simple text email:
#   text/plain
#
# HTML email with text fallback:
#   multipart/alternative
#     text/plain
#     text/html
#
# HTML email with inline images:
#   multipart/related
#     text/html
#     image/png (Content-ID: <cid>)
#
# Email with attachments:
#   multipart/mixed
#     text/plain (or multipart/alternative)
#     application/pdf (Content-Disposition: attachment)
#
# Complex email (text + HTML + inline images + attachments):
#   multipart/mixed
#     multipart/alternative
#       text/plain
#       multipart/related
#         text/html
#         image/png (inline)
#     application/pdf (attachment)
#     application/zip (attachment)
#
# get_body() handles all these structures automatically when using
# policy.default + EmailMessage.


# =============================================================================
# 9. PERFORMANCE NOTES
# =============================================================================
#
# - BytesParser reads the entire file into memory. For very large emails with
#   big attachments, this is unavoidable (MIME format requires full parse).
# - FeedParser/BytesFeedParser allows incremental parsing but still builds
#   the full object tree in memory.
# - For headersonly=True parsing (skip body), use:
#     BytesParser(policy=policy.default).parse(fp, headersonly=True)
#   This is much faster when you only need headers.
# - get_payload(decode=True) decodes base64/QP in memory -- for large
#   attachments this doubles memory usage temporarily.
# - walk() is a generator -- memory efficient for iteration.


# =============================================================================
# 10. KEY GOTCHAS
# =============================================================================
#
# 1. DEFAULT POLICY IS COMPAT32: Every convenience function (message_from_bytes,
#    message_from_string) defaults to compat32. You MUST pass policy=policy.default.
#
# 2. get_body() CAN RETURN None: If no part matches the preference list.
#    Always check: `body = msg.get_body(...)  # might be None`
#
# 3. get_content() ON MULTIPART RAISES KeyError: Don't call on container parts.
#
# 4. get_payload(decode=True) RETURNS bytes, NOT str: You must decode charset.
#    get_content() returns str for text parts -- prefer it.
#
# 5. FILENAMES ARE UNTRUSTED: Always sanitize before writing to disk.
#    Attackers can use path traversal: "../../etc/passwd"
#
# 6. InvalidBase64LengthDefect KEEPS RAW DATA: Unlike padding/character defects
#    where the parser recovers, length defects mean the base64 block is kept
#    encoded. Your attachment data will be base64 text, not decoded bytes.
#
# 7. CHARSET CAN BE WRONG: Emails frequently lie about their charset.
#    Always use errors='replace' when decoding.
#
# 8. iter_attachments() SKIPS "BODY" PARTS: It skips the first text/plain,
#    text/html, multipart/related, and multipart/alternative unless they have
#    Content-Disposition: attachment. This is usually what you want.
#
# 9. MESSAGE-ID HEADER: Use msg['Message-ID'], not msg['Message-Id'] -- the
#    email package is case-insensitive for header names, but be consistent.
#
# 10. DEFECTS ARE PER-PART: Check msg.defects AND each part's .defects
#     attribute separately. A defect on a nested part won't appear on the root.
