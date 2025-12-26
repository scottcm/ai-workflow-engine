"""Workflow event payload model."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from aiwf.domain.events.event_types import WorkflowEventType
from aiwf.domain.models.workflow_state import WorkflowPhase


class WorkflowEvent(BaseModel):
    """Immutable event payload for workflow notifications."""

    model_config = {"frozen": True}

    event_type: WorkflowEventType
    session_id: str
    timestamp: datetime
    phase: WorkflowPhase | None = None
    iteration: int | None = None
    artifact_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
