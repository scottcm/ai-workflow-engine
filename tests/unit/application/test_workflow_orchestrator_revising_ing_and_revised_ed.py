from __future__ import annotations

from pathlib import Path

import pytest

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.workflow_state import Artifact, ExecutionMode, WorkflowPhase, WorkflowStatus
from aiwf.domain.persistence.session_store import SessionStore
from aiwf.domain.profiles.profile_factory import ProfileFactory


def _require_revised_phase() -> None:
    assert hasattr(WorkflowPhase, "REVISED"), "WorkflowPhase.REVISED must exist for this contract"


class _StubRevisionProcessProfile:
    def __init__(self, status: WorkflowStatus = WorkflowStatus.SUCCESS, error_message: str | None = None) -> None:
        self.process_called = 0
        self._status = status
        self._error_message = error_message

    def process_revision_response(self, content: str, session_dir: Path, iteration: int) -> ProcessingResult:
        self.process_called += 1
        return ProcessingResult(status=self._status, error_message=self._error_message)


class _StubReviewPromptProfile:
    def generate_review_prompt(self, context: dict) -> str:
        return "REVIEW PROMPT FROM REVISED"


def _arrange_at_revising_with_prompt(
    sessions_root: Path,
    utf8: str
) -> tuple[WorkflowOrchestrator, SessionStore, str, Path]:
    """Arrange state at REVISING with revision prompt already written (as if from REVIEWED)."""
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

    # Simulate prompt was already generated on entry to REVISING
    (it_dir / "revision-prompt.md").write_text("REVISION PROMPT", encoding=utf8)

    state = store.load(session_id)
    state.current_iteration = 2
    state.phase = WorkflowPhase.REVISING
    state.status = WorkflowStatus.IN_PROGRESS
    store.save(state)

    return orch, store, session_id, it_dir


def test_revising_is_noop_when_response_missing(
    sessions_root: Path,
    utf8: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REVISING phase is a no-op waiting for response (prompt was generated on entry)."""
    orch, store, session_id, it_dir = _arrange_at_revising_with_prompt(sessions_root, utf8)

    # Guard: profile must not be called in REVISING phase (only checks for response)
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
    """When response exists, REVISING processes it, writes artifacts, and transitions to REVISED."""
    _require_revised_phase()
    orch, store, session_id, it_dir = _arrange_at_revising_with_prompt(sessions_root, utf8)

    # Prompt already exists from arrangement
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
    """REVISED advances to REVIEWING when code artifacts exist and are hashed (approved).

    On entry to REVIEWING, the review prompt is also generated.
    """
    _require_revised_phase()
    store = SessionStore(sessions_root=sessions_root)
    orch = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    session_id = orch.initialize_run(
        profile="jpa-mt",
        scope="domain",
        entity="Client",
        providers={"primary": "gemini"},
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

    # Put state into REVISED with artifacts that have sha256 set (simulating post-approval)
    state = store.load(session_id)
    state.current_iteration = 2
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

    # Stub the profile for review prompt generation (called on entry to REVIEWING)
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: _StubReviewPromptProfile()))

    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.REVIEWING
    assert after.status == WorkflowStatus.IN_PROGRESS

    # Review prompt was generated on entry
    review_prompt = it_dir / "review-prompt.md"
    assert review_prompt.is_file()
    assert review_prompt.read_text(encoding=utf8) == "REVIEW PROMPT FROM REVISED"


def test_revised_blocks_when_artifacts_not_hashed(
    sessions_root: Path,
    utf8: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REVISED blocks (no-op) when artifacts exist but are not yet hashed (not approved)."""
    _require_revised_phase()
    store = SessionStore(sessions_root=sessions_root)
    orch = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    session_id = orch.initialize_run(
        profile="jpa-mt",
        scope="domain",
        entity="Client",
        providers={"primary": "gemini"},
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

    # Put state into REVISED with artifacts that have sha256=None (not approved)
    state = store.load(session_id)
    state.current_iteration = 2
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

    # No profile call should happen since we don't advance
    monkeypatch.setattr(
        ProfileFactory,
        "create",
        classmethod(lambda cls, *a, **k: (_ for _ in ()).throw(AssertionError("ProfileFactory.create called"))),
    )

    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.REVISED  # Still blocked


def test_revising_error_is_recoverable_stays_in_phase(
    sessions_root: Path,
    utf8: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When process_revision_response returns ERROR, stay in REVISING with last_error set."""
    orch, store, session_id, it_dir = _arrange_at_revising_with_prompt(sessions_root, utf8)

    (it_dir / "revision-response.md").write_text("<<<FILE: x.py>>>\n    pass\n", encoding=utf8)

    error_msg = "No code blocks found in revision response."
    proc = _StubRevisionProcessProfile(status=WorkflowStatus.ERROR, error_message=error_msg)
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: proc))

    orch.step(session_id)

    after = store.load(session_id)
    # Should NOT transition to terminal ERROR phase
    assert after.phase == WorkflowPhase.REVISING
    assert after.status == WorkflowStatus.IN_PROGRESS
    assert after.last_error == error_msg
    assert proc.process_called == 1


def test_revising_success_clears_last_error(
    sessions_root: Path,
    utf8: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When process_revision_response succeeds after previous error, clear last_error."""
    orch, store, session_id, it_dir = _arrange_at_revising_with_prompt(sessions_root, utf8)

    # Set up previous error
    state = store.load(session_id)
    state.last_error = "Previous error"
    store.save(state)

    (it_dir / "revision-response.md").write_text("<<<FILE: x.py>>>\n    pass\n", encoding=utf8)

    proc = _StubRevisionProcessProfile()
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: proc))

    # Patch extractor
    import profiles.jpa_mt.bundle_extractor as be
    monkeypatch.setattr(be, "extract_files", lambda raw: {"x.py": "pass\n"})

    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.REVISED
    assert after.last_error is None
