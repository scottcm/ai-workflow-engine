from pathlib import Path
from typing import Iterable

from aiwf.domain.models.workflow_state import Artifact, WorkflowPhase
from aiwf.domain.models.write_plan import WritePlan


def write_plan(root_dir: Path, plan: WritePlan, *, phase: WorkflowPhase = WorkflowPhase.GENERATED) -> list[Artifact]:
    """Write the plan to disk and return Artifact metadata.

    Architecture constraints:
    - Engine owns all file I/O (this module).
    - Profiles perform zero file I/O and return WritePlan only.
    - SHA256 hashes are computed at write time and stored on Artifact metadata.

    Contract (defined by tests):
    - Creates parent directories as needed.
    - Writes text exactly as provided (UTF-8).
    - Rejects unsafe paths (absolute paths, '..' traversal).
    - Returns artifacts in deterministic order (sorted by file_path).
    """
    raise NotImplementedError("write_plan is not implemented yet")
