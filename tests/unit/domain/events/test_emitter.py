"""Tests for WorkflowEventEmitter."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from aiwf.domain.events.emitter import WorkflowEventEmitter
from aiwf.domain.events.event import WorkflowEvent
from aiwf.domain.events.event_types import WorkflowEventType


def _make_event(event_type: WorkflowEventType) -> WorkflowEvent:
    """Helper to create a test event."""
    return WorkflowEvent(
        event_type=event_type,
        session_id="sess_test",
        timestamp=datetime.now(timezone.utc),
    )


class TestWorkflowEventEmitter:
    """Tests for WorkflowEventEmitter."""

    def test_subscribe_global_receives_all_events(self) -> None:
        """Global subscriber receives events of all types."""
        emitter = WorkflowEventEmitter()
        observer = MagicMock()
        emitter.subscribe(observer)

        event1 = _make_event(WorkflowEventType.PHASE_ENTERED)
        event2 = _make_event(WorkflowEventType.ARTIFACT_CREATED)
        event3 = _make_event(WorkflowEventType.WORKFLOW_COMPLETED)

        emitter.emit(event1)
        emitter.emit(event2)
        emitter.emit(event3)

        assert observer.on_event.call_count == 3
        calls = [call[0][0] for call in observer.on_event.call_args_list]
        assert calls == [event1, event2, event3]

    def test_subscribe_specific_receives_only_matching_events(self) -> None:
        """Subscriber to specific types only receives those events."""
        emitter = WorkflowEventEmitter()
        observer = MagicMock()
        emitter.subscribe(
            observer,
            event_types=[
                WorkflowEventType.PHASE_ENTERED,
                WorkflowEventType.WORKFLOW_COMPLETED,
            ],
        )

        event1 = _make_event(WorkflowEventType.PHASE_ENTERED)
        event2 = _make_event(WorkflowEventType.ARTIFACT_CREATED)  # Not subscribed
        event3 = _make_event(WorkflowEventType.WORKFLOW_COMPLETED)

        emitter.emit(event1)
        emitter.emit(event2)
        emitter.emit(event3)

        assert observer.on_event.call_count == 2
        calls = [call[0][0] for call in observer.on_event.call_args_list]
        assert calls == [event1, event3]

    def test_unsubscribe_removes_global_observer(self) -> None:
        """Unsubscribe removes observer from global list."""
        emitter = WorkflowEventEmitter()
        observer = MagicMock()
        emitter.subscribe(observer)

        event1 = _make_event(WorkflowEventType.PHASE_ENTERED)
        emitter.emit(event1)
        assert observer.on_event.call_count == 1

        emitter.unsubscribe(observer)

        event2 = _make_event(WorkflowEventType.PHASE_ENTERED)
        emitter.emit(event2)
        assert observer.on_event.call_count == 1  # Still 1, not called again

    def test_unsubscribe_removes_specific_observer(self) -> None:
        """Unsubscribe removes observer from specific type lists."""
        emitter = WorkflowEventEmitter()
        observer = MagicMock()
        emitter.subscribe(
            observer, event_types=[WorkflowEventType.PHASE_ENTERED]
        )

        event1 = _make_event(WorkflowEventType.PHASE_ENTERED)
        emitter.emit(event1)
        assert observer.on_event.call_count == 1

        emitter.unsubscribe(observer)

        event2 = _make_event(WorkflowEventType.PHASE_ENTERED)
        emitter.emit(event2)
        assert observer.on_event.call_count == 1  # Still 1

    def test_emit_continues_if_observer_raises(self) -> None:
        """Emit continues to other observers even if one raises."""
        emitter = WorkflowEventEmitter()

        failing_observer = MagicMock()
        failing_observer.on_event.side_effect = ValueError("Test error")

        successful_observer = MagicMock()

        emitter.subscribe(failing_observer)
        emitter.subscribe(successful_observer)

        event = _make_event(WorkflowEventType.PHASE_ENTERED)
        emitter.emit(event)  # Should not raise

        failing_observer.on_event.assert_called_once_with(event)
        successful_observer.on_event.assert_called_once_with(event)

    def test_emit_with_no_observers_succeeds(self) -> None:
        """Emit with no observers does not raise."""
        emitter = WorkflowEventEmitter()
        event = _make_event(WorkflowEventType.PHASE_ENTERED)
        emitter.emit(event)  # Should not raise

    def test_multiple_observers_all_notified(self) -> None:
        """Multiple observers all receive the same event."""
        emitter = WorkflowEventEmitter()
        observer1 = MagicMock()
        observer2 = MagicMock()
        observer3 = MagicMock()

        emitter.subscribe(observer1)
        emitter.subscribe(observer2)
        emitter.subscribe(observer3)

        event = _make_event(WorkflowEventType.APPROVAL_GRANTED)
        emitter.emit(event)

        observer1.on_event.assert_called_once_with(event)
        observer2.on_event.assert_called_once_with(event)
        observer3.on_event.assert_called_once_with(event)

    def test_global_and_specific_observers_both_notified(self) -> None:
        """Both global and type-specific observers receive matching events."""
        emitter = WorkflowEventEmitter()
        global_observer = MagicMock()
        specific_observer = MagicMock()

        emitter.subscribe(global_observer)
        emitter.subscribe(
            specific_observer, event_types=[WorkflowEventType.PHASE_ENTERED]
        )

        event = _make_event(WorkflowEventType.PHASE_ENTERED)
        emitter.emit(event)

        global_observer.on_event.assert_called_once_with(event)
        specific_observer.on_event.assert_called_once_with(event)

    def test_unsubscribe_nonexistent_observer_is_safe(self) -> None:
        """Unsubscribing an observer that was never subscribed is safe."""
        emitter = WorkflowEventEmitter()
        observer = MagicMock()
        emitter.unsubscribe(observer)  # Should not raise
