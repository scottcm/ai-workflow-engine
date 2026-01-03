"""Unit tests for approval configuration module."""

import pytest
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from aiwf.application.approval_config import (
    ApprovalConfig,
    StageApprovalConfig,
    load_approval_config,
)


class TestStageApprovalConfig:
    """Tests for StageApprovalConfig model."""

    def test_default_values(self):
        """StageApprovalConfig has sensible defaults."""
        config = StageApprovalConfig()

        assert config.approver == "manual"
        assert config.max_retries == 0
        assert config.allow_rewrite is False

    def test_custom_values(self):
        """StageApprovalConfig accepts custom values."""
        config = StageApprovalConfig(
            approver="claude-code",
            max_retries=3,
            allow_rewrite=True,
        )

        assert config.approver == "claude-code"
        assert config.max_retries == 3
        assert config.allow_rewrite is True


class TestApprovalConfig:
    """Tests for ApprovalConfig model."""

    def test_default_values(self):
        """ApprovalConfig has sensible defaults."""
        config = ApprovalConfig()

        assert config.default_approver == "manual"
        assert config.default_max_retries == 0
        assert config.default_allow_rewrite is False
        assert config.stages == {}

    def test_get_stage_config_returns_configured(self):
        """get_stage_config returns configured stage config."""
        config = ApprovalConfig(
            stages={
                "plan.response": StageApprovalConfig(
                    approver="claude-code",
                    max_retries=2,
                ),
            }
        )

        result = config.get_stage_config("plan", "response")

        assert result.approver == "claude-code"
        assert result.max_retries == 2

    def test_get_stage_config_returns_defaults(self):
        """get_stage_config returns defaults for unconfigured stage."""
        config = ApprovalConfig(
            default_approver="skip",
            default_max_retries=1,
            default_allow_rewrite=True,
        )

        result = config.get_stage_config("generate", "prompt")

        assert result.approver == "skip"
        assert result.max_retries == 1
        assert result.allow_rewrite is True


class TestApprovalConfigFromDict:
    """Tests for ApprovalConfig.from_dict()."""

    def test_from_none_returns_defaults(self):
        """from_dict(None) returns default config."""
        config = ApprovalConfig.from_dict(None)

        assert config.default_approver == "manual"
        assert config.stages == {}

    def test_from_empty_dict_returns_defaults(self):
        """from_dict({}) returns default config."""
        config = ApprovalConfig.from_dict({})

        assert config.default_approver == "manual"
        assert config.stages == {}

    def test_simple_string_format(self):
        """from_dict handles simple stage -> approver mapping."""
        data = {
            "plan.prompt": "skip",
            "plan.response": "claude-code",
            "generate.response": "manual",
        }

        config = ApprovalConfig.from_dict(data)

        assert config.get_stage_config("plan", "prompt").approver == "skip"
        assert config.get_stage_config("plan", "response").approver == "claude-code"
        assert config.get_stage_config("generate", "response").approver == "manual"

    def test_full_format_with_defaults(self):
        """from_dict handles full format with defaults."""
        data = {
            "default_approver": "skip",
            "default_max_retries": 2,
            "default_allow_rewrite": True,
            "stages": {
                "plan.response": {
                    "approver": "claude-code",
                    "max_retries": 5,
                },
            },
        }

        config = ApprovalConfig.from_dict(data)

        assert config.default_approver == "skip"
        assert config.default_max_retries == 2
        assert config.default_allow_rewrite is True

        # Configured stage
        plan_response = config.get_stage_config("plan", "response")
        assert plan_response.approver == "claude-code"
        assert plan_response.max_retries == 5

        # Unconfigured stage uses defaults
        generate_prompt = config.get_stage_config("generate", "prompt")
        assert generate_prompt.approver == "skip"
        assert generate_prompt.max_retries == 2
        assert generate_prompt.allow_rewrite is True

    def test_mixed_format(self):
        """from_dict handles mixed string and dict values."""
        data = {
            "plan.prompt": "skip",  # Simple string
            "plan.response": {      # Full dict
                "approver": "claude-code",
                "max_retries": 3,
                "allow_rewrite": True,
            },
        }

        config = ApprovalConfig.from_dict(data)

        plan_prompt = config.get_stage_config("plan", "prompt")
        assert plan_prompt.approver == "skip"
        assert plan_prompt.max_retries == 0  # default

        plan_response = config.get_stage_config("plan", "response")
        assert plan_response.approver == "claude-code"
        assert plan_response.max_retries == 3
        assert plan_response.allow_rewrite is True

    def test_stages_key_and_top_level_combined(self):
        """from_dict combines stages key with top-level stage configs."""
        data = {
            "default_approver": "manual",
            "stages": {
                "plan.response": {"approver": "claude-code"},
            },
            "generate.response": "skip",  # Top-level stage key
        }

        config = ApprovalConfig.from_dict(data)

        assert config.get_stage_config("plan", "response").approver == "claude-code"
        assert config.get_stage_config("generate", "response").approver == "skip"

    def test_partial_stage_config_uses_defaults(self):
        """Stage config missing fields uses defaults."""
        data = {
            "default_max_retries": 5,
            "plan.response": {
                "approver": "claude-code",
                # max_retries not specified
            },
        }

        config = ApprovalConfig.from_dict(data)

        stage = config.get_stage_config("plan", "response")
        assert stage.approver == "claude-code"
        assert stage.max_retries == 5  # From default

    def test_invalid_value_type_raises(self):
        """from_dict raises on invalid value types."""
        data = {
            "plan.response": 123,  # Invalid: not string or dict
        }

        with pytest.raises(ValueError) as exc_info:
            ApprovalConfig.from_dict(data)

        assert "Invalid stage config" in str(exc_info.value)
        assert "plan.response" in str(exc_info.value)


class TestLoadApprovalConfig:
    """Tests for load_approval_config function."""

    def test_from_dict(self):
        """load_approval_config accepts dict."""
        data = {"plan.prompt": "skip"}

        config = load_approval_config(config_dict=data)

        assert config.get_stage_config("plan", "prompt").approver == "skip"

    def test_from_none_returns_defaults(self):
        """load_approval_config with no args returns defaults."""
        config = load_approval_config()

        assert config.default_approver == "manual"

    def test_from_yaml_file(self, tmp_path):
        """load_approval_config loads from YAML file."""
        config_file = tmp_path / "approval.yml"
        config_file.write_text("""
plan.prompt: skip
plan.response:
  approver: claude-code
  max_retries: 3
""")

        config = load_approval_config(config_file=str(config_file))

        assert config.get_stage_config("plan", "prompt").approver == "skip"
        assert config.get_stage_config("plan", "response").approver == "claude-code"
        assert config.get_stage_config("plan", "response").max_retries == 3

    def test_from_yaml_with_approval_key(self, tmp_path):
        """load_approval_config extracts 'approval' key from YAML."""
        config_file = tmp_path / "config.yml"
        config_file.write_text("""
other_setting: value
approval:
  plan.response: claude-code
  default_max_retries: 2
""")

        config = load_approval_config(config_file=str(config_file))

        assert config.get_stage_config("plan", "response").approver == "claude-code"
        assert config.default_max_retries == 2

    def test_from_yaml_with_approval_config_key(self, tmp_path):
        """load_approval_config extracts 'approval_config' key from YAML."""
        config_file = tmp_path / "config.yml"
        config_file.write_text("""
approval_config:
  generate.response: skip
""")

        config = load_approval_config(config_file=str(config_file))

        assert config.get_stage_config("generate", "response").approver == "skip"

    def test_file_not_found_raises(self):
        """load_approval_config raises on missing file."""
        with pytest.raises(FileNotFoundError):
            load_approval_config(config_file="/nonexistent/file.yml")

    def test_dict_takes_priority_over_file(self, tmp_path):
        """config_dict takes priority over config_file."""
        config_file = tmp_path / "config.yml"
        config_file.write_text("plan.prompt: skip")

        config = load_approval_config(
            config_dict={"plan.prompt": "claude-code"},
            config_file=str(config_file),
        )

        # Dict value should win
        assert config.get_stage_config("plan", "prompt").approver == "claude-code"


class TestApprovalConfigStageKeys:
    """Tests for stage key handling."""

    def test_all_phase_stage_combinations(self):
        """Config handles all valid phase.stage combinations."""
        data = {
            "plan.prompt": "skip",
            "plan.response": "claude-code",
            "generate.prompt": "manual",
            "generate.response": "claude-code",
            "review.prompt": "skip",
            "review.response": "claude-code",
            "revise.prompt": "skip",
            "revise.response": "manual",
        }

        config = ApprovalConfig.from_dict(data)

        # All 8 combinations should be accessible
        assert config.get_stage_config("plan", "prompt").approver == "skip"
        assert config.get_stage_config("plan", "response").approver == "claude-code"
        assert config.get_stage_config("generate", "prompt").approver == "manual"
        assert config.get_stage_config("generate", "response").approver == "claude-code"
        assert config.get_stage_config("review", "prompt").approver == "skip"
        assert config.get_stage_config("review", "response").approver == "claude-code"
        assert config.get_stage_config("revise", "prompt").approver == "skip"
        assert config.get_stage_config("revise", "response").approver == "manual"

    def test_unconfigured_stages_use_defaults(self):
        """Stages not in config use defaults."""
        config = ApprovalConfig(
            default_approver="skip",
            default_max_retries=1,
            stages={
                "plan.response": StageApprovalConfig(approver="claude-code"),
            },
        )

        # Configured
        assert config.get_stage_config("plan", "response").approver == "claude-code"

        # Not configured - uses defaults
        assert config.get_stage_config("plan", "prompt").approver == "skip"
        assert config.get_stage_config("plan", "prompt").max_retries == 1
        assert config.get_stage_config("generate", "response").approver == "skip"
