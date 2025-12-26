"""Tests for StderrEventObserver."""

from datetime import datetime, timezone
from io import StringIO
from unittest.mock import patch

import pytest

from aiwf.domain.events.event import WorkflowEvent
from aiwf.domain.events.event_types import WorkflowEventType
from aiwf.domain.events.stderr_observer import StderrEventObserver
from aiwf.domain.models.workflow_state import WorkflowPhase


class TestStderrEventObserver:
    """Tests for StderrEventObserver."""

    def test_emits_event_type_to_stderr(self) -> None:
        """Observer emits [EVENT] prefix with event type."""
        observer = StderrEventObserver()
        event = WorkflowEvent(
            event_type=WorkflowEventType.PHASE_ENTERED,
            session_id="sess_123",
            timestamp=datetime.now(timezone.utc),
        )

        with patch("click.echo") as mock_echo:
            observer.on_event(event)
            mock_echo.assert_called_once()
            output = mock_echo.call_args[0][0]
            assert output.startswith("[EVENT] phase_entered")
            assert mock_echo.call_args[1]["err"] is True

    def test_includes_phase_when_present(self) -> None:
        """Observer includes phase= when phase is set."""
        observer = StderrEventObserver()
        event = WorkflowEvent(
            event_type=WorkflowEventType.PHASE_ENTERED,
            session_id="sess_123",
            timestamp=datetime.now(timezone.utc),
            phase=WorkflowPhase.GENERATING,
        )

        with patch("click.echo") as mock_echo:
            observer.on_event(event)
            output = mock_echo.call_args[0][0]
            assert "phase=GENERATING" in output

    def test_includes_iteration_when_present(self) -> None:
        """Observer includes iteration= when iteration is set."""
        observer = StderrEventObserver()
        event = WorkflowEvent(
            event_type=WorkflowEventType.ITERATION_STARTED,
            session_id="sess_123",
            timestamp=datetime.now(timezone.utc),
            iteration=3,
        )

        with patch("click.echo") as mock_echo:
            observer.on_event(event)
            output = mock_echo.call_args[0][0]
            assert "iteration=3" in output

    def test_includes_path_when_present(self) -> None:
        """Observer includes path= when artifact_path is set."""
        observer = StderrEventObserver()
        event = WorkflowEvent(
            event_type=WorkflowEventType.ARTIFACT_CREATED,
            session_id="sess_123",
            timestamp=datetime.now(timezone.utc),
            artifact_path="iteration-1/code/Entity.java",
        )

        with patch("click.echo") as mock_echo:
            observer.on_event(event)
            output = mock_echo.call_args[0][0]
            assert "path=iteration-1/code/Entity.java" in output

    def test_omits_optional_fields_when_none(self) -> None:
        """Observer omits phase, iteration, path when None."""
        observer = StderrEventObserver()
        event = WorkflowEvent(
            event_type=WorkflowEventType.WORKFLOW_COMPLETED,
            session_id="sess_123",
            timestamp=datetime.now(timezone.utc),
        )

        with patch("click.echo") as mock_echo:
            observer.on_event(event)
            output = mock_echo.call_args[0][0]
            assert output == "[EVENT] workflow_completed"
            assert "phase=" not in output
            assert "iteration=" not in output
            assert "path=" not in output

    def test_full_event_format(self) -> None:
        """Observer formats full event with all fields."""
        observer = StderrEventObserver()
        event = WorkflowEvent(
            event_type=WorkflowEventType.ARTIFACT_CREATED,
            session_id="sess_123",
            timestamp=datetime.now(timezone.utc),
            phase=WorkflowPhase.GENERATING,
            iteration=2,
            artifact_path="iteration-2/code/MyEntity.java",
        )

        with patch("click.echo") as mock_echo:
            observer.on_event(event)
            output = mock_echo.call_args[0][0]
            assert output == (
                "[EVENT] artifact_created phase=GENERATING iteration=2 "
                "path=iteration-2/code/MyEntity.java"
            )

    def test_iteration_zero_is_included(self) -> None:
        """Observer includes iteration=0 (not treated as falsy)."""
        observer = StderrEventObserver()
        event = WorkflowEvent(
            event_type=WorkflowEventType.PHASE_ENTERED,
            session_id="sess_123",
            timestamp=datetime.now(timezone.utc),
            iteration=0,
        )

        with patch("click.echo") as mock_echo:
            observer.on_event(event)
            output = mock_echo.call_args[0][0]
            assert "iteration=0" in output
