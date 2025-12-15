from __future__ import annotations

from pathlib import Path
import shutil

import pytest
import yaml

from profiles.jpa_mt.jpa_mt_profile import JpaMtProfile
from aiwf.domain.models.processing_result import ProcessingResult


class _TestableJpaMtProfile(JpaMtProfile):
    """Concrete test-only subclass to satisfy WorkflowProfile abstract methods.

    These tests only exercise prompt generation. Response-processing methods are
    required by the WorkflowProfile contract but are not invoked here.
    """

    def process_planning_response(self, content: str) -> ProcessingResult:
        raise NotImplementedError

    def process_generation_response(
        self, content: str, session_dir: Path, iteration: int
    ) -> ProcessingResult:
        raise NotImplementedError

    def process_review_response(self, content: str) -> ProcessingResult:
        raise NotImplementedError

    def process_revision_response(
        self, content: str, session_dir: Path, iteration: int
    ) -> ProcessingResult:
        raise NotImplementedError


def _write(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


def _write_config(config_path: Path, standards_root: Path) -> None:
    # IMPORTANT: JpaMtProfile validates standards.root as an existing absolute directory.
    cfg = {
        "standards": {"root": str(standards_root.resolve())},
        "artifacts": {},
        "scopes": {"domain": {"layers": []}},
        "layer_standards": {},
    }
    _write(config_path, yaml.safe_dump(cfg))


@pytest.fixture
def jpa_mt_test_profile_root(repo_root: Path) -> Path:
    """Repo-local scratch directory for this test module (not tmp_path)."""
    root = repo_root / ".pytest_tmp" / "jpa_mt_prompt_generation"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_generate_planning_prompt_happy_path(
    standards_samples_dir: Path, jpa_mt_test_profile_root: Path
) -> None:
    # Use the shared fixture that points at the repo's standards sample directory.
    standards_root = standards_samples_dir
    if not standards_root.exists():
        pytest.skip(f"standards sample directory not found: {standards_root}")

    config_path = jpa_mt_test_profile_root / "config.yml"
    templates_root = jpa_mt_test_profile_root / "templates"

    _write_config(config_path, standards_root)

    _write(
        templates_root / "planning" / "domain.md",
        """Hello {{ENTITY}}
{{include: shared.md}}
""",
    )
    _write(templates_root / "shared.md", "Table={{TABLE}}")

    profile = _TestableJpaMtProfile(config_path=config_path)

    context = {
        "TASK_ID": "TEST-1",
        "DEV": "Scott",
        "DATE": "2025-01-01",
        "ENTITY": "Tier",
        "SCOPE": "domain",
        "TABLE": "global.tiers",
        "BOUNDED_CONTEXT": "catalog",
        "SESSION_ID": "session-1",
        "PROFILE": "jpa-mt",
        "ITERATION": "1",
        "scope": "domain",
    }

    prompt = profile.generate_planning_prompt(context)

    assert isinstance(prompt, str)
    assert "{{include:" not in prompt
    assert "{{ENTITY}}" not in prompt
    assert "Tier" in prompt
    assert "global.tiers" in prompt


def test_generate_planning_prompt_missing_context_key_raises(
    standards_samples_dir: Path, jpa_mt_test_profile_root: Path
) -> None:
    standards_root = standards_samples_dir
    if not standards_root.exists():
        pytest.skip(f"standards sample directory not found: {standards_root}")

    config_path = jpa_mt_test_profile_root / "config.yml"
    templates_root = jpa_mt_test_profile_root / "templates"

    _write_config(config_path, standards_root)
    _write(templates_root / "planning" / "domain.md", "Hello {{ENTITY}}")

    profile = _TestableJpaMtProfile(config_path=config_path)

    context = {
        "ENTITY": "Tier",
        "SCOPE": "domain",
    }

    with pytest.raises(KeyError):
        profile.generate_planning_prompt(context)
