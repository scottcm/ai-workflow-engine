from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


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
