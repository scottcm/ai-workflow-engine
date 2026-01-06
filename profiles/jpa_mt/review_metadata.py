"""
Review metadata parsing for JPA-MT profile.

Parses @@@REVIEW_META blocks from AI-generated review responses per ADR-0004.

Format:
    @@@REVIEW_META
    verdict: PASS | FAIL
    issues_total: <int>
    issues_critical: <int>
    missing_inputs: <int>
    @@@
"""

from __future__ import annotations

import re
from enum import Enum
from typing import NamedTuple


class ReviewVerdict(str, Enum):
    """Review verdict values."""

    PASS = "PASS"
    FAIL = "FAIL"


class ReviewMetadata(NamedTuple):
    """Parsed review metadata from @@@REVIEW_META block."""

    verdict: ReviewVerdict
    issues_total: int
    issues_critical: int
    missing_inputs: int


class ParseError(Exception):
    """Raised when @@@REVIEW_META block is missing or malformed."""

    pass


# Regex to extract the @@@REVIEW_META...@@@ block
_META_BLOCK_PATTERN = re.compile(
    r"@@@REVIEW_META\s*\n(.*?)\n\s*@@@", re.DOTALL | re.IGNORECASE
)


def parse_review_metadata(content: str) -> ReviewMetadata:
    """
    Parse @@@REVIEW_META block from review response content.

    Args:
        content: Full review response content.

    Returns:
        ReviewMetadata with parsed values.

    Raises:
        ParseError: If block is missing, malformed, or has invalid values.
    """
    if not content:
        raise ParseError("Empty content")

    match = _META_BLOCK_PATTERN.search(content)
    if not match:
        raise ParseError("Missing @@@REVIEW_META block")

    block_content = match.group(1)
    fields: dict[str, str] = {}

    for line in block_content.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip().lower()] = value.strip()

    # Validate required fields
    required = ["verdict", "issues_total", "issues_critical", "missing_inputs"]
    missing = [f for f in required if f not in fields]
    if missing:
        raise ParseError(f"Missing required fields: {', '.join(missing)}")

    # Parse verdict
    verdict_str = fields["verdict"].upper()
    if verdict_str not in ("PASS", "FAIL"):
        raise ParseError(f"Invalid verdict: {fields['verdict']} (expected PASS or FAIL)")
    verdict = ReviewVerdict(verdict_str)

    # Parse integers
    try:
        issues_total = int(fields["issues_total"])
        issues_critical = int(fields["issues_critical"])
        missing_inputs = int(fields["missing_inputs"])
    except ValueError as e:
        raise ParseError(f"Invalid integer value: {e}")

    # Validate non-negative
    if issues_total < 0 or issues_critical < 0 or missing_inputs < 0:
        raise ParseError("Integer fields must be non-negative")

    return ReviewMetadata(
        verdict=verdict,
        issues_total=issues_total,
        issues_critical=issues_critical,
        missing_inputs=missing_inputs,
    )


def format_review_summary(metadata: ReviewMetadata) -> str:
    """
    Format metadata for CLI display per ADR-0004.

    Returns:
        Summary string like "PASS | issues=0 (critical=0) | missing_inputs=0"
    """
    return (
        f"{metadata.verdict.value} | "
        f"issues={metadata.issues_total} (critical={metadata.issues_critical}) | "
        f"missing_inputs={metadata.missing_inputs}"
    )
