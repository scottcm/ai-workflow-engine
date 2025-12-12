from pathlib import Path
from typing import Callable
from datetime import datetime, timezone

from aiwf.domain.models.workflow_state import Artifact, WorkflowPhase

def process_generation_response(
    bundle_content: str,
    session_dir: Path,
    iteration: int,
    extractor: Callable[[str], dict[str, str]],
    writer: Callable[[Path, dict[str, str]], list[Path]],
) -> list[Artifact]:
    """
    Processes the AI generation response bundle, extracts code files,
    writes them to the iteration's code directory, and returns artifacts.

    This function is immutable with respect to WorkflowState.

    Args:
        bundle_content: The raw string content of the AI response.
        session_dir: The root directory of the session.
        iteration: The current iteration number (must be >= 1).
        extractor: Callable that parses the bundle into {filename: content}.
        writer: Callable that writes files to disk and returns written paths.

    Returns:
        List of created Artifact objects.

    Raises:
        ValueError: If iteration < 1, bundle is empty, parsing fails, or writing fails.
    """
    if iteration < 1:
        raise ValueError(f"Iteration must be >= 1, got {iteration}")

    if not bundle_content or not bundle_content.strip():
        raise ValueError("Bundle content cannot be empty or whitespace only")

    # Determine output directory
    code_dir = session_dir / f"iteration-{iteration}" / "code"

    # Extract files (propagates ValueError on failure)
    files = extractor(bundle_content)

    # Write files (propagates ValueError on failure)
    written_paths = writer(code_dir, files)

    # Create artifacts
    artifacts = []
    now = datetime.now(timezone.utc)

    for path in written_paths:
        # Artifact path must be relative to session_dir
        relative_path = path.relative_to(session_dir)
        
        artifacts.append(Artifact(
            phase=WorkflowPhase.GENERATED,
            artifact_type="code",
            file_path=relative_path.as_posix(),
            created_at=now
        ))

    return artifacts
