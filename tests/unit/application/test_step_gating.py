from pathlib import Path
import pytest

from aiwf.application.approval_specs import ED_APPROVAL_SPECS, ING_APPROVAL_SPECS
from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.workflow_state import (
    Artifact,
    ExecutionMode,
    PhaseTransition,
    WorkflowPhase,
    WorkflowState,
    WorkflowStatus,
)
from aiwf.domain.persistence.session_store import SessionStore


def _build_state(
    *,
    session_id: str,
    phase: WorkflowPhase,
    status: WorkflowStatus = WorkflowStatus.IN_PROGRESS,
    current_iteration: int = 1,
    plan_approved: bool = False,
) -> WorkflowState:
    return WorkflowState(
        session_id=session_id,
        profile="test-profile",
        scope="test-scope",
        entity="TestEntity",
        providers={
            "planner": "manual",
            "generator": "manual",
            "reviewer": "manual",
            "reviser": "manual",
        },
        execution_mode=ExecutionMode.INTERACTIVE,
        phase=phase,
        status=status,
        current_iteration=current_iteration,
        standards_hash="0" * 64,
        plan_approved=plan_approved,
        plan_hash=None,
        phase_history=[PhaseTransition(phase=phase, status=status)],
    )


def test_step_planned_blocks_until_plan_approved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sessions_root = tmp_path / "sessions"
    store = SessionStore(sessions_root=sessions_root)
    orch = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    session_id = "sess-planned-gate"
    session_dir = sessions_root / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    # State: PLANNED, NOT approved
    state = _build_state(session_id=session_id, phase=WorkflowPhase.PLANNED, plan_approved=False)
    store.save(state)

    # Required inputs for _step_planned to run:
    # planning-response must exist (derive from ING specs; no hardcoding)
    planning_resp_rel = ING_APPROVAL_SPECS[WorkflowPhase.PLANNING].response_relpath_template.format(N=1)
    planning_resp_path = session_dir / planning_resp_rel
    planning_resp_path.parent.mkdir(parents=True, exist_ok=True)
    planning_resp_path.write_text("planning response\n", encoding="utf-8", newline="\n")

    # Ensure plan file exists (resolver-derived)
    plan_rel = ED_APPROVAL_SPECS[WorkflowPhase.PLANNED].plan_relpath
    assert plan_rel is not None
    (session_dir / plan_rel).write_text("plan\n", encoding="utf-8", newline="\n")

    # Mock ProfileFactory to handle "test-profile"
    class FakeProfile:
        def process_planning_response(self, content: str) -> ProcessingResult:
            return ProcessingResult(status=WorkflowStatus.SUCCESS)

    import aiwf.application.workflow_orchestrator as orch_mod
    monkeypatch.setattr(orch_mod.ProfileFactory, "create", lambda _name: FakeProfile(), raising=True)

    # Gate: step must not advance when plan_approved=False
    state1 = orch.step(session_id)
    assert state1.phase == WorkflowPhase.PLANNED

    # Flip approval marker
    state1.plan_approved = True
    store.save(state1)

    # Now step may advance to GENERATING
    state2 = orch.step(session_id)
    assert state2.phase == WorkflowPhase.GENERATING


@pytest.mark.parametrize("phase", [WorkflowPhase.GENERATED, WorkflowPhase.REVISED])
def test_step_ed_blocks_until_code_hashes_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: WorkflowPhase) -> None:
    sessions_root = tmp_path / "sessions"
    store = SessionStore(sessions_root=sessions_root)
    orch = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    session_id = f"sess-{phase.value}-gate"
    session_dir = sessions_root / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    iteration = 1
    code_dir_template = ED_APPROVAL_SPECS[phase].code_dir_relpath_template
    assert code_dir_template is not None
    code_dir_rel = code_dir_template.format(N=iteration)

    # Create at least one code file on disk
    code_dir = session_dir / code_dir_rel
    code_dir.mkdir(parents=True, exist_ok=True)
    (code_dir / "A.txt").write_text("code\n", encoding="utf-8", newline="\n")

    # Artifact exists but sha256 is None => gate should block
    artifact_rel = f"{code_dir_rel}/A.txt"
    state = _build_state(session_id=session_id, phase=phase, current_iteration=iteration)
    state.artifacts = [
        Artifact(path=artifact_rel, phase=phase, iteration=iteration, sha256=None)
    ]
    store.save(state)

    # Make the processing step "want" to advance by returning SUCCESS.
    # For GENERATED: orchestrator calls profile.process_generation_response(...)
    # For REVISED: orchestrator calls profile.process_revision_response(...)
    class FakeProfile:
        def process_generation_response(self, content: str, session_dir: Path, iteration: int) -> ProcessingResult:
            return ProcessingResult(status=WorkflowStatus.SUCCESS)

        def process_revision_response(self, content: str, session_dir: Path, iteration: int) -> ProcessingResult:
            return ProcessingResult(status=WorkflowStatus.SUCCESS)

    import aiwf.application.workflow_orchestrator as orch_mod
    monkeypatch.setattr(orch_mod.ProfileFactory, "create", lambda _name: FakeProfile(), raising=True)

    # Ensure the response file exists so _step_generated/_step_revised executes processing
    if phase == WorkflowPhase.GENERATED:
        resp_rel = ING_APPROVAL_SPECS[WorkflowPhase.GENERATING].response_relpath_template.format(N=iteration)
        resp_path = session_dir / resp_rel
        resp_path.parent.mkdir(parents=True, exist_ok=True)
        resp_path.write_text("gen response\n", encoding="utf-8", newline="\n")
    else:
        resp_rel = ING_APPROVAL_SPECS[WorkflowPhase.REVISING].response_relpath_template.format(N=iteration)
        resp_path = session_dir / resp_rel
        resp_path.parent.mkdir(parents=True, exist_ok=True)
        resp_path.write_text("rev response\n", encoding="utf-8", newline="\n")

    # Gate: step must NOT advance when any code artifact sha256 is missing
    state1 = orch.step(session_id)
    assert state1.phase == phase

    # Approve (ED) should set hashes; then step can advance
    orch.approve(session_id, hash_prompts=False)
    state2 = orch.step(session_id)

    # Expected transitions after unblocking:
    # GENERATED -> REVIEWING
    # REVISED -> REVIEWING
    assert state2.phase == WorkflowPhase.REVIEWING


def test_step_generating_blocks_until_response_exists_or_autoapproved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sessions_root = tmp_path / "sessions"
    store = SessionStore(sessions_root=sessions_root)
    orch = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    session_id = "sess-generating-ing-gate"
    session_dir = sessions_root / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    iteration = 1
    state = _build_state(session_id=session_id, phase=WorkflowPhase.GENERATING, current_iteration=iteration)
    store.save(state)

    spec = ING_APPROVAL_SPECS[WorkflowPhase.GENERATING]
    prompt_rel = spec.prompt_relpath_template.format(N=iteration)
    resp_rel = spec.response_relpath_template.format(N=iteration)

    prompt_path = session_dir / prompt_rel
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text("prompt\n", encoding="utf-8", newline="\n")

    # Ensure response is absent
    assert not (session_dir / resp_rel).exists()

    # Mock ProfileFactory to handle auto-approval logic
    class FakeProfile:
        def __init__(self, approved: bool):
            self._approved = approved

        def process_generation_response(self, content: str, session_dir: Path, iteration: int) -> ProcessingResult:
            return ProcessingResult(status=WorkflowStatus.SUCCESS, approved=self._approved)

    import aiwf.application.workflow_orchestrator as orch_mod
    # Start with NOT approved
    monkeypatch.setattr(orch_mod.ProfileFactory, "create", lambda _name: FakeProfile(approved=False), raising=True)

    # Gate: no response => step must not advance
    s1 = orch.step(session_id)
    assert s1.phase == WorkflowPhase.GENERATING

    # Auto-approval contract: approved=True can bypass explicit approve.
    # Define contract by monkeypatching orchestrator's GENERATING processing path:
    # step() should be updated in Part 3 to consult profile processing even without response
    # when profile returns approved=True.
    monkeypatch.setattr(orch_mod.ProfileFactory, "create", lambda _name: FakeProfile(approved=True), raising=True)

    # Second call should advance (contract). Current code will not, so this test should FAIL until implemented.
    s2 = orch.step(session_id)
    assert s2.phase == WorkflowPhase.GENERATED


def test_generated_does_not_auto_advance_until_approved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Critical: after code is written and phase becomes GENERATED, workflow must NOT auto-advance to REVIEWING
    until ED approve hashes code artifacts.
    """
    sessions_root = tmp_path / "sessions"
    store = SessionStore(sessions_root=sessions_root)
    orch = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    session_id = "sess-generated-no-auto-advance"
    session_dir = sessions_root / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    iteration = 1
    state = _build_state(session_id=session_id, phase=WorkflowPhase.GENERATED, current_iteration=iteration)

    # Create an un-hashed code artifact and file under resolver-derived code dir
    code_dir_template = ED_APPROVAL_SPECS[WorkflowPhase.GENERATED].code_dir_relpath_template
    assert code_dir_template is not None
    code_dir_rel = code_dir_template.format(N=iteration)
    code_dir = session_dir / code_dir_rel
    code_dir.mkdir(parents=True, exist_ok=True)
    (code_dir / "A.txt").write_text("code\n", encoding="utf-8", newline="\n")

    state.artifacts = [
        Artifact(path=f"{code_dir_rel}/A.txt", phase=WorkflowPhase.GENERATED, iteration=iteration, sha256=None)
    ]
    store.save(state)

    # Ensure generation-response exists so _step_generated runs its processing path
    resp_rel = ING_APPROVAL_SPECS[WorkflowPhase.GENERATING].response_relpath_template.format(N=iteration)
    resp_path = session_dir / resp_rel
    resp_path.parent.mkdir(parents=True, exist_ok=True)
    resp_path.write_text("gen response\n", encoding="utf-8", newline="\n")

    # Make processing "successful" so orchestrator would normally try to advance.
    class FakeProfile:
        def process_generation_response(self, content: str, session_dir: Path, iteration: int) -> ProcessingResult:
            return ProcessingResult(status=WorkflowStatus.SUCCESS)

    import aiwf.application.workflow_orchestrator as orch_mod
    monkeypatch.setattr(orch_mod.ProfileFactory, "create", lambda _name: FakeProfile(), raising=True)

    # Contract: must remain GENERATED until approved (currently will advance; should FAIL until gating is added)
    s1 = orch.step(session_id)
    assert s1.phase == WorkflowPhase.GENERATED
