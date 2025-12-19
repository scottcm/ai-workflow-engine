from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from aiwf.domain.models.workflow_state import Artifact, WorkflowPhase


def test_artifact_happy_path_constructs() -> None:
    a = Artifact(
        path="iteration-1/code/Tier.java",
        phase=WorkflowPhase.GENERATED,
        iteration=1,
        created_at=datetime.now(timezone.utc),
        sha256=None,
    )
    assert a.path == "iteration-1/code/Tier.java"
    assert a.phase == WorkflowPhase.GENERATED
    assert a.iteration == 1
    assert a.sha256 is None
    assert isinstance(a.created_at, datetime)


def test_artifact_enforces_iteration_ge_1() -> None:
    with pytest.raises(ValidationError):
        Artifact(
            path="iteration-0/code/Tier.java",
            phase=WorkflowPhase.GENERATED,
            iteration=0,
            created_at=datetime.now(timezone.utc),
            sha256=None,
        )


def test_artifact_rejects_empty_path() -> None:
    with pytest.raises(ValidationError):
        Artifact(
            path="",
            phase=WorkflowPhase.GENERATED,
            iteration=1,
            created_at=datetime.now(timezone.utc),
            sha256=None,
        )


def test_artifact_rejects_artifact_type_input() -> None:
    # Contract: legacy key must be rejected
    with pytest.raises(ValidationError):
        Artifact(
            artifact_type="code",
            path="iteration-1/code/Tier.java",
            phase=WorkflowPhase.GENERATED,
            iteration=1,
            created_at=datetime.now(timezone.utc),
            sha256=None,
        )


def test_artifact_rejects_file_path_input() -> None:
    # Contract: legacy key must be rejected
    with pytest.raises(ValidationError):
        Artifact(
            file_path="iteration-1/code/Tier.java",
            phase=WorkflowPhase.GENERATED,
            iteration=1,
            created_at=datetime.now(timezone.utc),
            sha256=None,
        )


def test_artifact_rejects_kind_input() -> None:
    # Contract: kind semantics must be rejected
    with pytest.raises(ValidationError):
        Artifact(
            kind="code",
            path="iteration-1/code/Tier.java",
            phase=WorkflowPhase.GENERATED,
            iteration=1,
            created_at=datetime.now(timezone.utc),
            sha256=None,
        )
