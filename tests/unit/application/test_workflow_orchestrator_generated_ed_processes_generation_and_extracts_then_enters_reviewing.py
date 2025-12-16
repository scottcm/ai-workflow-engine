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


class _StubPlanningProfile:
    def process_planning_response(self, content: str) -> ProcessingResult:
        return ProcessingResult(status=WorkflowStatus.SUCCESS)


class _StubGenerationProfile:
    def __init__(self) -> None:
        self.process_called = 0

    def process_generation_response(self, content: str, session_dir: Path, iteration: int) -> ProcessingResult:
        self.process_called += 1
        return ProcessingResult(status=WorkflowStatus.SUCCESS)


def _arrange_at_generated(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
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
    orch.step(session_id)  # -> PLANNING

    session_dir = sessions_root / session_id
    (session_dir / PROMPTS_DIR).mkdir(parents=True, exist_ok=True)
    (session_dir / PROMPTS_DIR / "planning-prompt.md").write_text("PROMPT", encoding=utf8)
    (session_dir / RESPONSES_DIR).mkdir(parents=True, exist_ok=True)
    (session_dir / RESPONSES_DIR / "planning-response.md").write_text("# PLAN\n", encoding=utf8)

    monkeypatch.setattr(
        ProfileFactory,
        "create",
        classmethod(lambda cls, *a, **k: (_ for _ in ()).throw(AssertionError("ProfileFactory.create called"))),
    )
    orch.step(session_id)  # PLANNING -> PLANNED

    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: _StubPlanningProfile()))
    orch.step(session_id)  # PLANNED -> GENERATING

    it_dir = session_dir / "iteration-1"
    (it_dir / PROMPTS_DIR).mkdir(parents=True, exist_ok=True)
    (it_dir / PROMPTS_DIR / "generation-prompt.md").write_text("PROMPT", encoding=utf8)
    (it_dir / RESPONSES_DIR).mkdir(parents=True, exist_ok=True)
    (it_dir / RESPONSES_DIR / "generation-response.md").write_text("<<<FILE: x.py>>>\n    pass\n", encoding=utf8)

    monkeypatch.setattr(
        ProfileFactory,
        "create",
        classmethod(lambda cls, *a, **k: (_ for _ in ()).throw(AssertionError("ProfileFactory.create called"))),
    )
    orch.step(session_id)  # GENERATING -> GENERATED

    assert store.load(session_id).phase == WorkflowPhase.GENERATED
    return orch, store, session_id, it_dir


def test_generated_processes_generation_response_extracts_and_enters_reviewing(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    orch, store, session_id, it_dir = _arrange_at_generated(sessions_root, utf8, monkeypatch)

    gen_profile = _StubGenerationProfile()
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: gen_profile))

    # Patch extractor to avoid relying on implementation details
    import profiles.jpa_mt.bundle_extractor as be
    monkeypatch.setattr(be, "extract_files", lambda raw: {"x.py": "pass\n"})

    orch.step(session_id)  # GENERATED -> REVIEWING (process + extract)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.REVIEWING

    code_file = it_dir / "code" / "x.py"
    assert code_file.is_file()
    assert code_file.read_text(encoding=utf8) == "pass\n"
    assert gen_profile.process_called == 1
