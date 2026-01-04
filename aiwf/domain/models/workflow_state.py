from enum import Enum
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# Shared config for strict models - reject unknown fields
STRICT_MODEL_CONFIG = ConfigDict(extra="forbid")


class ExecutionMode(str, Enum):
    """Execution mode for workflow sessions."""

    INTERACTIVE = "interactive"
    AUTOMATED = "automated"


class WorkflowPhase(str, Enum):
    """Workflow phase - WHAT work is being done.

    ADR-0012: 4 active phases + terminal states.
    Each active phase has PROMPT and RESPONSE stages.
    """

    INIT = "init"            # Session created, ready to start
    PLAN = "plan"            # Creating implementation plan
    GENERATE = "generate"    # Generating code artifacts
    REVIEW = "review"        # Reviewing generated code
    REVISE = "revise"        # Revising based on feedback
    COMPLETE = "complete"    # All work done successfully
    ERROR = "error"          # Unrecoverable error
    CANCELLED = "cancelled"  # User cancelled session


class WorkflowStage(str, Enum):
    """Workflow stage - WHAT we're working on in the phase.

    ADR-0012: Each active phase has two stages.

    PROMPT: Prompt is created, editable, awaiting approval.
            Approve → transition to RESPONSE.

    RESPONSE: Prompt sent to AI, response created, editable, awaiting approval.
              Approve → transition to next phase's PROMPT (or COMPLETE).
    """

    PROMPT = "prompt"      # Working on prompt; awaiting approval
    RESPONSE = "response"  # Working on response; awaiting approval


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
    """Complete state snapshot of a workflow session.

    Profile-specific data goes in `context` dict, not as top-level fields.
    This model rejects unknown fields to enforce this boundary.
    """

    model_config = ConfigDict(extra="forbid")

    # Identity
    session_id: str
    profile: str

    # Generic context for profile-specific data
    context: dict[str, Any] = Field(default_factory=dict)

    # State
    phase: WorkflowPhase
    stage: WorkflowStage | None = None  # None for INIT and terminal phases
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
    pending_approval: bool = Field(
        default=False,
        description="True when workflow is paused waiting for manual approval decision.",
    )

    # Error tracking
    last_error: str | None = None

    # Approval tracking (reject/retry state - separate from operational errors)
    # Lifecycle: These fields are cleared by _clear_approval_state() on successful
    # approval. retry_count also resets on stage/phase transitions.
    approval_feedback: str | None = Field(
        default=None,
        description="Rejection feedback from approver. Cleared on successful approval or stage change.",
    )
    suggested_content: str | None = Field(
        default=None,
        description="Suggested rewrite from approver. Cleared on successful approval.",
    )
    retry_count: int = Field(
        default=0,
        description="Retry attempts in current stage. Reset to 0 on stage/phase transition or successful approval.",
    )

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Phase history
    phase_history: list[PhaseTransition] = Field(default_factory=list)

    # Transient progress messages (excluded from serialization)
    messages: list[str] = Field(default_factory=list, exclude=True)

    @field_validator("current_iteration")
    @classmethod
    def _current_iteration_ge_1(cls, v: int) -> int:
        """Ensure current_iteration is always >= 1 (iterations are 1-based)."""
        if v < 1:
            raise ValueError("current_iteration must be >= 1")
        return v
