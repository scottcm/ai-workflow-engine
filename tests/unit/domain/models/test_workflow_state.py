import pytest
from aiwf.domain.models.workflow_state import WorkflowState, WorkflowPhase, WorkflowStatus, ExecutionMode


class TestWorkflowStateContext:
    """Tests for generic context dict in WorkflowState."""

    def test_creates_with_empty_context(self):
        """WorkflowState can be created with empty context."""
        state = WorkflowState(
            session_id="test-123",
            profile="jpa-mt",
            context={},
            phase=WorkflowPhase.INITIALIZED,
            status=WorkflowStatus.SUCCESS,
            execution_mode=ExecutionMode.INTERACTIVE,
            standards_hash="0" * 64,
            providers={},
        )
        assert state.context == {}

    def test_creates_with_populated_context(self):
        """WorkflowState can be created with profile-specific context."""
        context = {
            "scope": "domain",
            "entity": "Customer",
            "table": "customer",
            "bounded_context": "sales",
        }
        state = WorkflowState(
            session_id="test-123",
            profile="jpa-mt",
            context=context,
            phase=WorkflowPhase.INITIALIZED,
            status=WorkflowStatus.SUCCESS,
            execution_mode=ExecutionMode.INTERACTIVE,
            standards_hash="0" * 64,
            providers={},
        )
        assert state.context == context
        assert state.context["entity"] == "Customer"

    def test_context_serializes_to_json(self):
        """Context dict serializes correctly to JSON."""
        context = {"entity": "Customer", "count": 42, "enabled": True}
        state = WorkflowState(
            session_id="test-123",
            profile="jpa-mt",
            context=context,
            phase=WorkflowPhase.INITIALIZED,
            status=WorkflowStatus.SUCCESS,
            execution_mode=ExecutionMode.INTERACTIVE,
            standards_hash="0" * 64,
            providers={},
        )
        json_str = state.model_dump_json()
        assert '"entity": "Customer"' in json_str or '"entity":"Customer"' in json_str

    def test_context_deserializes_from_json(self):
        """Context dict deserializes correctly from JSON."""
        context = {"entity": "Customer", "count": 42}
        state = WorkflowState(
            session_id="test-123",
            profile="jpa-mt",
            context=context,
            phase=WorkflowPhase.INITIALIZED,
            status=WorkflowStatus.SUCCESS,
            execution_mode=ExecutionMode.INTERACTIVE,
            standards_hash="0" * 64,
            providers={},
        )
        json_str = state.model_dump_json()
        restored = WorkflowState.model_validate_json(json_str)
        assert restored.context == context

    def test_no_legacy_named_fields(self):
        """WorkflowState should not have legacy named fields."""
        # Check the class, not instance, to avoid deprecation warning
        # These should NOT exist as direct attributes on the model
        assert "entity" not in WorkflowState.model_fields
        assert "scope" not in WorkflowState.model_fields
        assert "table" not in WorkflowState.model_fields
        assert "bounded_context" not in WorkflowState.model_fields
        assert "dev" not in WorkflowState.model_fields
        assert "task_id" not in WorkflowState.model_fields


class TestWorkflowStateCurrentIteration:
    """Tests for current_iteration validation."""

    def test_current_iteration_defaults_to_1(self):
        """current_iteration defaults to 1."""
        state = WorkflowState(
            session_id="test-123",
            profile="jpa-mt",
            phase=WorkflowPhase.INITIALIZED,
            status=WorkflowStatus.IN_PROGRESS,
            execution_mode=ExecutionMode.INTERACTIVE,
            standards_hash="0" * 64,
            providers={},
        )
        assert state.current_iteration == 1

    def test_current_iteration_accepts_positive_values(self):
        """current_iteration accepts positive integer values."""
        state = WorkflowState(
            session_id="test-123",
            profile="jpa-mt",
            phase=WorkflowPhase.REVISING,
            status=WorkflowStatus.IN_PROGRESS,
            execution_mode=ExecutionMode.INTERACTIVE,
            standards_hash="0" * 64,
            providers={},
            current_iteration=5,
        )
        assert state.current_iteration == 5

    def test_current_iteration_rejects_zero(self):
        """current_iteration rejects 0."""
        with pytest.raises(ValueError, match="current_iteration must be >= 1"):
            WorkflowState(
                session_id="test-123",
                profile="jpa-mt",
                phase=WorkflowPhase.INITIALIZED,
                status=WorkflowStatus.IN_PROGRESS,
                execution_mode=ExecutionMode.INTERACTIVE,
                standards_hash="0" * 64,
                providers={},
                current_iteration=0,
            )

    def test_current_iteration_rejects_negative(self):
        """current_iteration rejects negative values."""
        with pytest.raises(ValueError, match="current_iteration must be >= 1"):
            WorkflowState(
                session_id="test-123",
                profile="jpa-mt",
                phase=WorkflowPhase.INITIALIZED,
                status=WorkflowStatus.IN_PROGRESS,
                execution_mode=ExecutionMode.INTERACTIVE,
                standards_hash="0" * 64,
                providers={},
                current_iteration=-1,
            )