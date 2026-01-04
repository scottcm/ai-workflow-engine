from pathlib import Path
from typing import Any, TYPE_CHECKING

import yaml
from pydantic import ValidationError

from aiwf.domain.providers.capabilities import VALID_FS_ABILITIES
from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStage

if TYPE_CHECKING:
    from aiwf.application.config_models import WorkflowConfig


class ConfigLoadError(Exception):
    def __init__(self, message: str, *, path: Path | None = None, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.path = path
        self.cause = cause

    def __str__(self) -> str:
        if self.path is None:
            return self.message
        return f"{self.message}: {self.path}"



def _defaults() -> dict[str, Any]:
    return {
        "profile": None,  # No default profile - must be specified via CLI or config
        "providers": {
            "planner": "manual",
            "generator": "manual",
            "reviewer": "manual",
            "reviser": "manual",
        },
        "hash_prompts": False,
        "dev": None,
        "default_standards_provider": "scoped-layer-fs",
        "profiles_dir": None,  # Default: ~/.aiwf/profiles/
    }


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """
    Deep-merge mapping keys. For non-dict values, overlay wins.

    This satisfies "deep-merge providers by key" and is generally safe for other nested maps.
    """
    merged: dict[str, Any] = dict(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = _deep_merge(merged[k], v)  # type: ignore[arg-type]
        else:
            merged[k] = v
    return merged


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    """
    Load YAML file and ensure root is a mapping.
    """
    # Protect against TOCTOU race conditions.
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except Exception as e:  # pragma: no cover
        raise ConfigLoadError("Failed to read config file", path=path, cause=e) from e

    try:
        data = yaml.safe_load(raw)
    except Exception as e:
        raise ConfigLoadError("Malformed YAML", path=path, cause=e) from e

    if data is None:
        return {}

    if not isinstance(data, dict):
        raise ConfigLoadError("YAML root must be a mapping", path=path)

    return data


def _expand_default_provider(providers: dict[str, str]) -> dict[str, str]:
    """
    Expand 'default' key to all provider roles.

    If providers contains a 'default' key, its value is applied to any
    role that isn't explicitly set. The 'default' key is then removed.

    Example:
        Input:  {"default": "claude", "reviewer": "manual"}
        Output: {"planner": "claude", "generator": "claude",
                 "reviewer": "manual", "reviser": "claude"}
    """
    if "default" not in providers:
        return providers

    default_value = providers["default"]
    roles = ["planner", "generator", "reviewer", "reviser"]

    expanded = {}
    for role in roles:
        if role in providers:
            expanded[role] = providers[role]
        else:
            expanded[role] = default_value

    return expanded


def _validate_fs_ability(value: str, source: str) -> str:
    """Validate fs_ability value.

    Args:
        value: The fs_ability value to validate
        source: Description of where the value came from (for error message)

    Returns:
        The validated value

    Raises:
        ConfigLoadError: If value is not valid
    """
    if value not in VALID_FS_ABILITIES:
        valid = ", ".join(sorted(VALID_FS_ABILITIES))
        raise ConfigLoadError(
            f"Invalid fs_ability '{value}' in {source}. Valid values: {valid}"
        )
    return value


def resolve_fs_ability(
    cli_override: str | None,
    provider_key: str,
    config: dict[str, Any],
    provider_metadata: dict[str, Any],
) -> str:
    """Resolve fs_ability with precedence: CLI > config > provider > default.

    Args:
        cli_override: Value from --fs-ability CLI flag (already validated by Click)
        provider_key: Provider name (e.g., "manual", "claude-code")
        config: Loaded config dict
        provider_metadata: Provider's get_metadata() result

    Returns:
        Resolved fs_ability value

    Raises:
        ConfigLoadError: If config contains invalid fs_ability value
    """
    # 1. CLI override (highest precedence) - already validated by Click
    if cli_override:
        return cli_override

    # 2. Config: per-provider setting
    providers_config = config.get("providers", {})
    provider_config = providers_config.get(provider_key, {})
    if isinstance(provider_config, dict) and "fs_ability" in provider_config:
        return _validate_fs_ability(
            provider_config["fs_ability"],
            f"providers.{provider_key}.fs_ability",
        )

    # 3. Config: global default
    defaults_config = providers_config.get("defaults", {})
    if isinstance(defaults_config, dict) and "fs_ability" in defaults_config:
        return _validate_fs_ability(
            defaults_config["fs_ability"],
            "providers.defaults.fs_ability",
        )

    # 4. Provider metadata
    provider_fs_ability = provider_metadata.get("fs_ability")
    if provider_fs_ability:
        return provider_fs_ability

    # 5. Engine default
    return "local-write"


def load_config(*, project_root: Path | None = None, user_home: Path | None = None) -> dict[str, Any]:
    """
    Load and merge config with precedence (highest wins):
    CLI args (handled in CLI) > project > user > defaults.

    Files:
      - user:    user_home/.aiwf/config.yml
      - project: project_root/.aiwf/config.yml

    Special handling:
      - providers.default: Expands to all roles not explicitly set.
        Expansion happens per-layer before merge so that 'default: claude'
        correctly overrides built-in defaults.
    """
    project_root = project_root or Path.cwd()
    user_home = user_home or Path.home()

    cfg: dict[str, Any] = _defaults()

    # Load and expand user config before merge
    user_path = user_home / ".aiwf" / "config.yml"
    user_cfg = _load_yaml_mapping(user_path)
    if "providers" in user_cfg and isinstance(user_cfg["providers"], dict):
        user_cfg["providers"] = _expand_default_provider(user_cfg["providers"])
    cfg = _deep_merge(cfg, user_cfg)

    # Load and expand project config before merge
    project_path = project_root / ".aiwf" / "config.yml"
    project_cfg = _load_yaml_mapping(project_path)
    if "providers" in project_cfg and isinstance(project_cfg["providers"], dict):
        project_cfg["providers"] = _expand_default_provider(project_cfg["providers"])
    cfg = _deep_merge(cfg, project_cfg)

    return cfg


# Valid phase and stage names for V2 workflow config
_VALID_PHASES = {"defaults", "plan", "generate", "review", "revise"}
_VALID_STAGES = {"prompt", "response"}


def load_workflow_config(yaml_path: Path) -> "WorkflowConfig":
    """Load and validate V2 workflow configuration from YAML.

    Args:
        yaml_path: Path to the workflow config YAML file

    Returns:
        Parsed and validated WorkflowConfig

    Raises:
        ConfigLoadError: If file not found, malformed, or invalid structure
    """
    # Import here to avoid circular imports
    from aiwf.application.config_models import (
        WorkflowConfig,
        PhaseConfig,
        StageConfig,
    )

    # Load YAML file
    if not yaml_path.exists():
        raise ConfigLoadError(f"Config file not found: {yaml_path}", path=yaml_path)

    try:
        raw = yaml_path.read_text(encoding="utf-8")
    except Exception as e:
        raise ConfigLoadError("Failed to read config file", path=yaml_path, cause=e) from e

    try:
        data = yaml.safe_load(raw)
    except Exception as e:
        raise ConfigLoadError("Malformed YAML", path=yaml_path, cause=e) from e

    if not isinstance(data, dict):
        raise ConfigLoadError("YAML root must be a mapping", path=yaml_path)

    # Extract workflow section
    if "workflow" not in data:
        raise ConfigLoadError(
            "Missing 'workflow' key in config file",
            path=yaml_path,
        )

    workflow_data = data["workflow"]
    if not isinstance(workflow_data, dict):
        raise ConfigLoadError(
            "'workflow' must be a mapping",
            path=yaml_path,
        )

    # Validate phase/stage names before parsing
    for key in workflow_data:
        if key not in _VALID_PHASES:
            raise ConfigLoadError(
                f"Unknown phase '{key}' in workflow config. "
                f"Valid phases: {sorted(_VALID_PHASES)}",
                path=yaml_path,
            )
        # Check stage names for phase configs (not defaults)
        if key != "defaults" and isinstance(workflow_data[key], dict):
            for stage_key in workflow_data[key]:
                if stage_key not in _VALID_STAGES:
                    raise ConfigLoadError(
                        f"Unknown stage '{stage_key}' in workflow.{key}. "
                        f"Valid stages: {sorted(_VALID_STAGES)}",
                        path=yaml_path,
                    )

    # Parse into Pydantic models
    try:
        # Parse defaults
        defaults_data = workflow_data.get("defaults", {})
        defaults = StageConfig(**defaults_data) if defaults_data else StageConfig()

        # Parse phase configs
        phases: dict[str, PhaseConfig | None] = {}
        for phase_name in ["plan", "generate", "review", "revise"]:
            phase_data = workflow_data.get(phase_name)
            if phase_data is None:
                phases[phase_name] = None
            else:
                prompt_data = phase_data.get("prompt")
                response_data = phase_data.get("response")
                phases[phase_name] = PhaseConfig(
                    prompt=StageConfig(**prompt_data) if prompt_data else None,
                    response=StageConfig(**response_data) if response_data else None,
                )

        return WorkflowConfig(
            defaults=defaults,
            plan=phases["plan"],
            generate=phases["generate"],
            review=phases["review"],
            revise=phases["revise"],
        )

    except ValidationError as e:
        raise ConfigLoadError(
            f"Invalid config structure: {e}",
            path=yaml_path,
            cause=e,
        ) from e


def validate_provider_keys(config: "WorkflowConfig") -> None:
    """Dry-run validation: ensure all AI/approval provider keys resolve.

    Iterates all phase/stage combinations and validates that:
    1. AI provider keys exist in AIProviderFactory (RESPONSE stages only)
    2. Approval provider keys exist in ApprovalProviderFactory OR AIProviderFactory

    Args:
        config: The WorkflowConfig to validate

    Raises:
        ConfigLoadError: If any provider key is not registered
    """
    from aiwf.domain.providers.provider_factory import AIProviderFactory
    from aiwf.domain.providers.approval_factory import ApprovalProviderFactory

    # Active phases that need validation
    active_phases = [
        WorkflowPhase.PLAN,
        WorkflowPhase.GENERATE,
        WorkflowPhase.REVIEW,
        WorkflowPhase.REVISE,
    ]

    for phase in active_phases:
        for stage in [WorkflowStage.PROMPT, WorkflowStage.RESPONSE]:
            stage_config = config.get_stage_config(phase, stage)

            # Validate ai_provider for RESPONSE stages
            if stage == WorkflowStage.RESPONSE:
                ai_provider = stage_config.ai_provider
                if not ai_provider:
                    raise ConfigLoadError(
                        f"ai_provider required for RESPONSE stage in {phase.value}. "
                        f"Set ai_provider in defaults or {phase.value}.response."
                    )
                if ai_provider not in AIProviderFactory.list_providers():
                    available = AIProviderFactory.list_providers()
                    raise ConfigLoadError(
                        f"Unknown ai_provider '{ai_provider}' in {phase.value}.{stage.value}. "
                        f"Available AI providers: {available}"
                    )

            # Validate approval_provider for all stages
            approval_provider = stage_config.approval_provider
            # Check if it's a built-in approval provider
            builtin_approval = {"skip", "manual"}
            if approval_provider not in builtin_approval:
                # Must be a registered AI provider (for wrapping)
                if approval_provider not in AIProviderFactory.list_providers():
                    available_ai = AIProviderFactory.list_providers()
                    raise ConfigLoadError(
                        f"Unknown approval_provider '{approval_provider}' "
                        f"in {phase.value}.{stage.value}. "
                        f"Valid options: {sorted(builtin_approval)} or AI providers: {available_ai}"
                    )
