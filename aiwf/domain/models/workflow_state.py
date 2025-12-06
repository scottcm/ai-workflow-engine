from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field

class ExecutionMode(str, Enum):
  """Execution mode for workflow sessions"""
  INTERACTIVE = "interactive"
  AUTOMATED = "automated"

class WorkflowPhase(str, Enum):
  """Workflow lifecycle phases"""
  INITIALIZED = "initialized"
  PLANNED = "planned"
  PLAN_APPROVED = "plan_approved"
  GENERATED = "generated"
  REVIEWED = "reviewed"
  REVISED = "revised"
  COMPLETE = "complete"
  FAILED = "failed"

class Artifact(BaseModel):
  """Output artifact from a workflow phase"""
  phase: WorkflowPhase
  artifact_type: str
  file_path: str
  created_at: datetime

class WorkflowState(BaseModel):
  """Complete state snapshot of a workflow session"""
  # Identity
  session_id: str
  profile: str

  # State
  phase: WorkflowPhase
  execution_mode: ExecutionMode

  # Profile-specific Context
  entity: str
  bounded_context: str | None = None
  table: str | None = None
  dev: str | None = None

  # Multi-provider strategy
  providers: dict[str, str] # role -> provider_key

  # Outputs
  ## Avoid mutability bug that list[] = [] would cause
  artifacts: list[Artifact] = Field(default_factory=list)

  # Interactive mode
  pending_action: str | None = None

  # Error tracking
  last_error: str | None = None

  # Timestamps
  created_at: datetime
  updated_at: datetime

  # Phase history
  phase_history: list[WorkflowPhase] = Field(default_factory=list)