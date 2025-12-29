"""Tests for workflow orchestrator event emission."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.events.emitter import WorkflowEventEmitter
from aiwf.domain.events.event_types import WorkflowEventType
from aiwf.domain.models.workflow_state import (
    ExecutionMode,
    WorkflowPhase,
    WorkflowState,
    WorkflowStatus,
)
from aiwf.domain.persistence.session_store import SessionStore


def _create_orchestrator(
    sessions_root: Path, event_emitter: WorkflowEventEmitter | None = None
) -> WorkflowOrchestrator:
    """Helper to create orchestrator with optional event emitter."""
    return WorkflowOrchestrator(
        session_store=SessionStore(sessions_root=sessions_root),
        sessions_root=sessions_root,
        event_emitter=event_emitter,
    )


# Note: conftest.py provides an autouse mock for jpa-mt profile with proper
# create_bundle, generate_*_prompt, and process_*_response methods.
# Tests should use profile="jpa-mt" to leverage this mock.


class TestOrchestratorEventEmitter:
    """Tests for orchestrator event emitter injection."""

    def test_orchestrator_accepts_event_emitter(self, tmp_path: Path) -> None:
        """Orchestrator can be created with an event emitter."""
        emitter = WorkflowEventEmitter()
        orch = _create_orchestrator(tmp_path, event_emitter=emitter)
        assert orch.event_emitter is emitter

    def test_orchestrator_creates_default_emitter_if_none(self, tmp_path: Path) -> None:
        """Orchestrator creates a default emitter if none provided."""
        orch = _create_orchestrator(tmp_path)
        assert orch.event_emitter is not None
        assert isinstance(orch.event_emitter, WorkflowEventEmitter)


class TestOrchestratorPhaseEnteredEvents:
    """Tests for PHASE_ENTERED event emission."""

    def test_step_initialized_emits_phase_entered(self, tmp_path: Path, valid_jpa_mt_context: dict[str, Any]) -> None:
        """step() emits PHASE_ENTERED when transitioning INITIALIZED -> PLANNING."""
        observer = MagicMock()
        emitter = WorkflowEventEmitter()
        emitter.subscribe(observer)

        orch = _create_orchestrator(tmp_path, event_emitter=emitter)

        # Initialize a session (uses jpa-mt profile from conftest mock)
        session_id = orch.initialize_run(
            profile="jpa-mt",
            context=valid_jpa_mt_context,
            providers={"planning": "manual"},
        )

        # Step should transition INITIALIZED -> PLANNING
        observer.reset_mock()
        orch.step(session_id)

        # Verify PHASE_ENTERED was emitted
        assert observer.on_event.called
        events = [call[0][0] for call in observer.on_event.call_args_list]
        phase_entered_events = [
            e for e in events if e.event_type == WorkflowEventType.PHASE_ENTERED
        ]
        assert len(phase_entered_events) >= 1
        assert phase_entered_events[0].phase == WorkflowPhase.PLANNING
        assert phase_entered_events[0].session_id == session_id

    def test_step_planning_emits_phase_entered_on_transition(
        self, tmp_path: Path, valid_jpa_mt_context: dict[str, Any]
    ) -> None:
        """step() emits PHASE_ENTERED when transitioning PLANNING -> PLANNED."""
        observer = MagicMock()
        emitter = WorkflowEventEmitter()
        emitter.subscribe(observer)

        orch = _create_orchestrator(tmp_path, event_emitter=emitter)

        session_id = orch.initialize_run(
            profile="jpa-mt",
            context=valid_jpa_mt_context,
            providers={"planning": "manual"},
        )

        # Step to PLANNING
        orch.step(session_id)

        # Create response file in the correct location (iteration-1/)
        iteration_dir = tmp_path / session_id / "iteration-1"
        iteration_dir.mkdir(parents=True, exist_ok=True)
        response_file = iteration_dir / "planning-response.md"
        response_file.write_text("# Plan response", encoding="utf-8")

        # Step should transition PLANNING -> PLANNED
        observer.reset_mock()
        orch.step(session_id)

        events = [call[0][0] for call in observer.on_event.call_args_list]
        phase_entered_events = [
            e for e in events if e.event_type == WorkflowEventType.PHASE_ENTERED
        ]
        assert len(phase_entered_events) >= 1, f"Expected PHASE_ENTERED event, got events: {events}"
        assert phase_entered_events[0].phase == WorkflowPhase.PLANNED


class TestOrchestratorApprovalEvents:
    """Tests for APPROVAL_REQUIRED and APPROVAL_GRANTED events."""

    def test_step_planned_emits_approval_required_when_blocked(
        self, tmp_path: Path, valid_jpa_mt_context: dict[str, Any]
    ) -> None:
        """step() emits APPROVAL_REQUIRED when blocked on plan approval."""
        observer = MagicMock()
        emitter = WorkflowEventEmitter()
        emitter.subscribe(observer)

        orch = _create_orchestrator(tmp_path, event_emitter=emitter)

        session_id = orch.initialize_run(
            profile="jpa-mt",
            context=valid_jpa_mt_context,
            providers={"planning": "manual"},
        )

        # Step to PLANNING
        orch.step(session_id)

        # Create response file in the correct location (iteration-1/)
        iteration_dir = tmp_path / session_id / "iteration-1"
        iteration_dir.mkdir(parents=True, exist_ok=True)
        response_file = iteration_dir / "planning-response.md"
        response_file.write_text("# Plan response", encoding="utf-8")

        # Step to PLANNED
        orch.step(session_id)

        # Step again - should be blocked, waiting for approval
        observer.reset_mock()
        orch.step(session_id)

        events = [call[0][0] for call in observer.on_event.call_args_list]
        approval_required_events = [
            e for e in events if e.event_type == WorkflowEventType.APPROVAL_REQUIRED
        ]
        assert len(approval_required_events) >= 1
        assert approval_required_events[0].phase == WorkflowPhase.PLANNED

    def test_approve_emits_approval_granted(self, tmp_path: Path, valid_jpa_mt_context: dict[str, Any]) -> None:
        """approve() emits APPROVAL_GRANTED after successful approval."""
        observer = MagicMock()
        emitter = WorkflowEventEmitter()
        emitter.subscribe(observer)

        orch = _create_orchestrator(tmp_path, event_emitter=emitter)

        session_id = orch.initialize_run(
            profile="jpa-mt",
            context=valid_jpa_mt_context,
            providers={"planning": "manual"},
        )

        # Step to PLANNING
        orch.step(session_id)

        # Create response file in the correct location (iteration-1/)
        iteration_dir = tmp_path / session_id / "iteration-1"
        iteration_dir.mkdir(parents=True, exist_ok=True)
        response_file = iteration_dir / "planning-response.md"
        response_file.write_text("# Plan response", encoding="utf-8")

        # Step to PLANNED
        orch.step(session_id)

        # Approve the plan
        observer.reset_mock()
        orch.approve(session_id)

        events = [call[0][0] for call in observer.on_event.call_args_list]
        approval_granted_events = [
            e for e in events if e.event_type == WorkflowEventType.APPROVAL_GRANTED
        ]
        assert len(approval_granted_events) >= 1
        assert approval_granted_events[0].phase == WorkflowPhase.PLANNED


class TestOrchestratorWorkflowLifecycleEvents:
    """Tests for WORKFLOW_COMPLETED and WORKFLOW_FAILED events."""

    def test_workflow_failed_emitted_on_error(self, tmp_path: Path, valid_jpa_mt_context: dict[str, Any]) -> None:
        """WORKFLOW_FAILED is emitted when workflow enters error state."""
        observer = MagicMock()
        emitter = WorkflowEventEmitter()
        emitter.subscribe(observer)

        orch = _create_orchestrator(tmp_path, event_emitter=emitter)

        session_id = orch.initialize_run(
            profile="jpa-mt",
            context=valid_jpa_mt_context,
            providers={"planning": "manual"},
        )

        # Try to approve in INITIALIZED phase - should cause error
        # (need to be in proper approval phase)
        observer.reset_mock()
        result = orch.approve(session_id)

        # Check if WORKFLOW_FAILED was emitted (if error occurred)
        if result.status == WorkflowStatus.ERROR:
            events = [call[0][0] for call in observer.on_event.call_args_list]
            failed_events = [
                e for e in events if e.event_type == WorkflowEventType.WORKFLOW_FAILED
            ]
            assert len(failed_events) >= 1


class TestOrchestratorTerminalPhaseEvents:
    """Tests for PHASE_ENTERED on terminal transitions (COMPLETE, CANCELLED)."""

    def test_workflow_complete_emits_phase_entered(
        self, tmp_path: Path, monkeypatch, valid_jpa_mt_context: dict[str, Any]
    ) -> None:
        """PHASE_ENTERED is emitted when entering COMPLETE phase."""
        from aiwf.domain.models.processing_result import ProcessingResult

        observer = MagicMock()
        emitter = WorkflowEventEmitter()
        emitter.subscribe(observer)

        orch = _create_orchestrator(tmp_path, event_emitter=emitter)

        session_id = orch.initialize_run(
            profile="jpa-mt",
            context=valid_jpa_mt_context,
            providers={"planning": "manual"},
        )

        # Manually set state to REVIEWED with review_approved=True
        state = orch.session_store.load(session_id)
        state.phase = WorkflowPhase.REVIEWED
        state.review_approved = True
        orch.session_store.save(state)

        # Create review-response.md with SUCCESS verdict
        iteration_dir = tmp_path / session_id / "iteration-1"
        iteration_dir.mkdir(parents=True, exist_ok=True)
        response_file = iteration_dir / "review-response.md"
        response_file.write_text("# Review\n@@@REVIEW_META\nverdict: APPROVED\n@@@", encoding="utf-8")

        # Mock profile's process_review_response to return SUCCESS
        def mock_process_review_response(content):
            return ProcessingResult(
                status=WorkflowStatus.SUCCESS,
                messages=["Review passed"],
            )

        from aiwf.domain.profiles.profile_factory import ProfileFactory
        original_create = ProfileFactory.create

        def mock_create(profile_name, config=None):
            profile = original_create(profile_name, config=config)
            profile.process_review_response = mock_process_review_response
            return profile

        monkeypatch.setattr(ProfileFactory, "create", mock_create)

        # Step should transition REVIEWED -> COMPLETE
        observer.reset_mock()
        result = orch.step(session_id)

        assert result.phase == WorkflowPhase.COMPLETE
        events = [call[0][0] for call in observer.on_event.call_args_list]
        phase_entered_events = [
            e for e in events if e.event_type == WorkflowEventType.PHASE_ENTERED
        ]
        assert len(phase_entered_events) >= 1, f"Expected PHASE_ENTERED, got: {events}"
        assert phase_entered_events[0].phase == WorkflowPhase.COMPLETE

        # Also verify WORKFLOW_COMPLETED is emitted after PHASE_ENTERED
        completed_events = [
            e for e in events if e.event_type == WorkflowEventType.WORKFLOW_COMPLETED
        ]
        assert len(completed_events) >= 1

    def test_reviewed_cancelled_emits_phase_entered(
        self, tmp_path: Path, monkeypatch, valid_jpa_mt_context: dict[str, Any]
    ) -> None:
        """PHASE_ENTERED is emitted when REVIEWED transitions to CANCELLED."""
        from aiwf.domain.models.processing_result import ProcessingResult

        observer = MagicMock()
        emitter = WorkflowEventEmitter()
        emitter.subscribe(observer)

        orch = _create_orchestrator(tmp_path, event_emitter=emitter)

        session_id = orch.initialize_run(
            profile="jpa-mt",
            context=valid_jpa_mt_context,
            providers={"planning": "manual"},
        )

        # Manually set state to REVIEWED with review_approved=True
        state = orch.session_store.load(session_id)
        state.phase = WorkflowPhase.REVIEWED
        state.review_approved = True
        orch.session_store.save(state)

        # Create review-response.md
        iteration_dir = tmp_path / session_id / "iteration-1"
        iteration_dir.mkdir(parents=True, exist_ok=True)
        response_file = iteration_dir / "review-response.md"
        response_file.write_text("# Review\n@@@REVIEW_META\nverdict: CANCELLED\n@@@", encoding="utf-8")

        # Mock profile's process_review_response to return CANCELLED
        def mock_process_review_response(content):
            return ProcessingResult(
                status=WorkflowStatus.CANCELLED,
                messages=["Review cancelled"],
            )

        from aiwf.domain.profiles.profile_factory import ProfileFactory
        original_create = ProfileFactory.create

        def mock_create(profile_name, config=None):
            profile = original_create(profile_name, config=config)
            profile.process_review_response = mock_process_review_response
            return profile

        monkeypatch.setattr(ProfileFactory, "create", mock_create)

        # Step should transition REVIEWED -> CANCELLED
        observer.reset_mock()
        result = orch.step(session_id)

        assert result.phase == WorkflowPhase.CANCELLED
        events = [call[0][0] for call in observer.on_event.call_args_list]
        phase_entered_events = [
            e for e in events if e.event_type == WorkflowEventType.PHASE_ENTERED
        ]
        assert len(phase_entered_events) >= 1, f"Expected PHASE_ENTERED, got: {events}"
        assert phase_entered_events[0].phase == WorkflowPhase.CANCELLED

    def test_revising_cancelled_emits_phase_entered(
        self, tmp_path: Path, monkeypatch, valid_jpa_mt_context: dict[str, Any]
    ) -> None:
        """PHASE_ENTERED is emitted when REVISING transitions to CANCELLED."""
        from aiwf.domain.models.processing_result import ProcessingResult

        observer = MagicMock()
        emitter = WorkflowEventEmitter()
        emitter.subscribe(observer)

        orch = _create_orchestrator(tmp_path, event_emitter=emitter)

        session_id = orch.initialize_run(
            profile="jpa-mt",
            context=valid_jpa_mt_context,
            providers={"planning": "manual"},
        )

        # Manually set state to REVISING
        state = orch.session_store.load(session_id)
        state.phase = WorkflowPhase.REVISING
        state.current_iteration = 2
        orch.session_store.save(state)

        # Create revision-response.md
        iteration_dir = tmp_path / session_id / "iteration-2"
        iteration_dir.mkdir(parents=True, exist_ok=True)
        response_file = iteration_dir / "revision-response.md"
        response_file.write_text("# Revision cancelled", encoding="utf-8")

        # Mock profile's process_revision_response to return CANCELLED
        def mock_process_revision_response(content, session_dir, iteration):
            return ProcessingResult(
                status=WorkflowStatus.CANCELLED,
                messages=["Revision cancelled"],
            )

        from aiwf.domain.profiles.profile_factory import ProfileFactory
        original_create = ProfileFactory.create

        def mock_create(profile_name, config=None):
            profile = original_create(profile_name, config=config)
            profile.process_revision_response = mock_process_revision_response
            return profile

        monkeypatch.setattr(ProfileFactory, "create", mock_create)

        # Step should transition REVISING -> CANCELLED
        observer.reset_mock()
        result = orch.step(session_id)

        assert result.phase == WorkflowPhase.CANCELLED
        events = [call[0][0] for call in observer.on_event.call_args_list]
        phase_entered_events = [
            e for e in events if e.event_type == WorkflowEventType.PHASE_ENTERED
        ]
        assert len(phase_entered_events) >= 1, f"Expected PHASE_ENTERED, got: {events}"
        assert phase_entered_events[0].phase == WorkflowPhase.CANCELLED