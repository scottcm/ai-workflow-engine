"""Tests for JPA-MT review metadata parsing (ADR-0004)."""

import pytest

from profiles.jpa_mt.review_metadata import (
    ParseError,
    ReviewMetadata,
    ReviewVerdict,
    format_review_summary,
    parse_review_metadata,
)


class TestParseReviewMetadata:
    """Test parse_review_metadata function."""

    def test_parse_valid_pass(self):
        """Parse valid PASS metadata."""
        content = """
# Code Review

Some review content here.

@@@REVIEW_META
verdict: PASS
issues_total: 0
issues_critical: 0
missing_inputs: 0
@@@

More content after.
"""
        result = parse_review_metadata(content)
        assert result.verdict == ReviewVerdict.PASS
        assert result.issues_total == 0
        assert result.issues_critical == 0
        assert result.missing_inputs == 0

    def test_parse_valid_fail(self):
        """Parse valid FAIL metadata with issues."""
        content = """
@@@REVIEW_META
verdict: FAIL
issues_total: 5
issues_critical: 2
missing_inputs: 1
@@@
"""
        result = parse_review_metadata(content)
        assert result.verdict == ReviewVerdict.FAIL
        assert result.issues_total == 5
        assert result.issues_critical == 2
        assert result.missing_inputs == 1

    def test_parse_case_insensitive_verdict(self):
        """Verdict is case-insensitive."""
        content = """
@@@REVIEW_META
verdict: pass
issues_total: 0
issues_critical: 0
missing_inputs: 0
@@@
"""
        result = parse_review_metadata(content)
        assert result.verdict == ReviewVerdict.PASS

    def test_parse_case_insensitive_block_marker(self):
        """Block marker is case-insensitive."""
        content = """
@@@review_meta
verdict: PASS
issues_total: 0
issues_critical: 0
missing_inputs: 0
@@@
"""
        result = parse_review_metadata(content)
        assert result.verdict == ReviewVerdict.PASS

    def test_parse_with_whitespace(self):
        """Parse with extra whitespace."""
        content = """
@@@REVIEW_META
  verdict:   PASS
  issues_total:  0
  issues_critical: 0
  missing_inputs: 0
@@@
"""
        result = parse_review_metadata(content)
        assert result.verdict == ReviewVerdict.PASS

    def test_parse_empty_content_raises(self):
        """Empty content raises ParseError."""
        with pytest.raises(ParseError, match="Empty content"):
            parse_review_metadata("")

    def test_parse_none_content_raises(self):
        """None content raises ParseError."""
        with pytest.raises(ParseError, match="Empty content"):
            parse_review_metadata(None)

    def test_parse_missing_block_raises(self):
        """Missing metadata block raises ParseError."""
        content = "Just some review content without metadata."
        with pytest.raises(ParseError, match="Missing @@@REVIEW_META block"):
            parse_review_metadata(content)

    def test_parse_missing_verdict_raises(self):
        """Missing verdict field raises ParseError."""
        content = """
@@@REVIEW_META
issues_total: 0
issues_critical: 0
missing_inputs: 0
@@@
"""
        with pytest.raises(ParseError, match="Missing required fields.*verdict"):
            parse_review_metadata(content)

    def test_parse_missing_issues_total_raises(self):
        """Missing issues_total field raises ParseError."""
        content = """
@@@REVIEW_META
verdict: PASS
issues_critical: 0
missing_inputs: 0
@@@
"""
        with pytest.raises(ParseError, match="Missing required fields.*issues_total"):
            parse_review_metadata(content)

    def test_parse_invalid_verdict_raises(self):
        """Invalid verdict value raises ParseError."""
        content = """
@@@REVIEW_META
verdict: MAYBE
issues_total: 0
issues_critical: 0
missing_inputs: 0
@@@
"""
        with pytest.raises(ParseError, match="Invalid verdict.*MAYBE"):
            parse_review_metadata(content)

    def test_parse_invalid_integer_raises(self):
        """Non-integer value raises ParseError."""
        content = """
@@@REVIEW_META
verdict: PASS
issues_total: many
issues_critical: 0
missing_inputs: 0
@@@
"""
        with pytest.raises(ParseError, match="Invalid integer value"):
            parse_review_metadata(content)

    def test_parse_negative_integer_raises(self):
        """Negative integer raises ParseError."""
        content = """
@@@REVIEW_META
verdict: PASS
issues_total: -1
issues_critical: 0
missing_inputs: 0
@@@
"""
        with pytest.raises(ParseError, match="non-negative"):
            parse_review_metadata(content)


class TestFormatReviewSummary:
    """Test format_review_summary function."""

    def test_format_pass_no_issues(self):
        """Format PASS with no issues."""
        metadata = ReviewMetadata(
            verdict=ReviewVerdict.PASS,
            issues_total=0,
            issues_critical=0,
            missing_inputs=0,
        )
        result = format_review_summary(metadata)
        assert result == "PASS | issues=0 (critical=0) | missing_inputs=0"

    def test_format_fail_with_issues(self):
        """Format FAIL with issues."""
        metadata = ReviewMetadata(
            verdict=ReviewVerdict.FAIL,
            issues_total=5,
            issues_critical=2,
            missing_inputs=1,
        )
        result = format_review_summary(metadata)
        assert result == "FAIL | issues=5 (critical=2) | missing_inputs=1"


class TestReviewMetadataNamedTuple:
    """Test ReviewMetadata as NamedTuple."""

    def test_is_immutable(self):
        """ReviewMetadata is immutable."""
        metadata = ReviewMetadata(
            verdict=ReviewVerdict.PASS,
            issues_total=0,
            issues_critical=0,
            missing_inputs=0,
        )
        with pytest.raises(AttributeError):
            metadata.verdict = ReviewVerdict.FAIL

    def test_equality(self):
        """ReviewMetadata equality comparison."""
        m1 = ReviewMetadata(ReviewVerdict.PASS, 0, 0, 0)
        m2 = ReviewMetadata(ReviewVerdict.PASS, 0, 0, 0)
        m3 = ReviewMetadata(ReviewVerdict.FAIL, 0, 0, 0)
        assert m1 == m2
        assert m1 != m3
