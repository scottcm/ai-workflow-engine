from pathlib import Path
import pytest

from aiwf.domain.profiles.profile_factory import ProfileFactory
from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.workflow_state import WorkflowStatus


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
