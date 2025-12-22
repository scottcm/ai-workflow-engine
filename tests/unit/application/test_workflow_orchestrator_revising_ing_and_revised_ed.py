from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.workflow_state import Artifact, ExecutionMode, WorkflowPhase, WorkflowStatus
from aiwf.domain.persistence.session_store import SessionStore
from aiwf.domain.profiles.profile_factory import ProfileFactory


def _require_revised_phase() -> None:
    assert hasattr(WorkflowPhase, "REVISED"), "WorkflowPhase.REVISED must exist for this contract"


class _StubRevisionPromptProfile:
    def __init__(self) -> None:
        self.generate_called = 0

    def generate_revision_prompt(self, context: dict[str, Any]) -> str:
        self.generate_called += 1
        return "REVISION PROMPT"


class _StubRevisionProcessProfile:
    def __init__(self) -> None:
        self.process_called = 0

    def process_revision_response(self, content: str, session_dir: Path, iteration: int) -> ProcessingResult:
        self.process_called += 1
        return ProcessingResult(status=WorkflowStatus.SUCCESS)


def _arrange_at_revising(
    sessions_root: Path,
    utf8: str
) -> tuple[WorkflowOrchestrator, SessionStore, str, Path]:
    store = SessionStore(sessions_root=sessions_root)
    orch = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    session_id = orch.initialize_run(
        profile="jpa-mt",
        scope="domain",
        entity="Client",
        providers={"planner": "manual", "generator": "manual", "reviewer": "manual", "reviser": "manual"},
        execution_mode=ExecutionMode.INTERACTIVE,
        bounded_context="client",
        table="app.clients",
        dev="test",
        task_id="LMS-000",
        metadata={"test": True},
    )

    session_dir = sessions_root / session_id
    it_dir = session_dir / "iteration-2"
    it_dir.mkdir(parents=True, exist_ok=True)

    state = store.load(session_id)
    state.current_iteration = 2
    state.phase = WorkflowPhase.REVISING
    state.status = WorkflowStatus.IN_PROGRESS
    store.save(state)

    return orch, store, session_id, it_dir


def test_revising_writes_revision_prompt_if_missing_and_stays_revising(
    sessions_root: Path,
    utf8: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orch, store, session_id, it_dir = _arrange_at_revising(sessions_root, utf8)

    stub = _StubRevisionPromptProfile()
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: stub))

    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.REVISING

    prompt_file = it_dir / "revision-prompt.md"
    assert prompt_file.is_file()
    assert prompt_file.read_text(encoding=utf8) == "REVISION PROMPT"
    assert stub.generate_called == 1


def test_revising_is_noop_when_prompt_exists_and_response_missing(
    sessions_root: Path,
    utf8: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orch, store, session_id, it_dir = _arrange_at_revising(sessions_root, utf8)

    (it_dir / "revision-prompt.md").write_text("PROMPT", encoding=utf8)
    # Intentionally no revision-response.md

    monkeypatch.setattr(
        ProfileFactory,
        "create",
        classmethod(lambda cls, *a, **k: (_ for _ in ()).throw(AssertionError("ProfileFactory.create called"))),
    )

    before = store.load(session_id)
    before_updated_at = before.updated_at
    before_hist_len = len(before.phase_history)

    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.REVISING
    assert after.updated_at == before_updated_at
    assert len(after.phase_history) == before_hist_len


def test_revising_processes_response_and_transitions_to_revised(
    sessions_root: Path,
    utf8: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When response exists, REVISING processes it, writes artifacts, and transitions to REVISED.
    
    Note: Current implementation processes response in REVISING (ING phase), not REVISED (ED phase).
    This differs from ADR-0001's intended ING/ED split but matches actual implementation.
    """
    _require_revised_phase()
    orch, store, session_id, it_dir = _arrange_at_revising(sessions_root, utf8)

    (it_dir / "revision-prompt.md").write_text("PROMPT", encoding=utf8)
    (it_dir / "revision-response.md").write_text("<<<FILE: x.py>>>\n    pass\n", encoding=utf8)

    proc = _StubRevisionProcessProfile()
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: proc))

    # Patch extractor
    import profiles.jpa_mt.bundle_extractor as be
    monkeypatch.setattr(be, "extract_files", lambda raw: {"x.py": "pass\n"})

    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.REVISED
    assert after.status == WorkflowStatus.IN_PROGRESS
    assert proc.process_called == 1

    # Code extracted
    code_file = it_dir / "code" / "x.py"
    assert code_file.is_file()
    assert code_file.read_text(encoding=utf8) == "pass\n"


def test_revised_gates_on_artifact_hashes_and_advances_to_reviewing(
    sessions_root: Path,
    utf8: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REVISED only advances to REVIEWING when code artifacts exist and are hashed (approved).
    
    REVISED is an ED phase that gates on approval, not processes responses.
    """
    _require_revised_phase()
    orch, store, session_id, it_dir = _arrange_at_revising(sessions_root, utf8)

    # Put state into REVISED with artifacts that have sha256 set (simulating post-approval)
    state = store.load(session_id)
    state.phase = WorkflowPhase.REVISED
    state.artifacts = [
        Artifact(
            path="iteration-2/code/x.py",
            phase=WorkflowPhase.REVISED,
            iteration=2,
            sha256="abc123"  # Hashed = approved
        )
    ]
    store.save(state)

    # Create the actual file
    code_dir = it_dir / "code"
    code_dir.mkdir(parents=True, exist_ok=True)
    (code_dir / "x.py").write_text("pass\n", encoding=utf8)

    # No profile call should happen - REVISED only gates
    monkeypatch.setattr(
        ProfileFactory,
        "create",
        classmethod(lambda cls, *a, **k: (_ for _ in ()).throw(AssertionError("ProfileFactory.create called"))),
    )

    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.REVIEWING
    assert after.status == WorkflowStatus.IN_PROGRESS


def test_revised_blocks_when_artifacts_not_hashed(
    sessions_root: Path,
    utf8: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REVISED blocks (no-op) when artifacts exist but are not yet hashed (not approved)."""
    _require_revised_phase()
    orch, store, session_id, it_dir = _arrange_at_revising(sessions_root, utf8)

    # Put state into REVISED with artifacts that have sha256=None (not approved)
    state = store.load(session_id)
    state.phase = WorkflowPhase.REVISED
    state.artifacts = [
        Artifact(
            path="iteration-2/code/x.py",
            phase=WorkflowPhase.REVISED,
            iteration=2,
            sha256=None  # Not hashed = not approved
        )
    ]
    store.save(state)

    # No profile call should happen
    monkeypatch.setattr(
        ProfileFactory,
        "create",
        classmethod(lambda cls, *a, **k: (_ for _ in ()).throw(AssertionError("ProfileFactory.create called"))),
    )

    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.REVISED  # Still blocked
