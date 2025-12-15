from enum import Enum
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class ExecutionMode(str, Enum):
    """Execution mode for workflow sessions."""

    INTERACTIVE = "interactive"
    AUTOMATED = "automated"


class WorkflowPhase(str, Enum):
    INITIALIZED = "initialized"    # Session created
    PLANNING = "planning"          # Planning prompt sent
    PLANNED = "planned"            # Plan response received
    GENERATING = "generating"      # Generation prompt sent
    GENERATED = "generated"        # Code received
    REVIEWING = "reviewing"        # Review prompt sent
    REVIEWED = "reviewed"          # Review completed
    REVISING = "revising"          # Revision prompt sent
    COMPLETE = "complete"          # All work done


class WorkflowStatus(str, Enum):
    IN_PROGRESS = "in_progress"    # Waiting on user/LLM response
    SUCCESS = "success"            # Completed successfully
    FAILED = "failed"              # Completed, needs rework
    ERROR = "error"                # Technical failure
    CANCELLED = "cancelled"        # User stopped


class Artifact(BaseModel):
    """Output artifact from a workflow phase."""

    phase: WorkflowPhase
    artifact_type: str
    file_path: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PhaseTransition(BaseModel):
    """Record of a phase/status change."""

    phase: WorkflowPhase
    status: WorkflowStatus
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WorkflowState(BaseModel):
    """Complete state snapshot of a workflow session."""

    # Identity
    session_id: str
    profile: str
    scope: str  # e.g., "domain", "vertical"

    # Work context (used by templates)
    entity: str
    bounded_context: str | None = None
    table: str | None = None
    dev: str | None = None
    task_id: str | None = None

    # State
    phase: WorkflowPhase
    status: WorkflowStatus
    execution_mode: ExecutionMode
    current_iteration: int = 1  # Starts at 1, increments on revision

    # Multi-provider strategy
    providers: dict[str, str]  # role -> provider_key

    # Extensibility (profile/engine-specific data)
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Outputs
    # Avoid mutability bug that list[] = [] would cause
    artifacts: list[Artifact] = Field(default_factory=list)

    # Interactive mode
    pending_action: str | None = None

    # Error tracking
    last_error: str | None = None

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Phase history
    phase_history: list[PhaseTransition] = Field(default_factory=list)
