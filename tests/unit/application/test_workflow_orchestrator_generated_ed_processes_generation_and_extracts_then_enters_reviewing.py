from pathlib import Path
from typing import Any

import pytest

from aiwf.domain.models.write_plan import WriteOp, WritePlan

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.workflow_state import Artifact, ExecutionMode, WorkflowPhase, WorkflowStatus
from aiwf.domain.persistence.session_store import SessionStore
from aiwf.domain.profiles.profile_factory import ProfileFactory


class _StubPlanningProfile:
    def process_planning_response(self, content: str) -> ProcessingResult:
        return ProcessingResult(status=WorkflowStatus.SUCCESS)

    def generate_generation_prompt(self, context: dict) -> str:
        """Called on entry to GENERATING."""
        return "GENERATION PROMPT"


class _StubGenerationProfile:
    def __init__(self) -> None:
        self.process_called = 0

    def process_generation_response(self, content: str, session_dir: Path, iteration: int) -> ProcessingResult:
        self.process_called += 1
        return ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(writes=[
                WriteOp(path="code/x.py", content="pass\n")
            ])
        )


class _StubReviewPromptProfile:
    def generate_review_prompt(self, context: dict) -> str:
        """Called on entry to REVIEWING."""
        return "REVIEW PROMPT"


def _arrange_at_generated(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
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
    orch.step(session_id)  # -> PLANNING

    session_dir = sessions_root / session_id
    it_dir = session_dir / "iteration-1"
    it_dir.mkdir(parents=True, exist_ok=True)
    
    # Planning artifacts in iteration-1
    (it_dir / "planning-prompt.md").write_text("PROMPT", encoding=utf8)
    (it_dir / "planning-response.md").write_text("# PLAN\n", encoding=utf8)
    
    # Create plan.md at session root for ED approval
    (session_dir / "plan.md").write_text("# PLAN\n", encoding=utf8)

    # PLANNING -> PLANNED (no profile call needed)
    monkeypatch.setattr(
        ProfileFactory,
        "create",
        classmethod(lambda cls, *a, **k: (_ for _ in ()).throw(AssertionError("ProfileFactory.create called"))),
    )
    orch.step(session_id)
    assert store.load(session_id).phase == WorkflowPhase.PLANNED

    # Approve PLANNED (required before step advances)
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: _StubPlanningProfile()))
    orch.approve(session_id)

    # PLANNED -> GENERATING
    orch.step(session_id)
    assert store.load(session_id).phase == WorkflowPhase.GENERATING

    # Create generation response
    (it_dir / "generation-prompt.md").write_text("PROMPT", encoding=utf8)
    (it_dir / "generation-response.md").write_text("<<<FILE: x.py>>>\n    pass\n", encoding=utf8)

    # GENERATING -> GENERATED (processes response, writes artifacts in current impl)
    gen_stub = _StubGenerationProfile()
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: gen_stub))
    orch.step(session_id)
    
    assert store.load(session_id).phase == WorkflowPhase.GENERATED
    return orch, store, session_id, it_dir


def test_generated_gates_on_artifact_hashes_and_enters_reviewing(
    sessions_root: Path, utf8: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GENERATED is an ED phase that gates on artifact hashes (approval required).
    
    After approval sets sha256 on artifacts, step() advances to REVIEWING.
    """
    orch, store, session_id, it_dir = _arrange_at_generated(sessions_root, utf8, monkeypatch)

    # At GENERATED, artifacts exist but are unhashed
    state = store.load(session_id)
    assert state.phase == WorkflowPhase.GENERATED
    assert len(state.artifacts) > 0
    assert all(a.sha256 is None for a in state.artifacts)

    # Step should be blocked (no-op) because artifacts not approved
    monkeypatch.setattr(
        ProfileFactory,
        "create",
        classmethod(lambda cls, *a, **k: (_ for _ in ()).throw(AssertionError("ProfileFactory.create called"))),
    )
    orch.step(session_id)
    assert store.load(session_id).phase == WorkflowPhase.GENERATED  # Still blocked

    # Approve GENERATED (hashes artifacts)
    orch.approve(session_id)

    state = store.load(session_id)
    assert all(a.sha256 is not None for a in state.artifacts)

    # Now step advances to REVIEWING (generates review prompt)
    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, *a, **k: _StubReviewPromptProfile()))
    orch.step(session_id)

    after = store.load(session_id)
    assert after.phase == WorkflowPhase.REVIEWING

    code_file = it_dir / "code" / "x.py"
    assert code_file.is_file()