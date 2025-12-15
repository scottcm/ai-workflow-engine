from __future__ import annotations

import pytest

from profiles.jpa_mt.review_metadata import (
    ReviewMetadataMultipleBlocksError,
    parse_review_metadata,
)


def test_parse_valid_metadata_block_pass_is_case_insensitive_and_normalized() -> None:
    content = """Some header text

@@@REVIEW_META
verdict: pass
issues_total: 3
issues_critical: 1
missing_inputs: 0
@@@

Body content here
"""
    metadata = parse_review_metadata(content)
    assert metadata == {
        "verdict": "PASS",
        "issues_total": 3,
        "issues_critical": 1,
        "missing_inputs": 0,
    }


def test_parse_valid_metadata_block_fail_is_case_insensitive_and_normalized() -> None:
    content = """@@@REVIEW_META
verdict: FaIl
issues_total: 0
issues_critical: 0
missing_inputs: 2
@@@"""
    metadata = parse_review_metadata(content)
    assert metadata == {
        "verdict": "FAIL",
        "issues_total": 0,
        "issues_critical": 0,
        "missing_inputs": 2,
    }


def test_returns_none_when_block_missing() -> None:
    content = """No metadata here
verdict: PASS
issues_total: 1
"""
    assert parse_review_metadata(content) is None


@pytest.mark.parametrize(
    "content",
    [
        # Missing closing delimiter
        """@@@REVIEW_META
verdict: PASS
issues_total: 1
issues_critical: 0
missing_inputs: 0
""",
        # Missing opening delimiter
        """verdict: PASS
issues_total: 1
issues_critical: 0
missing_inputs: 0
@@@""",
        # Non key:value line in block should not salvage missing required keys
        """@@@REVIEW_META
this is not a kv line
@@@""",
    ],
)
def test_returns_none_for_malformed_delimiters_or_no_kv(content: str) -> None:
    assert parse_review_metadata(content) is None


@pytest.mark.parametrize(
    "content",
    [
        # Missing required field
        """@@@REVIEW_META
verdict: PASS
issues_total: 1
issues_critical: 0
@@@""",
        # Missing verdict
        """@@@REVIEW_META
issues_total: 1
issues_critical: 0
missing_inputs: 0
@@@""",
        # Empty verdict value is invalid
        """@@@REVIEW_META
verdict:
issues_total: 1
issues_critical: 0
missing_inputs: 0
@@@""",
        # Verdict must be PASS/FAIL (case-insensitive) only
        """@@@REVIEW_META
verdict: MAYBE
issues_total: 1
issues_critical: 0
missing_inputs: 0
@@@""",
        # Empty numeric value is invalid
        """@@@REVIEW_META
verdict: PASS
issues_total:
issues_critical: 0
missing_inputs: 0
@@@""",
    ],
)
def test_returns_none_when_required_fields_missing_or_empty_or_invalid(content: str) -> None:
    assert parse_review_metadata(content) is None


@pytest.mark.parametrize(
    "content",
    [
        # Non-int values for numeric fields
        """@@@REVIEW_META
verdict: PASS
issues_total: three
issues_critical: 0
missing_inputs: 0
@@@""",
        """@@@REVIEW_META
verdict: FAIL
issues_total: 1
issues_critical: none
missing_inputs: 0
@@@""",
        """@@@REVIEW_META
verdict: FAIL
issues_total: 1
issues_critical: 0
missing_inputs: zero
@@@""",
        # Negative values are not allowed
        """@@@REVIEW_META
verdict: PASS
issues_total: -1
issues_critical: 0
missing_inputs: 0
@@@""",
        """@@@REVIEW_META
verdict: PASS
issues_total: 1
issues_critical: -2
missing_inputs: 0
@@@""",
        """@@@REVIEW_META
verdict: PASS
issues_total: 1
issues_critical: 0
missing_inputs: -3
@@@""",
    ],
)
def test_returns_none_when_numeric_fields_not_non_negative_int(content: str) -> None:
    assert parse_review_metadata(content) is None


def test_handles_whitespace_variations() -> None:
    content = """\n\n
    @@@REVIEW_META

      verdict   :   FAIL
      issues_total:    10
      issues_critical:  2
      missing_inputs:   5

    @@@

    trailing text
    """
    metadata = parse_review_metadata(content)
    assert metadata == {
        "verdict": "FAIL",
        "issues_total": 10,
        "issues_critical": 2,
        "missing_inputs": 5,
    }


def test_ignores_unknown_keys_but_still_requires_required_set() -> None:
    content = """@@@REVIEW_META
verdict: PASS
issues_total: 0
issues_critical: 0
missing_inputs: 0
foo: bar
@@@"""
    metadata = parse_review_metadata(content)
    assert metadata == {
        "verdict": "PASS",
        "issues_total": 0,
        "issues_critical": 0,
        "missing_inputs": 0,
    }


def test_raises_when_multiple_meta_blocks_present() -> None:
    content = """@@@REVIEW_META
verdict: PASS
issues_total: 0
issues_critical: 0
missing_inputs: 0
@@@

Some text in between

@@@REVIEW_META
verdict: FAIL
issues_total: 1
issues_critical: 0
missing_inputs: 0
@@@
"""
    with pytest.raises(ReviewMetadataMultipleBlocksError):
        parse_review_metadata(content)
