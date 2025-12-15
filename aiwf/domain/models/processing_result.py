from typing import Any
from pydantic import BaseModel, Field

from aiwf.domain.models.workflow_state import WorkflowStatus, Artifact


class ProcessingResult(BaseModel):
    """Result of processing a phase response."""

    status: WorkflowStatus
    artifacts: list[Artifact] = Field(default_factory=list)
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
