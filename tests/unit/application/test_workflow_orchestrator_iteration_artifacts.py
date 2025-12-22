from pathlib import Path
import importlib

import pytest

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.workflow_state import ExecutionMode, WorkflowPhase, WorkflowStatus
from aiwf.domain.models.write_plan import WriteOp, WritePlan
from aiwf.domain.persistence.session_store import SessionStore
from aiwf.domain.profiles.profile_factory import ProfileFactory


# --------------------------- 
# Local overrides / utilities
# --------------------------- 

@pytest.fixture(autouse=True)
def mock_jpa_mt_profile():
    """
    Disable tests/unit/application/conftest.py's autouse fixture of the same name.

    Slice 7 tests need full control over ProfileFactory.create("jpa-mt") and
    must inject non-empty write plans.
    """
    yield


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _assert_safe_rel_path(p: str) -> None:
    # Must be session-root-relative and normalized (no traversal)
    assert not (p.startswith("/") or p.startswith("\\"))
    assert ":" not in p  # guard against Windows drive prefixes like C:
    assert ".." not in p


# --------------------------- 
# Concrete fakes (no MagicMock)
# --------------------------- 

class FakeStandardsProvider:
    def create_bundle(self, context) -> str:
        # Deterministic, minimal bundle
        return "STANDARDS\n"


class FakeBundleExtractor:
    """
    Compatibility shim for current orchestrator revision behavior, if it still
    attempts to import and call bundle_extractor.extract_files().
    """
    def extract_files(self, _content: str) -> dict[str, str]:
        return {"Foo.java": "class Foo { /*legacy*/ }\n"}


class FakeProfile:
    def __init__(
        self,
        *,
        generation_write_plan: WritePlan,
        revision_write_plan: WritePlan,
        review_status: WorkflowStatus,
    ) -> None:
        self._generation_write_plan = generation_write_plan
        self._revision_write_plan = revision_write_plan
        self._review_status = review_status

    def validate_metadata(self, metadata):
        pass  # No validation needed for tests

    def get_standards_provider(self) -> FakeStandardsProvider:
        return FakeStandardsProvider()

    # Prompts (content irrelevant for these tests)
    def generate_planning_prompt(self, context):
        return "PLANNING PROMPT\n"

    def generate_generation_prompt(self, context):
        return "GENERATION PROMPT\n"

    def generate_review_prompt(self, context):
        return "REVIEW PROMPT\n"

    def generate_revision_prompt(self, context):
        return "REVISION PROMPT\n"

    # Response processing
    def process_planning_response(self, content: str) -> ProcessingResult:
        return ProcessingResult(status=WorkflowStatus.SUCCESS)

    def process_generation_response(self, content: str, session_dir: Path, iteration: int) -> ProcessingResult:
        return ProcessingResult(status=WorkflowStatus.SUCCESS, write_plan=self._generation_write_plan)

    def process_review_response(self, content: str) -> ProcessingResult:
        return ProcessingResult(status=self._review_status)

    def process_revision_response(self, content: str, session_dir: Path, iteration: int) -> ProcessingResult:
        return ProcessingResult(status=WorkflowStatus.SUCCESS, write_plan=self._revision_write_plan)


@pytest.fixture
def orchestrator(sessions_root: Path) -> WorkflowOrchestrator:
    store = SessionStore(sessions_root)
    return WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)


# --------------------------- 
# Tests
# --------------------------- 

def test_generated_artifacts_record_iteration_and_iteration_relative_paths(
    sessions_root: Path,
    orchestrator: WorkflowOrchestrator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    gen_plan = WritePlan(
        writes=[
            WriteOp(path="code/Foo.java", content="class Foo {}\n"),
            WriteOp(path="code/Bar.java", content="class Bar {}\n"),
        ]
    )

    fake_profile = FakeProfile(
        generation_write_plan=gen_plan,
        revision_write_plan=WritePlan(writes=[]),
        review_status=WorkflowStatus.SUCCESS,
    )

    monkeypatch.setattr(ProfileFactory, "create", lambda _profile_key, **_kw: fake_profile)

    import aiwf.application.workflow_orchestrator as wo_mod
    monkeypatch.setattr(wo_mod, "materialize_standards", lambda session_dir, context, provider: "0" * 64)

    session_id = orchestrator.initialize_run(
        profile="jpa-mt",
        scope="domain",
        entity="Foo",
        providers={"planner": "manual", "generator": "manual", "reviewer": "manual", "reviser": "manual"},
        execution_mode=ExecutionMode.INTERACTIVE,
    )
    session_dir = sessions_root / session_id

    # INITIALIZED -> PLANNING
    state = orchestrator.step(session_id)
    assert state.phase == WorkflowPhase.PLANNING

    # PLANNING -> PLANNED
    _write_text(session_dir / "iteration-1" / "planning-response.md", "PLAN RESPONSE\n")
    _write_text(session_dir / "plan.md", "PLAN RESPONSE\n")  # For ED approval
    state = orchestrator.step(session_id)
    assert state.phase == WorkflowPhase.PLANNED

    # Approve PLANNED
    orchestrator.approve(session_id)

    # PLANNED -> GENERATING
    state = orchestrator.step(session_id)
    assert state.phase == WorkflowPhase.GENERATING
    assert state.current_iteration == 1

    # GENERATING -> GENERATED (processes response, writes artifacts)
    _write_text(session_dir / "iteration-1" / "generation-response.md", "GEN RESPONSE\n")
    state = orchestrator.step(session_id)
    assert state.phase == WorkflowPhase.GENERATED

    # Artifacts recorded with sha256=None
    assert state.artifacts, "Expected at least one Artifact recorded from generation writes"
    for a in state.artifacts:
        assert a.iteration == 1
        assert a.path.startswith("iteration-1/")
        _assert_safe_rel_path(a.path)
        assert a.sha256 is None  # Not hashed until approve()

    # Approve GENERATED (hashes artifacts)
    orchestrator.approve(session_id)
    state = orchestrator.session_store.load(session_id)
    for a in state.artifacts:
        assert a.sha256 is not None

    # GENERATED -> REVIEWING
    state = orchestrator.step(session_id)
    assert state.phase == WorkflowPhase.REVIEWING


def test_revised_artifacts_record_iteration_2_and_do_not_pollute_iteration_1(
    sessions_root: Path,
    orchestrator: WorkflowOrchestrator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    gen_plan = WritePlan(
        writes=[WriteOp(path="code/Foo.java", content="class Foo {}\n")]
    )
    rev_plan = WritePlan(
        writes=[WriteOp(path="code/Foo.java", content="class Foo { /*rev*/ }\n")]
    )

    fake_profile = FakeProfile(
        generation_write_plan=gen_plan,
        revision_write_plan=rev_plan,
        review_status=WorkflowStatus.FAILED,  # force REVISING and iteration increment
    )

    monkeypatch.setattr(ProfileFactory, "create", lambda _profile_key, **_kw: fake_profile)

    import aiwf.application.workflow_orchestrator as wo_mod
    monkeypatch.setattr(wo_mod, "materialize_standards", lambda session_dir, context, provider: "0" * 64)

    # Compatibility: if current code still imports a bundle_extractor during revision
    extractor = FakeBundleExtractor()
    monkeypatch.setattr(importlib, "import_module", lambda _name: extractor)

    session_id = orchestrator.initialize_run(
        profile="jpa-mt",
        scope="domain",
        entity="Foo",
        providers={"planner": "manual", "generator": "manual", "reviewer": "manual", "reviser": "manual"},
        execution_mode=ExecutionMode.INTERACTIVE,
    )
    session_dir = sessions_root / session_id

    # INITIALIZED -> PLANNING
    state = orchestrator.step(session_id)
    assert state.phase == WorkflowPhase.PLANNING

    # PLANNING -> PLANNED
    _write_text(session_dir / "iteration-1" / "planning-response.md", "PLAN RESPONSE\n")
    _write_text(session_dir / "plan.md", "PLAN RESPONSE\n")
    state = orchestrator.step(session_id)
    assert state.phase == WorkflowPhase.PLANNED

    # Approve PLANNED
    orchestrator.approve(session_id)

    # PLANNED -> GENERATING
    state = orchestrator.step(session_id)
    assert state.phase == WorkflowPhase.GENERATING
    assert state.current_iteration == 1

    # GENERATING -> GENERATED
    _write_text(session_dir / "iteration-1" / "generation-response.md", "GEN RESPONSE\n")
    state = orchestrator.step(session_id)
    assert state.phase == WorkflowPhase.GENERATED
    assert any(a.iteration == 1 for a in state.artifacts)

    # Approve GENERATED
    orchestrator.approve(session_id)

    # GENERATED -> REVIEWING
    state = orchestrator.step(session_id)
    assert state.phase == WorkflowPhase.REVIEWING

    # REVIEWING -> REVIEWED
    _write_text(session_dir / "iteration-1" / "review-response.md", "REVIEW RESPONSE\n")
    state = orchestrator.step(session_id)
    assert state.phase == WorkflowPhase.REVIEWED

    # Approve REVIEWED (required per 7C)
    orchestrator.approve(session_id)

    # REVIEWED -> REVISING (FAILED review => iteration increments)
    state = orchestrator.step(session_id)
    assert state.phase == WorkflowPhase.REVISING
    assert state.current_iteration == 2
    assert (session_dir / "iteration-2").is_dir()

    # REVISING -> REVISED (processes response, writes artifacts)
    _write_text(session_dir / "iteration-2" / "revision-response.md", "REV RESPONSE\n")
    state = orchestrator.step(session_id)
    assert state.phase == WorkflowPhase.REVISED

    # Revision artifacts recorded
    iter2 = [a for a in state.artifacts if a.iteration == 2]
    assert iter2, "Expected at least one Artifact recorded from revision writes"

    for a in iter2:
        assert a.path.startswith("iteration-2/")
        _assert_safe_rel_path(a.path)
        assert a.sha256 is None  # Not hashed until approve()

    # Ensure iteration-1 artifacts remain intact (no mutation/pollution)
    iter1 = [a for a in state.artifacts if a.iteration == 1]
    assert iter1, "Expected iteration-1 artifacts to still exist"
    for a in iter1:
        assert a.iteration == 1
        assert a.path.startswith("iteration-1/")

    # Approve REVISED
    orchestrator.approve(session_id)

    # REVISED -> REVIEWING
    state = orchestrator.step(session_id)
    assert state.phase == WorkflowPhase.REVIEWING

    # Verify iteration-2 outputs exist on disk
    assert (session_dir / "iteration-2" / "code" / "Foo.java").exists()