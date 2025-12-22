"""Conftest for profile tests.

Ensures profile registration happens before tests run.
"""
import pytest

# Import the profiles package to trigger registration
import profiles  # noqa: F401


@pytest.fixture
def standards_dir(tmp_path, monkeypatch):
    """Set STANDARDS_DIR env var for profile tests that need it."""
    standards_dir = tmp_path / "standards"
    standards_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("STANDARDS_DIR", str(standards_dir))
    return standards_dir
