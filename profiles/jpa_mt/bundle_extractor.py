import re


def extract_files(raw_output: str) -> dict[str, str]:
    """
    Extracts files from an AI-generated raw response string using <<<FILE: >>> markers.

    Args:
        raw_output: The raw string containing file markers and code.

    Returns:
        A dictionary mapping filenames to their content.

    Raises:
        ValueError: If no markers found, invalid filename, or duplicates.
    """
    marker_pattern = re.compile(r'^\s*<<<FILE:\s*(.+?)>>>[ \t]*(\r?\n|\Z)', re.MULTILINE)
    matches = list(marker_pattern.finditer(raw_output))

    if not matches:
        raise ValueError("No <<<FILE: ...>>> markers found in output.")

    files = {}

    for i, match in enumerate(matches):
        filename = match.group(1).strip()
        start_index = match.end()

        # Determine the end of the current block
        if i + 1 < len(matches):
            end_index = matches[i + 1].start()
        else:
            end_index = len(raw_output)

        block_content = raw_output[start_index:end_index]

        # Validate filename
        if not filename.endswith(".java") or any(
            char in filename for char in ['/', '\\', ':', '..']
        ):
            raise ValueError(
                f"Invalid filename: '{filename}'. Must end in .java and contain no paths."
            )

        if filename in files:
            raise ValueError(f"Duplicate filename detected: {filename}")

        files[filename] = block_content

    return files