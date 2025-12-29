# Phase 1: WorkflowState Generalization - Implementation Guide

**Goal:** Replace ORM-specific fields in WorkflowState with a generic `context` dict.

**Dependencies:** None

**Approach:** Test-Driven Development (TDD)

---

## Overview

Currently `WorkflowState` has hardcoded fields for jpa-mt profile:
- `entity`, `table`, `bounded_context`, `scope`, `dev`, `task_id`

Replace these with a generic `context: dict[str, Any]` that any profile can populate with its own data.

---

## Step 1: Write Tests First

Write all tests before implementation. Tests should fail initially (red), then pass after implementation (green).

### 1.1 WorkflowState Model Tests

**File:** `tests/unit/domain/models/test_workflow_state.py`

```python
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
            execution_mode=ExecutionMode.MANUAL,
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
            execution_mode=ExecutionMode.MANUAL,
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
            execution_mode=ExecutionMode.MANUAL,
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
            execution_mode=ExecutionMode.MANUAL,
        )
        json_str = state.model_dump_json()
        restored = WorkflowState.model_validate_json(json_str)
        assert restored.context == context

    def test_no_legacy_named_fields(self):
        """WorkflowState should not have legacy named fields."""
        state = WorkflowState(
            session_id="test-123",
            profile="jpa-mt",
            context={},
            phase=WorkflowPhase.INITIALIZED,
            status=WorkflowStatus.SUCCESS,
            execution_mode=ExecutionMode.MANUAL,
        )
        # These should NOT exist as direct attributes
        assert not hasattr(state, "entity") or "entity" not in state.model_fields
        assert not hasattr(state, "scope") or "scope" not in state.model_fields
        assert not hasattr(state, "table") or "table" not in state.model_fields
```

### 1.2 Context Validation Tests

**File:** `tests/unit/application/test_context_validation.py` (new)

```python
import pytest
from pathlib import Path
from unittest.mock import patch

from aiwf.application.context_validation import validate_context, ValidationError


class TestValidateContext:
    """Tests for context validation against profile schema."""

    @pytest.fixture
    def jpa_mt_schema(self):
        """Schema matching jpa-mt profile requirements."""
        return {
            "scope": {"type": "string", "required": True, "choices": ["domain", "vertical"]},
            "entity": {"type": "string", "required": True},
            "table": {"type": "string", "required": True},
            "bounded_context": {"type": "string", "required": True},
            "schema_file": {"type": "path", "required": True, "exists": True},
            "dev": {"type": "string", "required": False},
            "task_id": {"type": "string", "required": False},
        }

    def test_valid_context_returns_no_errors(self, jpa_mt_schema, tmp_path):
        """Valid context passes validation."""
        schema_file = tmp_path / "schema.sql"
        schema_file.write_text("CREATE TABLE customer (...);")

        context = {
            "scope": "domain",
            "entity": "Customer",
            "table": "customer",
            "bounded_context": "sales",
            "schema_file": str(schema_file),
        }
        errors = validate_context(jpa_mt_schema, context)
        assert errors == []

    def test_missing_required_field_returns_error(self, jpa_mt_schema, tmp_path):
        """Missing required field produces error with field name."""
        schema_file = tmp_path / "schema.sql"
        schema_file.write_text("CREATE TABLE customer (...);")

        context = {
            "scope": "domain",
            # "entity" is missing
            "table": "customer",
            "bounded_context": "sales",
            "schema_file": str(schema_file),
        }
        errors = validate_context(jpa_mt_schema, context)
        assert len(errors) == 1
        assert errors[0].field == "entity"
        assert "required" in errors[0].message.lower() or "missing" in errors[0].message.lower()

    def test_invalid_choice_returns_error_with_value(self, jpa_mt_schema, tmp_path):
        """Invalid choice produces error with expected values and actual value."""
        schema_file = tmp_path / "schema.sql"
        schema_file.write_text("CREATE TABLE customer (...);")

        context = {
            "scope": "invalid_scope",  # Not in ["domain", "vertical"]
            "entity": "Customer",
            "table": "customer",
            "bounded_context": "sales",
            "schema_file": str(schema_file),
        }
        errors = validate_context(jpa_mt_schema, context)
        assert len(errors) == 1
        assert errors[0].field == "scope"
        assert "domain" in errors[0].message
        assert "vertical" in errors[0].message
        assert "invalid_scope" in errors[0].message

    def test_wrong_type_returns_error(self, jpa_mt_schema, tmp_path):
        """Wrong type produces error with expected and actual type."""
        schema_file = tmp_path / "schema.sql"
        schema_file.write_text("CREATE TABLE customer (...);")

        context = {
            "scope": "domain",
            "entity": 123,  # Should be string, not int
            "table": "customer",
            "bounded_context": "sales",
            "schema_file": str(schema_file),
        }
        errors = validate_context(jpa_mt_schema, context)
        assert len(errors) == 1
        assert errors[0].field == "entity"
        assert "string" in errors[0].message.lower()
        assert "int" in errors[0].message.lower()

    def test_nonexistent_path_returns_error(self, jpa_mt_schema):
        """Path that doesn't exist produces error."""
        context = {
            "scope": "domain",
            "entity": "Customer",
            "table": "customer",
            "bounded_context": "sales",
            "schema_file": "/nonexistent/path/schema.sql",
        }
        errors = validate_context(jpa_mt_schema, context)
        assert len(errors) == 1
        assert errors[0].field == "schema_file"
        assert "exist" in errors[0].message.lower()

    def test_optional_field_can_be_omitted(self, jpa_mt_schema, tmp_path):
        """Optional fields don't cause errors when omitted."""
        schema_file = tmp_path / "schema.sql"
        schema_file.write_text("CREATE TABLE customer (...);")

        context = {
            "scope": "domain",
            "entity": "Customer",
            "table": "customer",
            "bounded_context": "sales",
            "schema_file": str(schema_file),
            # dev and task_id are optional, not provided
        }
        errors = validate_context(jpa_mt_schema, context)
        assert errors == []

    def test_multiple_errors_returned(self, jpa_mt_schema):
        """Multiple validation failures return multiple errors."""
        context = {
            "scope": "invalid",
            # entity missing
            "table": "customer",
            # bounded_context missing
            "schema_file": "/nonexistent/path.sql",
        }
        errors = validate_context(jpa_mt_schema, context)
        assert len(errors) >= 3  # scope invalid, entity missing, bounded_context missing, path invalid
        fields_with_errors = {e.field for e in errors}
        assert "scope" in fields_with_errors
        assert "entity" in fields_with_errors
        assert "bounded_context" in fields_with_errors

    def test_empty_schema_accepts_any_context(self):
        """Profile with no schema accepts any context."""
        errors = validate_context({}, {"anything": "goes", "count": 42})
        assert errors == []
```

### 1.3 Orchestrator Integration Tests

**File:** `tests/unit/application/test_workflow_orchestrator.py` (add to existing)

```python
class TestInitializeRunWithContext:
    """Tests for initialize_run with context parameter."""

    def test_initialize_run_accepts_context(self, orchestrator, tmp_path):
        """initialize_run accepts context dict and stores in state."""
        schema_file = tmp_path / "schema.sql"
        schema_file.write_text("CREATE TABLE customer (...);")

        context = {
            "scope": "domain",
            "entity": "Customer",
            "table": "customer",
            "bounded_context": "sales",
            "schema_file": str(schema_file),
        }
        state = orchestrator.initialize_run(profile="jpa-mt", context=context)
        assert state.context == context

    def test_initialize_run_validates_context(self, orchestrator):
        """initialize_run raises ValueError for invalid context."""
        invalid_context = {"scope": "invalid"}  # Missing required fields
        with pytest.raises(ValueError) as exc_info:
            orchestrator.initialize_run(profile="jpa-mt", context=invalid_context)
        assert "validation" in str(exc_info.value).lower()

    def test_initialize_run_validation_error_is_actionable(self, orchestrator):
        """Validation error message includes field name and constraint."""
        invalid_context = {"scope": "wrong", "entity": "Foo"}  # scope invalid, others missing
        with pytest.raises(ValueError) as exc_info:
            orchestrator.initialize_run(profile="jpa-mt", context=invalid_context)
        error_msg = str(exc_info.value)
        # Should mention the problematic field
        assert "scope" in error_msg or "table" in error_msg or "bounded_context" in error_msg
```

---

## Step 2: Implement to Pass Tests

Now implement the code to make tests pass.

### 2.1 Update WorkflowState Model

**File:** `aiwf/domain/models/workflow_state.py`

Remove named fields, add context dict:

```python
class WorkflowState(BaseModel):
    # Identity
    session_id: str
    profile: str

    # REMOVE these fields:
    # scope: str
    # entity: str
    # table: str | None = None
    # bounded_context: str | None = None
    # dev: str | None = None
    # task_id: str | None = None

    # ADD generic context
    context: dict[str, Any] = Field(default_factory=dict)

    # State (unchanged)
    phase: WorkflowPhase
    status: WorkflowStatus
    execution_mode: ExecutionMode
    current_iteration: int = 1
    # ... rest unchanged
```

### 2.2 Create Context Validation Module

**File:** `aiwf/application/context_validation.py` (new)

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ValidationError:
    field: str
    message: str


def validate_context(
    schema: dict[str, dict[str, Any]],
    context: dict[str, Any]
) -> list[ValidationError]:
    """Validate context against schema.

    Args:
        schema: Dict of field_name -> rules (type, required, choices, exists)
        context: The context dict to validate

    Returns:
        List of ValidationError, empty if valid
    """
    errors = []

    for field, rules in schema.items():
        value = context.get(field)

        # Required check
        if rules.get("required") and value is None:
            errors.append(ValidationError(
                field=field,
                message=f"Required field missing"
            ))
            continue

        if value is None:
            continue  # Optional field not provided

        # Type check
        field_type = rules.get("type", "string")
        if field_type == "string" and not isinstance(value, str):
            errors.append(ValidationError(
                field=field,
                message=f"Expected string, got {type(value).__name__}"
            ))
        elif field_type == "int" and not isinstance(value, int):
            errors.append(ValidationError(
                field=field,
                message=f"Expected int, got {type(value).__name__}"
            ))
        elif field_type == "bool" and not isinstance(value, bool):
            errors.append(ValidationError(
                field=field,
                message=f"Expected bool, got {type(value).__name__}"
            ))
        elif field_type == "path":
            if not isinstance(value, str):
                errors.append(ValidationError(
                    field=field,
                    message=f"Expected path string, got {type(value).__name__}"
                ))
            elif rules.get("exists") and not Path(value).exists():
                errors.append(ValidationError(
                    field=field,
                    message=f"Path does not exist: {value}"
                ))

        # Choices check
        if "choices" in rules and value not in rules["choices"]:
            errors.append(ValidationError(
                field=field,
                message=f"Must be one of {rules['choices']}, got '{value}'"
            ))

    return errors
```

### 2.3 Add Context Schema to Profile Metadata

**File:** `aiwf/domain/profiles/workflow_profile.py`

```python
@classmethod
def get_metadata(cls) -> dict[str, Any]:
    return {
        "name": "unknown",
        "description": "No description available",
        # ... existing fields ...
        "context_schema": {},  # NEW: optional schema for validation
    }
```

### 2.4 Update jpa-mt Profile Metadata

**File:** `profiles/jpa_mt/jpa_mt_profile.py`

```python
@classmethod
def get_metadata(cls) -> dict[str, Any]:
    return {
        "name": "jpa-mt",
        "description": "Multi-tenant JPA domain layer generation",
        # ... existing fields ...
        "context_schema": {
            "scope": {"type": "string", "required": True, "choices": ["domain", "vertical"]},
            "entity": {"type": "string", "required": True},
            "table": {"type": "string", "required": True},
            "bounded_context": {"type": "string", "required": True},
            "schema_file": {"type": "path", "required": True, "exists": True},
            "dev": {"type": "string", "required": False},
            "task_id": {"type": "string", "required": False},
        },
    }
```

### 2.5 Update initialize_run()

**File:** `aiwf/application/workflow_orchestrator.py`

```python
from aiwf.application.context_validation import validate_context

def initialize_run(
    self,
    profile: str,
    context: dict[str, Any],  # NEW parameter
    execution_mode: ExecutionMode = ExecutionMode.MANUAL,
    providers: dict[str, str] | None = None,
) -> WorkflowState:
    # Get profile class
    profile_class = ProfileFactory.get(profile)
    if not profile_class:
        raise ValueError(f"Unknown profile: {profile}")

    # Validate context
    schema = profile_class.get_metadata().get("context_schema", {})
    errors = validate_context(schema, context)
    if errors:
        error_details = "; ".join(f"{e.field}: {e.message}" for e in errors)
        raise ValueError(f"Context validation failed: {error_details}")

    # Create state with context
    state = WorkflowState(
        session_id=self._generate_session_id(),
        profile=profile,
        context=context,  # NEW
        phase=WorkflowPhase.INITIALIZED,
        status=WorkflowStatus.SUCCESS,
        execution_mode=execution_mode,
        providers=providers or {},
    )
    # ... rest of initialization
```

### 2.6 Update _prompt_context()

**File:** `aiwf/application/workflow_orchestrator.py`

```python
def _prompt_context(self, state: WorkflowState) -> dict[str, Any]:
    """Build context dict for prompt templates."""
    return {
        **state.context,  # Spread all context values
        "session_id": state.session_id,
        "profile": state.profile,
        "iteration": state.current_iteration,
        # ... any other engine-provided values
    }
```

### 2.7 Update CLI (Temporary)

**File:** `aiwf/interface/cli/cli.py`

```python
@cli.command("init")
# ... existing options ...
def init(json_mode, profile, scope, entity, table, bounded_context, schema_file, dev, task_id, ...):
    # Build context from CLI args
    context = {
        "scope": scope,
        "entity": entity,
        "table": table,
        "bounded_context": bounded_context,
        "schema_file": schema_file,
        "dev": dev,
        "task_id": task_id,
    }
    # Remove None values
    context = {k: v for k, v in context.items() if v is not None}

    state = orchestrator.initialize_run(profile=profile, context=context, ...)
```

### 2.8 Update Output Models

**File:** `aiwf/interface/cli/output_models.py`

```python
class SessionSummary(BaseModel):
    session_id: str
    profile: str
    context: dict[str, Any]  # Was: scope: str, entity: str, etc.
    phase: str
    status: str
    # ...
```

---

## Step 3: Verify All Tests Pass

Run the test suite:

```bash
poetry run pytest tests/unit/domain/models/test_workflow_state.py -v
poetry run pytest tests/unit/application/test_context_validation.py -v
poetry run pytest tests/unit/application/test_workflow_orchestrator.py -v
poetry run pytest tests/integration/test_cli.py -v
```

All tests should pass (green).

---

## Files Changed

| File | Change |
|------|--------|
| `tests/unit/domain/models/test_workflow_state.py` | New context tests |
| `tests/unit/application/test_context_validation.py` | New validation tests |
| `tests/unit/application/test_workflow_orchestrator.py` | New initialize_run tests |
| `aiwf/domain/models/workflow_state.py` | Remove named fields, add context dict |
| `aiwf/application/context_validation.py` | New module |
| `aiwf/domain/profiles/workflow_profile.py` | Add context_schema to metadata |
| `profiles/jpa_mt/jpa_mt_profile.py` | Add context_schema |
| `aiwf/application/workflow_orchestrator.py` | Add validation, update initialize_run |
| `aiwf/interface/cli/cli.py` | Build context from CLI args |
| `aiwf/interface/cli/output_models.py` | Update SessionSummary |

---

## Acceptance Criteria

- [ ] All TDD tests written and initially failing
- [ ] WorkflowState has `context: dict[str, Any]` instead of named fields
- [ ] Profile metadata includes `context_schema`
- [ ] Context validated at initialize_run()
- [ ] Validation errors include field name, expected constraint, and actual value (e.g., "scope: must be one of ['domain', 'vertical'], got 'invalid'")
- [ ] Sessions serialize/deserialize correctly
- [ ] All tests pass (green)