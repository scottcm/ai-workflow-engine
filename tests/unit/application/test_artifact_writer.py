import hashlib
from datetime import datetime
from pathlib import Path

import pytest

from aiwf.application.artifact_writer import write_artifacts
from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.workflow_state import Artifact, ExecutionMode, WorkflowPhase, WorkflowState, WorkflowStatus
from aiwf.domain.models.write_plan import WriteOp, WritePlan


def _mk_state(*, session_id: str) -> WorkflowState:
    return WorkflowState(
        session_id=session_id,
        profile="jpa_mt",
        scope="domain",
        entity="Tier",
        phase=WorkflowPhase.GENERATED,
        status=WorkflowStatus.IN_PROGRESS,
        execution_mode=ExecutionMode.INTERACTIVE,
        providers={"planner": "manual", "generator": "manual", "reviewer": "manual", "reviser": "manual"},
        standards_hash="sha256:deadbeef",
    )


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def test_write_artifacts_writes_files_in_order_and_creates_artifacts(tmp_path: Path) -> None:
    session_dir = tmp_path / "sess"
    session_dir.mkdir(parents=True, exist_ok=True)

    state = _mk_state(session_id="sess")
    state.current_iteration = 3
    state.phase = WorkflowPhase.GENERATED

    plan = WritePlan(
        writes=[
            WriteOp(path="iteration-3/code/A.java", content="class A {}\n"),
            WriteOp(path="iteration-3/code/B.java", content="class B {}\n"),
        ]
    )
    result = ProcessingResult(status=WorkflowStatus.SUCCESS, write_plan=plan)

    ret = write_artifacts(session_dir=session_dir, state=state, result=result)
    assert ret is None

    p1 = session_dir / "iteration-3/code/A.java"
    p2 = session_dir / "iteration-3/code/B.java"
    assert p1.exists()
    assert p2.exists()
    assert p1.read_text(encoding="utf-8") == "class A {}\n"
    assert p2.read_text(encoding="utf-8") == "class B {}\n"

    assert len(state.artifacts) == 2

    a1, a2 = state.artifacts
    assert isinstance(a1, Artifact)
    assert isinstance(a2, Artifact)

    # Order follows WritePlan.writes order
    assert a1.path == "iteration-3/code/A.java"
    assert a2.path == "iteration-3/code/B.java"

    assert a1.iteration == 3
    assert a2.iteration == 3
    assert a1.phase == WorkflowPhase.GENERATED
    assert a2.phase == WorkflowPhase.GENERATED

    assert a1.sha256 is None
    assert a2.sha256 is None

    assert isinstance(a1.created_at, datetime)
    assert isinstance(a2.created_at, datetime)


def test_write_artifacts_noop_when_write_plan_is_none(tmp_path: Path) -> None:
    session_dir = tmp_path / "sess"
    session_dir.mkdir(parents=True, exist_ok=True)

    state = _mk_state(session_id="sess")
    result = ProcessingResult(status=WorkflowStatus.SUCCESS, write_plan=None)

    ret = write_artifacts(session_dir=session_dir, state=state, result=result)
    assert ret is None

    assert state.artifacts == []
    assert list(session_dir.rglob("*")) == []


def test_write_artifacts_propagates_write_failure_and_records_no_partial_artifacts(tmp_path: Path) -> None:
    session_dir = tmp_path / "sess"
    session_dir.mkdir(parents=True, exist_ok=True)

    # Create a file where a directory is required to force a deterministic failure.
    conflict = session_dir / "iteration-1"
    conflict.write_text("not a directory", encoding="utf-8")

    state = _mk_state(session_id="sess")
    state.current_iteration = 1
    state.phase = WorkflowPhase.GENERATED

    plan = WritePlan(writes=[WriteOp(path="iteration-1/code/A.java", content="class A {}\n")])
    result = ProcessingResult(status=WorkflowStatus.SUCCESS, write_plan=plan)

    with pytest.raises(Exception):
        write_artifacts(session_dir=session_dir, state=state, result=result)

    # No artifacts recorded on failure
    assert state.artifacts == []

    # File should not exist (write should have failed before creating it)
    assert not (session_dir / "iteration-1/code/A.java").exists()


def test_write_artifacts_propagates_io_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session_dir = tmp_path / "sess"
    session_dir.mkdir(parents=True, exist_ok=True)

    state = _mk_state(session_id="sess")
    state.current_iteration = 1
    state.phase = WorkflowPhase.GENERATED

    plan = WritePlan(writes=[WriteOp(path="iteration-1/code/A.java", content="class A {}\n")])
    result = ProcessingResult(status=WorkflowStatus.SUCCESS, write_plan=plan)

    def _boom(*args, **kwargs):
        raise OSError("I/O error")

    monkeypatch.setattr(Path, "write_text", _boom)

    with pytest.raises(OSError, match="I/O error"):
        write_artifacts(session_dir=session_dir, state=state, result=result)

    assert state.artifacts == []
