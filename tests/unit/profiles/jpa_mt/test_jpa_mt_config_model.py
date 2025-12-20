from typing import Any

import pytest
from pydantic import ValidationError

from aiwf.domain.validation.path_validator import PathValidator
from profiles.jpa_mt.jpa_mt_config import JpaMtConfig


def _minimal_valid_config(*, root: str) -> dict[str, Any]:
    return {
        "standards": {"root": root},
        "scopes": {
            "domain": {
                "description": "optional",
                "layers": ["entity", "repository"],
            }
        },
        "layer_standards": {
            "_universal": ["core/ORG.md"],
            "entity": ["db/java/JPA_AND_DATABASE.md"],
            "repository": [r"db\java\JPA_AND_DATABASE.md"],
        },
    }


def test_minimal_valid_config_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STANDARDS_DIR", "/tmp/standards")
    cfg = _minimal_valid_config(root="${STANDARDS_DIR}")

    model = JpaMtConfig.model_validate(cfg)

    assert model.standards.root == "/tmp/standards"
    assert "domain" in model.scopes
    assert model.scopes["domain"].layers == ["entity", "repository"]
    assert "_universal" in model.layer_standards


def test_env_expansion_occurs_via_pathvalidator(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STANDARDS_DIR", "/x/y/z")
    cfg = _minimal_valid_config(root="${STANDARDS_DIR}")

    calls: list[str] = []
    original = PathValidator.expand_env_vars

    def _spy(v: str) -> str:
        calls.append(v)
        return original(v)

    monkeypatch.setattr(PathValidator, "expand_env_vars", _spy)

    model = JpaMtConfig.model_validate(cfg)

    assert model.standards.root == "/x/y/z"
    # Relaxed: assert we invoked PathValidator with the env-var pattern somewhere.
    assert any("${STANDARDS_DIR}" in c for c in calls)


def test_missing_env_var_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STANDARDS_DIR", raising=False)
    cfg = _minimal_valid_config(root="${STANDARDS_DIR}")

    with pytest.raises(ValidationError):
        JpaMtConfig.model_validate(cfg)


def test_scopes_require_non_empty_layers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STANDARDS_DIR", "/tmp/standards")
    cfg = _minimal_valid_config(root="${STANDARDS_DIR}")
    cfg["scopes"]["domain"]["layers"] = []

    with pytest.raises(ValidationError):
        JpaMtConfig.model_validate(cfg)


def test_layer_standards_entries_validated_via_pathvalidator(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Must allow subdirs and backslashes; must call validate_relative_path_pattern,
    but test must not depend on validation ordering.
    """
    monkeypatch.setenv("STANDARDS_DIR", "/tmp/standards")
    cfg = _minimal_valid_config(root="${STANDARDS_DIR}")
    entries = ["dir/subdir/file.md", r"dir\subdir\file.md"]
    cfg["layer_standards"]["entity"] = entries

    calls: list[str] = []
    original = PathValidator.validate_relative_path_pattern

    def _spy(v: str) -> str:
        calls.append(v)
        return original(v)

    monkeypatch.setattr(PathValidator, "validate_relative_path_pattern", _spy)

    model = JpaMtConfig.model_validate(cfg)

    assert model.layer_standards["entity"] == entries
    assert set(calls) >= set(entries)



@pytest.mark.parametrize("bad_path", ["/x.md", r"\x.md", r"C:\x.md", r"\\srv\share\x.md"])
def test_absolute_paths_rejected(monkeypatch: pytest.MonkeyPatch, bad_path: str) -> None:
    monkeypatch.setenv("STANDARDS_DIR", "/tmp/standards")
    cfg = _minimal_valid_config(root="${STANDARDS_DIR}")
    cfg["layer_standards"]["entity"] = [bad_path]

    with pytest.raises(ValidationError):
        JpaMtConfig.model_validate(cfg)


@pytest.mark.parametrize("bad_path", ["../x.md", r"..\x.md", "a/../x.md", r"a\..\x.md"])
def test_traversal_rejected(monkeypatch: pytest.MonkeyPatch, bad_path: str) -> None:
    monkeypatch.setenv("STANDARDS_DIR", "/tmp/standards")
    cfg = _minimal_valid_config(root="${STANDARDS_DIR}")
    cfg["layer_standards"]["entity"] = [bad_path]

    with pytest.raises(ValidationError):
        JpaMtConfig.model_validate(cfg)


@pytest.mark.parametrize("bad_path", ["./x.md", r".\x.md", "a/./x.md", r"a\.\x.md"])
def test_dot_segments_rejected(monkeypatch: pytest.MonkeyPatch, bad_path: str) -> None:
    monkeypatch.setenv("STANDARDS_DIR", "/tmp/standards")
    cfg = _minimal_valid_config(root="${STANDARDS_DIR}")
    cfg["layer_standards"]["entity"] = [bad_path]

    with pytest.raises(ValidationError):
        JpaMtConfig.model_validate(cfg)


def test_null_list_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STANDARDS_DIR", "/tmp/standards")
    cfg = _minimal_valid_config(root="${STANDARDS_DIR}")
    cfg["layer_standards"]["dto"] = None  # YAML null equivalent

    with pytest.raises(ValidationError):
        JpaMtConfig.model_validate(cfg)


def test_empty_list_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Locks contract: null is invalid, but an explicit empty list is valid.
    """
    monkeypatch.setenv("STANDARDS_DIR", "/tmp/standards")
    cfg = _minimal_valid_config(root="${STANDARDS_DIR}")
    cfg["layer_standards"]["dto"] = []

    model = JpaMtConfig.model_validate(cfg)

    assert model.layer_standards["dto"] == []


def test_coverage_rule_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STANDARDS_DIR", "/tmp/standards")

    cfg: dict[str, Any] = {
        "standards": {"root": "${STANDARDS_DIR}"},
        "scopes": {"domain": {"layers": ["entity"]}},
        "layer_standards": {
            # missing "entity" and missing "_universal"
            "repository": ["x.md"]
        },
    }

    with pytest.raises(ValidationError):
        JpaMtConfig.model_validate(cfg)


def test_coverage_satisfied_by_universal(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Positive coverage case:
    - scopes references 'entity'
    - layer_standards lacks 'entity'
    - but has '_universal', which satisfies coverage
    """
    monkeypatch.setenv("STANDARDS_DIR", "/tmp/standards")

    cfg: dict[str, Any] = {
        "standards": {"root": "${STANDARDS_DIR}"},
        "scopes": {"domain": {"layers": ["entity"]}},
        "layer_standards": {
            "_universal": ["core/ORG.md"],
            # no 'entity' key
        },
    }

    model = JpaMtConfig.model_validate(cfg)
    assert model.layer_standards["_universal"] == ["core/ORG.md"]


def test_legacy_top_level_keys_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STANDARDS_DIR", "/tmp/standards")
    cfg = _minimal_valid_config(root="${STANDARDS_DIR}")
    cfg["artifacts"] = {"session_root": ".aiwf/sessions"}  # legacy key; must be ignored

    model = JpaMtConfig.model_validate(cfg)

    assert "artifacts" not in model.model_dump()
