"""Stderr event observer for CLI integration."""

import click

from aiwf.domain.events.event import WorkflowEvent


class StderrEventObserver:
    """Emits events as structured lines to stderr."""

    def on_event(self, event: WorkflowEvent) -> None:
        """Emit event as structured line to stderr."""
        parts = [f"[EVENT] {event.event_type.value}"]
        if event.phase:
            parts.append(f"phase={event.phase.name}")
        if event.iteration is not None:
            parts.append(f"iteration={event.iteration}")
        if event.artifact_path:
            parts.append(f"path={event.artifact_path}")
        click.echo(" ".join(parts), err=True)
