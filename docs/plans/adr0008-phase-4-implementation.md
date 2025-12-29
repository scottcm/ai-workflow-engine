# Phase 4: Profile Migration (jpa-mt) - Implementation Guide

**Goal:** Migrate jpa-mt profile to new CLI pattern with profile-owned commands and context-based state.

**Dependencies:** Phase 1 (WorkflowState), Phase 2 (CLI Entry Points)

---

## Overview

1. Implement full `register()` function with profile-specific CLI commands
2. Move init parameters from core CLI to profile CLI (`aiwf jpa-mt init`)
3. Update templates to use context variables
4. Ensure profile works with new WorkflowState context

**Note:** The `--planner`, `--generator`, `--reviewer`, `--revisor` flags use the provider architecture from ADR-0007 (Plugin Architecture). These map to provider keys that are resolved via ProviderFactory.

---

## Step 1: Implement Full register() Function

**File:** `profiles/jpa_mt/__init__.py`

```python
import click
from pathlib import Path

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.models.workflow_state import ExecutionMode
from aiwf.interface.cli.cli import pass_json_context, output_json
from profiles.jpa_mt.jpa_mt_profile import JpaMtProfile


def register(cli_group: click.Group) -> type:
    """Register jpa-mt commands and return profile class."""

    @cli_group.command("init")
    @click.option(
        "--scope",
        required=True,
        type=click.Choice(["domain", "vertical"]),
        help="Layer scope: domain (entity+repo) or vertical (full stack)",
    )
    @click.option("--entity", required=True, help="Entity name (e.g., Customer)")
    @click.option("--table", required=True, help="Database table name")
    @click.option("--bounded-context", required=True, help="DDD bounded context")
    @click.option(
        "--schema-file",
        required=True,
        type=click.Path(exists=True),
        help="Path to schema DDL file",
    )
    @click.option("--dev", default=None, help="Developer identifier")
    @click.option("--task-id", default=None, help="Task/ticket identifier")
    @click.option(
        "--execution-mode",
        type=click.Choice(["manual", "automated"]),
        default="manual",
        help="Execution mode",
    )
    @click.option("--planner", default="manual", help="Provider for planning phase")
    @click.option("--generator", default="manual", help="Provider for generation phase")
    @click.option("--reviewer", default="manual", help="Provider for review phase")
    @click.option("--revisor", default="manual", help="Provider for revision phase")
    @pass_json_context
    def init(
        json_mode,
        scope,
        entity,
        table,
        bounded_context,
        schema_file,
        dev,
        task_id,
        execution_mode,
        planner,
        generator,
        reviewer,
        revisor,
    ):
        """Initialize a new JPA multi-tenant workflow session."""
        # Build context from CLI args
        context = {
            "scope": scope,
            "entity": entity,
            "table": table,
            "bounded_context": bounded_context,
            "schema_file": str(Path(schema_file).resolve()),
        }
        if dev:
            context["dev"] = dev
        if task_id:
            context["task_id"] = task_id

        # Build providers dict
        providers = {
            "planner": planner,
            "generator": generator,
            "reviewer": reviewer,
            "revisor": revisor,
        }

        # Initialize session
        orchestrator = WorkflowOrchestrator()
        exec_mode = (
            ExecutionMode.AUTOMATED
            if execution_mode == "automated"
            else ExecutionMode.MANUAL
        )

        state = orchestrator.initialize_run(
            profile="jpa-mt",
            context=context,
            execution_mode=exec_mode,
            providers=providers,
        )

        if json_mode:
            from aiwf.interface.cli.output_models import InitOutput
            output_json(InitOutput.from_state(state))
        else:
            click.echo(f"Session initialized: {state.session_id}")
            click.echo(f"Entity: {entity}")
            click.echo(f"Phase: {state.phase.value}")

    @cli_group.command("schema-info")
    @click.argument("session_id")
    @pass_json_context
    def schema_info(json_mode, session_id):
        """Display parsed schema information for a session."""
        orchestrator = WorkflowOrchestrator()
        state = orchestrator.get_state(session_id)

        schema_file = state.context.get("schema_file")
        if not schema_file:
            click.echo("No schema file in session context", err=True)
            raise SystemExit(1)

        click.echo(f"Schema file: {schema_file}")
        click.echo(f"Table: {state.context.get('table')}")
        click.echo(f"Entity: {state.context.get('entity')}")

    @cli_group.command("layers")
    @pass_json_context
    def layers(json_mode):
        """List available layer scopes for JPA-MT profile."""
        if json_mode:
            output_json({"layers": ["domain", "vertical"]})
        else:
            click.echo("Available scopes:")
            click.echo("  domain   - Entity class + Repository interface")
            click.echo("  vertical - Full vertical slice (future)")

    return JpaMtProfile
```

---

## Step 2: Update Template Variable References

Templates need to access context values. Update from `{{entity}}` to `{{entity}}` (if using flat context in _prompt_context) or handle in profile.

**File:** `profiles/jpa_mt/jpa_mt_profile.py`

Update `_fill_placeholders` to work with context-based state:

```python
def _fill_placeholders(self, content: str, context: dict[str, Any]) -> str:
    """Replace {{PLACEHOLDER}} with context values.

    Context now comes from state.context spread with engine values.
    Keys are already flattened (entity, table, etc. - not context.entity).
    """
    effective_context = dict(context)

    # Read schema file content if path provided
    schema_file = effective_context.get("schema_file")
    if schema_file:
        schema_path = Path(schema_file)
        if schema_path.exists():
            effective_context["schema_ddl"] = schema_path.read_text(encoding="utf-8")
        else:
            effective_context["schema_ddl"] = ""
    else:
        effective_context["schema_ddl"] = ""

    # Format code_files list as markdown
    code_files = effective_context.get("code_files")
    if code_files and isinstance(code_files, list):
        effective_context["code_files"] = "\n".join(f"- `{f}`" for f in code_files)
    elif code_files is None:
        effective_context["code_files"] = ""

    result = content
    for key, value in effective_context.items():
        placeholder = f"{{{{{key.upper()}}}}}"
        display_value = "" if value is None else str(value)
        result = result.replace(placeholder, display_value)
    return result
```

---

## Step 3: Verify Template Variables

Templates use uppercase placeholders like `{{ENTITY}}`, `{{TABLE}}`, etc.

The engine's `_prompt_context()` (updated in Phase 1) spreads `state.context` which contains lowercase keys (`entity`, `table`).

The `_fill_placeholders` method converts keys to uppercase for matching.

**No template changes needed** if templates already use uppercase and the profile's placeholder replacement handles the case conversion.

---

## Step 4: Update Template Metadata Block

**File:** `profiles/jpa_mt/templates/_shared/base.md`

The metadata block should reflect what the profile provides. Keep domain variables, remove any engine path references:

```markdown
---
# METADATA
task-id: {{TASK_ID}}
dev: {{DEV}}
date: {{DATE}}
entity: {{ENTITY}}
scope: {{SCOPE}}
table: {{TABLE}}
bounded-context: {{BOUNDED_CONTEXT}}
profile: {{PROFILE}}
schema-file: {{SCHEMA_FILE}}
---
```

Note: `session-id` and `iteration` can stay if informational, but shouldn't be used for path construction.

---

## Step 5: Update Profile to Accept Context

**File:** `profiles/jpa_mt/jpa_mt_profile.py`

Ensure profile methods work with context-based workflow:

```python
def validate_metadata(self, metadata: dict[str, Any] | None) -> None:
    """Validate that required metadata is provided for jpa-mt profile.

    Note: With context-based state, validation happens at init time via
    context_schema. This method is for additional runtime validation.
    """
    # Could validate schema_file exists, etc.
    pass
```

---

## Step 6: Remove Hardcoded References in Profile

**File:** `profiles/jpa_mt/jpa_mt_profile.py`

Ensure profile doesn't reference old WorkflowState fields:

```python
# BAD - old pattern
def some_method(self, state: WorkflowState):
    entity = state.entity  # Old field

# GOOD - new pattern
def some_method(self, state: WorkflowState):
    entity = state.context.get("entity")  # From context
```

Also update any code that builds paths - profile should not construct session paths.

---

## Step 7: Update Standards Provider

**File:** `profiles/jpa_mt/jpa_mt_standards_provider.py`

Update to read from context:

```python
def create_bundle(self, state: WorkflowState, ...) -> str:
    # OLD
    # scope = state.scope

    # NEW
    scope = state.context.get("scope", "domain")
```

---

## Testing Requirements

**File:** `tests/unit/profiles/jpa_mt/test_jpa_mt_profile.py`

1. Test profile works with context-based WorkflowState
2. Test _fill_placeholders handles context values
3. Test templates render correctly with context

**File:** `tests/integration/test_cli.py`

4. Test `aiwf jpa-mt init` creates session with correct context
5. Test `aiwf jpa-mt init --help` shows all options
6. Test `aiwf jpa-mt schema-info` works
7. Test `aiwf jpa-mt layers` works

**File:** `tests/integration/test_workflow.py`

8. Test full workflow with context-based state
9. Test prompts generated correctly

---

## Files Changed

| File | Change |
|------|--------|
| `profiles/jpa_mt/__init__.py` | Full register() implementation |
| `profiles/jpa_mt/jpa_mt_profile.py` | Work with context, remove old field refs |
| `profiles/jpa_mt/jpa_mt_standards_provider.py` | Read from context |
| `profiles/jpa_mt/templates/_shared/base.md` | Review metadata block |
| `tests/unit/profiles/jpa_mt/test_jpa_mt_profile.py` | Update for context |
| `tests/integration/test_cli.py` | Test profile commands |

---

## Acceptance Criteria

- [ ] `aiwf jpa-mt init` works with all options
- [ ] `aiwf jpa-mt init --help` shows profile-specific help
- [ ] `aiwf jpa-mt schema-info` displays session schema info
- [ ] `aiwf jpa-mt layers` lists available scopes
- [ ] Session created with context dict (not named fields)
- [ ] Templates render correctly with context values
- [ ] Profile doesn't reference old WorkflowState fields
- [ ] All tests pass