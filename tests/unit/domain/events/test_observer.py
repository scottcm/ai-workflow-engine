"""Tests for WorkflowObserver protocol."""

from datetime import datetime, timezone

from aiwf.domain.events.event import WorkflowEvent
from aiwf.domain.events.event_types import WorkflowEventType
from aiwf.domain.events.observer import WorkflowObserver


class TestWorkflowObserver:
    """Tests for WorkflowObserver protocol."""

    def test_class_can_implement_protocol(self) -> None:
        """A class with on_event method satisfies the protocol."""

        class MyObserver:
            def __init__(self) -> None:
                self.events: list[WorkflowEvent] = []

            def on_event(self, event: WorkflowEvent) -> None:
                self.events.append(event)

        observer = MyObserver()
        event = WorkflowEvent(
            event_type=WorkflowEventType.PHASE_ENTERED,
            session_id="sess_123",
            timestamp=datetime.now(timezone.utc),
        )
        observer.on_event(event)
        assert len(observer.events) == 1
        assert observer.events[0] is event

        # Verify it satisfies the protocol (structural typing)
        def accepts_observer(obs: WorkflowObserver) -> None:
            pass

        accepts_observer(observer)  # Should not raise

    def test_lambda_like_callable_with_on_event(self) -> None:
        """An object with on_event callable satisfies the protocol."""
        events_received: list[WorkflowEvent] = []

        class CallableObserver:
            def on_event(self, event: WorkflowEvent) -> None:
                events_received.append(event)

        observer = CallableObserver()
        event = WorkflowEvent(
            event_type=WorkflowEventType.WORKFLOW_COMPLETED,
            session_id="sess_456",
            timestamp=datetime.now(timezone.utc),
        )
        observer.on_event(event)
        assert len(events_received) == 1

    def test_observer_receives_correct_event_data(self) -> None:
        """Observer receives event with all its data intact."""
        received_event: WorkflowEvent | None = None

        class CapturingObserver:
            def on_event(self, event: WorkflowEvent) -> None:
                nonlocal received_event
                received_event = event

        observer = CapturingObserver()
        ts = datetime.now(timezone.utc)
        original_event = WorkflowEvent(
            event_type=WorkflowEventType.ARTIFACT_CREATED,
            session_id="sess_789",
            timestamp=ts,
            artifact_path="path/to/file.java",
            metadata={"key": "value"},
        )
        observer.on_event(original_event)

        assert received_event is not None
        assert received_event.event_type == WorkflowEventType.ARTIFACT_CREATED
        assert received_event.session_id == "sess_789"
        assert received_event.artifact_path == "path/to/file.java"
        assert received_event.metadata == {"key": "value"}
