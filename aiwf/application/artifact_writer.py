import hashlib
from pathlib import Path

from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.workflow_state import Artifact, WorkflowState
from aiwf.domain.validation.path_validator import PathValidator  # Add import


def write_artifacts(*, session_dir: Path, state: WorkflowState, result: ProcessingResult) -> None:
    if result.write_plan is None:
        return

    new_artifacts: list[Artifact] = []

    try:
        for op in result.write_plan.writes:
            path_str = op.path
            prefix = f"iteration-{state.current_iteration}/"
            if not path_str.startswith(prefix):
                path_str = f"{prefix}{path_str}"

            full_path = session_dir / path_str
            
            # SECURITY: Validate path is within session_dir
            PathValidator.validate_within_root(full_path, session_dir)
            
            # Create parent directories
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write content
            full_path.write_text(op.content, encoding="utf-8")
            
            # Compute SHA-256
            sha256_hex = hashlib.sha256(op.content.encode("utf-8")).hexdigest()
            
            # Create Artifact
            artifact = Artifact(
                path=path_str,
                phase=state.phase,
                iteration=state.current_iteration,
                sha256=sha256_hex
            )
            new_artifacts.append(artifact)
            
    except Exception:
        raise

    state.artifacts.extend(new_artifacts)