import hashlib
from pathlib import Path

import pytest

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.models.workflow_state import ExecutionMode
from aiwf.domain.persistence.session_store import SessionStore
from aiwf.domain.profiles import profile_factory as profile_factory_module


class _FakeProvider:
    def __init__(self, bundle_text: str):
        self.bundle_text = bundle_text
        self.calls: int = 0

    def create_bundle(self, context) -> str:
        self.calls += 1
        return self.bundle_text


class _StubProfile:
    def __init__(self, provider: _FakeProvider):
        self._provider = provider
        self.calls: int = 0

    def get_standards_provider(self):
        self.calls += 1
        return self._provider


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def test_orchestrator_materializes_standards_on_initialize(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir(parents=True, exist_ok=True)

    session_store = SessionStore(sessions_root=sessions_root)
    orchestrator = WorkflowOrchestrator(session_store=session_store, sessions_root=sessions_root)

    provider = _FakeProvider(bundle_text="standards\n")
    profile = _StubProfile(provider=provider)

    # Capture the state object saved during initialization without asserting persistence behavior.
    saved: dict[str, object] = {}
    orig_save = session_store.save

    def _save_capture(state):
        saved["state"] = state
        return orig_save(state)

    monkeypatch.setattr(session_store, "save", _save_capture)

    monkeypatch.setattr(profile_factory_module.ProfileFactory, "create", staticmethod(lambda profile_name: profile))

    session_id = orchestrator.initialize_run(
        profile="jpa_mt",
        scope="domain",
        entity="Tier",
        providers={"planner": "manual", "generator": "manual", "reviewer": "manual", "reviser": "manual"},
        execution_mode=ExecutionMode.INTERACTIVE,
    )

    assert session_id

    # Standards provider call path enforced
    assert profile.calls == 1
    assert provider.calls == 1

    # Engine must write standards-bundle.md into the session directory
    bundle_path = sessions_root / session_id / "standards-bundle.md"
    assert bundle_path.exists()
    assert bundle_path.read_text(encoding="utf-8") == "standards\n"

    # Engine must compute hash of exact bytes written and store raw digest into state
    assert "state" in saved
    assert saved["state"].standards_hash == _sha256_hex("standards\n")
