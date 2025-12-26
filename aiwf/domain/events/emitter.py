"""Workflow event emitter for dispatching events to observers."""

import logging
from collections import defaultdict

from aiwf.domain.events.event import WorkflowEvent
from aiwf.domain.events.event_types import WorkflowEventType
from aiwf.domain.events.observer import WorkflowObserver

logger = logging.getLogger(__name__)


class WorkflowEventEmitter:
    """Central event dispatcher for workflow events."""

    def __init__(self) -> None:
        self._observers: dict[WorkflowEventType, list[WorkflowObserver]] = defaultdict(
            list
        )
        self._global_observers: list[WorkflowObserver] = []

    def subscribe(
        self,
        observer: WorkflowObserver,
        event_types: list[WorkflowEventType] | None = None,
    ) -> None:
        """Subscribe to specific event types, or all events if None."""
        if event_types is None:
            self._global_observers.append(observer)
        else:
            for event_type in event_types:
                self._observers[event_type].append(observer)

    def unsubscribe(self, observer: WorkflowObserver) -> None:
        """Remove observer from all subscriptions."""
        if observer in self._global_observers:
            self._global_observers.remove(observer)
        for observers in self._observers.values():
            if observer in observers:
                observers.remove(observer)

    def emit(self, event: WorkflowEvent) -> None:
        """Dispatch event to all relevant observers."""
        for observer in self._global_observers:
            self._safe_notify(observer, event)
        for observer in self._observers.get(event.event_type, []):
            self._safe_notify(observer, event)

    def _safe_notify(self, observer: WorkflowObserver, event: WorkflowEvent) -> None:
        """Notify observer, catching and logging any exceptions."""
        try:
            observer.on_event(event)
        except Exception as e:
            logger.warning(f"Observer {observer} failed on {event.event_type}: {e}")
