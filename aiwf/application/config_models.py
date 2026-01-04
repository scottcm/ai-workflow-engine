"""V2 Workflow Configuration Models.

ADR-0016: Unified per-stage workflow config with cascade resolution.

Config structure:
    workflow:
      defaults:
        ai_provider: claude-code
        approval_provider: manual
        ...
      plan:
        prompt:
          approval_provider: skip
        response:
          ai_provider: claude-code
          approval_provider: claude-code

Cascade resolution: defaults → phase → stage (later values override)
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStage


class StageConfig(BaseModel):
    """Unified stage configuration (parsed from YAML).

    Note: ai_provider is only used for RESPONSE stages; ignored for PROMPT.
    """

    model_config = ConfigDict(extra="forbid")

    ai_provider: str | None = None
    approval_provider: str = "manual"
    approval_max_retries: int = 0
    approval_allow_rewrite: bool = False
    approver_config: dict[str, Any] = Field(default_factory=dict)


class PhaseConfig(BaseModel):
    """Phase configuration with optional stage overrides."""

    model_config = ConfigDict(extra="forbid")

    prompt: StageConfig | None = None
    response: StageConfig | None = None


class WorkflowConfig(BaseModel):
    """Top-level workflow configuration.

    Supports cascade resolution: defaults → phase → stage.
    """

    model_config = ConfigDict(extra="forbid")

    defaults: StageConfig = Field(default_factory=StageConfig)
    plan: PhaseConfig | None = None
    generate: PhaseConfig | None = None
    review: PhaseConfig | None = None
    revise: PhaseConfig | None = None

    def get_stage_config(self, phase: WorkflowPhase, stage: WorkflowStage) -> StageConfig:
        """Resolve config for phase/stage with cascade: defaults → phase → stage.

        Args:
            phase: The workflow phase (PLAN, GENERATE, REVIEW, REVISE, etc.)
            stage: The workflow stage (PROMPT or RESPONSE)

        Returns:
            Resolved StageConfig with values cascaded from defaults through
            phase-specific and stage-specific overrides.
        """
        # Start with defaults
        result = StageConfig(
            ai_provider=self.defaults.ai_provider,
            approval_provider=self.defaults.approval_provider,
            approval_max_retries=self.defaults.approval_max_retries,
            approval_allow_rewrite=self.defaults.approval_allow_rewrite,
            approver_config=dict(self.defaults.approver_config),
        )

        # Get phase config if exists
        phase_config = self._get_phase_config(phase)
        if phase_config is None:
            return result

        # Get stage config from phase
        stage_config = (
            phase_config.prompt if stage == WorkflowStage.PROMPT else phase_config.response
        )
        if stage_config is None:
            return result

        # Merge stage overrides (only non-default values)
        if stage_config.ai_provider is not None:
            result = result.model_copy(update={"ai_provider": stage_config.ai_provider})

        # approval_provider always has a value (default "manual"), so check if different
        if stage_config.approval_provider != "manual":
            result = result.model_copy(update={"approval_provider": stage_config.approval_provider})
        elif stage_config.model_fields_set and "approval_provider" in stage_config.model_fields_set:
            # Explicitly set to "manual"
            result = result.model_copy(update={"approval_provider": stage_config.approval_provider})

        # approval_max_retries: check if explicitly set
        if stage_config.model_fields_set and "approval_max_retries" in stage_config.model_fields_set:
            result = result.model_copy(update={"approval_max_retries": stage_config.approval_max_retries})

        # approval_allow_rewrite: check if explicitly set
        if stage_config.model_fields_set and "approval_allow_rewrite" in stage_config.model_fields_set:
            result = result.model_copy(update={"approval_allow_rewrite": stage_config.approval_allow_rewrite})

        # approver_config: merge if non-empty
        if stage_config.approver_config:
            result = result.model_copy(update={"approver_config": dict(stage_config.approver_config)})

        return result

    def _get_phase_config(self, phase: WorkflowPhase) -> PhaseConfig | None:
        """Get phase-specific config by phase enum."""
        phase_map: dict[WorkflowPhase, PhaseConfig | None] = {
            WorkflowPhase.PLAN: self.plan,
            WorkflowPhase.GENERATE: self.generate,
            WorkflowPhase.REVIEW: self.review,
            WorkflowPhase.REVISE: self.revise,
            # Terminal phases have no specific config
            WorkflowPhase.INIT: None,
            WorkflowPhase.COMPLETE: None,
            WorkflowPhase.ERROR: None,
            WorkflowPhase.CANCELLED: None,
        }
        return phase_map.get(phase)