import hashlib
from pathlib import Path
from typing import Any

from aiwf.application.standards_provider import StandardsProvider
from aiwf.domain.models.workflow_state import WorkflowState


def materialize_standards(*, session_dir: Path, state: WorkflowState, provider: StandardsProvider) -> Path:
    # 1. Call provider to create bundle
    bundle_text = provider.create_bundle(state)
    
    # 2. Compute hash
    bundle_hash = hashlib.sha256(bundle_text.encode("utf-8")).hexdigest()
    
    # 3. Write file
    bundle_path = session_dir / "standards-bundle.md"
    bundle_path.write_text(bundle_text, encoding="utf-8")
    
    # 4. Update state
    state.standards_hash = bundle_hash