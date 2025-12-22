import hashlib
from pathlib import Path
import pytest

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.models.workflow_state import Artifact, WorkflowPhase, WorkflowState, WorkflowStatus, ExecutionMode, PhaseTransition
from aiwf.domain.persistence.session_store import SessionStore
from aiwf.application.approval_specs import ED_APPROVAL_SPECS, ING_APPROVAL_SPECS


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def _build_state(session_id: str, phase: WorkflowPhase, current_iteration: int) -> WorkflowState:
    return WorkflowState(
        session_id=session_id,
        profile="test-profile",
        scope="test-scope",
        entity="TestEntity",
        providers={"default": "test-provider"},
        execution_mode=ExecutionMode.INTERACTIVE,
        phase=phase,
        status=WorkflowStatus.IN_PROGRESS,
        current_iteration=current_iteration,
        standards_hash="test-hash",
        phase_history=[PhaseTransition(phase=phase, status=WorkflowStatus.IN_PROGRESS)],
    )

def test_approve_planned_creates_plan_from_planning_response(tmp_path: Path) -> None:
    # Arrange
    sessions_root = tmp_path / 'sessions'
    store = SessionStore(sessions_root=sessions_root)
    orch = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    phase = WorkflowPhase.PLANNED
    session_id = 'sess-planned'
    session_dir = sessions_root / session_id
    iteration_dir = session_dir / 'iteration-1'
    iteration_dir.mkdir(parents=True, exist_ok=True)

    state = _build_state(session_id=session_id, phase=phase, current_iteration=1)
    store.save(state)

    # Write planning-response.md (source file)
    response_relpath = ING_APPROVAL_SPECS[WorkflowPhase.PLANNING].response_relpath_template.format(N=1)
    response_path = session_dir / response_relpath
    plan_content = "Plan content\n"
    response_path.write_text(plan_content, encoding='utf-8', newline='\n')

    # Act
    orch.approve(session_id=session_id)

    # Assert
    reloaded = store.load(session_id)
    assert reloaded.plan_approved is True
    assert reloaded.plan_hash == _sha256_text(plan_content)

    # Verify plan.md was created in session root
    plan_relpath = ED_APPROVAL_SPECS[phase].plan_relpath
    assert plan_relpath is not None
    plan_path = session_dir / plan_relpath
    assert plan_path.exists()
    assert plan_path.read_text(encoding='utf-8') == plan_content


@pytest.mark.parametrize(
    'phase,iteration',
    [
        (WorkflowPhase.GENERATED, 1),
        (WorkflowPhase.REVISED, 2),
    ],
)
def test_approve_ed_hashes_all_code_files(tmp_path: Path, phase: WorkflowPhase, iteration: int) -> None:
    # Arrange
    sessions_root = tmp_path / 'sessions'
    store = SessionStore(sessions_root=sessions_root)
    orch = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    session_id = f'sess-{phase.value}'
    session_dir = sessions_root / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    state = _build_state(session_id=session_id, phase=phase, current_iteration=iteration)

    # Derive code directory from resolver table (single source of truth)
    code_dir_template = ED_APPROVAL_SPECS[phase].code_dir_relpath_template
    assert code_dir_template is not None, 'ED_APPROVAL_SPECS must define code_dir_relpath_template for this phase'
    code_dir_relpath = code_dir_template.format(N=iteration)

    # Derive all artifact paths from code_dir_relpath (do not hardcode iteration/code layout)
    a1_path = f'{code_dir_relpath}/A.txt'
    a2_path = f'{code_dir_relpath}/B.txt'
    extra_rel = f'{code_dir_relpath}/EXTRA.txt'

    # Two artifacts tracked by state, sha256 must be None before approval
    state.artifacts.extend(
        [
            Artifact(path=a1_path, phase=phase, iteration=iteration, sha256=None),
            Artifact(path=a2_path, phase=phase, iteration=iteration, sha256=None),
        ]
    )
    store.save(state)

    # Ensure code directory exists
    code_dir = session_dir / code_dir_relpath
    code_dir.mkdir(parents=True, exist_ok=True)

    # Ensure files exist on disk, then edit one to simulate user modification after initial write.
    (session_dir / a1_path).write_text('one\n', encoding='utf-8', newline='\n')
    (session_dir / a2_path).write_text('two\n', encoding='utf-8', newline='\n')
    (session_dir / a2_path).write_text('two-edited\n', encoding='utf-8', newline='\n')

    # Extra file on disk not present in artifacts must be discovered and added
    (session_dir / extra_rel).write_text('extra\n', encoding='utf-8', newline='\n')

    # Act
    orch.approve(session_id=session_id, hash_prompts=False)

    # Assert
    reloaded = store.load(session_id)

    # All code files under iteration-N/code must now have sha256 computed from disk content.
    artifact_by_path = {a.path: a for a in reloaded.artifacts}

    assert artifact_by_path[a1_path].sha256 == _sha256_text('one\n')
    assert artifact_by_path[a2_path].sha256 == _sha256_text('two-edited\n')
    assert artifact_by_path[extra_rel].sha256 == _sha256_text('extra\n')

def test_approve_planned_missing_response_sets_error_status(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    sessions_root = tmp_path / 'sessions'
    store = SessionStore(sessions_root=sessions_root)
    orch = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    phase = WorkflowPhase.PLANNED
    session_id = 'sess-planned-missing'
    session_dir = sessions_root / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    state = _build_state(session_id=session_id, phase=phase, current_iteration=1)
    store.save(state)

    state = orch.approve(session_id=session_id)

    assert state.status == WorkflowStatus.ERROR
    assert state.last_error is not None

    # Error should reference the missing planning-response.md, not plan.md
    response_relpath = ING_APPROVAL_SPECS[WorkflowPhase.PLANNING].response_relpath_template.format(N=1)

    normalized_err = state.last_error.replace("\\", "/")
    err_lower = normalized_err.lower()

    assert response_relpath in normalized_err  # helpful: points to missing file
    assert ("missing" in err_lower) or ("not found" in err_lower)


def test_successful_approve_clears_error_status(tmp_path: Path) -> None:
    sessions_root = tmp_path / 'sessions'
    store = SessionStore(sessions_root=sessions_root)
    orch = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    phase = WorkflowPhase.PLANNED
    session_id = 'sess-clear-error'
    session_dir = sessions_root / session_id
    iteration_dir = session_dir / 'iteration-1'
    iteration_dir.mkdir(parents=True, exist_ok=True)

    state = _build_state(session_id=session_id, phase=phase, current_iteration=1)
    state.status = WorkflowStatus.ERROR
    store.save(state)

    # Ensure planning-response.md exists so approve succeeds
    response_relpath = ING_APPROVAL_SPECS[WorkflowPhase.PLANNING].response_relpath_template.format(N=1)
    response_path = session_dir / response_relpath
    response_path.write_text("Plan content\n", encoding='utf-8')

    # Act
    orch.approve(session_id=session_id)

    # Assert
    reloaded = store.load(session_id)
    assert reloaded.status == WorkflowStatus.IN_PROGRESS


@pytest.mark.parametrize('phase', [WorkflowPhase.GENERATED, WorkflowPhase.REVISED])
def test_approve_ed_missing_code_dir_sets_error_status(
    tmp_path: Path, capsys: pytest.CaptureFixture, phase: WorkflowPhase
) -> None:
    sessions_root = tmp_path / 'sessions'
    store = SessionStore(sessions_root=sessions_root)
    orch = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    session_id = f'sess-{phase.value}-missing'
    session_dir = sessions_root / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    iteration = 1
    state = _build_state(session_id=session_id, phase=phase, current_iteration=iteration)
    store.save(state)

    state = orch.approve(session_id=session_id)

    assert state.status == WorkflowStatus.ERROR
    assert state.last_error is not None

    code_dir_template = ED_APPROVAL_SPECS[phase].code_dir_relpath_template
    assert code_dir_template is not None
    code_dir_relpath = code_dir_template.format(N=iteration)

    normalized_err = state.last_error.replace("\\", "/")
    err_lower = normalized_err.lower()

    assert code_dir_relpath in normalized_err  # helpful: points to missing dir
    assert ("missing" in err_lower) or ("not found" in err_lower)
