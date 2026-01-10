# tests/unit/application/artifacts/test_artifact_service.py
"""Tests for ArtifactService - pre-transition approval handling."""

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aiwf.application.artifacts.artifact_service import ArtifactService
from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.workflow_state import (
    WorkflowPhase,
    WorkflowStage,
    WorkflowState,
    WorkflowStatus,
)
from aiwf.domain.models.write_plan import WriteOp, WritePlan


@pytest.fixture
def artifact_service() -> ArtifactService:
    """Create ArtifactService instance."""
    return ArtifactService()


@pytest.fixture
def base_state() -> WorkflowState:
    """Create base workflow state for testing."""
    return WorkflowState(
        session_id="test-session",
        profile="jpa-mt",
        phase=WorkflowPhase.PLAN,
        stage=WorkflowStage.RESPONSE,
        status=WorkflowStatus.IN_PROGRESS,
        current_iteration=1,
        standards_hash="abc123",
        ai_providers={"planner": "manual", "generator": "manual"},
        metadata={},
    )


@pytest.fixture
def session_with_plan_response(tmp_path: Path) -> Path:
    """Create session dir with planning-response.md."""
    session_dir = tmp_path / "sessions" / "test-session"
    iteration_dir = session_dir / "iteration-1"
    iteration_dir.mkdir(parents=True)

    response_file = iteration_dir / "planning-response.md"
    response_file.write_text("# Plan Content\nThis is the plan.", encoding="utf-8")

    return session_dir


@pytest.fixture
def session_with_generation_response(tmp_path: Path) -> Path:
    """Create session dir with generation-response.md."""
    session_dir = tmp_path / "sessions" / "test-session"
    iteration_dir = session_dir / "iteration-1"
    iteration_dir.mkdir(parents=True)

    response_file = iteration_dir / "generation-response.md"
    response_file.write_text("# Generated Code\n```java\nclass Foo {}\n```", encoding="utf-8")

    return session_dir


@pytest.fixture
def session_with_review_response(tmp_path: Path) -> Path:
    """Create session dir with review-response.md."""
    session_dir = tmp_path / "sessions" / "test-session"
    iteration_dir = session_dir / "iteration-1"
    iteration_dir.mkdir(parents=True)

    response_file = iteration_dir / "review-response.md"
    response_file.write_text("# Review\nLooks good.", encoding="utf-8")

    return session_dir


@pytest.fixture
def session_with_revision_response(tmp_path: Path) -> Path:
    """Create session dir with revision-response.md."""
    session_dir = tmp_path / "sessions" / "test-session"
    iteration_dir = session_dir / "iteration-1"
    iteration_dir.mkdir(parents=True)

    response_file = iteration_dir / "revision-response.md"
    response_file.write_text("# Revised Code\n```java\nclass Bar {}\n```", encoding="utf-8")

    return session_dir


@pytest.fixture
def mock_add_message() -> MagicMock:
    """Create mock add_message callback."""
    return MagicMock()


class TestApprovePlanResponse:
    """Tests for _approve_plan_response."""

    def test_hashes_file_and_sets_approved(
        self,
        artifact_service: ArtifactService,
        base_state: WorkflowState,
        session_with_plan_response: Path,
        mock_add_message: MagicMock,
    ):
        """Verify plan response is hashed and plan_approved is set."""
        base_state.phase = WorkflowPhase.PLAN
        base_state.stage = WorkflowStage.RESPONSE

        artifact_service.handle_pre_transition_approval(
            base_state, session_with_plan_response, mock_add_message
        )

        # Verify hash computed (read file bytes to match implementation)
        response_file = session_with_plan_response / "iteration-1" / "planning-response.md"
        expected_hash = hashlib.sha256(response_file.read_bytes()).hexdigest()
        assert base_state.plan_hash == expected_hash

        # Verify approved flag set
        assert base_state.plan_approved is True

        # Verify message added
        mock_add_message.assert_called_once_with(base_state, "Plan approved")

    def test_file_not_found_raises_value_error(
        self,
        artifact_service: ArtifactService,
        base_state: WorkflowState,
        tmp_path: Path,
        mock_add_message: MagicMock,
    ):
        """Verify ValueError raised when planning-response.md missing."""
        base_state.phase = WorkflowPhase.PLAN
        base_state.stage = WorkflowStage.RESPONSE

        session_dir = tmp_path / "sessions" / "test-session"
        session_dir.mkdir(parents=True)

        with pytest.raises(ValueError, match="planning-response.md not found"):
            artifact_service.handle_pre_transition_approval(
                base_state, session_dir, mock_add_message
            )


class TestApproveGenerateResponse:
    """Tests for _approve_generate_response."""

    def test_extracts_code_and_creates_artifacts(
        self,
        artifact_service: ArtifactService,
        base_state: WorkflowState,
        session_with_generation_response: Path,
        mock_add_message: MagicMock,
    ):
        """Verify code extraction creates artifacts."""
        base_state.phase = WorkflowPhase.GENERATE
        base_state.stage = WorkflowStage.RESPONSE

        # Mock profile to return write plan with code files
        mock_profile = MagicMock()
        mock_profile.process_generation_response.return_value = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[
                    WriteOp(path="Foo.java", content="class Foo {}"),
                    WriteOp(path="Bar.java", content="class Bar {}"),
                ]
            ),
        )

        with patch("aiwf.application.artifacts.artifact_service.ProfileFactory") as mock_factory:
            mock_factory.create.return_value = mock_profile

            artifact_service.handle_pre_transition_approval(
                base_state, session_with_generation_response, mock_add_message
            )

        # Verify artifacts created
        assert len(base_state.artifacts) == 2
        assert base_state.artifacts[0].path == "iteration-1/code/Foo.java"
        assert base_state.artifacts[0].phase == WorkflowPhase.GENERATE
        assert base_state.artifacts[1].path == "iteration-1/code/Bar.java"

        # Verify files written
        code_dir = session_with_generation_response / "iteration-1" / "code"
        assert (code_dir / "Foo.java").read_text() == "class Foo {}"
        assert (code_dir / "Bar.java").read_text() == "class Bar {}"

        # Verify message
        mock_add_message.assert_called_once_with(base_state, "Extracted 2 code file(s)")

    def test_no_code_extracted_message(
        self,
        artifact_service: ArtifactService,
        base_state: WorkflowState,
        session_with_generation_response: Path,
        mock_add_message: MagicMock,
    ):
        """Verify message when no code extracted."""
        base_state.phase = WorkflowPhase.GENERATE
        base_state.stage = WorkflowStage.RESPONSE

        # Mock profile to return no write plan
        mock_profile = MagicMock()
        mock_profile.process_generation_response.return_value = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=None,
        )

        with patch("aiwf.application.artifacts.artifact_service.ProfileFactory") as mock_factory:
            mock_factory.create.return_value = mock_profile

            artifact_service.handle_pre_transition_approval(
                base_state, session_with_generation_response, mock_add_message
            )

        # Verify no artifacts
        assert len(base_state.artifacts) == 0

        # Verify message
        mock_add_message.assert_called_once_with(
            base_state, "Generation approved (no code extracted)"
        )

    def test_file_not_found_raises_value_error(
        self,
        artifact_service: ArtifactService,
        base_state: WorkflowState,
        tmp_path: Path,
        mock_add_message: MagicMock,
    ):
        """Verify ValueError raised when generation-response.md missing."""
        base_state.phase = WorkflowPhase.GENERATE
        base_state.stage = WorkflowStage.RESPONSE

        session_dir = tmp_path / "sessions" / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)

        with pytest.raises(ValueError, match="generation-response.md not found"):
            artifact_service.handle_pre_transition_approval(
                base_state, session_dir, mock_add_message
            )


class TestApproveReviewResponse:
    """Tests for _approve_review_response."""

    def test_hashes_file_and_sets_approved(
        self,
        artifact_service: ArtifactService,
        base_state: WorkflowState,
        session_with_review_response: Path,
        mock_add_message: MagicMock,
    ):
        """Verify review response is hashed and review_approved is set."""
        base_state.phase = WorkflowPhase.REVIEW
        base_state.stage = WorkflowStage.RESPONSE

        artifact_service.handle_pre_transition_approval(
            base_state, session_with_review_response, mock_add_message
        )

        # Verify hash computed (read file bytes to match implementation)
        response_file = session_with_review_response / "iteration-1" / "review-response.md"
        expected_hash = hashlib.sha256(response_file.read_bytes()).hexdigest()
        assert base_state.review_hash == expected_hash

        # Verify approved flag set
        assert base_state.review_approved is True

        # Verify message added
        mock_add_message.assert_called_once_with(base_state, "Review approved")

    def test_file_not_found_raises_value_error(
        self,
        artifact_service: ArtifactService,
        base_state: WorkflowState,
        tmp_path: Path,
        mock_add_message: MagicMock,
    ):
        """Verify ValueError raised when review-response.md missing."""
        base_state.phase = WorkflowPhase.REVIEW
        base_state.stage = WorkflowStage.RESPONSE

        session_dir = tmp_path / "sessions" / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)

        with pytest.raises(ValueError, match="review-response.md not found"):
            artifact_service.handle_pre_transition_approval(
                base_state, session_dir, mock_add_message
            )


class TestApproveReviseResponse:
    """Tests for _approve_revise_response."""

    def test_extracts_revised_code_and_creates_artifacts(
        self,
        artifact_service: ArtifactService,
        base_state: WorkflowState,
        session_with_revision_response: Path,
        mock_add_message: MagicMock,
    ):
        """Verify revised code extraction creates artifacts."""
        base_state.phase = WorkflowPhase.REVISE
        base_state.stage = WorkflowStage.RESPONSE

        # Mock profile to return write plan with revised code
        mock_profile = MagicMock()
        mock_profile.process_revision_response.return_value = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[WriteOp(path="Revised.java", content="class Revised {}")]
            ),
        )

        with patch("aiwf.application.artifacts.artifact_service.ProfileFactory") as mock_factory:
            mock_factory.create.return_value = mock_profile

            artifact_service.handle_pre_transition_approval(
                base_state, session_with_revision_response, mock_add_message
            )

        # Verify artifact created with REVISE phase
        assert len(base_state.artifacts) == 1
        assert base_state.artifacts[0].path == "iteration-1/code/Revised.java"
        assert base_state.artifacts[0].phase == WorkflowPhase.REVISE

        # Verify file written
        code_dir = session_with_revision_response / "iteration-1" / "code"
        assert (code_dir / "Revised.java").read_text() == "class Revised {}"

        # Verify message
        mock_add_message.assert_called_once_with(
            base_state, "Extracted 1 revised code file(s)"
        )

    def test_file_not_found_raises_value_error(
        self,
        artifact_service: ArtifactService,
        base_state: WorkflowState,
        tmp_path: Path,
        mock_add_message: MagicMock,
    ):
        """Verify ValueError raised when revision-response.md missing."""
        base_state.phase = WorkflowPhase.REVISE
        base_state.stage = WorkflowStage.RESPONSE

        session_dir = tmp_path / "sessions" / "test-session"
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True)

        with pytest.raises(ValueError, match="revision-response.md not found"):
            artifact_service.handle_pre_transition_approval(
                base_state, session_dir, mock_add_message
            )


class TestCopyPlanToSession:
    """Tests for copy_plan_to_session."""

    def test_copies_plan_to_session_level(
        self,
        artifact_service: ArtifactService,
        base_state: WorkflowState,
        session_with_plan_response: Path,
        mock_add_message: MagicMock,
    ):
        """Verify planning-response.md copied to session-level plan.md."""
        artifact_service.copy_plan_to_session(
            base_state, session_with_plan_response, mock_add_message
        )

        # Verify plan.md exists at session level
        plan_file = session_with_plan_response / "plan.md"
        assert plan_file.exists()
        assert plan_file.read_text() == "# Plan Content\nThis is the plan."

        # Verify message
        mock_add_message.assert_called_once_with(base_state, "Copied plan to session")

    def test_file_not_found_raises_value_error(
        self,
        artifact_service: ArtifactService,
        base_state: WorkflowState,
        tmp_path: Path,
        mock_add_message: MagicMock,
    ):
        """Verify ValueError raised when planning-response.md missing."""
        session_dir = tmp_path / "sessions" / "test-session"
        session_dir.mkdir(parents=True)

        with pytest.raises(ValueError, match="Cannot copy plan"):
            artifact_service.copy_plan_to_session(
                base_state, session_dir, mock_add_message
            )


class TestHandlePreTransitionDispatch:
    """Tests for handle_pre_transition_approval dispatch logic."""

    def test_dispatches_to_correct_handler(
        self,
        artifact_service: ArtifactService,
        base_state: WorkflowState,
        session_with_plan_response: Path,
        mock_add_message: MagicMock,
    ):
        """Verify correct handler called based on phase/stage."""
        # Test PLAN/RESPONSE dispatches to _approve_plan_response
        base_state.phase = WorkflowPhase.PLAN
        base_state.stage = WorkflowStage.RESPONSE

        artifact_service.handle_pre_transition_approval(
            base_state, session_with_plan_response, mock_add_message
        )

        # Handler was called (plan_approved set proves it)
        assert base_state.plan_approved is True

    def test_no_handler_for_prompt_stage(
        self,
        artifact_service: ArtifactService,
        base_state: WorkflowState,
        tmp_path: Path,
        mock_add_message: MagicMock,
    ):
        """Verify no-op when no handler for (phase, stage) key."""
        base_state.phase = WorkflowPhase.PLAN
        base_state.stage = WorkflowStage.PROMPT

        session_dir = tmp_path / "sessions" / "test-session"
        session_dir.mkdir(parents=True)

        # Should not raise, should be no-op
        artifact_service.handle_pre_transition_approval(
            base_state, session_dir, mock_add_message
        )

        # No message added (no handler called)
        mock_add_message.assert_not_called()

    def test_no_handler_for_init_phase(
        self,
        artifact_service: ArtifactService,
        base_state: WorkflowState,
        tmp_path: Path,
        mock_add_message: MagicMock,
    ):
        """Verify no-op for phases without handlers."""
        base_state.phase = WorkflowPhase.INIT
        base_state.stage = WorkflowStage.RESPONSE

        session_dir = tmp_path / "sessions" / "test-session"
        session_dir.mkdir(parents=True)

        # Should not raise
        artifact_service.handle_pre_transition_approval(
            base_state, session_dir, mock_add_message
        )

        mock_add_message.assert_not_called()
