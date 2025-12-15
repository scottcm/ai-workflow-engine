"""JPA-MT review metadata parsing.

M4 scope: deterministic parsing of the @@@REVIEW_META block produced by review templates.

This module MUST remain free of workflow orchestration concerns. It provides a single, pure
parsing function that converts a review response string into a structured dictionary
(or returns None when the block is missing or malformed).

Special-case behavior:
- If multiple @@@REVIEW_META blocks are present, parsing MUST raise ReviewMetadataMultipleBlocksError.
"""

from __future__ import annotations


class ReviewMetadataMultipleBlocksError(ValueError):
    """Raised when a review response contains more than one @@@REVIEW_META block."""


def parse_review_metadata(content: str) -> dict | None:
    """Parse an @@@REVIEW_META block from a review response.

    Expected format (order not significant, whitespace tolerant):

        @@@REVIEW_META
        verdict: PASS | FAIL   (case-insensitive; normalized to uppercase in output)
        issues_total: <non-negative int>
        issues_critical: <non-negative int>
        missing_inputs: <non-negative int>
        @@@

    Returns:
        A dict containing:
            - verdict: "PASS" | "FAIL"
            - issues_total: int
            - issues_critical: int
            - missing_inputs: int
        None if the block is missing or malformed (except multiple blocks).

    Raises:
        ReviewMetadataMultipleBlocksError: if more than one @@@REVIEW_META block is present.

    Notes:
        - This function is intentionally deterministic and side-effect free.
        - Validation rules are defined by the unit tests in
          tests/unit/profiles/jpa_mt/test_review_metadata.py.
    """
    start_marker = "@@@REVIEW_META"
    end_marker = "@@@"

    start_count = content.count(start_marker)
    if start_count == 0:
        return None
    if start_count > 1:
        raise ReviewMetadataMultipleBlocksError("Multiple review metadata blocks found.")

    start_index = content.find(start_marker)
    # Extract content after the start marker and split into lines
    content_after_start = content[start_index + len(start_marker):]
    lines_after_start = content_after_start.splitlines()

    end_line_index = None
    for i, line in enumerate(lines_after_start):
        if line.strip() == end_marker:
            end_line_index = i
            break

    if end_line_index is None:
        return None

    block_content = "\n".join(lines_after_start[:end_line_index])

    lines = block_content.splitlines()
    parsed_data = {}

    for line in lines:
        if ":" in line:
            key, value = line.split(":", 1)
            parsed_data[key.strip()] = value.strip()

    # Validation
    required_keys = {"verdict", "issues_total", "issues_critical", "missing_inputs"}
    if not required_keys.issubset(parsed_data.keys()):
        return None

    # Verdict validation
    verdict = parsed_data["verdict"].upper()
    if verdict not in ("PASS", "FAIL"):
        return None

    # Numeric validation
    numeric_fields = ["issues_total", "issues_critical", "missing_inputs"]
    final_data = {"verdict": verdict}

    for field in numeric_fields:
        value_str = parsed_data[field]
        if not value_str:  # Empty check
            return None
        try:
            value = int(value_str)
            if value < 0:
                return None
            final_data[field] = value
        except ValueError:
            return None

    return final_data