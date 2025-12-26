"""Workflow observer protocol."""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from aiwf.domain.events.event import WorkflowEvent


class WorkflowObserver(Protocol):
    """Protocol for workflow event observers."""

    def on_event(self, event: "WorkflowEvent") -> None:
        """Handle a workflow event. Must not throw or block."""
        ...
