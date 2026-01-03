"""Approval configuration for workflow stages.

Per-stage configuration for approval providers and their settings.
"""

from typing import Any

from pydantic import BaseModel, Field


class StageApprovalConfig(BaseModel):
    """Configuration for approval at a specific stage.

    Attributes:
        approver: Approval provider key ("skip", "manual", or response provider key)
        max_retries: Maximum automatic retries on rejection (0 = no retries)
        allow_rewrite: Whether approver can suggest content rewrites
    """

    approver: str = "manual"
    max_retries: int = 0
    allow_rewrite: bool = False


class ApprovalConfig(BaseModel):
    """Complete approval configuration for a workflow.

    Maps stage keys to their approval settings.
    Stage keys use format: "{phase}.{stage}" (e.g., "plan.prompt", "generate.response")

    Attributes:
        stages: Dict mapping stage key to StageApprovalConfig
        default_approver: Default approver for stages not explicitly configured
        default_max_retries: Default max retries for stages not configured
        default_allow_rewrite: Default allow_rewrite for stages not configured
    """

    stages: dict[str, StageApprovalConfig] = Field(default_factory=dict)
    default_approver: str = "manual"
    default_max_retries: int = 0
    default_allow_rewrite: bool = False

    def get_stage_config(self, phase: str, stage: str) -> StageApprovalConfig:
        """Get approval config for a specific stage.

        Args:
            phase: Phase name (e.g., "plan", "generate", "review", "revise")
            stage: Stage name (e.g., "prompt", "response")

        Returns:
            StageApprovalConfig for the stage, using defaults if not configured
        """
        key = f"{phase}.{stage}"

        if key in self.stages:
            return self.stages[key]

        # Return default config
        return StageApprovalConfig(
            approver=self.default_approver,
            max_retries=self.default_max_retries,
            allow_rewrite=self.default_allow_rewrite,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ApprovalConfig":
        """Create ApprovalConfig from a configuration dictionary.

        Supports multiple input formats:

        Format 1: Simple stage -> approver mapping
        ```
        {
            "plan.prompt": "skip",
            "plan.response": "claude-code",
        }
        ```

        Format 2: Full configuration with defaults
        ```
        {
            "default_approver": "manual",
            "default_max_retries": 2,
            "stages": {
                "plan.response": {
                    "approver": "claude-code",
                    "max_retries": 3,
                },
            }
        }
        ```

        Format 3: Stage with mixed values (string or dict)
        ```
        {
            "plan.prompt": "skip",  # Simple string
            "plan.response": {"approver": "claude-code", "max_retries": 3},  # Full config
        }
        ```

        Args:
            data: Configuration dictionary

        Returns:
            ApprovalConfig instance
        """
        if data is None:
            return cls()

        # Extract defaults if present
        default_approver = data.get("default_approver", "manual")
        default_max_retries = data.get("default_max_retries", 0)
        default_allow_rewrite = data.get("default_allow_rewrite", False)

        # Build stages dict
        stages: dict[str, StageApprovalConfig] = {}

        # Check for explicit "stages" key (Format 2)
        stages_data = data.get("stages", {})

        # Also check for stage keys at top level (Format 1 & 3)
        for key, value in data.items():
            if key in ("default_approver", "default_max_retries", "default_allow_rewrite", "stages"):
                continue

            # Check if this looks like a stage key (contains a dot)
            if "." in key:
                stages_data[key] = value

        # Parse each stage
        for key, value in stages_data.items():
            if isinstance(value, str):
                # Simple string -> just the approver key
                stages[key] = StageApprovalConfig(
                    approver=value,
                    max_retries=default_max_retries,
                    allow_rewrite=default_allow_rewrite,
                )
            elif isinstance(value, dict):
                # Full config dict
                stages[key] = StageApprovalConfig(
                    approver=value.get("approver", default_approver),
                    max_retries=value.get("max_retries", default_max_retries),
                    allow_rewrite=value.get("allow_rewrite", default_allow_rewrite),
                )
            else:
                raise ValueError(
                    f"Invalid stage config for '{key}': expected str or dict, got {type(value)}"
                )

        return cls(
            stages=stages,
            default_approver=default_approver,
            default_max_retries=default_max_retries,
            default_allow_rewrite=default_allow_rewrite,
        )


def load_approval_config(
    config_dict: dict[str, Any] | None = None,
    config_file: str | None = None,
) -> ApprovalConfig:
    """Load approval configuration from dict or file.

    Args:
        config_dict: Configuration dictionary (takes priority)
        config_file: Path to YAML configuration file

    Returns:
        ApprovalConfig instance

    Raises:
        FileNotFoundError: If config_file specified but not found
        ValueError: If configuration is invalid
    """
    if config_dict is not None:
        return ApprovalConfig.from_dict(config_dict)

    if config_file is not None:
        import yaml
        from pathlib import Path

        config_path = Path(config_file)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_file}")

        with open(config_path) as f:
            data = yaml.safe_load(f)

        # Look for approval config in the data
        if "approval" in data:
            return ApprovalConfig.from_dict(data["approval"])
        elif "approval_config" in data:
            return ApprovalConfig.from_dict(data["approval_config"])
        else:
            return ApprovalConfig.from_dict(data)

    # Return default config
    return ApprovalConfig()
