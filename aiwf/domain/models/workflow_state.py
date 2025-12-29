from enum import Enum
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    REVISED = "revised"            # Revision completed
    COMPLETE = "complete"          # All work done
    ERROR = "error"                # Unrecoverable error
    CANCELLED = "cancelled"        # User cancelled session


class WorkflowStatus(str, Enum):
    IN_PROGRESS = "in_progress"    # Waiting on user/LLM response
    SUCCESS = "success"            # Completed successfully
    FAILED = "failed"              # Completed, needs rework
    ERROR = "error"                # Technical failure
    CANCELLED = "cancelled"        # User stopped


class Artifact(BaseModel):
    """
    Artifact metadata only.

    Notes:
    - Strict: rejects unknown keys (no legacy alias coercion).
    - No kind/role/type semantics.
    """

    model_config = ConfigDict(extra="forbid")

    path: str
    phase: WorkflowPhase
    iteration: int
    sha256: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("path")
    @classmethod
    def _path_non_empty(cls, v: str) -> str:
        v2 = v.strip()
        if not v2:
            raise ValueError("path must be non-empty")
        return v2

    @field_validator("iteration")
    @classmethod
    def _iteration_ge_1(cls, v: int) -> int:
        if v < 1:
            raise ValueError("iteration must be >= 1")
        return v

    @model_validator(mode="before")
    @classmethod
    def _reject_legacy_keys(cls, data: Any) -> Any:
        # Explicitly reject common legacy keys instead of aliasing/coercion.
        if isinstance(data, dict):
            forbidden = {"file_path", "artifact_type", "kind"}
            present = forbidden.intersection(data.keys())
            if present:
                # Raise a clear error rather than relying on generic "extra forbidden".
                raise ValueError(f"Unsupported legacy keys: {sorted(present)}")
        return data


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

    # Hashing and approval
    standards_hash: str                 # Required, set at session init
    plan_approved: bool = False
    plan_hash: str | None = None        # None until plan approved
    prompt_hashes: dict[str, str] = Field(default_factory=dict)
    review_approved: bool = False
    review_hash: str | None = None      # None until review approved

    # Multi-provider strategy
    providers: dict[str, str]  # role -> provider_key

    # Standards provider key used for this session (empty = profile default)
    standards_provider: str = ""

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

    # Transient progress messages (excluded from serialization)
    messages: list[str] = Field(default_factory=list, exclude=True)
