from pathlib import Path
import pytest

from profiles.jpa_mt.jpa_mt_standards_provider import JpaMtStandardsProvider


def _provider_config(standards_root: Path, *, scopes: dict, layer_standards: dict) -> dict:
    return {
        "standards": {"root": str(standards_root)},
        "scopes": scopes,
        "layer_standards": layer_standards,
    }


def test_unknown_scope_raises_value_error(temp_standards_root: Path) -> None:
    config = _provider_config(
        temp_standards_root,
        scopes={"domain": {"layers": ["entity"]}},
        layer_standards={"entity": []},
    )
    provider = JpaMtStandardsProvider(config)

    with pytest.raises(ValueError) as excinfo:
        provider.create_bundle({"scope": "not-a-scope"})

    assert "Unknown scope" in str(excinfo.value)


def test_missing_scope_key_raises_value_error(temp_standards_root: Path) -> None:
    config = _provider_config(
        temp_standards_root,
        scopes={"domain": {"layers": ["entity"]}},
        layer_standards={"entity": []},
    )
    provider = JpaMtStandardsProvider(config)

    with pytest.raises(ValueError) as excinfo:
        provider.create_bundle({})

    # Lock message contract on the same substring as the unknown-scope case.
    assert "Unknown scope" in str(excinfo.value)


def test_missing_standards_file_raises_file_not_found(temp_standards_root: Path) -> None:
    # Do NOT create the referenced file.
    config = _provider_config(
        temp_standards_root,
        scopes={"domain": {"layers": ["entity"]}},
        layer_standards={"entity": ["MISSING.md"]},
    )
    provider = JpaMtStandardsProvider(config)

    with pytest.raises(FileNotFoundError) as excinfo:
        provider.create_bundle({"scope": "domain"})

    msg = str(excinfo.value)
    assert "Standards file not found" in msg
    # Include the failing path in the message (full path or suffix is acceptable).
    assert "MISSING.md" in msg


def test_ordering_semantics_preserve_semantic_order(temp_standards_root: Path) -> None:
    # Create files with distinct headers so we can assert ordering by header position.
    (temp_standards_root / "A.md").write_text("A\n", encoding="utf-8")
    (temp_standards_root / "B.md").write_text("B\n", encoding="utf-8")
    (temp_standards_root / "C.md").write_text("C\n", encoding="utf-8")

    config = _provider_config(
        temp_standards_root,
        scopes={"domain": {"layers": ["entity"]}},
        layer_standards={
            "_universal": ["B.md", "A.md"],
            "entity": ["C.md", "A.md"],  # A.md duplicate; must be ignored (first occurrence kept)
        },
    )
    provider = JpaMtStandardsProvider(config)

    bundle = provider.create_bundle({"scope": "domain"})

    idx_b = bundle.index("--- B.md ---\n")
    idx_a = bundle.index("--- A.md ---\n")
    idx_c = bundle.index("--- C.md ---\n")

    assert idx_b < idx_a < idx_c

    # Dedup invariant: A.md appears exactly once.
    assert bundle.count("--- A.md ---\n") == 1


def test_bundle_formatting_invariant_sections_are_well_formed(temp_standards_root: Path) -> None:
    (temp_standards_root / "ORG.md").write_text("# Org\n", encoding="utf-8")
    (temp_standards_root / "JPA.md").write_text("# JPA\n", encoding="utf-8")

    config = _provider_config(
        temp_standards_root,
        scopes={"domain": {"layers": ["entity"]}},
        layer_standards={
            "_universal": ["ORG.md"],
            "entity": ["JPA.md"],
        },
    )
    provider = JpaMtStandardsProvider(config)

    bundle = provider.create_bundle({"scope": "domain"})

    # Required headers must exist exactly once
    assert bundle.count("--- ORG.md ---") == 1
    assert bundle.count("--- JPA.md ---") == 1

    # Split by headers and validate each section content shape.
    # This allows blank lines (or no blank lines) between sections.
    parts = bundle.split("--- ")
    # parts[0] is preamble (expected empty or whitespace)
    sections = [p for p in parts[1:] if p.strip()]

    # Expect two sections in semantic order.
    assert sections[0].startswith("ORG.md ---\n")
    assert sections[1].startswith("JPA.md ---\n")

    org_section = "--- " + sections[0]
    jpa_section = "--- " + sections[1]

    assert org_section.startswith("--- ORG.md ---\n")
    assert "# Org\n" in org_section

    assert jpa_section.startswith("--- JPA.md ---\n")
    assert "# JPA\n" in jpa_section
