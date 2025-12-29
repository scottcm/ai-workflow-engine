# ADR-0008: Profile-Specific Commands and Generic WorkflowState

**Status:** Draft
**Date:** December 26, 2024
**Deciders:** Scott

---

## Context and Problem Statement

The AI Workflow Engine's `init` command has ORM-specific parameters hardcoded into both the CLI and `WorkflowState`:

```python
# Current WorkflowState - ORM-specific fields
entity: str
bounded_context: str | None = None
table: str | None = None
dev: str | None = None
task_id: str | None = None
```

```bash
# Current init command - ORM-specific parameters
aiwf init --scope domain --entity Foo --table foo --bounded-context bar --schema-file ./schema.sql
```

This design couples the engine to JPA/ORM workflows. Non-ORM profiles (React components, API schemas, documentation generators) cannot define their own required parameters without modifying the core engine.

**Version Context:** This is a breaking change for v2.0.0. There are no existing users on v1.x, so this is the right time to make foundational changes.

---

## Decision Drivers

1. **Profile autonomy** - Profiles should define their own parameters without engine changes
2. **Clear namespacing** - Profile commands should not collide with core or other profile commands
3. **Discoverability** - Users should easily find available profile commands
4. **Clean break** - v2.0.0 is not backward-compatible with v1.x sessions
5. **Single-profile sessions** - A session uses exactly one profile (no multi-profile composition)

---

## Decision

### 1. Namespaced Profile Commands

Profile commands live under their profile name:

```bash
# Profile-specific init
aiwf jpa-mt init --entity Foo --table foo --bounded-context bar --schema-file ./schema.sql

# Profile-specific commands
aiwf jpa-mt schema-info <session-id>
aiwf jpa-mt layers

# Another profile with different parameters
aiwf react-component init --component Button --variant primary --with-tests
aiwf react-component preview <session-id>
```

Core commands remain at the top level:

```bash
# Core commands (profile-agnostic)
aiwf step <session-id>
aiwf approve <session-id>
aiwf status <session-id>
aiwf list
aiwf profiles
aiwf providers
aiwf validate
```

### 2. Generic WorkflowState

Replace hardcoded fields with a generic `context` dict:

```python
class WorkflowState(BaseModel):
    # Identity
    session_id: str
    profile: str

    # REMOVED: scope (moved to context - profile-specific concept)
    # REMOVED: entity, table, bounded_context, dev, task_id

    # NEW: Generic context for all profile-specific data
    context: dict[str, Any] = Field(default_factory=dict)

    # State (unchanged)
    phase: WorkflowPhase
    status: WorkflowStatus
    execution_mode: ExecutionMode
    current_iteration: int = 1

    # ... rest unchanged
```

**All** profile-specific data lives in `context`, including `scope`:

```python
# JPA-MT session - scope is a jpa-mt concept for template/layer selection
context = {
    "scope": "domain",
    "entity": "Customer",
    "table": "customer",
    "bounded_context": "sales",
    "schema_file": "./schema.sql",
}

# React component session - no scope concept, different organization
context = {
    "component": "Button",
    "variant": "primary",
    "with_tests": True,
}

# Simple script profile - minimal context
context = {
    "script_name": "deploy.sh",
}
```

**Why `scope` moves to `context`:**

| Consideration | Analysis |
|---------------|----------|
| jpa-mt uses scope for | Template selection (`planning/domain.md`) and layer bundling |
| Other profiles | May have different organizational concepts or none at all |
| Forcing scope on all profiles | Would leak ORM-thinking into generic engine |
| Filtering sessions | `aiwf list --profile jpa-mt` is the natural filter; advanced filtering via `--filter context.scope=domain` if needed |

### 3. Unified Profile Registration

Profiles register **both commands and profile class** via a single entry point. This prevents "commands present, profile missing" failures.

```toml
# pyproject.toml
[project.entry-points."aiwf.profiles"]
jpa-mt = "profiles.jpa_mt:register"
react-component = "profiles.react_component:register"
```

```python
# profiles/jpa_mt/__init__.py
import click
from aiwf.interface.cli.cli import pass_json_context
from .jpa_mt_profile import JpaMtProfile

def register(cli_group: click.Group) -> type[WorkflowProfile]:
    """Register jpa-mt commands and return profile class."""

    @cli_group.command("init")
    @click.option("--scope", required=True, type=click.Choice(["domain", "vertical"]))
    @click.option("--entity", required=True, help="Entity name (e.g., Customer)")
    @click.option("--table", required=True, help="Database table name")
    @click.option("--bounded-context", required=True, help="DDD bounded context")
    @click.option("--schema-file", required=True, type=click.Path(exists=True))
    @click.option("--dev", help="Development environment identifier")
    @click.option("--task-id", help="Task/ticket identifier")
    @pass_json_context
    def init(json_mode, scope, entity, table, bounded_context, schema_file, dev, task_id):
        """Initialize a new JPA multi-tenant workflow session."""
        context = {
            "scope": scope,
            "entity": entity,
            "table": table,
            "bounded_context": bounded_context,
            "schema_file": schema_file,
            "dev": dev,
            "task_id": task_id,
        }
        # Call orchestrator.initialize_run(profile="jpa-mt", context=context)
        ...

    @cli_group.command("schema-info")
    @click.argument("session_id")
    @pass_json_context
    def schema_info(json_mode, session_id):
        """Display parsed schema information for a session."""
        ...

    @cli_group.command("layers")
    @pass_json_context
    def layers(json_mode):
        """List available layers for JPA-MT profile."""
        ...

    # Return profile class for ProfileFactory registration
    return JpaMtProfile
```

**Key change:** The `register()` function returns the `WorkflowProfile` class. The CLI loader registers both commands and the profile atomically.

### 4. CLI Discovery and Loading

The main CLI discovers profiles and registers both commands and profile classes atomically:

```python
# aiwf/interface/cli/cli.py
import click
import logging
from importlib.metadata import entry_points
from aiwf.domain.profiles.profile_factory import ProfileFactory

logger = logging.getLogger(__name__)

@click.group()
@click.option("--json", is_flag=True, help="Output JSON")
@click.pass_context
def cli(ctx, json):
    ctx.ensure_object(dict)
    ctx.obj["json"] = json

# Register core commands
# ... step, approve, status, list, profiles, providers, validate ...

def _discover_and_register_profiles():
    """Discover profiles from entry points and local directory."""

    # 1. Local directory first (~/.aiwf/profiles/<name>/)
    local_dir = Path.home() / ".aiwf" / "profiles"
    if local_dir.exists():
        for profile_dir in local_dir.iterdir():
            if not profile_dir.is_dir():
                continue
            init_file = profile_dir / "__init__.py"
            if not init_file.exists():
                continue
            try:
                spec = importlib.util.spec_from_file_location(
                    f"aiwf_local_profile_{profile_dir.name}",
                    init_file
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if hasattr(module, "register"):
                    profile_group = click.Group(
                        name=profile_dir.name,
                        help=f"Commands for {profile_dir.name} profile"
                    )
                    profile_class = module.register(profile_group)
                    cli.add_command(profile_group)
                    ProfileFactory.register(profile_dir.name, profile_class)
                    logger.debug(f"Loaded local profile: {profile_dir.name}")
            except Exception as e:
                logger.warning(f"Failed to load local profile '{profile_dir.name}': {e}")
                # Continue - don't crash CLI for one bad profile

    # 2. Entry points (installed packages) - override local on collision
    for ep in entry_points(group="aiwf.profiles"):
        try:
            register_fn = ep.load()
            profile_group = click.Group(name=ep.name, help=f"Commands for {ep.name} profile")
            profile_class = register_fn(profile_group)
            cli.add_command(profile_group)
            ProfileFactory.register(ep.name, profile_class)
            logger.debug(f"Loaded installed profile: {ep.name}")
        except Exception as e:
            logger.warning(f"Failed to load profile '{ep.name}': {e}")

# Call at module load time
_discover_and_register_profiles()
```

**Error handling:** Profile load failures are logged as warnings but don't crash the CLI. Users can still use other profiles and core commands.

### 5. Profile Context Schema

Profiles declare their context schema in metadata for validation and documentation:

```python
# profiles/jpa_mt/jpa_mt_profile.py
@classmethod
def get_metadata(cls) -> dict[str, Any]:
    return {
        "name": "jpa-mt",
        "description": "Multi-tenant JPA domain layer generation",
        "target_stack": "Java 21, Spring Data JPA, PostgreSQL",
        "phases": ["planning", "generation", "review", "revision"],
        "context_schema": {
            "scope": {"type": "string", "required": True, "choices": ["domain", "vertical"]},
            "entity": {"type": "string", "required": True},
            "table": {"type": "string", "required": True},
            "bounded_context": {"type": "string", "required": True},
            "schema_file": {"type": "path", "required": True},
            "dev": {"type": "string", "required": False},
            "task_id": {"type": "string", "required": False},
        },
    }
```

The engine validates context against this schema at init time.

### 6. Template Variable Migration

Templates change from top-level variables to context-prefixed:

```markdown
<!-- Before (v1.x) -->
Generate JPA entity for {{entity}} mapped to table {{table}}.

<!-- After (v2.0) -->
Generate JPA entity for {{context.entity}} mapped to table {{context.table}}.
```

### 7. Context Validation

Context is validated at init time, before session creation. Validation happens in the orchestrator using the profile's `context_schema`.

#### Supported Types

| Type | Validation |
|------|------------|
| `string` | Must be a string |
| `int` | Must be an integer |
| `bool` | Must be a boolean |
| `path` | Must be a string; if `exists: true`, file must exist |
| `choice` | Must be one of the specified `choices` |

#### Validation Flow

```python
# aiwf/application/workflow_orchestrator.py
def validate_context(profile_class: type[WorkflowProfile], context: dict) -> list[ValidationError]:
    """Validate context against profile's context_schema."""
    errors = []
    schema = profile_class.get_metadata().get("context_schema", {})

    for field, rules in schema.items():
        value = context.get(field)

        # Required check
        if rules.get("required") and value is None:
            errors.append(ValidationError(field=field, message="Required field missing"))
            continue

        if value is None:
            continue  # Optional field not provided

        # Type check
        field_type = rules.get("type", "string")
        if field_type == "string" and not isinstance(value, str):
            errors.append(ValidationError(field=field, message=f"Expected string, got {type(value).__name__}"))
        elif field_type == "int" and not isinstance(value, int):
            errors.append(ValidationError(field=field, message=f"Expected int, got {type(value).__name__}"))
        elif field_type == "bool" and not isinstance(value, bool):
            errors.append(ValidationError(field=field, message=f"Expected bool, got {type(value).__name__}"))
        elif field_type == "path":
            if not isinstance(value, str):
                errors.append(ValidationError(field=field, message=f"Expected path string, got {type(value).__name__}"))
            elif rules.get("exists") and not Path(value).exists():
                errors.append(ValidationError(field=field, message=f"Path does not exist: {value}"))

        # Choices check
        if "choices" in rules and value not in rules["choices"]:
            errors.append(ValidationError(field=field, message=f"Must be one of {rules['choices']}, got '{value}'"))

    return errors
```

#### Error Output

**Text mode:**
```
Error: Context validation failed for profile 'jpa-mt':
  - entity: Required field missing
  - scope: Must be one of ['domain', 'vertical'], got 'invalid'
```

**JSON mode:**
```json
{
  "schema_version": 1,
  "command": "init",
  "exit_code": 1,
  "error": "Context validation failed",
  "validation_errors": [
    {"field": "entity", "message": "Required field missing"},
    {"field": "scope", "message": "Must be one of ['domain', 'vertical'], got 'invalid'"}
  ]
}
```

### 8. Legacy Init Handling

When a user runs bare `aiwf init` (the removed v1.x command), provide a helpful error:

```python
@cli.command("init", hidden=True)
def legacy_init():
    """Legacy init command - removed in v2.0."""
    profiles = list(ProfileFactory.list_profiles())
    click.echo("Error: 'init' is not a core command in v2.0.", err=True)
    click.echo("", err=True)
    click.echo("Use 'aiwf <profile> init' instead:", err=True)
    for name in profiles:
        click.echo(f"  aiwf {name} init --help", err=True)
    click.echo("", err=True)
    click.echo("Run 'aiwf profiles' for details on available profiles.", err=True)
    raise SystemExit(1)
```

**Example output:**
```
$ aiwf init --entity Foo
Error: 'init' is not a core command in v2.0.

Use 'aiwf <profile> init' instead:
  aiwf jpa-mt init --help
  aiwf react-component init --help

Run 'aiwf profiles' for details on available profiles.
```

---

## Consequences

### Positive

- **Profile autonomy**: Profiles define their own commands and parameters
- **No collisions**: Namespaced commands prevent conflicts between profiles
- **Discoverable**: `aiwf --help` shows all available profile command groups
- **Extensible**: New profiles add commands without engine changes
- **Type-safe context**: Schema validation catches errors early

### Negative

- **Breaking change**: v1.x sessions incompatible (acceptable for v2.0)
- **Template migration**: All templates must update variable references
- **Entry point dependency**: Profiles must be installed as packages (not just dropped in a folder)

### Neutral

- **Learning curve**: Users must learn `aiwf <profile> init` instead of `aiwf init --profile`
- **Two init patterns**: Core has no `init`, each profile has its own

---

## Alternatives Considered

### Alternative A: Generic Init with --param

```bash
aiwf init --profile jpa-mt --param entity=Foo --param table=foo
```

**Rejected because:**
- Poor ergonomics (repeating `--param`)
- No type validation at CLI level
- No profile-specific help text
- Harder to discover required parameters

### Alternative B: Config File for Init

```bash
aiwf init --profile jpa-mt --config ./my-session.yml
```

**Rejected because:**
- Extra file management overhead
- Doesn't solve the command namespace problem
- Still need a way to discover required config keys

### Alternative C: Profile Types with Shared Commands

Define profile "types" (ORM, WebAPI, CLI) that share common command sets.

**Rejected because:**
- Rigid taxonomy that's hard to evolve
- Combinatorial explosion (ORM+WebAPI?)
- Assumes we can predict all profile categories upfront

---

## Implementation Plan

### Phase 1: WorkflowState Generalization

1. Replace named fields with `context: dict[str, Any]`
2. Add `context_schema` to profile metadata
3. Add context validation in orchestrator
4. Update `SessionStore` (no migration needed - clean break)

**Files:**
- `aiwf/domain/models/workflow_state.py`
- `aiwf/domain/profiles/workflow_profile.py`
- `aiwf/application/workflow_orchestrator.py`

### Phase 2: Entry Point Infrastructure

1. Add entry point discovery to CLI
2. Create `register_commands` pattern
3. Document profile command authoring

**Files:**
- `aiwf/interface/cli/cli.py`
- `pyproject.toml`

### Phase 3: Migrate jpa-mt

1. Create `profiles/jpa_mt/commands.py`
2. Move init logic to profile command
3. Add `context_schema` to metadata
4. Update templates to use `{{context.*}}`

**Files:**
- `profiles/jpa_mt/commands.py` (new)
- `profiles/jpa_mt/jpa_mt_profile.py`
- `profiles/jpa_mt/templates/*.md`

### Phase 4: Remove Legacy Init

1. Remove `--entity`, `--table`, etc. from core CLI
2. Remove hardcoded fields from WorkflowState
3. Update documentation

**Files:**
- `aiwf/interface/cli/cli.py`
- `aiwf/domain/models/workflow_state.py`

---

## Migration Breakage Points

The following code locations reference the removed `WorkflowState` fields and must be updated:

### WorkflowState Field References

| File | Line(s) | Current Code | Migration |
|------|---------|--------------|-----------|
| `aiwf/domain/models/workflow_state.py` | 97-104 | `scope`, `entity`, `table`, etc. fields | Remove fields, add `context: dict` |
| `aiwf/application/workflow_orchestrator.py` | 55, 89 | `scope=scope` parameter | Change to `context=context` |
| `aiwf/application/workflow_orchestrator.py` | 260, 775 | `"scope": state.scope` in context dict | Change to `**state.context` spread |
| `aiwf/interface/cli/cli.py` | 93-103, 138 | `--scope`, `--entity` options | Remove from core, move to profile |
| `aiwf/interface/cli/cli.py` | 468 | `scope=state.scope` in list output | Change to `context=state.context` |
| `aiwf/interface/cli/output_models.py` | 52 | `scope: str` in SessionSummary | Change to `context: dict[str, Any]` |

### Template Context References

All templates currently receive top-level variables. After migration, they receive nested context:

| Template Pattern | Before | After |
|------------------|--------|-------|
| Entity reference | `{{entity}}` | `{{context.entity}}` |
| Table reference | `{{table}}` | `{{context.table}}` |
| Scope reference | `{{scope}}` | `{{context.scope}}` |
| Bounded context | `{{bounded_context}}` | `{{context.bounded_context}}` |

**Files to update:**
- `profiles/jpa_mt/templates/**/*.md` (all template files)
- `profiles/jpa_mt/templates/_shared/base.md` (base template)

### Runtime Code Paths

Code that builds template context or reads state fields:

| File | Function | Change Required |
|------|----------|-----------------|
| `profiles/jpa_mt/jpa_mt_profile.py` | `_load_template()` | Access `context.get("scope")` |
| `profiles/jpa_mt/jpa_mt_profile.py` | `generate_*_prompt()` | Pass `state.context` to templates |
| `profiles/jpa_mt/jpa_mt_standards_provider.py` | `create_bundle()` | Access `context.get("scope")` |

### SessionStore Persistence

- **Format:** `context` stored as JSON object in `session.json`
- **No migration needed:** v1.x sessions are incompatible; clean break
- **Serialization:** Standard JSON - strings, ints, bools, nested objects allowed
- **Paths:** Stored as strings; profile responsible for resolution

### Testing Requirements

Add tests to verify:
1. Context validation catches missing required fields
2. Context validation catches invalid types/choices
3. Templates render correctly with `{{context.*}}` variables
4. Legacy `aiwf init` shows helpful error
5. Profile discovery loads both commands and profile class
6. Profile load failures don't crash CLI

---

## Command Structure Summary

### v1.x (Current)

```
aiwf
├── init --profile --scope --entity --table --bounded-context --schema-file
├── step
├── approve
├── status
├── list
├── profiles
└── providers
```

### v2.0 (Proposed)

```
aiwf
├── step <session-id>           # Core
├── approve <session-id>        # Core
├── status <session-id>         # Core
├── list                        # Core
├── profiles                    # Core
├── providers                   # Core
├── validate                    # Core (from ADR-0007)
├── jpa-mt                      # Profile namespace
│   ├── init --scope --entity --table --bounded-context --schema-file
│   ├── schema-info <session-id>
│   └── layers
└── react-component             # Profile namespace (example)
    ├── init --component --variant --with-tests
    └── preview <session-id>
```

---

## Related ADRs

- **ADR-0007**: Plugin Architecture (provider factories, standards provider injection)
- **ADR-0001**: Architecture Overview (Strategy, Factory patterns)

---

## Decisions Made

1. **`scope` moves to `context`** (Option B)
   - `scope` is a jpa-mt concept for template/layer selection, not universal
   - Other profiles may have different organizational concepts or none
   - Session filtering uses `--profile` as primary filter
   - Advanced filtering via `--filter context.key=value` if needed later

2. **Core `init` removed immediately in v2.0.0**
   - Clean break, no users yet
   - No deprecation period needed

3. **Dual profile discovery: entry points + local directory**
   - Entry points for distributed/installed profiles
   - `~/.aiwf/profiles/<name>/` directory scan for local development
   - Entry points take precedence on name collision (installed = official)

4. **Unified profile registration** (commands + profile class)
   - Single `register()` function returns profile class
   - Prevents "commands present, profile missing" failures
   - Entry point: `aiwf.profiles` (not `aiwf.profile_commands`)

### Local Profile Structure

```
~/.aiwf/profiles/
└── my-local-profile/
    ├── __init__.py          # Must define register(group) -> ProfileClass
    ├── my_profile.py        # WorkflowProfile implementation
    └── templates/           # Profile templates
```

| Source | Use Case | Precedence |
|--------|----------|------------|
| `~/.aiwf/profiles/` | Local development, experimentation | Lower (overridden by entry points) |
| Entry points | Distributed/installed profiles | Higher (wins on collision) |