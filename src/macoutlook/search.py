"""Fuzzy matching for sender/recipient search in macoutlook.

Provides word-boundary-aware fuzzy matching that avoids false positives
like "Tom" matching "Thomas". Uses difflib.SequenceMatcher for similarity
scoring with configurable thresholds.

Based on the fuzzy matching approach from Jon Hammant's outlook-connector-package.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher


class FuzzyMatcher:
    """Word-boundary-aware fuzzy matcher for name/email search.

    Matching strategy (in order):
    1. Exact match (case-insensitive)
    2. Word boundary match (query appears as a whole word in text)
    3. Split-and-match (each query word matched independently)

    The word boundary check prevents "Tom" from matching "Thomas".
    """

    def __init__(self, threshold: float = 0.8) -> None:
        """Initialize with similarity threshold.

        Args:
            threshold: Minimum SequenceMatcher ratio for a match (0.0-1.0).
        """
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(f"threshold must be 0.0-1.0, got {threshold}")
        self.threshold = threshold

    def match(self, query: str, text: str) -> float:
        """Score how well query matches text.

        Returns a confidence score between 0.0 (no match) and 1.0 (exact).
        """
        if not query or not text:
            return 0.0

        query_lower = query.lower().strip()
        text_lower = text.lower().strip()

        # 1. Exact match
        if query_lower == text_lower:
            return 1.0

        # 2. Word boundary match — query appears as complete word(s) in text
        pattern = r"\b" + re.escape(query_lower) + r"\b"
        if re.search(pattern, text_lower):
            return 0.95

        # 3. Split-and-match — each query part matched independently
        query_parts = [p for p in query_lower.split() if len(p) >= 2]
        if not query_parts:
            return 0.0

        matched_parts = 0
        for part in query_parts:
            # Check word boundary first
            part_pattern = r"\b" + re.escape(part) + r"\b"
            if re.search(part_pattern, text_lower):
                matched_parts += 1
                continue

            # Fall back to SequenceMatcher for fuzzy comparison
            # Compare against each word in text
            for word in text_lower.split():
                if len(word) < 2:
                    continue
                ratio = SequenceMatcher(None, part, word).ratio()
                if ratio >= self.threshold:
                    matched_parts += 1
                    break

        if not matched_parts:
            return 0.0

        # Require all parts to match for multi-word queries,
        # or at least one for single-word queries
        if len(query_parts) == 1:
            return matched_parts * 0.85
        else:
            match_ratio = matched_parts / len(query_parts)
            if match_ratio < 0.8:
                return 0.0
            return match_ratio * 0.9

    def is_match(self, query: str, text: str) -> bool:
        """Check if query matches text above the threshold."""
        return self.match(query, text) >= self.threshold
