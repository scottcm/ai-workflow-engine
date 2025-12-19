import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from aiwf.application.standards_materializer import materialize_standards
from aiwf.application.standards_provider import FileBasedStandardsProvider
from aiwf.domain.models.workflow_state import ExecutionMode, WorkflowPhase, WorkflowState, WorkflowStatus


def _mk_state(*, session_id: str) -> WorkflowState:
    # Minimal valid WorkflowState for unit tests; no persistence expectations.
    return WorkflowState(
        session_id=session_id,
        profile="jpa_mt",
        scope="domain",
        entity="Tier",
        phase=WorkflowPhase.INITIALIZED,
        status=WorkflowStatus.IN_PROGRESS,
        execution_mode=ExecutionMode.INTERACTIVE,
        providers={"planner": "manual", "generator": "manual", "reviewer": "manual", "reviser": "manual"},
        standards_hash="0" * 64,  # raw digest placeholder
        current_iteration=1,
    )


def _sha256_hex_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def test_materialize_standards_writes_bundle_file_sets_hash_and_does_not_create_artifacts(tmp_path: Path) -> None:
    session_dir = tmp_path / "session"
    session_dir.mkdir(parents=True, exist_ok=True)

    standards_root = tmp_path / "standards"
    standards_root.mkdir(parents=True, exist_ok=True)

    (standards_root / "A.md").write_text("alpha\n", encoding="utf-8")
    (standards_root / "B.md").write_text("beta\n", encoding="utf-8")

    # Provider owns standards I/O and selection; engine does not take file paths directly.
    provider = FileBasedStandardsProvider(
        standards_root=standards_root,
        standards_files=["B.md", "A.md"],  # out-of-order input; provider must be deterministic
    )

    state = _mk_state(session_id="s1")

    materialize_standards(session_dir=session_dir, state=state, provider=provider)

    bundle_path = session_dir / "standards-bundle.md"
    assert bundle_path.exists()

    expected = (
        "--- A.md ---\n"
        "alpha\n"
        "--- B.md ---\n"
        "beta\n"
    )
    assert bundle_path.read_text(encoding="utf-8") == expected

    expected_hash = _sha256_hex_bytes(expected.encode("utf-8"))
    assert state.standards_hash == expected_hash

    # Standards are not artifacts.
    assert state.artifacts == []


def test_materialize_standards_is_deterministic_on_rerun(tmp_path: Path) -> None:
    session_dir = tmp_path / "session"
    session_dir.mkdir(parents=True, exist_ok=True)

    standards_root = tmp_path / "standards"
    standards_root.mkdir(parents=True, exist_ok=True)

    (standards_root / "A.md").write_text("alpha\n", encoding="utf-8")
    (standards_root / "B.md").write_text("beta\n", encoding="utf-8")

    provider = FileBasedStandardsProvider(
        standards_root=standards_root,
        standards_files=["A.md", "B.md"],
    )

    state = _mk_state(session_id="s2")

    materialize_standards(session_dir=session_dir, state=state, provider=provider)
    first_hash = state.standards_hash
    first_bytes = (session_dir / "standards-bundle.md").read_bytes()

    materialize_standards(session_dir=session_dir, state=state, provider=provider)
    second_hash = state.standards_hash
    second_bytes = (session_dir / "standards-bundle.md").read_bytes()

    assert first_hash == second_hash
    assert first_bytes == second_bytes


def test_materialize_standards_deduplicates_provider_selection(tmp_path: Path) -> None:
    session_dir = tmp_path / "session"
    session_dir.mkdir(parents=True, exist_ok=True)

    standards_root = tmp_path / "standards"
    standards_root.mkdir(parents=True, exist_ok=True)

    (standards_root / "A.md").write_text("alpha\n", encoding="utf-8")

    provider = FileBasedStandardsProvider(
        standards_root=standards_root,
        standards_files=["A.md", "A.md"],  # duplicate selection must not duplicate inclusion
    )

    state = _mk_state(session_id="s3")

    materialize_standards(session_dir=session_dir, state=state, provider=provider)

    bundle_path = session_dir / "standards-bundle.md"
    assert bundle_path.read_text(encoding="utf-8") == (
        "--- A.md ---\n"
        "alpha\n"
    )


def test_materialize_standards_missing_file_is_hard_failure_no_write_and_state_unchanged(tmp_path: Path) -> None:
    session_dir = tmp_path / "session"
    session_dir.mkdir(parents=True, exist_ok=True)

    standards_root = tmp_path / "standards"
    standards_root.mkdir(parents=True, exist_ok=True)

    (standards_root / "A.md").write_text("alpha\n", encoding="utf-8")
    # Missing: B.md

    provider = FileBasedStandardsProvider(
        standards_root=standards_root,
        standards_files=["A.md", "B.md"],
    )

    state = _mk_state(session_id="s4")
    old_hash = state.standards_hash

    with pytest.raises(FileNotFoundError):
        materialize_standards(session_dir=session_dir, state=state, provider=provider)

    assert not (session_dir / "standards-bundle.md").exists()
    assert state.standards_hash == old_hash
    assert state.artifacts == []


def test_materialize_standards_read_error_is_hard_failure_no_write_and_state_unchanged(tmp_path: Path) -> None:
    session_dir = tmp_path / "session"
    session_dir.mkdir(parents=True, exist_ok=True)

    standards_root = tmp_path / "standards"
    standards_root.mkdir(parents=True, exist_ok=True)

    (standards_root / "A.md").write_text("alpha\n", encoding="utf-8")
    (standards_root / "B.md").mkdir()  # reading as file should fail deterministically

    provider = FileBasedStandardsProvider(
        standards_root=standards_root,
        standards_files=["A.md", "B.md"],
    )

    state = _mk_state(session_id="s5")
    old_hash = state.standards_hash

    with pytest.raises(Exception):
        materialize_standards(session_dir=session_dir, state=state, provider=provider)

    assert not (session_dir / "standards-bundle.md").exists()
    assert state.standards_hash == old_hash
    assert state.artifacts == []


def test_materialize_standards_requires_state_with_standards_hash(tmp_path: Path) -> None:
    # Guardrail: standards_hash is required on WorkflowState by domain contract.
    with pytest.raises(ValidationError):
        WorkflowState(
            session_id="s-x",
            profile="jpa_mt",
            scope="domain",
            entity="Tier",
            phase=WorkflowPhase.INITIALIZED,
            status=WorkflowStatus.IN_PROGRESS,
            execution_mode=ExecutionMode.INTERACTIVE,
            providers={"planner": "manual", "generator": "manual", "reviewer": "manual", "reviser": "manual"},
        )
