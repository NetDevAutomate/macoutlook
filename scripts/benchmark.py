#!/usr/bin/env python3
"""Private benchmark script for macoutlook.

NOT published to PyPI — contains queries against local Outlook data.
Run with: uv run python scripts/benchmark.py

Measures:
1. Database connection and email retrieval speed
2. Message source index build time (cold vs warm)
3. Single email enrichment time
4. Batch enrichment throughput
5. Fuzzy search performance
6. Content extraction quality metrics
"""

import time
from datetime import datetime, timedelta

from macoutlook import ContentSource, create_client
from macoutlook.core.message_source import MessageSourceReader
from macoutlook.search import FuzzyMatcher


def timed(label: str):
    """Context manager for timing operations."""
    class Timer:
        def __init__(self):
            self.elapsed = 0.0
        def __enter__(self):
            self.start = time.perf_counter()
            return self
        def __exit__(self, *args):
            self.elapsed = time.perf_counter() - self.start
            print(f"  {label}: {self.elapsed:.3f}s")
    return Timer()


def benchmark_database():
    """Benchmark database operations."""
    print("\n=== Database Operations ===")

    client = create_client(enable_enrichment=False)

    with timed("get_emails(limit=100)") as t:
        emails = client.get_emails(limit=100)
    print(f"    -> {len(emails)} emails ({len(emails)/t.elapsed:.0f} emails/s)")

    with timed("get_emails(limit=1000)") as t:
        emails_1k = client.get_emails(limit=1000)
    print(f"    -> {len(emails_1k)} emails ({len(emails_1k)/t.elapsed:.0f} emails/s)")

    with timed("get_emails(limit=5000)") as t:
        emails_5k = client.get_emails(limit=5000)
    print(f"    -> {len(emails_5k)} emails ({len(emails_5k)/t.elapsed:.0f} emails/s)")

    with timed("search_emails(query='meeting')"):
        results = client.search_emails(query="meeting", limit=100)
    print(f"    -> {len(results)} results")

    with timed("get_database_info()"):
        info = client.get_database_info()
    print(f"    -> {info.get('mail_count', '?')} emails in DB")

    with timed("get_calendar_events(limit=100)"):
        events = client.get_calendar_events(limit=100)
    print(f"    -> {len(events)} events")

    return emails


def benchmark_index():
    """Benchmark message source index operations."""
    print("\n=== Message Source Index ===")

    reader = MessageSourceReader()
    print(f"  Sources dir: {reader.sources_dir}")
    print(f"  Exists: {reader.sources_dir.exists()}")

    if not reader.sources_dir.exists():
        print("  SKIPPED: sources directory not found")
        return None

    # Warm load (from cache)
    with timed("Warm index load (from cache)") as t:
        count = reader.build_index()
    print(f"    -> {count} entries")

    if count == 0:
        print("  No cached index. Run 'macoutlook build-index' first.")
        return None

    return reader


def benchmark_enrichment(emails, reader):
    """Benchmark email enrichment."""
    print("\n=== Email Enrichment ===")

    if reader is None or reader.index_size == 0:
        print("  SKIPPED: no index available")
        return

    from macoutlook.core.enricher import EmailEnricher

    enricher = EmailEnricher(source_reader=reader)

    # Single enrichment
    matched = 0
    enriched_count = 0
    total_text_chars = 0
    total_html_chars = 0
    total_attachments = 0

    sample = emails[:50]
    with timed(f"Enrich {len(sample)} emails") as t:
        for email in sample:
            result = enricher.enrich(email.message_id, markdown=False)
            if result.source == ContentSource.MESSAGE_SOURCE:
                enriched_count += 1
                total_text_chars += len(result.body_text or "")
                total_html_chars += len(result.body_html or "")
                total_attachments += len(result.attachments)

    print(f"    -> {enriched_count}/{len(sample)} enriched ({enriched_count/len(sample)*100:.0f}%)")
    if enriched_count > 0:
        print(f"    -> avg text: {total_text_chars/enriched_count:.0f} chars")
        print(f"    -> avg html: {total_html_chars/enriched_count:.0f} chars")
        print(f"    -> total attachments: {total_attachments}")
        print(f"    -> {t.elapsed/len(sample)*1000:.0f}ms per email")


def benchmark_fuzzy_search():
    """Benchmark fuzzy matching performance."""
    print("\n=== Fuzzy Search ===")

    client = create_client(enable_enrichment=False)

    with timed("search_emails(sender='Taylor', fuzzy=False)"):
        exact = client.search_emails(sender="Taylor", limit=100)
    print(f"    -> {len(exact)} results")

    with timed("search_emails(sender='Taylor', fuzzy=True)"):
        fuzzy = client.search_emails(sender="Taylor", fuzzy=True, limit=100)
    print(f"    -> {len(fuzzy)} results")

    # Matcher micro-benchmark
    matcher = FuzzyMatcher()
    names = ["Andy Taylor", "Andrew Taylor", "A. Taylor", "Thomas Anderson",
             "Jane Smith", "Taylor Swift", "Bob Taylor-Jones"]

    with timed(f"FuzzyMatcher.match() x {len(names)*1000}"):
        for _ in range(1000):
            for name in names:
                matcher.match("Andy Taylor", name)


def benchmark_content_quality(emails):
    """Report content extraction quality metrics."""
    print("\n=== Content Quality Metrics ===")

    total = len(emails)
    with_preview = sum(1 for e in emails if e.preview)
    preview_lengths = [len(e.preview) for e in emails if e.preview]
    with_message_id = sum(1 for e in emails if e.message_id)

    print(f"  Emails sampled: {total}")
    print(f"  With preview: {with_preview} ({with_preview/total*100:.1f}%)")
    print(f"  With Message-ID: {with_message_id} ({with_message_id/total*100:.1f}%)")
    if preview_lengths:
        print(f"  Preview length: avg={sum(preview_lengths)/len(preview_lengths):.0f}, "
              f"min={min(preview_lengths)}, max={max(preview_lengths)}")


def main():
    print("macoutlook Benchmark")
    print("=" * 50)
    print(f"Timestamp: {datetime.now().isoformat()}")

    emails = benchmark_database()
    reader = benchmark_index()
    if emails:
        benchmark_enrichment(emails, reader)
        benchmark_content_quality(emails)
    benchmark_fuzzy_search()

    print("\n" + "=" * 50)
    print("Benchmark complete.")


if __name__ == "__main__":
    main()
