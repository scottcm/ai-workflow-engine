"""Unit tests for V2 workflow config models.

Tests cascade resolution: defaults → phase → stage.
"""

import pytest
from pydantic import ValidationError

from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStage
from aiwf.application.config_models import (
    StageConfig,
    PhaseConfig,
    WorkflowConfig,
)


class TestStageConfig:
    """Tests for StageConfig model."""

    def test_default_values(self):
        """StageConfig has sensible defaults."""
        config = StageConfig()
        assert config.ai_provider is None
        assert config.approval_provider == "manual"
        assert config.approval_max_retries == 0
        assert config.approval_allow_rewrite is False
        assert config.approver_config == {}

    def test_explicit_values(self):
        """StageConfig accepts explicit values."""
        config = StageConfig(
            ai_provider="claude-code",
            approval_provider="skip",
            approval_max_retries=3,
            approval_allow_rewrite=True,
            approver_config={"key": "value"},
        )
        assert config.ai_provider == "claude-code"
        assert config.approval_provider == "skip"
        assert config.approval_max_retries == 3
        assert config.approval_allow_rewrite is True
        assert config.approver_config == {"key": "value"}

    def test_approver_config_preserved(self):
        """approver_config dict is passed through unchanged."""
        nested_config = {
            "nested": {"deep": {"value": 123}},
            "list": [1, 2, 3],
        }
        config = StageConfig(approver_config=nested_config)
        assert config.approver_config == nested_config


class TestPhaseConfig:
    """Tests for PhaseConfig model."""

    def test_default_empty(self):
        """PhaseConfig defaults to None for both stages."""
        config = PhaseConfig()
        assert config.prompt is None
        assert config.response is None

    def test_with_prompt_only(self):
        """PhaseConfig with only prompt stage."""
        config = PhaseConfig(
            prompt=StageConfig(approval_provider="skip")
        )
        assert config.prompt is not None
        assert config.prompt.approval_provider == "skip"
        assert config.response is None

    def test_with_response_only(self):
        """PhaseConfig with only response stage."""
        config = PhaseConfig(
            response=StageConfig(ai_provider="claude-code")
        )
        assert config.prompt is None
        assert config.response is not None
        assert config.response.ai_provider == "claude-code"

    def test_with_both_stages(self):
        """PhaseConfig with both stages configured."""
        config = PhaseConfig(
            prompt=StageConfig(approval_provider="skip"),
            response=StageConfig(
                ai_provider="claude-code",
                approval_provider="claude-code",
            ),
        )
        assert config.prompt.approval_provider == "skip"
        assert config.response.ai_provider == "claude-code"


class TestWorkflowConfig:
    """Tests for WorkflowConfig model."""

    def test_minimal_config(self):
        """WorkflowConfig with just defaults."""
        config = WorkflowConfig(
            defaults=StageConfig(ai_provider="claude-code")
        )
        assert config.defaults.ai_provider == "claude-code"
        assert config.plan is None
        assert config.generate is None
        assert config.review is None
        assert config.revise is None

    def test_full_config(self):
        """WorkflowConfig with all phases specified."""
        config = WorkflowConfig(
            defaults=StageConfig(ai_provider="claude-code"),
            plan=PhaseConfig(
                response=StageConfig(approval_provider="skip")
            ),
            generate=PhaseConfig(
                response=StageConfig(approval_max_retries=2)
            ),
            review=PhaseConfig(),
            revise=PhaseConfig(),
        )
        assert config.plan is not None
        assert config.generate is not None
        assert config.review is not None
        assert config.revise is not None


class TestCascadeResolution:
    """Tests for get_stage_config cascade resolution."""

    def test_cascade_defaults_to_stage(self):
        """Stage inherits all defaults when phase/stage not specified."""
        config = WorkflowConfig(
            defaults=StageConfig(
                ai_provider="claude-code",
                approval_provider="manual",
                approval_max_retries=3,
            )
        )
        resolved = config.get_stage_config(WorkflowPhase.PLAN, WorkflowStage.RESPONSE)
        assert resolved.ai_provider == "claude-code"
        assert resolved.approval_provider == "manual"
        assert resolved.approval_max_retries == 3

    def test_cascade_stage_overrides_defaults(self):
        """Stage-level value overrides defaults."""
        config = WorkflowConfig(
            defaults=StageConfig(approval_provider="manual"),
            plan=PhaseConfig(
                response=StageConfig(approval_provider="skip")
            ),
        )
        resolved = config.get_stage_config(WorkflowPhase.PLAN, WorkflowStage.RESPONSE)
        assert resolved.approval_provider == "skip"

    def test_partial_override_preserves_defaults(self):
        """Overriding one field preserves other defaults."""
        config = WorkflowConfig(
            defaults=StageConfig(
                ai_provider="claude-code",
                approval_provider="manual",
                approval_max_retries=3,
            ),
            plan=PhaseConfig(
                response=StageConfig(approval_provider="skip")
            ),
        )
        resolved = config.get_stage_config(WorkflowPhase.PLAN, WorkflowStage.RESPONSE)
        assert resolved.ai_provider == "claude-code"  # from defaults
        assert resolved.approval_provider == "skip"  # overridden
        assert resolved.approval_max_retries == 3  # from defaults

    def test_prompt_stage_resolution(self):
        """PROMPT stage resolves correctly."""
        config = WorkflowConfig(
            defaults=StageConfig(approval_provider="manual"),
            plan=PhaseConfig(
                prompt=StageConfig(approval_provider="skip")
            ),
        )
        resolved = config.get_stage_config(WorkflowPhase.PLAN, WorkflowStage.PROMPT)
        assert resolved.approval_provider == "skip"

    def test_different_stages_in_same_phase(self):
        """PROMPT and RESPONSE can have different configs in same phase."""
        config = WorkflowConfig(
            defaults=StageConfig(ai_provider="claude-code"),
            plan=PhaseConfig(
                prompt=StageConfig(approval_provider="skip"),
                response=StageConfig(approval_provider="claude-code"),
            ),
        )
        prompt_resolved = config.get_stage_config(WorkflowPhase.PLAN, WorkflowStage.PROMPT)
        response_resolved = config.get_stage_config(WorkflowPhase.PLAN, WorkflowStage.RESPONSE)

        assert prompt_resolved.approval_provider == "skip"
        assert response_resolved.approval_provider == "claude-code"

    def test_different_phases_resolve_independently(self):
        """Different phases resolve their own configs."""
        config = WorkflowConfig(
            defaults=StageConfig(
                ai_provider="claude-code",
                approval_provider="manual",
            ),
            plan=PhaseConfig(
                response=StageConfig(approval_provider="skip")
            ),
            generate=PhaseConfig(
                response=StageConfig(approval_max_retries=2)
            ),
        )
        plan_resolved = config.get_stage_config(WorkflowPhase.PLAN, WorkflowStage.RESPONSE)
        generate_resolved = config.get_stage_config(WorkflowPhase.GENERATE, WorkflowStage.RESPONSE)

        assert plan_resolved.approval_provider == "skip"
        assert plan_resolved.approval_max_retries == 0  # default

        assert generate_resolved.approval_provider == "manual"  # default
        assert generate_resolved.approval_max_retries == 2  # overridden

    def test_approver_config_passed_through(self):
        """approver_config dict is preserved through cascade."""
        approver_cfg = {"model": "gpt-4", "temperature": 0.1}
        config = WorkflowConfig(
            defaults=StageConfig(ai_provider="claude-code"),
            plan=PhaseConfig(
                response=StageConfig(approver_config=approver_cfg)
            ),
        )
        resolved = config.get_stage_config(WorkflowPhase.PLAN, WorkflowStage.RESPONSE)
        assert resolved.approver_config == approver_cfg

    def test_review_phase_resolution(self):
        """REVIEW phase resolves correctly."""
        config = WorkflowConfig(
            defaults=StageConfig(ai_provider="claude-code"),
            review=PhaseConfig(
                response=StageConfig(approval_max_retries=1)
            ),
        )
        resolved = config.get_stage_config(WorkflowPhase.REVIEW, WorkflowStage.RESPONSE)
        assert resolved.ai_provider == "claude-code"
        assert resolved.approval_max_retries == 1

    def test_revise_phase_resolution(self):
        """REVISE phase resolves correctly."""
        config = WorkflowConfig(
            defaults=StageConfig(ai_provider="claude-code"),
            revise=PhaseConfig(
                prompt=StageConfig(approval_provider="skip"),
                response=StageConfig(approval_allow_rewrite=True),
            ),
        )
        prompt_resolved = config.get_stage_config(WorkflowPhase.REVISE, WorkflowStage.PROMPT)
        response_resolved = config.get_stage_config(WorkflowPhase.REVISE, WorkflowStage.RESPONSE)

        assert prompt_resolved.approval_provider == "skip"
        assert response_resolved.approval_allow_rewrite is True


class TestValidation:
    """Tests for config validation."""

    def test_prompt_stage_ignores_ai_provider(self):
        """PROMPT stage doesn't error if ai_provider is present (just ignored)."""
        config = WorkflowConfig(
            defaults=StageConfig(ai_provider="claude-code"),
            plan=PhaseConfig(
                prompt=StageConfig(ai_provider="gemini-cli")  # ignored for PROMPT
            ),
        )
        # Should not raise - ai_provider on PROMPT is just ignored
        resolved = config.get_stage_config(WorkflowPhase.PLAN, WorkflowStage.PROMPT)
        assert resolved.ai_provider == "gemini-cli"  # value is there, just unused

    def test_response_requires_ai_provider_after_cascade(self):
        """RESPONSE stage requires ai_provider after cascade resolution."""
        config = WorkflowConfig(
            defaults=StageConfig(approval_provider="manual"),  # no ai_provider
            plan=PhaseConfig(
                response=StageConfig(approval_provider="skip")  # still no ai_provider
            ),
        )
        # get_stage_config should work (validation is separate)
        resolved = config.get_stage_config(WorkflowPhase.PLAN, WorkflowStage.RESPONSE)
        assert resolved.ai_provider is None  # No ai_provider set

    def test_unknown_fields_rejected(self):
        """Unknown fields in StageConfig are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            StageConfig(unknown_field="value")
        assert "unknown_field" in str(exc_info.value)


class TestTerminalPhases:
    """Tests for terminal phase handling."""

    def test_init_phase_returns_defaults(self):
        """INIT phase (terminal) returns defaults."""
        config = WorkflowConfig(
            defaults=StageConfig(ai_provider="claude-code")
        )
        # INIT doesn't have stages but get_stage_config should return defaults
        resolved = config.get_stage_config(WorkflowPhase.INIT, WorkflowStage.PROMPT)
        assert resolved.ai_provider == "claude-code"

    def test_complete_phase_returns_defaults(self):
        """COMPLETE phase (terminal) returns defaults."""
        config = WorkflowConfig(
            defaults=StageConfig(ai_provider="claude-code")
        )
        resolved = config.get_stage_config(WorkflowPhase.COMPLETE, WorkflowStage.RESPONSE)
        assert resolved.ai_provider == "claude-code"


class TestConfigCascadeContract:
    """Contract tests: cascade resolution must follow spec.

    These tests are copied from the implementation plan to verify
    the contract behavior is correct.
    """

    def test_defaults_apply_when_no_override(self):
        """Stage config inherits all defaults when phase/stage not specified."""
        config = WorkflowConfig(defaults=StageConfig(ai_provider="claude-code"))
        resolved = config.get_stage_config(WorkflowPhase.PLAN, WorkflowStage.RESPONSE)
        assert resolved.ai_provider == "claude-code"

    def test_stage_override_wins(self):
        """Stage-level value overrides defaults."""
        config = WorkflowConfig(
            defaults=StageConfig(approval_provider="manual"),
            plan=PhaseConfig(
                response=StageConfig(approval_provider="skip")
            ),
        )
        resolved = config.get_stage_config(WorkflowPhase.PLAN, WorkflowStage.RESPONSE)
        assert resolved.approval_provider == "skip"

    def test_partial_override_preserves_defaults(self):
        """Overriding one field preserves other defaults."""
        config = WorkflowConfig(
            defaults=StageConfig(
                ai_provider="claude-code",
                approval_provider="manual",
                approval_max_retries=3,
            ),
            plan=PhaseConfig(
                response=StageConfig(approval_provider="skip")
            ),
        )
        resolved = config.get_stage_config(WorkflowPhase.PLAN, WorkflowStage.RESPONSE)
        assert resolved.ai_provider == "claude-code"  # from defaults
        assert resolved.approval_provider == "skip"  # overridden
        assert resolved.approval_max_retries == 3  # from defaults