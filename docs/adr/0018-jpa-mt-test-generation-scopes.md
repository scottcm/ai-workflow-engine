# ADR-0018: JPA-MT Test Generation Scopes

**Status:** Proposed
**Date:** January 15, 2026
**Deciders:** Scott

---

## Context and Problem Statement

The AI Workflow Engine currently generates JPA entities, repositories, services, and controllers via the `jpa-mt` profile with `domain`, `service`, `api`, and `full` scopes. To complete the development workflow, we need to generate tests for this code.

**Key questions:**

1. Should test generation be a separate profile (`jpa-mt-test`) or extend the existing `jpa-mt` profile?
2. Should tests be generated in the same session as code, or in a separate session referencing existing code?
3. How do we handle different test types (unit, integration) with different infrastructure requirements?

**Constraints:**

- Skills Harbor uses PostgreSQL with Row-Level Security (RLS) for tenant isolation
- Tests require different infrastructure: unit tests (no DB), integration tests (testcontainers)
- Schema/security tests are structurally different and will be addressed in a separate ADR
- Token budget concerns: combining code standards + test standards + generated code in one session may be too large

---

## Decision Drivers

1. **Incremental delivery** - Deliver test generation without major engine rearchitecture
2. **Reusable investment** - Work done now should migrate cleanly to future versions
3. **Code-test alignment** - Generated tests must align with source code exactly
4. **Flexibility** - Support tests for engine-generated code AND existing codebase code
5. **Token efficiency** - Keep prompt bundles focused (code OR tests, not both)
6. **Existing infrastructure** - Build on established jpa-mt profile patterns

---

## Considered Options

### Option A: Separate Profile (`jpa-mt-test`)

Create a new profile specifically for test generation.

**Pros:**
- Clean separation
- Independent evolution
- Simpler profile logic

**Cons:**
- User learns new profile
- Duplicate context setup (entity, table, bounded-context)
- No connection to generated code session

### Option B: Extend `jpa-mt` with Test Scope

Add a single `tests` scope to the existing `jpa-mt` profile.

**Pros:**
- Single profile for all JPA development
- Shared configuration and context
- Natural workflow progression
- Leverages existing profile infrastructure

**Cons:**
- More complex profile logic

### Option C: Same-Session Test Generation

Generate code and tests within a single workflow session using an `extend` command or `--with-tests` flag.

**Pros:**
- AI has full context from code generation
- Single audit trail
- Potential prompt caching benefits

**Cons:**
- Large token budget (code standards + test standards + generated code)
- Requires engine changes (multi-cycle sessions, new directory structure)
- More complex implementation

---

## Decision Outcome

**Chosen: Option B with separate-session approach (v2.x)**

Test generation will be added to the `jpa-mt` profile as a `tests` scope. Tests are generated in a **separate session** that references source code via:
- `--source-session <id>` - link to a previous code generation session
- `--source-files <paths>` - provide arbitrary source files

Same-session test generation (`--with-tests`) is deferred to v3, which will introduce multi-cycle sessions and a new directory structure.

**Rationale:**
- Delivers test generation quickly with minimal engine changes
- Profile work (templates, standards, scope logic) is fully reusable in v3
- Engine changes (session linking) are small and carry forward
- Keeps token budgets manageable (separate focused sessions)

---

## Single `tests` Scope

Rather than separate `unit-tests` and `integration-tests` scopes, a single `tests` scope generates all appropriate tests based on what source code is provided. Each layer maps to exactly one test type:

| Layer | Test Type | Test Class | Infrastructure |
|-------|-----------|------------|----------------|
| entity | Unit | `EntityTest.java` | JUnit only |
| repository | Integration | `EntityRepositoryIT.java` | Testcontainers |
| service | Unit | `ServiceTest.java` | JUnit + mocks |
| controller | Unit | `ControllerTest.java` | JUnit + mocks |
| mapper | Unit | `MapperTest.java` | JUnit only |
| dto | - | (no tests) | - |

The profile inspects the provided source artifacts and generates the appropriate test types automatically.

---

## Scope Structure

### Existing Scopes (Code Generation)

| Scope | Layers | Output |
|-------|--------|--------|
| `domain` | entity, repository | Entity.java, EntityRepository.java |
| `service` | service | EntityService.java |
| `api` | controller, dto, mapper | EntityController.java, EntityDto.java, EntityMapper.java |
| `full` | all layers | Complete vertical slice |

### New Scope (Test Generation)

| Scope | Behavior | Output |
|-------|----------|--------|
| `tests` | Generate tests for all provided source artifacts | Test classes matching source layers |

---

## Test Categories

### Unit Tests (entity, service, controller, mapper)

| Category | What to Test | Example |
|----------|--------------|---------|
| Construction | Required fields, defaults | `new Entity(null)` throws |
| Validation | Bean Validation annotations | `@NotBlank`, `@Email` |
| Business methods | State transitions, calculations | `entity.activate()` |
| Invariants | Business rules | Effective dates ordered |
| Equals/hashCode | Business key based | Not ID-based |
| Lifecycle | `onCreate()`, `onUpdate()` | Timestamps set |

**What NOT to test:**
- Getters/setters without logic
- JPA annotations (trust Hibernate)
- Framework-generated code

### Integration Tests (repository)

| Category | What to Test | Example |
|----------|--------------|---------|
| CRUD | Basic operations | Save, find, update, delete |
| Custom queries | Profile-specific queries | `findByClientIdAndStatus()` |
| Constraints | Unique indexes, FK | Duplicate rejection |
| Auditing | Timestamp population | `createdAt` set on save |
| Cascade | Delete behavior | Cascades correctly |
| Tenant isolation | RLS enforcement | Cross-tenant queries fail |

**What NOT to test:**
- Spring Data generated methods (trust framework)
- `findById`, `findAll` unless custom behavior

---

## Source Code Input

Tests can only be generated for code that is provided as input. Three sources are supported:

### 1. From Previous Session (`--source-session`)

```bash
# Generate tests for code from session abc123
aiwf init jpa-mt -c scope=tests --source-session abc123
```

Engine loads artifacts from the referenced session's output directory.

### 2. From Files (`--source-files`)

```bash
# Generate tests for existing codebase files
aiwf init jpa-mt -c scope=tests \
  --source-files src/main/java/.../Subscription.java,src/main/java/.../SubscriptionRepository.java
```

Engine loads specified files as context.

### 3. Same-Session (v3 - Future)

```bash
# Generate code and tests in one session
aiwf init jpa-mt -c scope=domain --with-tests
```

Deferred to v3. Requires multi-cycle session support.

---

## Engine Changes (v2.x)

Minimal changes required:

1. **`--source-session` flag** - Load artifacts from a completed session as input context
2. **`--source-files` flag** - Load arbitrary files as input context
3. **Source artifacts in context** - Pass loaded files to profile for prompt generation

These changes are small and fully reusable in v3.

---

## Profile Changes

### New Scope

```yaml
# profiles/jpa-mt/config.yml

scopes:
  # Existing code generation scopes
  domain:
    layers: [entity, repository]
  service:
    layers: [service]
  api:
    layers: [controller, dto, mapper]
  full:
    layers: [entity, repository, service, controller, dto, mapper]

  # New test generation scope
  tests:
    requires_source: true  # Must have --source-session or --source-files
```

### Standards Assembly

The profile's standards provider inspects source artifacts and assembles appropriate test standards:

- Entity source present → include `TESTING_UNIT.md`
- Repository source present → include `TESTING_INTEGRATION.md`, `TESTCONTAINERS.md`
- Service/controller source present → include `TESTING_UNIT.md`, `TESTING_MOCKING.md`

### Template Structure

```
profiles/jpa-mt/templates/
├── generation/
│   ├── domain.md           # Existing
│   ├── service.md          # Existing
│   ├── api.md              # Existing
│   ├── full.md             # Existing
│   └── tests.md            # NEW - generates all test types
└── _shared/
    └── test-patterns.md    # NEW - common test patterns
```

---

## Session State

### New Context Fields

```python
class WorkflowState(BaseModel):
    context: dict[str, Any]  # Now includes:
    # {
    #   "entity": "Subscription",
    #   "scope": "tests",
    #   "source_session_id": "abc123",     # If --source-session used
    #   "source_files": ["path1", "path2"], # If --source-files used
    #   "source_artifacts": {...},          # Loaded source code content
    # }
```

### Output Location

Tests are written to the standard location: `<session-dir>/iteration-{N}/code/`

No directory structure changes in v2.x.

---

## v3 Roadmap

Future version will add:

1. **Multi-cycle sessions** - Run multiple phase cycles within one session
2. **New directory structure** - `<type>/iteration-{N}/` where type is profile-provided (e.g., `domain/`, `service/`, `api/`, `tests/`)
3. **`Profile.get_cycles()` method** - Profile declares what cycles a workflow needs
4. **`--with-tests` flag** - Same-session test generation
5. **Scope decomposition** - Break `full` scope into `domain` → `service` → `api` cycles

The v2.x implementation migrates cleanly:
- Session linking (`--source-session`, `--source-files`) remains useful for "tests for existing code"
- All profile work (templates, standards, scope logic) carries forward
- Engine changes are additive, not replacements

---

## Implementation Phases

### Phase 1: Engine Support

1. Add `--source-session` flag to `init` command
2. Add `--source-files` flag to `init` command
3. Load source artifacts into session context
4. Pass source artifacts to profile

### Phase 2: Profile `tests` Scope

1. Add `tests` scope to jpa-mt config
2. Create `tests.md` generation template
3. Implement standards assembly based on source artifacts
4. Add test standards documents (`TESTING_UNIT.md`, `TESTING_INTEGRATION.md`, etc.)

### Phase 3: Validation & Polish

1. Test with Skills Harbor entities
2. Handle edge cases (missing sources, partial sources)
3. Documentation and examples

---

## Out of Scope

- **Schema/security tests** - Separate concern, covered in ADR-0019
- **Same-session generation** - Deferred to v3
- **Multi-cycle sessions** - Deferred to v3
- **Directory restructuring** - Deferred to v3
- **Test data factories** - One-time scaffold, not per-entity generation

---

## Consequences

### Positive

1. **Quick delivery** - Test generation without major engine rework
2. **Reusable investment** - All work migrates to v3
3. **Focused sessions** - Smaller token budgets, clearer scope
4. **Flexibility** - Works with engine-generated OR existing code
5. **Single profile** - Users learn one profile for JPA development

### Negative

1. **Two sessions required** - Must run code gen, then test gen separately (until v3)
2. **Manual linking** - User must specify `--source-session` or `--source-files`

### Risks

| Risk | Mitigation |
|------|------------|
| Source artifacts too large for context | Profile can summarize/extract key elements |
| Test quality varies by layer | Clear template boundaries, layer-specific patterns |
| v3 scope creep | ADR documents clear v2.x vs v3 boundary |

---

## Related Decisions

- **ADR-0001**: Architecture Overview (profile/scope model)
- **ADR-0008**: Engine-Profile Separation (context handling)
- **ADR-0012**: Phase+Stage Model (workflow for test generation)
- **ADR-0019**: PostgreSQL Schema Test Profile (separate, for RLS/trigger tests)

---

## Open Questions

1. **Source artifact format** - Should engine pass raw file content or parsed structure?
2. **Partial source handling** - If only entity provided (no repo), generate only entity tests?
3. **Test file naming** - `EntityTest.java` vs `EntityTests.java` vs `EntityUnitTest.java`?