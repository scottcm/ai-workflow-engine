from __future__ import annotations

from pathlib import Path
import pytest
import yaml

from profiles.jpa_mt.jpa_mt_profile import JpaMtProfile
from aiwf.domain.models.processing_result import ProcessingResult


class _TestableJpaMtProfile(JpaMtProfile):
    """Concrete test-only subclass to satisfy WorkflowProfile abstract methods.

    These tests exercise prompt generation only. Response-processing contracts are
    satisfied with stubs that should never be invoked here.
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
    # IMPORTANT: standards.root must be an absolute path for PathValidator.
    config = {
        "standards": {"root": str(standards_root.resolve())},
        "artifacts": {},
        "scopes": {"domain": {"layers": []}},
        "layer_standards": {},
    }
    _write(config_path, yaml.safe_dump(config))


def test_generate_planning_prompt_happy_path(repo_root: Path) -> None:
    # Use real standards fixtures; do not create fake standards directories.
    standards_root = repo_root / "docs" / "samples" / "standards"
    assert standards_root.exists(), "Expected docs/samples/standards to exist"

    # Isolated, repo-local scratch area (not tmp_path) to avoid touching real profile config/templates.
    work_root = repo_root / ".pytest_tmp" / "jpa_mt_prompt_generation"
    config_path = work_root / "config.yml"
    templates_root = work_root / "templates"

    _write_config(config_path, standards_root)

    # JpaMtProfile expects templates/{phase_dir}/{scope}.md
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
        # JpaMtProfile.generate_* uses the lower-case key for scope selection.
        "scope": "domain",
    }

    prompt = profile.generate_planning_prompt(context)

    assert isinstance(prompt, str)
    assert "{{include:" not in prompt
    assert "{{ENTITY}}" not in prompt
    assert "Tier" in prompt
    assert "global.tiers" in prompt


def test_generate_planning_prompt_missing_context_key_raises(repo_root: Path) -> None:
    standards_root = repo_root / "docs" / "samples" / "standards"
    assert standards_root.exists(), "Expected docs/samples/standards to exist"

    work_root = repo_root / ".pytest_tmp" / "jpa_mt_prompt_generation_missing_key"
    config_path = work_root / "config.yml"
    templates_root = work_root / "templates"

    _write_config(config_path, standards_root)
    _write(templates_root / "planning" / "domain.md", "Hello {{ENTITY}}")

    profile = _TestableJpaMtProfile(config_path=config_path)

    context = {
        "ENTITY": "Tier",
        "SCOPE": "domain",
    }

    with pytest.raises(KeyError):
        profile.generate_planning_prompt(context)
