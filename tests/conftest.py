from pathlib import Path
from typing import Any
import pytest

from aiwf.domain.profiles.profile_factory import ProfileFactory
from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.workflow_state import WorkflowStatus
from aiwf.domain.providers.ai_provider import AIProvider
from aiwf.domain.providers.provider_factory import ProviderFactory


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Resolve the repository root directory.

    Assumes tests live under <repo>/tests/.
    """
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def standards_samples_dir(repo_root: Path) -> Path:
    """Return the repo-relative standards samples directory.

    Fails fast if missing so tests do not silently rely on machine state.
    """
    samples_dir = repo_root / "docs" / "samples"
    if not samples_dir.is_dir():
        pytest.fail(f"Expected standards samples dir at: {samples_dir}")
    return samples_dir


@pytest.fixture
def sessions_root(tmp_path: Path) -> Path:
    """Isolated sessions root for tests.

    Tests should not write into the real repo's .aiwf/sessions directory.
    """
    return tmp_path


@pytest.fixture
def temp_standards_root(tmp_path: Path) -> Path:
    """Hermetic standards root for tests that must not depend on repo samples."""
    d = tmp_path / "standards"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def utf8() -> str:
    """Canonical encoding used throughout tests."""
    return "utf-8"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent unit tests from accidentally using developer machine env vars.

    If a test needs an env var, it should set it explicitly via monkeypatch.
    """
    monkeypatch.delenv("STANDARDS_DIR", raising=False)
    monkeypatch.delenv("AIWF_SESSIONS_ROOT", raising=False)


class FakeProvider(AIProvider):
    """Fake provider for testing - validates successfully and returns None."""

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        return {
            "name": "fake",
            "description": "Fake provider for testing",
            "requires_config": False,
            "config_keys": [],
            "default_connection_timeout": None,
            "default_response_timeout": None,
        }

    def validate(self) -> None:
        pass  # Always valid

    def generate(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
    ) -> str | None:
        return None  # Like manual provider


@pytest.fixture(autouse=True)
def _register_test_providers():
    """Register fake providers used in tests with proper cleanup.

    Tests often use provider keys like 'gemini', 'planner', 'reviewer' without
    actually needing real provider implementations. This fixture registers
    fake providers so validation passes, and restores the registry afterward
    to prevent test pollution.
    """
    # Snapshot registry state before test
    original_registry = dict(ProviderFactory._registry)

    # Register common test provider keys
    for key in ["gemini", "planner", "reviewer", "generator"]:
        if key not in ProviderFactory._registry:
            ProviderFactory.register(key, FakeProvider)

    yield

    # Restore original registry state after test
    ProviderFactory._registry.clear()
    ProviderFactory._registry.update(original_registry)


def make_fake_approve(return_value=None, side_effect=None):
    """Factory for creating mock orchestrator.approve() methods.

    This centralizes the signature so tests don't duplicate the full signature
    when mocking WorkflowOrchestrator.approve().

    Args:
        return_value: Value to return from the mock (a WorkflowState or mock).
        side_effect: Exception to raise, or callable to invoke.

    Returns:
        A mock function with the correct signature for orchestrator.approve().

    Example:
        def test_approve_success(monkeypatch):
            fake_state = _build_state(...)
            monkeypatch.setattr(
                WorkflowOrchestrator, "approve",
                make_fake_approve(return_value=fake_state),
            )
    """
    def fake_approve(
        self,
        session_id: str,
        hash_prompts: bool = False,
        fs_ability: str | None = None,
    ):
        if side_effect is not None:
            if callable(side_effect) and not isinstance(side_effect, type):
                return side_effect(session_id, hash_prompts, fs_ability)
            raise side_effect
        return return_value

    return fake_approve
