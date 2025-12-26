"""Workflow event types for observer pattern notifications."""

from enum import Enum


class WorkflowEventType(str, Enum):
    """Typed workflow events for IDE integration notifications."""

    # Phase lifecycle
    PHASE_ENTERED = "phase_entered"

    # Artifacts
    ARTIFACT_CREATED = "artifact_created"
    ARTIFACT_APPROVED = "artifact_approved"

    # Approval gates
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_GRANTED = "approval_granted"

    # Workflow lifecycle
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"

    # Iteration
    ITERATION_STARTED = "iteration_started"
