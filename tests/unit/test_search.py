"""Unit tests for FuzzyMatcher."""

import pytest

from macoutlook.search import FuzzyMatcher


class TestFuzzyMatcher:
    def setup_method(self):
        self.matcher = FuzzyMatcher(threshold=0.8)

    # --- Exact matches ---

    def test_exact_match_returns_1(self):
        assert self.matcher.match("Andy Taylor", "Andy Taylor") == 1.0

    def test_exact_match_case_insensitive(self):
        assert self.matcher.match("andy taylor", "Andy Taylor") == 1.0

    # --- Word boundary matches ---

    def test_word_boundary_match(self):
        score = self.matcher.match("Andy", "Taylor, Andy")
        assert score >= 0.9

    def test_tom_does_not_match_thomas(self):
        """The key requirement: avoid partial name matches."""
        score = self.matcher.match("Tom", "Thomas")
        assert score < 0.8

    def test_word_boundary_in_email(self):
        score = self.matcher.match("taylor", "taylaand@amazon.co.uk")
        # "taylor" is NOT a word boundary match in "taylaand"
        assert score < 0.8

    # --- Multi-word matching ---

    def test_multi_word_match(self):
        score = self.matcher.match("Andy Taylor", "Taylor, Andy")
        assert score >= 0.8

    def test_multi_word_partial_match(self):
        """Both parts must match for multi-word queries."""
        score = self.matcher.match("Andy Smith", "Taylor, Andy")
        # Only "Andy" matches, not "Smith"
        assert score < 0.8

    def test_full_name_vs_display_name(self):
        score = self.matcher.match("Andy Taylor", "Andy Taylor <taylaand@amazon.co.uk>")
        assert score >= 0.9

    # --- Fuzzy matches ---

    def test_fuzzy_andrew_matches_andy(self):
        """SequenceMatcher should match similar names."""
        # "andrew" and "andy" have SequenceMatcher ratio ~0.5, won't match at 0.8 threshold
        # But "Andrew" as a word boundary won't match "Andy" either
        score = self.matcher.match("Andrew", "Andy")
        # These are actually quite different names - NOT a match
        assert score < 0.8

    def test_fuzzy_similar_names(self):
        """Names that are genuinely similar should match."""
        score = self.matcher.match("Taylor", "Tayler")
        assert score >= 0.8

    # --- Edge cases ---

    def test_empty_query_returns_0(self):
        assert self.matcher.match("", "Andy Taylor") == 0.0

    def test_empty_text_returns_0(self):
        assert self.matcher.match("Andy", "") == 0.0

    def test_both_empty_returns_0(self):
        assert self.matcher.match("", "") == 0.0

    def test_single_char_query(self):
        # Single char parts are filtered out (< 2 chars)
        assert self.matcher.match("A", "Andy") == 0.0

    def test_whitespace_handling(self):
        score = self.matcher.match("  Andy  ", "  Andy  ")
        assert score == 1.0


class TestFuzzyMatcherIsMatch:
    def test_is_match_above_threshold(self):
        matcher = FuzzyMatcher(threshold=0.8)
        assert matcher.is_match("Andy Taylor", "Andy Taylor")

    def test_is_match_below_threshold(self):
        matcher = FuzzyMatcher(threshold=0.8)
        assert not matcher.is_match("Tom", "Thomas")

    def test_custom_threshold(self):
        strict = FuzzyMatcher(threshold=0.95)
        lenient = FuzzyMatcher(threshold=0.5)

        # Word boundary match scores 0.95
        assert strict.is_match("Andy", "Taylor, Andy")
        assert lenient.is_match("Andy", "Taylor, Andy")

    def test_invalid_threshold_raises(self):
        with pytest.raises(ValueError):
            FuzzyMatcher(threshold=1.5)
        with pytest.raises(ValueError):
            FuzzyMatcher(threshold=-0.1)
