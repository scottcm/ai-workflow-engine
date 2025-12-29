# Phase 8: Legacy Init Removal - Implementation Guide

**Goal:** Remove hardcoded ORM-specific CLI parameters from the core `init` command.

**Dependencies:** Phase 4 (Profile Migration - jpa-mt)

---

## Overview

After Phase 4, profiles register their own namespaced commands (e.g., `aiwf jpa-mt init`). The legacy core `init` command with hardcoded ORM-specific parameters is now redundant and should be removed.

**Current state (legacy):**
```bash
aiwf init --scope domain --entity Foo --table foo --bounded-context bar --schema-file ./schema.sql
```

**Target state:**
```bash
# Core init removed - profiles provide their own init commands
aiwf jpa-mt init --entity Foo --table foo --bounded-context bar --schema-file ./schema.sql
```

---

## Step 1: Verify Profile Commands Work

Before removing the legacy init, verify that profile-specific init commands are functional:

**Verification checklist:**
- [ ] `aiwf jpa-mt init --entity Foo --table foo` creates a valid session
- [ ] Session state has correct context dict populated
- [ ] Workflow can proceed through all phases using profile commands
- [ ] `aiwf --help` shows profile command groups

---

## Step 2: Remove Legacy Init Command

**File:** `aiwf/interface/cli/cli.py`

Remove the legacy `init` command and its ORM-specific options.

**Before:**
```python
@cli.command("init")
@click.option("--scope", type=click.Choice(["domain", "vertical"]), required=True)
@click.option("--entity", type=str, required=True)
@click.option("--table", type=str, default=None)
@click.option("--bounded-context", type=str, default=None)
@click.option("--schema-file", type=click.Path(exists=True), default=None)
@click.option("--dev", type=str, default=None)
@click.option("--task-id", type=str, default=None)
@click.option("--profile", type=str, default="jpa-mt")
@pass_json_context
def init(json_mode, scope, entity, table, bounded_context, schema_file, dev, task_id, profile):
    """Initialize a new workflow session."""
    # ... legacy implementation
```

**After:**
```python
# REMOVED: Legacy init command
# Sessions are now created via profile-specific commands:
#   aiwf jpa-mt init --entity Foo ...
#   aiwf react-component init --component Button ...
```

---

## Step 3: Update CLI Help Text

**File:** `aiwf/interface/cli/cli.py`

Update the main CLI group description to explain the new command structure:

```python
@click.group()
@click.option("--json", "json_mode", is_flag=True, help="Output in JSON format")
@click.pass_context
def cli(ctx, json_mode):
    """AI Workflow Engine - Multi-phase AI-assisted code generation.

    Sessions are created using profile-specific commands:

        aiwf jpa-mt init --entity Customer --table customer
        aiwf react-component init --component Button

    Core commands work with existing sessions:

        aiwf step <session-id>
        aiwf approve <session-id>
        aiwf status <session-id>
        aiwf list

    Use 'aiwf profiles' to see available profiles.
    """
    ctx.ensure_object(dict)
    ctx.obj["json_mode"] = json_mode
```

---

## Step 4: Remove Legacy WorkflowState Fields

**File:** `aiwf/domain/models/workflow_state.py`

This should already be done in Phase 1, but verify no legacy fields remain:

**Verify removed:**
```python
# These should NOT be present (moved to context dict in Phase 1):
# entity: str
# bounded_context: str | None = None
# table: str | None = None
# dev: str | None = None
# task_id: str | None = None
# scope: str  # Also moved to context - profile-specific concept
```

**Should have:**
```python
class WorkflowState(BaseModel):
    session_id: str
    profile: str
    context: dict[str, Any] = Field(default_factory=dict)  # All profile data here
    phase: WorkflowPhase
    status: WorkflowStatus
    # ... rest unchanged
```

---

## Step 5: Remove Legacy Output Models

**File:** `aiwf/interface/cli/output_models.py`

Remove any output models specific to the legacy init command if they exist.

Check for and remove:
- `InitOutput` or similar models with hardcoded field names
- Update `SessionListItem` if it references legacy fields

---

## Step 6: Update Session List Display

**File:** `aiwf/interface/cli/cli.py` (list command)

Update the `list` command to display context-aware information:

**Before (if using hardcoded fields):**
```python
# Don't display entity/table as top-level fields
output = SessionListItem(
    session_id=state.session_id,
    entity=state.entity,  # REMOVE
    scope=state.scope,    # MOVE to context display
    ...
)
```

**After:**
```python
output = SessionListItem(
    session_id=state.session_id,
    profile=state.profile,
    phase=state.phase.value,
    status=state.status.value,
    # Let profile determine summary display via context
    summary=_get_session_summary(state),
)

def _get_session_summary(state: WorkflowState) -> str:
    """Generate a profile-appropriate summary string."""
    context = state.context
    if state.profile == "jpa-mt":
        entity = context.get("entity", "?")
        scope = context.get("scope", "?")
        return f"{entity} ({scope})"
    elif state.profile == "react-component":
        component = context.get("component", "?")
        return f"{component}"
    else:
        return str(context)[:50]  # Fallback: truncated context
```

---

## Step 7: Update Tests

**File:** `tests/integration/test_cli.py`

Remove or update tests for the legacy init command:

```python
# REMOVE: Tests for legacy init
# def test_init_creates_session():
#     result = runner.invoke(cli, ["init", "--scope", "domain", "--entity", "Foo"])
#     ...

# ADD: Tests for profile-specific init (should be in profile tests)
# See tests/unit/profiles/jpa_mt/test_cli.py
```

**File:** `tests/unit/interface/cli/test_cli.py`

Remove unit tests for legacy init options.

---

## Step 8: Clean Up Imports and References

Search the codebase for any remaining references to legacy init:

```bash
# Search for legacy field references
grep -r "state\.entity" aiwf/
grep -r "state\.scope" aiwf/
grep -r "state\.table" aiwf/
grep -r "state\.bounded_context" aiwf/
grep -r "state\.dev" aiwf/
grep -r "state\.task_id" aiwf/
```

All should now use `state.context.get("field_name")` pattern.

---

## Migration Notes

### For Existing Users

Since v2.0.0 is a clean break with no existing users, no migration is needed.

### Documentation Update

Update user documentation to reflect new command structure:

**Old:**
```bash
aiwf init --scope domain --entity Customer --table customer --profile jpa-mt
```

**New:**
```bash
aiwf jpa-mt init --entity Customer --table customer
```

---

## Testing Requirements

**File:** `tests/integration/test_cli.py`

1. Test that `aiwf init` is no longer a valid command (should show error or help)
2. Test that `aiwf --help` shows profile command groups
3. Test that `aiwf jpa-mt init` works correctly
4. Test that `aiwf list` displays sessions from profile commands
5. Test that `aiwf status` works with new session format

**File:** `tests/unit/domain/models/test_workflow_state.py`

6. Test WorkflowState has no legacy fields (entity, table, etc.)
7. Test WorkflowState serializes/deserializes context correctly

---

## Files Changed

| File | Change |
|------|--------|
| `aiwf/interface/cli/cli.py` | Remove legacy init command, update help text |
| `aiwf/interface/cli/output_models.py` | Remove/update legacy output models |
| `aiwf/domain/models/workflow_state.py` | Verify legacy fields removed (Phase 1) |
| `tests/integration/test_cli.py` | Remove legacy init tests |
| `tests/unit/interface/cli/test_cli.py` | Remove legacy init unit tests |
| `docs/` | Update user documentation |

---

## Verification Checklist

After removal, verify:

- [ ] `aiwf init` shows error or redirects to help
- [ ] `aiwf --help` shows profile command groups
- [ ] `aiwf profiles` lists available profiles
- [ ] `aiwf jpa-mt init --entity Foo --table foo` creates valid session
- [ ] `aiwf list` shows sessions with profile-appropriate summaries
- [ ] `aiwf status <session-id>` works with new sessions
- [ ] No code references legacy fields (entity, table, scope as top-level)
- [ ] All tests pass

---

## Acceptance Criteria

- [ ] Legacy `init` command removed from CLI
- [ ] Help text explains new profile-based command structure
- [ ] No hardcoded ORM parameters in core CLI
- [ ] Session list displays profile-appropriate information
- [ ] WorkflowState has no legacy field references in codebase
- [ ] All integration tests pass with new command structure
- [ ] Documentation updated to reflect new commands