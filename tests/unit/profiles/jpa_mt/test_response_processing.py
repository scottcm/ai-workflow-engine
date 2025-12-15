from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStatus
from profiles.jpa_mt.jpa_mt_profile import JpaMtProfile


@pytest.fixture
def profile(tmp_path: Path) -> JpaMtProfile:
    standards_dir = tmp_path / "standards"
    standards_dir.mkdir(parents=True, exist_ok=True)

    config_path = tmp_path / "config.yml"
    config = {
        "standards": {"root": str(standards_dir.resolve())},
        "artifacts": {},
        "scopes": {"domain": {"layers": []}},
        "layer_standards": {},
    }
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    return JpaMtProfile(config_path=config_path)



def test_process_planning_response_success(profile: JpaMtProfile) -> None:
    result = profile.process_planning_response("Some valid planning content")

    assert isinstance(result, ProcessingResult)
    assert result.status == WorkflowStatus.SUCCESS
    assert result.error_message is None


def test_process_planning_response_error_on_empty(profile: JpaMtProfile) -> None:
    result = profile.process_planning_response("")

    assert result.status == WorkflowStatus.ERROR
    assert result.error_message is not None


def test_process_planning_response_error_on_whitespace(profile: JpaMtProfile) -> None:
    result = profile.process_planning_response("   \n\t   ")

    assert result.status == WorkflowStatus.ERROR
    assert result.error_message is not None


def test_process_generation_response_success(profile: JpaMtProfile, tmp_path: Path) -> None:
    content = """<<<FILE: Foo.java>>>
    public class Foo {}
    """

    result = profile.process_generation_response(
        content=content,
        session_dir=tmp_path,
        iteration=1,
    )

    assert result.status == WorkflowStatus.SUCCESS
    assert len(result.artifacts) == 1

    artifact = result.artifacts[0]
    assert artifact.phase == WorkflowPhase.GENERATED
    assert artifact.artifact_type == "code"
    assert artifact.file_path == "iteration-1/code/Foo.java"

    written = tmp_path / artifact.file_path
    assert written.exists()
    assert "public class Foo {}" in written.read_text(encoding="utf-8")


def test_process_generation_response_error_on_invalid_bundle(profile: JpaMtProfile, tmp_path: Path) -> None:
    result = profile.process_generation_response(
        content="not a bundle",
        session_dir=tmp_path,
        iteration=1,
    )

    assert result.status == WorkflowStatus.ERROR
    assert result.error_message is not None


def test_process_generation_response_error_on_empty(profile: JpaMtProfile, tmp_path: Path) -> None:
    result = profile.process_generation_response(
        content="",
        session_dir=tmp_path,
        iteration=1,
    )

    assert result.status == WorkflowStatus.ERROR
    assert result.error_message is not None


def test_process_review_response_pass(profile: JpaMtProfile) -> None:
    content = """@@@REVIEW_META
verdict: PASS
issues_total: 0
issues_critical: 0
missing_inputs: 0
@@@
"""

    result = profile.process_review_response(content)

    assert result.status == WorkflowStatus.SUCCESS
    assert result.error_message is None
    assert result.metadata.get("verdict") == "PASS"


def test_process_review_response_fail(profile: JpaMtProfile) -> None:
    content = """@@@REVIEW_META
verdict: FAIL
issues_total: 2
issues_critical: 1
missing_inputs: 0
@@@
"""

    result = profile.process_review_response(content)

    assert result.status == WorkflowStatus.FAILED
    assert result.metadata.get("verdict") == "FAIL"


def test_process_review_response_captures_metadata(profile: JpaMtProfile) -> None:
    content = """@@@REVIEW_META
verdict: FAIL
issues_total: 5
issues_critical: 2
missing_inputs: 1
@@@
"""

    result = profile.process_review_response(content)

    assert result.status == WorkflowStatus.FAILED
    assert result.metadata["verdict"] == "FAIL"
    assert result.metadata["issues_total"] == 5
    assert result.metadata["issues_critical"] == 2
    assert result.metadata["missing_inputs"] == 1


def test_process_review_response_error_on_invalid_metadata(profile: JpaMtProfile) -> None:
    result = profile.process_review_response("nonsense")

    assert result.status == WorkflowStatus.ERROR
    assert result.error_message is not None


def test_process_review_response_error_on_empty(profile: JpaMtProfile) -> None:
    result = profile.process_review_response("")

    assert result.status == WorkflowStatus.ERROR
    assert result.error_message is not None


def test_process_revision_response_success(profile: JpaMtProfile, tmp_path: Path) -> None:
    content = """<<<FILE: Bar.java>>>
    public class Bar {}
    """

    result = profile.process_revision_response(
        content=content,
        session_dir=tmp_path,
        iteration=2,
    )

    assert result.status == WorkflowStatus.SUCCESS
    assert len(result.artifacts) == 1

    artifact = result.artifacts[0]
    assert artifact.phase == WorkflowPhase.GENERATED
    assert artifact.artifact_type == "code"
    assert artifact.file_path == "iteration-2/code/Bar.java"

    written = tmp_path / artifact.file_path
    assert written.exists()
    assert "public class Bar {}" in written.read_text(encoding="utf-8")


def test_process_revision_response_error_on_invalid_bundle(profile: JpaMtProfile, tmp_path: Path) -> None:
    result = profile.process_revision_response(
        content="bad",
        session_dir=tmp_path,
        iteration=2,
    )

    assert result.status == WorkflowStatus.ERROR
    assert result.error_message is not None


def test_process_revision_response_error_on_empty(profile: JpaMtProfile, tmp_path: Path) -> None:
    result = profile.process_revision_response(
        content="",
        session_dir=tmp_path,
        iteration=2,
    )

    assert result.status == WorkflowStatus.ERROR
    assert result.error_message is not None
