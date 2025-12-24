from typing import Any
from pydantic import BaseModel, Field

from aiwf.domain.models.workflow_state import WorkflowStatus, Artifact
from aiwf.domain.models.write_plan import WritePlan


class ProcessingResult(BaseModel):
    status: WorkflowStatus
    approved: bool = False       # ← ADD THIS
    artifacts: list[Artifact] = Field(default_factory=list)
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    write_plan: WritePlan | None = None
    messages: list[str] = Field(default_factory=list)

