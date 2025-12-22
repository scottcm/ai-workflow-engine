import hashlib
from pathlib import Path

import pytest

from aiwf.application.approval_specs import ED_APPROVAL_SPECS, EdApprovalSpec
from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.workflow_state import ExecutionMode, WorkflowPhase, WorkflowState, WorkflowStatus
from aiwf.domain.persistence.session_store import SessionStore
from aiwf.domain.profiles import profile_factory


class _FakeProfile:
    def process_review_response(self, content: str) -> ProcessingResult:
        return ProcessingResult(status=WorkflowStatus.SUCCESS)


@pytest.fixture(autouse=True)
def _patch_profile_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    # Keep the test hermetic: REVIEWED step calls ProfileFactory.create(...).process_review_response(...)
    monkeypatch.setattr(profile_factory.ProfileFactory, "create", lambda *_args, **_kwargs: _FakeProfile())


def _persist_state(store: SessionStore, *, session_id: str, phase: WorkflowPhase, review_approved: bool) -> None:
    state = WorkflowState(
        session_id=session_id,
        profile="fake",
        scope="domain",
        entity="Widget",
        providers={},
        execution_mode=ExecutionMode.INTERACTIVE,
        phase=phase,
        status=WorkflowStatus.IN_PROGRESS,
        standards_hash="0" * 64,
        current_iteration=1,
        review_approved=review_approved,
        review_hash=None,
    )
    store.save(state)


def test_step_reviewed_blocks_until_review_approved(tmp_path: Path) -> None:
    store = SessionStore(sessions_root=tmp_path)
    orch = WorkflowOrchestrator(session_store=store, sessions_root=tmp_path)

    session_id = "s1"
    _persist_state(store, session_id=session_id, phase=WorkflowPhase.REVIEWED, review_approved=False)

    rr_rel = "iteration-1/review-response.md"
    p = tmp_path / session_id / rr_rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("PASS\n", encoding="utf-8")

    state1 = orch.step(session_id)
    assert state1.phase == WorkflowPhase.REVIEWED

    state1.review_approved = True
    store.save(state1)

    state2 = orch.step(session_id)
    assert state2.phase != WorkflowPhase.REVIEWED


def test_approve_reviewed_sets_review_hash_and_flag(tmp_path: Path) -> None:
    store = SessionStore(sessions_root=tmp_path)
    orch = WorkflowOrchestrator(session_store=store, sessions_root=tmp_path)

    session_id = "s2"
    _persist_state(store, session_id=session_id, phase=WorkflowPhase.REVIEWED, review_approved=False)

    rel = "iteration-1/review-response.md"
    content = "some review content\nwith lines\n"
    p = tmp_path / session_id / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content.encode("utf-8"))

    orch.approve(session_id)

    state = store.load(session_id)
    assert state.phase == WorkflowPhase.REVIEWED
    assert state.review_approved is True
    assert state.review_hash == hashlib.sha256(content.encode("utf-8")).hexdigest()


def test_approve_reviewed_missing_response_sets_error(tmp_path: Path) -> None:
    store = SessionStore(sessions_root=tmp_path)
    orch = WorkflowOrchestrator(session_store=store, sessions_root=tmp_path)

    session_id = "s3"
    _persist_state(store, session_id=session_id, phase=WorkflowPhase.REVIEWED, review_approved=False)

    orch.approve(session_id)

    state = store.load(session_id)
    assert state.status == WorkflowStatus.ERROR

    expected_rel = "iteration-1/review-response.md"
    expected_abs = str(tmp_path / session_id / expected_rel)
    assert state.last_error is not None
    assert expected_rel in state.last_error
    assert expected_abs in state.last_error


def test_ed_approval_spec_allows_exactly_one_field() -> None:
    with pytest.raises(ValueError):
        EdApprovalSpec()

    with pytest.raises(ValueError):
        EdApprovalSpec(plan_relpath="plan.md", code_dir_relpath_template="iteration-{N}/code")

    EdApprovalSpec(plan_relpath="plan.md")
    EdApprovalSpec(code_dir_relpath_template="iteration-{N}/code")

    # New third option for REVIEWED
    EdApprovalSpec(response_relpath_template="iteration-{N}/review-response.md")


def test_ed_approval_specs_includes_reviewed() -> None:
    spec = ED_APPROVAL_SPECS[WorkflowPhase.REVIEWED]
    assert spec.response_relpath_template == "iteration-{N}/review-response.md"
