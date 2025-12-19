from datetime import datetime, timezone

from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.workflow_state import Artifact, WorkflowPhase, WorkflowStatus
from aiwf.domain.models.write_plan import WriteOp, WritePlan


def test_processing_result_contract_defaults() -> None:
    pr = ProcessingResult(status=WorkflowStatus.IN_PROGRESS)

    assert pr.status == WorkflowStatus.IN_PROGRESS
    assert pr.approved is False
    assert pr.write_plan is None
    assert pr.artifacts == []
    assert pr.error_message is None
    assert pr.metadata == {}

    assert "status" in ProcessingResult.model_fields
    assert "approved" in ProcessingResult.model_fields
    assert "write_plan" in ProcessingResult.model_fields
    assert "artifacts" in ProcessingResult.model_fields
    assert "error_message" in ProcessingResult.model_fields
    assert "metadata" in ProcessingResult.model_fields


def test_processing_result_accepts_write_plan() -> None:
    plan = WritePlan(writes=[WriteOp(path="src/Foo.java", content="class Foo {}")])
    pr = ProcessingResult(status=WorkflowStatus.IN_PROGRESS, write_plan=plan)

    assert pr.write_plan is not None
    assert pr.write_plan.writes[0].path == "src/Foo.java"


def test_processing_result_accepts_artifacts_list() -> None:
    a = Artifact(
        path="iteration-1/code/Tier.java",
        phase=WorkflowPhase.GENERATED,
        iteration=1,
        created_at=datetime.now(timezone.utc),
        sha256=None,
    )
    pr = ProcessingResult(status=WorkflowStatus.IN_PROGRESS, artifacts=[a])

    assert len(pr.artifacts) == 1
    assert pr.artifacts[0].path.endswith("Tier.java")


def test_processing_result_metadata_default_factory_is_dict() -> None:
    pr1 = ProcessingResult(status=WorkflowStatus.IN_PROGRESS)
    pr2 = ProcessingResult(status=WorkflowStatus.IN_PROGRESS)

    pr1.metadata["k"] = "v"
    assert "k" not in pr2.metadata


def test_processing_result_artifacts_default_factory_is_list() -> None:
    pr1 = ProcessingResult(status=WorkflowStatus.IN_PROGRESS)
    pr2 = ProcessingResult(status=WorkflowStatus.IN_PROGRESS)

    pr1.artifacts.append(
        Artifact(
            path="iteration-1/code/A.java",
            phase=WorkflowPhase.GENERATED,
            iteration=1,
            created_at=datetime.now(timezone.utc),
            sha256=None,
        )
    )
    assert pr2.artifacts == []
