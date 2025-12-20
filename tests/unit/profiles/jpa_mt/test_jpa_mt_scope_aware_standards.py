from pathlib import Path

from profiles.jpa_mt.jpa_mt_profile import JpaMtProfile


def _write(root: Path, name: str, content: str) -> None:
    (root / name).write_text(content, encoding="utf-8")


def test_jpa_mt_profile_provider_is_scope_aware_and_filters(tmp_path: Path) -> None:
    standards_root = tmp_path / "standards"
    standards_root.mkdir(parents=True, exist_ok=True)

    _write(standards_root, "ORG.md", "ORG\n")
    _write(standards_root, "JPA_AND_DATABASE.md", "JPA\n")
    _write(standards_root, "ARCHITECTURE_AND_MULTITENANCY.md", "ARCH\n")
    _write(standards_root, "NAMING_AND_API.md", "NAME\n")

    config = {
        "standards": {"root": str(standards_root)},
        "scopes": {
            "domain": {"layers": ["entity", "repository"]},
            "vertical": {"layers": ["entity", "repository", "service"]},
        },
        "layer_standards": {
            "_universal": ["NAMING_AND_API.md"],
            "entity": ["ORG.md"],
            "repository": ["JPA_AND_DATABASE.md"],
            "service": ["ARCHITECTURE_AND_MULTITENANCY.md"],
        },
    }

    profile = JpaMtProfile(**config)
    provider = profile.get_standards_provider()

    bundle = provider.create_bundle({"scope": "domain"})

    assert "--- NAMING_AND_API.md ---\n" in bundle
    assert "--- ORG.md ---\n" in bundle
    assert "--- JPA_AND_DATABASE.md ---\n" in bundle
    assert "--- ARCHITECTURE_AND_MULTITENANCY.md ---\n" not in bundle
