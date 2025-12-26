"""Tests for WorkflowEvent model."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from aiwf.domain.events.event import WorkflowEvent
from aiwf.domain.events.event_types import WorkflowEventType
from aiwf.domain.models.workflow_state import WorkflowPhase


class TestWorkflowEvent:
    """Tests for WorkflowEvent Pydantic model."""

    def test_create_minimal_event(self) -> None:
        """Event can be created with only required fields."""
        event = WorkflowEvent(
            event_type=WorkflowEventType.PHASE_ENTERED,
            session_id="sess_123",
            timestamp=datetime.now(timezone.utc),
        )
        assert event.event_type == WorkflowEventType.PHASE_ENTERED
        assert event.session_id == "sess_123"
        assert event.phase is None
        assert event.iteration is None
        assert event.artifact_path is None
        assert event.metadata == {}

    def test_create_full_event(self) -> None:
        """Event can be created with all fields."""
        ts = datetime.now(timezone.utc)
        event = WorkflowEvent(
            event_type=WorkflowEventType.ARTIFACT_CREATED,
            session_id="sess_456",
            timestamp=ts,
            phase=WorkflowPhase.GENERATING,
            iteration=2,
            artifact_path="iteration-2/code/Entity.java",
            metadata={"size": 1024},
        )
        assert event.event_type == WorkflowEventType.ARTIFACT_CREATED
        assert event.session_id == "sess_456"
        assert event.timestamp == ts
        assert event.phase == WorkflowPhase.GENERATING
        assert event.iteration == 2
        assert event.artifact_path == "iteration-2/code/Entity.java"
        assert event.metadata == {"size": 1024}

    def test_event_is_immutable(self) -> None:
        """Event should be frozen (immutable)."""
        event = WorkflowEvent(
            event_type=WorkflowEventType.PHASE_ENTERED,
            session_id="sess_123",
            timestamp=datetime.now(timezone.utc),
        )
        with pytest.raises(ValidationError):
            event.session_id = "different"  # type: ignore[misc]

    def test_event_serializes_to_dict(self) -> None:
        """Event can be serialized to dict."""
        ts = datetime(2024, 12, 25, 12, 0, 0, tzinfo=timezone.utc)
        event = WorkflowEvent(
            event_type=WorkflowEventType.PHASE_ENTERED,
            session_id="sess_123",
            timestamp=ts,
            phase=WorkflowPhase.PLANNED,
            iteration=1,
        )
        data = event.model_dump()
        assert data["event_type"] == WorkflowEventType.PHASE_ENTERED
        assert data["session_id"] == "sess_123"
        assert data["phase"] == WorkflowPhase.PLANNED
        assert data["iteration"] == 1
        assert data["artifact_path"] is None
        assert data["metadata"] == {}

    def test_event_serializes_to_json(self) -> None:
        """Event can be serialized to JSON."""
        ts = datetime(2024, 12, 25, 12, 0, 0, tzinfo=timezone.utc)
        event = WorkflowEvent(
            event_type=WorkflowEventType.WORKFLOW_COMPLETED,
            session_id="sess_789",
            timestamp=ts,
        )
        json_str = event.model_dump_json()
        assert "workflow_completed" in json_str
        assert "sess_789" in json_str

    def test_optional_fields_default_correctly(self) -> None:
        """Optional fields should have correct defaults."""
        event = WorkflowEvent(
            event_type=WorkflowEventType.APPROVAL_GRANTED,
            session_id="sess_abc",
            timestamp=datetime.now(timezone.utc),
        )
        assert event.phase is None
        assert event.iteration is None
        assert event.artifact_path is None
        assert event.metadata == {}
        # Metadata should be a new dict each time (not shared)
        event2 = WorkflowEvent(
            event_type=WorkflowEventType.APPROVAL_GRANTED,
            session_id="sess_def",
            timestamp=datetime.now(timezone.utc),
        )
        assert event.metadata is not event2.metadata
