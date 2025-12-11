from pathlib import Path
from typing import Dict, List

from aiwf.domain.validation.path_validator import PathValidator, PathValidationError


def write_files(output_dir: Path, files: Dict[str, str]) -> List[Path]:
    """
    Write a mapping of filenames to file contents into the given output directory.

    Args:
        output_dir: The directory where files should be written. May be a Path or path-like.
        files: A dictionary mapping filenames (strings) to content strings.

    Returns:
        A list of pathlib.Path objects for the successfully written files,
        in deterministic (sorted filename) order.

    Raises:
        ValueError:
            - If the output directory cannot be created (message contains "Cannot create directory").
            - If any filename is invalid (message contains "Invalid filename").
            - If any file cannot be written (message contains "Failed to write file").
    """
    # Normalize output_dir to a Path
    if not isinstance(output_dir, Path):
        output_dir = Path(output_dir)

    # Ensure the directory exists (or can be created)
    if not output_dir.exists():
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:  # pragma: no cover (exact exception type not important)
            raise ValueError(f"Cannot create directory '{output_dir}'") from e

    # Deterministic processing order
    sorted_filenames = sorted(files.keys())

    # First pass: validate all filenames and cache sanitized versions
    sanitized_names: Dict[str, str] = {}

    for raw_name in sorted_filenames:
        try:
            sanitized = PathValidator.sanitize_filename(raw_name)
        except PathValidationError as e:
            # Do not leak internal PathValidator messages; expose a stable surface
            raise ValueError(f"Invalid filename '{raw_name}'") from e

        # JPA-MT specific constraint: must be a .java file
        if not sanitized.endswith(".java"):
            raise ValueError(f"Invalid filename '{raw_name}'")

        sanitized_names[raw_name] = sanitized

    # If we got here, all filenames are valid; now write files
    written_paths: List[Path] = []

    for raw_name in sorted_filenames:
        sanitized = sanitized_names[raw_name]
        file_path = output_dir / sanitized
        content = files[raw_name]

        try:
            # Preserve content exactly as provided
            file_path.write_text(content, encoding="utf-8")
        except Exception as e:  # pragma: no cover (exact exception type not important)
            raise ValueError(f"Failed to write file '{sanitized}'") from e

        written_paths.append(file_path)

    return written_paths
