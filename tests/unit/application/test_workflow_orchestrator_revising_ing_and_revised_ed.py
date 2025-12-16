from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.constants import PROMPTS_DIR, RESPONSES_DIR
from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.workflow_state import ExecutionMode, WorkflowPhase, WorkflowStatus
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
    sessions_root: Path, utf8: str
) -> tuple[WorkflowOrchestrator, SessionStore, str, Path]:
    store = SessionStore(sessions_root=sessions_root)
    orch = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    session_id = orch.initialize_run(
        profile="jpa_mt",
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

    state = store.load(session_id)
    state.current_iteration = 2
    state.phase = WorkflowPhase.REVISING
    state.status = WorkflowStatus.IN_PROGRESS
    store.save(state)

    return orch, store, session_id, it_dir


def test_revising_writes_revision_prompt_if_missing_and_stays_revising(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    orch, store, session_id, it_dir = _arrange_at_revising(sessions_root, utf8)

    stub = _StubRevisionPromptProfile()
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: stub))

    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.REVISING

    prompt_file = it_dir / PROMPTS_DIR / "revision-prompt.md"
    assert prompt_file.is_file()
    assert prompt_file.read_text(encoding=utf8) == "REVISION PROMPT"
    assert stub.generate_called == 1


def test_revising_is_noop_when_prompt_exists_and_response_missing(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    orch, store, session_id, it_dir = _arrange_at_revising(sessions_root, utf8)

    (it_dir / PROMPTS_DIR).mkdir(parents=True, exist_ok=True)
    (it_dir / PROMPTS_DIR / "revision-prompt.md").write_text("PROMPT", encoding=utf8)
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


def test_revising_transitions_to_revised_when_response_exists_without_processing(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _require_revised_phase()
    orch, store, session_id, it_dir = _arrange_at_revising(sessions_root, utf8)

    (it_dir / PROMPTS_DIR).mkdir(parents=True, exist_ok=True)
    (it_dir / PROMPTS_DIR / "revision-prompt.md").write_text("PROMPT", encoding=utf8)
    (it_dir / RESPONSES_DIR).mkdir(parents=True, exist_ok=True)
    (it_dir / RESPONSES_DIR / "revision-response.md").write_text("<<<FILE: x.py>>>\n    pass\n", encoding=utf8)

    # Guard: no processing in REVISING when response exists; must only phase-transition to REVISED.
    monkeypatch.setattr(
        ProfileFactory,
        "create",
        classmethod(lambda cls, *a, **k: (_ for _ in ()).throw(AssertionError("ProfileFactory.create called"))),
    )

    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.REVISED
    assert after.status == WorkflowStatus.IN_PROGRESS


def test_revised_processes_revision_response_extracts_and_enters_reviewing(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _require_revised_phase()
    orch, store, session_id, it_dir = _arrange_at_revising(sessions_root, utf8)

    # Put state into REVISED with a response present
    (it_dir / RESPONSES_DIR).mkdir(parents=True, exist_ok=True)
    (it_dir / RESPONSES_DIR / "revision-response.md").write_text("<<<FILE: x.py>>>\n    pass\n", encoding=utf8)

    state = store.load(session_id)
    state.phase = WorkflowPhase.REVISED
    store.save(state)

    proc = _StubRevisionProcessProfile()
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: proc))

    # Patch extractor to avoid relying on implementation details
    import profiles.jpa_mt.bundle_extractor as be
    monkeypatch.setattr(be, "extract_files", lambda raw: {"x.py": "pass\n"})

    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.REVIEWING
    assert after.status == WorkflowStatus.IN_PROGRESS

    code_file = it_dir / "code" / "x.py"
    assert code_file.is_file()
    assert code_file.read_text(encoding=utf8) == "pass\n"
    assert proc.process_called == 1
