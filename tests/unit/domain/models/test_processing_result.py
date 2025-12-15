import pytest
from datetime import datetime, timezone

from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.workflow_state import WorkflowStatus, WorkflowPhase, Artifact


def test_processing_result_instantiates_with_only_status():
    """
    Test that ProcessingResult can be instantiated with only the status field,
    and default values for artifacts, error_message, and metadata are correctly set.
    """
    result = ProcessingResult(status=WorkflowStatus.SUCCESS)

    assert result.status == WorkflowStatus.SUCCESS
    assert result.artifacts == []
    assert result.error_message is None
    assert result.metadata == {}


def test_processing_result_instantiates_with_error_message_and_metadata():
    """
    Test that ProcessingResult can be instantiated with error_message and metadata,
    and other fields are set correctly.
    """
    error_msg = "An error occurred during processing."
    metadata_dict = {"step": "planning", "attempt": 1}
    result = ProcessingResult(
        status=WorkflowStatus.FAILED,
        error_message=error_msg,
        metadata=metadata_dict
    )

    assert result.status == WorkflowStatus.FAILED
    assert result.artifacts == []
    assert result.error_message == error_msg
    assert result.metadata == metadata_dict


def test_default_lists_are_not_shared_across_instances():
    """
    Test that default lists (artifacts and metadata) are not shared across different
    ProcessingResult instances.
    """
    result1 = ProcessingResult(status=WorkflowStatus.SUCCESS)
    result2 = ProcessingResult(status=WorkflowStatus.SUCCESS)

    # Modify artifacts in result1
    artifact1 = Artifact(
        phase=WorkflowPhase.PLANNING,
        artifact_type="plan",
        file_path="path/to/plan1.md"
    )
    result1.artifacts.append(artifact1)

    # Modify metadata in result2
    result2.metadata["key"] = "value"

    assert result1.artifacts != result2.artifacts
    assert result1.metadata == {}  # result1's metadata should still be default
    assert result2.artifacts == []  # result2's artifacts should still be default
    assert result2.metadata == {"key": "value"}


def test_artifacts_accepts_list_of_artifact_objects():
    """
    Test that the artifacts field correctly accepts a list of Artifact objects.
    """
    artifact1 = Artifact(
        phase=WorkflowPhase.PLANNING,
        artifact_type="plan",
        file_path="path/to/plan.md",
        created_at=datetime.now(timezone.utc) # Explicitly setting for consistency, though default factory works
    )
    artifact2 = Artifact(
        phase=WorkflowPhase.GENERATING,
        artifact_type="code",
        file_path="path/to/code.py"
    )
    artifacts_list = [artifact1, artifact2]

    result = ProcessingResult(status=WorkflowStatus.SUCCESS, artifacts=artifacts_list)

    assert result.status == WorkflowStatus.SUCCESS
    assert result.artifacts == artifacts_list
    assert len(result.artifacts) == 2
    assert result.artifacts[0].file_path == "path/to/plan.md"
    assert result.artifacts[1].artifact_type == "code"
