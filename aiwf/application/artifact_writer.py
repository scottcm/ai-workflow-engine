import re
import shutil
from pathlib import Path

from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.workflow_state import Artifact, WorkflowState
from aiwf.domain.validation.path_validator import PathValidationError, PathValidator

# Pattern to match legacy iteration prefixes (e.g., "iteration-1/" or "iteration-1/code/")
_LEGACY_PREFIX_PATTERN = re.compile(r'^iteration-\d+(?:/code)?/')


# Protected files that cannot be overwritten by artifact writes
PROTECTED_FILES = {"session.json", "standards-bundle.md"}


class ArtifactWriteError(Exception):
    """Raised when artifact writing fails."""
    pass


def write_artifacts(*, session_dir: Path, state: WorkflowState, result: ProcessingResult) -> None:
    """
    Write artifacts from a WritePlan to the session directory.

    For iterations > 1, after writing profile files, copies any missing files
    from the previous iteration's code directory. This ensures each iteration
    has a complete snapshot of all code files for validation/hashing.
    """
    if result.write_plan is None:
        return

    new_artifacts: list[Artifact] = []
    current_iteration = state.current_iteration
    code_dir = session_dir / f"iteration-{current_iteration}" / "code"

    try:
        for op in result.write_plan.writes:
            path_str = op.path

            # Validate and normalize the artifact path
            try:
                validated_path = PathValidator.validate_artifact_path(
                    path_str,
                    protected_names=PROTECTED_FILES,
                )
            except PathValidationError as e:
                raise ArtifactWriteError(f"Invalid artifact path: {e}") from e

            # Strip any legacy iteration prefix (e.g., "iteration-1/" or "iteration-1/code/")
            # to normalize paths from profiles that may still include them
            stripped_path = _LEGACY_PREFIX_PATTERN.sub('', validated_path)

            # Always apply canonical prefix
            path_str = f"iteration-{current_iteration}/code/{stripped_path}"

            full_path = session_dir / path_str

            # SECURITY: Validate path is within session_dir (defense in depth)
            PathValidator.validate_within_root(full_path, session_dir)

            # Prevent overwriting existing files (profile should not output duplicates)
            if full_path.exists():
                raise ArtifactWriteError(
                    f"Cannot overwrite existing file: {path_str}"
                )

            # Create parent directories
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # Write content
            full_path.write_text(op.content, encoding="utf-8")

            # Create Artifact
            artifact = Artifact(
                path=path_str,
                phase=state.phase,
                iteration=current_iteration,
                sha256=None
            )
            new_artifacts.append(artifact)

        # For iterations > 1, copy missing files from previous iteration
        if current_iteration > 1:
            prev_code_dir = session_dir / f"iteration-{current_iteration - 1}" / "code"
            copied_artifacts = _copy_missing_from_previous(
                prev_code_dir=prev_code_dir,
                current_code_dir=code_dir,
                current_iteration=current_iteration,
                phase=state.phase,
            )
            new_artifacts.extend(copied_artifacts)

    except ArtifactWriteError:
        raise
    except PathValidationError as e:
        raise ArtifactWriteError(f"Path validation failed: {e}") from e
    except Exception:
        raise

    state.artifacts.extend(new_artifacts)


def _copy_missing_from_previous(
    *,
    prev_code_dir: Path,
    current_code_dir: Path,
    current_iteration: int,
    phase,
) -> list[Artifact]:
    """
    Copy files from previous iteration's code dir that don't exist in current.

    Returns list of Artifact records for copied files.
    """
    copied: list[Artifact] = []

    if not prev_code_dir.exists():
        return copied

    # Ensure current code dir exists
    current_code_dir.mkdir(parents=True, exist_ok=True)

    for src_file in prev_code_dir.rglob("*"):
        if not src_file.is_file():
            continue

        # Get relative path within code dir
        rel_path = src_file.relative_to(prev_code_dir)
        dest_file = current_code_dir / rel_path

        # Skip if file already exists (written by profile)
        if dest_file.exists():
            continue

        # Create parent directories if needed
        dest_file.parent.mkdir(parents=True, exist_ok=True)

        # Copy file
        shutil.copy2(src_file, dest_file)

        # Create artifact record
        artifact_path = f"iteration-{current_iteration}/code/{rel_path.as_posix()}"
        copied.append(Artifact(
            path=artifact_path,
            phase=phase,
            iteration=current_iteration,
            sha256=None,
        ))

    return copied