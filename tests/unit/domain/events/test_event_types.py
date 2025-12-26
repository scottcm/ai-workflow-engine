"""Tests for WorkflowEventType enum."""

import pytest

from aiwf.domain.events.event_types import WorkflowEventType


class TestWorkflowEventType:
    """Tests for WorkflowEventType enum."""

    def test_event_type_values_are_strings(self) -> None:
        """All event type values should be strings."""
        for event_type in WorkflowEventType:
            assert isinstance(event_type.value, str)

    def test_event_type_inherits_from_str(self) -> None:
        """Event types should be usable as strings."""
        assert isinstance(WorkflowEventType.PHASE_ENTERED, str)
        assert WorkflowEventType.PHASE_ENTERED == "phase_entered"

    def test_all_expected_event_types_exist(self) -> None:
        """Verify all expected event types are defined."""
        expected_types = {
            "PHASE_ENTERED",
            "ARTIFACT_CREATED",
            "ARTIFACT_APPROVED",
            "APPROVAL_REQUIRED",
            "APPROVAL_GRANTED",
            "WORKFLOW_COMPLETED",
            "WORKFLOW_FAILED",
            "ITERATION_STARTED",
        }
        actual_types = {e.name for e in WorkflowEventType}
        assert actual_types == expected_types

    def test_event_type_values_match_names(self) -> None:
        """Event type values should be lowercase snake_case of names."""
        for event_type in WorkflowEventType:
            expected_value = event_type.name.lower()
            assert event_type.value == expected_value
