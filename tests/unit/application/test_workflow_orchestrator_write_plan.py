from pathlib import Path

import pytest

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.workflow_state import ExecutionMode, WorkflowPhase, WorkflowState, WorkflowStatus
from aiwf.domain.models.write_plan import WriteOp, WritePlan
from aiwf.domain.persistence.session_store import SessionStore
from aiwf.domain.profiles import profile_factory as profile_factory_module


class _StubProfile:
    def __init__(self, *, result: ProcessingResult):
        self._result = result
        self.calls: int = 0

    def process_generation_response(self, content: str, session_dir: Path, iteration: int) -> ProcessingResult:
        self.calls += 1
        return self._result


def _mk_state(*, session_id: str) -> WorkflowState:
    """Create state at GENERATING phase (ING phase where response processing occurs)."""
    return WorkflowState(
        session_id=session_id,
        profile="jpa-mt",
        scope="domain",
        entity="Tier",
        phase=WorkflowPhase.GENERATING,  # Changed from GENERATED
        status=WorkflowStatus.IN_PROGRESS,
        execution_mode=ExecutionMode.INTERACTIVE,
        providers={"planner": "manual", "generator": "manual", "reviewer": "manual", "reviser": "manual"},
        standards_hash="a" * 64,
        current_iteration=1,
    )


def test_orchestrator_executes_write_plan_exactly_once_when_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir(parents=True, exist_ok=True)

    session_store = SessionStore(sessions_root=sessions_root)
    orchestrator = WorkflowOrchestrator(session_store=session_store, sessions_root=sessions_root)

    session_id = "s1"
    state = _mk_state(session_id=session_id)
    session_store.save(state)

    # Create the expected generation response file that _step_generating consumes
    iteration_dir = sessions_root / session_id / f"iteration-{state.current_iteration}"
    iteration_dir.mkdir(parents=True, exist_ok=True)
    (iteration_dir / "generation-response.md").write_text("ignored", encoding="utf-8")

    plan = WritePlan(writes=[WriteOp(path="A.java", content="class A {}\n")])
    stub = _StubProfile(result=ProcessingResult(status=WorkflowStatus.SUCCESS, write_plan=plan))

    monkeypatch.setattr(profile_factory_module.ProfileFactory, "create", staticmethod(lambda profile: stub))

    new_state = orchestrator.step(session_id)

    # Profile processing called exactly once
    assert stub.calls == 1

    # File written under session dir (write_artifacts prefixes with iteration-N/)
    written = sessions_root / session_id / "iteration-1" / "code" / "A.java"
    assert written.exists()
    assert written.read_text(encoding="utf-8") == "class A {}\n"

    # Artifact appended with sha256=None (hashing deferred to ED approval)
    assert len(new_state.artifacts) == 1
    assert new_state.artifacts[0].path == "iteration-1/code/A.java"
    assert new_state.artifacts[0].iteration == 1
    assert new_state.artifacts[0].phase == WorkflowPhase.GENERATING  # Phase when written
    assert new_state.artifacts[0].sha256 is None  # Not hashed until approve()

    # Phase advanced to GENERATED
    assert new_state.phase == WorkflowPhase.GENERATED


def test_orchestrator_does_not_write_files_when_write_plan_is_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir(parents=True, exist_ok=True)

    session_store = SessionStore(sessions_root=sessions_root)
    orchestrator = WorkflowOrchestrator(session_store=session_store, sessions_root=sessions_root)

    session_id = "s2"
    state = _mk_state(session_id=session_id)
    session_store.save(state)

    iteration_dir = sessions_root / session_id / f"iteration-{state.current_iteration}"
    iteration_dir.mkdir(parents=True, exist_ok=True)
    (iteration_dir / "generation-response.md").write_text("ignored", encoding="utf-8")

    stub = _StubProfile(result=ProcessingResult(status=WorkflowStatus.SUCCESS, write_plan=None))
    monkeypatch.setattr(profile_factory_module.ProfileFactory, "create", staticmethod(lambda profile: stub))

    new_state = orchestrator.step(session_id)

    assert stub.calls == 1
    assert new_state.artifacts == []
    assert not (sessions_root / session_id / "iteration-1" / "code").exists()

    # Phase still advances to GENERATED even without artifacts
    assert new_state.phase == WorkflowPhase.GENERATED
