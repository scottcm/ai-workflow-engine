# ADR-0008: Engine-Profile Separation of Concerns

**Status:** Draft
**Date:** December 26, 2024 (Updated December 29, 2024)
**Deciders:** Scott

---

## Context and Problem Statement

The AI Workflow Engine has several coupling issues between engine, profiles, and providers:

### CLI Parameter Coupling

The `init` command has ORM-specific parameters hardcoded into both the CLI and `WorkflowState`:

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

### Prompt Content Coupling

Profile templates currently contain engine concerns:

1. **Output file instructions** - Templates include hardcoded output filenames ("Save as `generation-response.md`...")
2. **Session artifact paths** - Templates reference session paths (`@.aiwf/sessions/{{SESSION_ID}}/plan.md`)
3. **Engine directory structure** - WritePlan returns full paths like `iteration-{N}/code/filename.java`
4. **Provider-agnostic output** - Templates can't adapt to provider capabilities (local file access vs web chat)

This violates separation of concerns: profiles should focus on domain expertise, not workflow mechanics.

**Version Context:** This is a breaking change for v2.0.0. There are no existing users on v1.x, so this is the right time to make foundational changes.

---

## Decision Drivers

1. **Profile autonomy** - Profiles should define their own parameters without engine changes
2. **Clear namespacing** - Profile commands should not collide with core or other profile commands
3. **Discoverability** - Users should easily find available profile commands
4. **Clean break** - v2.0.0 is not backward-compatible with v1.x sessions
5. **Single-profile sessions** - A session uses exactly one profile (no multi-profile composition)
6. **Engine owns session artifacts** - Plan, standards bundle, prompts, responses, and code directories are engine concerns
7. **Profile owns domain content** - What to generate, how to use standards, output format parsing
8. **Provider capability awareness** - Output instructions must adapt to what the provider can do
9. **Template portability** - Profile templates should work unchanged across different providers

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
```

### 3. Unified Profile Registration

Profiles register **both commands and profile class** via a single entry point:

```toml
# pyproject.toml
[project.entry-points."aiwf.profiles"]
jpa-mt = "profiles.jpa_mt:register"
react-component = "profiles.react_component:register"
```

The `register()` function returns the `WorkflowProfile` class. The CLI loader registers both commands and the profile atomically, preventing "commands present, profile missing" failures.

### 4. Engine vs Profile Responsibilities

| Concern | Owner | Rationale |
|---------|-------|-----------|
| Session artifacts & paths | Engine | Engine manages `.aiwf/sessions/` structure |
| Providing session artifacts to AI | Engine | Plan, standards bundle, previous code |
| Output instructions | Engine | Response filename, save method |
| Workflow transitions | Engine | What happens after pass/fail |
| Domain CLI parameters | Profile | --schema-file, --entity, etc. (via CLI extensions) |
| Domain inputs | Profile | Schema DDL content, entity/table names from context |
| Domain prompt content | Profile | Task description, how to use standards |
| Output format specification | Profile | `<<<FILE:>>>` markers, `@@@REVIEW_META` (profile parses these) |
| Pass/fail determination | Profile | Review verdict logic |

**Key principle:** Profiles should not know about:
- Session directory structure (`.aiwf/sessions/{id}/`)
- Iteration directory structure (`iteration-{N}/`)
- Session artifact filenames (`plan.md`, `standards-bundle.md`)
- Response filenames (`generation-response.md`)
- Session ID or iteration number for path construction

### 5. Provider Capability Metadata

Providers advertise capabilities that affect how the engine assembles prompts:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `fs_ability` | string | `"local-write"` | Filesystem capability |
| `supports_system_prompt` | bool | `False` | Can receive separate system instructions |
| `supports_file_attachments` | bool | `False` | Can receive file references/attachments |

**fs_ability values:**

| Value | Description | Example Provider |
|-------|-------------|------------------|
| `local-write` | Can read and write local files | Claude Code CLI, Aider, Cursor |
| `local-read` | Can read local files but not write | IDE plugins (read-only mode) |
| `write-only` | Can create downloadable files | Claude.ai web chat |
| `none` | No file capabilities (copy/paste only) | Gemini web chat |

**Default behavior:** `local-write` (best case). We default to the most capable option because most modern AI coding tools can write files. If a provider cannot, it typically informs the user and degrades gracefully (displays content for copy/paste, offers download). This "assume capable, degrade gracefully" approach provides better UX for the common case while still supporting less capable providers.

**ManualProvider:** Has no inherent fs_ability since it depends on where the user pastes the prompt. User specifies via CLI flag (`--fs-ability`) or config file.

**Resolution precedence (highest wins):**
1. CLI flag: `--fs-ability local-write`
2. Config file: per-provider or global default
3. Provider metadata: `get_metadata()["fs_ability"]`
4. Engine default: `local-write`

### 6. Engine Prompt Assembly

The engine assembles the final prompt from multiple sources:

```
+----------------------------------------------------------+
|                    FINAL PROMPT                          |
+----------------------------------------------------------+
|  1. Session Artifacts (engine-provided)                  |
|     - Approved plan content                              |
|     - Standards bundle content                           |
|     - Previous code (for review/revision phases)         |
|                                                          |
|  2. Domain Prompt (profile-generated)                    |
|     - Task description                                   |
|     - How to apply standards                             |
|     - Output format instructions (<<<FILE:>>>, etc.)     |
|     - Domain-specific rules                              |
|     - Domain inputs (schema DDL from context)            |
|                                                          |
|  3. Output Instructions (engine-generated)               |
|     - Response filename                                  |
|     - Save/delivery method (based on fs_ability)         |
+----------------------------------------------------------+
```

**Assembly based on provider capabilities:**
- If `supports_system_prompt`: output instructions go in system prompt
- If `supports_file_attachments`: session artifacts provided as file references
- Otherwise: everything inlined in user prompt

These capabilities combine independently: `supports_file_attachments` affects how session artifacts are provided (file references vs inline); `supports_system_prompt` affects where output instructions go (system prompt vs end of user prompt). A provider may support one, both, or neither.

**Rationale:** This separation allows profiles to focus purely on domain content while the engine handles all workflow mechanics. The same profile template works across different providers without modification.

### 7. Output Instructions

Based on resolved `fs_ability`, the engine generates output instructions:

| fs_ability | Instruction |
|------------|-------------|
| `local-write` | "Save your complete response to `{response_path}`" |
| `local-read` | "Name your output file `{response_filename}`" |
| `write-only` | "Create a downloadable file named `{response_filename}`" |
| `none` | (no instruction - user copies response manually) |

Response filenames are derived from existing `ING_APPROVAL_SPECS` - the engine already knows expected response paths.

### 8. WritePlan Path Handling

Profiles return filenames only in WritePlan. Engine adds path prefix when writing:

```python
# Profile returns filename only
WriteOp(path="Customer.java", content=code)

# Engine writes to:
session_dir / f"iteration-{iteration}/code/{write_op.path}"
```

**Rationale:** Profile doesn't know about `iteration-{N}/code/` structure. Engine controls directory layout, making it easier to change directory structure without touching profiles.

### 9. Template Cleanup

Profile templates remove engine concerns:

**Remove:**
- Output destination sections ("Save as `generation-response.md`...")
- Session artifact path references (`@.aiwf/sessions/{{SESSION_ID}}/...`)
- `{{SESSION_ID}}` and `{{ITERATION}}` for path construction

**Keep:**
- Domain variables (`{{ENTITY}}`, `{{TABLE}}`, `{{BOUNDED_CONTEXT}}`)
- Domain inputs (`{{SCHEMA_DDL}}`)
- Output format instructions (`<<<FILE:>>>` markers, `@@@REVIEW_META`)
- Standards application rules

---

## Consequences

### Positive

- **Profile autonomy**: Profiles define their own commands and parameters
- **No collisions**: Namespaced commands prevent conflicts between profiles
- **Discoverable**: `aiwf --help` shows all available profile command groups
- **Clean separation of concerns**: Profiles focus on domain, engine handles workflow mechanics
- **Provider flexibility**: Same profile works with CLI agents, web chat, IDE plugins
- **Maintainability**: Output conventions and session structure change in one place (engine)
- **Template portability**: Profile templates work unchanged across providers
- **Simpler profiles**: No need to know session directory structure

### Negative

- **Breaking change**: v1.x sessions incompatible (acceptable for v2.0 clean break)
- **Template migration**: Existing templates need output destinations and session references removed
- **Engine complexity**: Prompt assembly logic moves to engine
- **Learning curve**: Profile authors must understand what engine provides vs what they provide
- **Configuration complexity**: fs_ability resolution has four precedence levels; ManualProvider users must remember to specify fs_ability via CLI or config for correct output instructions

### Risks and Mitigations

**Misreported provider capabilities:** If a provider claims `local-write` but can't write files, the AI will fail to write and inform the user. No silent data loss occurs - the failure is visible.

**Prompt size constraints:** Inlining large session artifacts may exceed context limits. Future work may add truncation or summarization for very large artifacts.

**Legacy template compatibility:** This is a v2.0 clean break. No migration path for v1.x templates - they must be updated to remove engine concerns. The change is mechanical: delete output destination sections, remove `@.aiwf/sessions/` path references, and update "Required Attachments" sections to reference engine-provided inputs. Changes can be validated with grep (search for `@.aiwf/sessions/`, `Save your complete`, response filename patterns). No profile code changes required beyond template edits.

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

### Alternative C: Engine Variable Resolution

Have the engine resolve `{{{ENGINE_VAR}}}` placeholders in profile templates after profile resolves domain variables.

**Rejected because:**
- Unnecessary complexity - engine can inject content directly
- Profile templates would still need to know about engine variables
- Simpler to have engine append/prepend content rather than resolve placeholders

### Alternative D: fs_ability defaults to `none`

Require users to always specify fs_ability.

**Rejected because:**
- Poor UX for the common case (most AI tools can write files)
- AIs typically degrade gracefully when they can't write
- User override available when needed

---

## Implementation Plan

Implementation is organized into phases. The table below provides an overview; detailed step-by-step guides are in separate implementation plan documents.

| Phase | Name | Summary | Dependencies |
|-------|------|---------|--------------|
| 1 | WorkflowState Generalization | Replace named fields with `context` dict | None |
| 2 | CLI Entry Point Infrastructure | Profile command discovery and registration | None |
| 3 | Provider Capability Metadata | Add fs_ability, supports_system_prompt | None |
| 4 | Profile Migration (jpa-mt) | Migrate jpa-mt to new CLI pattern | 1, 2 |
| 5 | Engine Prompt Assembly | Session artifact injection, output instructions | 3 |
| 6 | WritePlan Simplification | Profile returns filenames only | - |
| 7 | Template Cleanup | Remove engine concerns from templates | 5, 6 |
| 8 | Legacy Init Removal | Remove hardcoded CLI parameters | 4 |

Phases 1, 2, 3 can run in parallel. Phases 5, 6 can run in parallel after their dependencies.

---

## Decisions Made

1. **`scope` moves to `context`**
   - `scope` is a jpa-mt concept for template/layer selection, not universal
   - Other profiles may have different organizational concepts or none
   - Session filtering uses `--profile` as primary filter

2. **Core `init` removed immediately in v2.0.0**
   - Clean break, no users yet
   - No deprecation period needed

3. **Dual profile discovery: entry points + local directory**
   - Entry points for distributed/installed profiles
   - `~/.aiwf/profiles/<name>/` directory scan for local development
   - Entry points take precedence on name collision

4. **Unified profile registration**
   - Single `register()` function returns profile class
   - Prevents "commands present, profile missing" failures

5. **Engine owns session artifacts in prompts**
   - Engine injects plan, standards bundle, previous code
   - Profile templates don't reference session paths
   - Cleaner separation of concerns

6. **fs_ability defaults to `local-write`**
   - Most capable AIs can write files
   - Graceful degradation if they can't
   - User override for ManualProvider via CLI/config

7. **Provider capabilities drive prompt assembly**
   - `supports_system_prompt`: output instructions as system prompt
   - `supports_file_attachments`: session artifacts as file references
   - Otherwise: inline everything in user prompt

8. **WritePlan contains filenames only**
   - Profile returns `Customer.java`, not `iteration-1/code/Customer.java`
   - Engine adds path prefix when writing
   - Profile doesn't know directory structure

9. **Output format stays with profile**
   - `<<<FILE:>>>` markers owned by profile (profile parses them)
   - `@@@REVIEW_META` owned by profile (profile determines verdict)
   - Engine only needs the parsed result (files, pass/fail)

---

## Related ADRs

- **ADR-0007**: Plugin Architecture (provider factories, standards provider injection)
- **ADR-0001**: Architecture Overview (Strategy, Factory patterns)