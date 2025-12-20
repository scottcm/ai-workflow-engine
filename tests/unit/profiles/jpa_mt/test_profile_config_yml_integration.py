from pathlib import Path

import pytest
import yaml

from profiles.jpa_mt.jpa_mt_config import JpaMtConfig
from profiles.jpa_mt.jpa_mt_standards_provider import JpaMtStandardsProvider


def _load_repo_config_yml() -> dict:
    cfg_path = Path("profiles/jpa_mt/config.yml")
    return yaml.safe_load(cfg_path.read_text(encoding="utf-8"))


def _required_files_for_scope(model: JpaMtConfig, scope: str) -> set[str]:
    required: set[str] = set()

    # Always include universal standards first, but we return a set because
    # the integration test validates membership, not ordering.
    required.update(model.layer_standards.get("_universal", []))

    scope_layers = model.scopes[scope].layers
    for layer in scope_layers:
        required.update(model.layer_standards.get(layer, []))

    return required


def _materialize_required_files(standards_root: Path, required: set[str]) -> None:
    for name in required:
        p = standards_root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"# {name}\n", encoding="utf-8")


def _pick_not_required_name(model: JpaMtConfig, required: set[str], *, exclude_scope: str) -> str | None:
    """
    Pick one standards file from a layer that is NOT in exclude_scope's layers,
    is present in config, and is NOT in the required set.
    """
    excluded_layers = set(model.scopes[exclude_scope].layers)

    for layer, files in model.layer_standards.items():
        if layer == "_universal":
            continue
        if layer in excluded_layers:
            continue
        for name in files:
            if name not in required:
                return name

    return None


def test_profile_config_yml_validates_and_bundles_domain_scope(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Arrange
    standards_root = tmp_path / "standards"
    standards_root.mkdir()
    monkeypatch.setenv("STANDARDS_DIR", str(standards_root))

    cfg = _load_repo_config_yml()
    model = JpaMtConfig.model_validate(cfg)

    required = _required_files_for_scope(model, "domain")
    _materialize_required_files(standards_root, required)

    # Instantiate provider using validated/expanded config (end-to-end realistic shape)
    provider = JpaMtStandardsProvider(model.model_dump())

    # Act
    bundle = provider.create_bundle({"scope": "domain"})

    # Assert: all required sections exist with expected marker content
    for name in required:
        assert f"--- {name} ---" in bundle
        assert f"# {name}\n" in bundle

    # Assert: one not-required config file does NOT appear in the domain bundle
    not_required_name = _pick_not_required_name(model, required, exclude_scope="domain")
    if not_required_name is None:
        pytest.skip("No non-domain standards file found in config.yml to use for absence assertion")

    assert f"--- {not_required_name} ---" not in bundle


def test_profile_config_yml_bundles_vertical_scope(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Arrange
    standards_root = tmp_path / "standards"
    standards_root.mkdir()
    monkeypatch.setenv("STANDARDS_DIR", str(standards_root))

    cfg = _load_repo_config_yml()
    model = JpaMtConfig.model_validate(cfg)

    # dto contributes nothing (recommended invariant)
    assert model.layer_standards["dto"] == []

    required = _required_files_for_scope(model, "vertical")
    _materialize_required_files(standards_root, required)

    provider = JpaMtStandardsProvider(model.model_dump())

    # Act
    bundle = provider.create_bundle({"scope": "vertical"})

    # Assert: all required sections exist with expected marker content
    for name in required:
        assert f"--- {name} ---" in bundle
        assert f"# {name}\n" in bundle

    # Assert: dto contributes nothing (no dto-only files should be expected)
    # (This is effectively guaranteed by assert dto == [] above; kept explicit per requirement.)
    assert model.layer_standards["dto"] == []
