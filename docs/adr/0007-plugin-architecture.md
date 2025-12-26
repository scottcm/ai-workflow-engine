# ADR-0007: Plugin Architecture for Extensible Workflow Components

**Status:** Draft
**Date:** December 25, 2024
**Deciders:** Scott

---

## Context and Problem Statement

The AI Workflow Engine needs to support flexible composition of three major component types:

1. **Profiles** - Define HOW code is generated (prompt templates, response parsing, file extraction)
2. **Standards Providers** - Define HOW standards are retrieved (file-based, RAG, API, database)
3. **AI Providers** - Define HOW LLMs are invoked (Claude, GPT, Gemini, manual)

Currently, these components are partially pluggable but have hardcoded dependencies that prevent full flexibility:

```
User Goal: ANY profile + ANY standards provider + ANY AI provider
Current State: Profile → (hardcoded) → StandardsProvider
               Provider role → (hardcoded) → "manual" only
```

---

## Value Proposition

### Why Decouple Standards Providers from Profiles?

Profiles should only care about **what** they receive (a standards bundle string), not **how** it's retrieved.

**Current coupling problem:**
```
Profile → knows config schema → creates StandardsProvider → reads files
```

**Decoupled design:**
```
Profile → requests standards bundle → doesn't care how it's generated
          ↑
    StandardsProvider (injected)
          ↑
    Could be: FileBasedProvider, RAGProvider, APIProvider, etc.
```

**Enterprise migration scenarios:**

| Scenario | Current Design | Decoupled Design |
|----------|----------------|------------------|
| Company uses file-based standards | Works | Works |
| Company migrates to RAG | Must modify profile | Swap provider, profile unchanged |
| Company uses API-served standards | Must modify profile | Swap provider, profile unchanged |
| Different teams, different standards sources | Fork profile | Same profile, different provider |

### Configuration Separation

Currently, profile config mixes concerns:

| Config Element | Belongs To |
|----------------|------------|
| `scopes`, `layers`, prompt templates | Profile (what layers exist, how to generate) |
| `standards.root`, `layer_standards` | Standards Provider (where/how to retrieve) |

Decoupling requires moving standards-related config to the standards provider.

---

## Value Assessment

| Feature | Priority | Value | Reasoning |
|---------|----------|-------|-----------|
| Fix `run_provider()` | HIGH | Bug fix | Providers registered but never invoked - blocking |
| Sync provider interface | HIGH | Bug fix | Async/sync mismatch prevents provider calls - blocking |
| Provider validation | HIGH | Reliability | Fail fast on misconfiguration |
| Provider error/timeout handling | HIGH | Reliability | Prevent hangs, surface failures clearly |
| Standards Provider Factory | HIGH | Enterprise | Enables RAG/API migration without profile changes |
| Standards config separation | HIGH | Clean design | Separation of concerns |
| Per-phase provider config | MEDIUM | Flexibility | Already works, just needs `run_provider()` fixed |
| Config file for providers | LOW | Ergonomics | Defer - CLI args work fine |

---

## Decision Drivers

1. Users should be able to mix and match components freely
2. Manual mode (copy/paste prompts) must remain first-class
3. Configuration should be simple for common cases, powerful for advanced cases
4. New plugins should be addable without modifying engine code
5. Companies should be able to change infrastructure (file → RAG) without forking profiles
6. Providers must fail fast and not hang indefinitely

---

## Current Architecture Analysis

### What's Already Pluggable

| Component | Mechanism | Status |
|-----------|-----------|--------|
| Profiles | `ProfileFactory.register(key, class)` | ✅ Works |
| AI Providers | `ProviderFactory.register(key, class)` | ⚠️ Registered but not invoked |
| Standards Providers | Protocol (duck typing) | ❌ Not factory-based, hardcoded to profile |

### Gaps Identified

#### Gap 1: `run_provider()` Not Implemented

**File:** `aiwf/application/approval_handler.py:92-93`
```python
def run_provider(provider_key: str, prompt: str) -> str | None:
    raise NotImplementedError("Provider execution is not implemented in scaffolding")
```

**Impact:** AI providers are registered via factory but never actually invoked. The approval flow always hits this `NotImplementedError`.

#### Gap 2: Sync/Async Mismatch

**File:** `aiwf/domain/providers/ai_provider.py:22-23`
```python
@abstractmethod
async def generate(self, prompt: str, context: dict[str, Any] | None = None) -> str:
```

**File:** `aiwf/application/approval_handler.py` (entire file is sync)

**Impact:** `AIProvider.generate()` is async, but the approval handler chain is synchronous. Cannot call async method from sync context without asyncio infrastructure.

#### Gap 3: Standards Providers Hardcoded to Profiles

**File:** `aiwf/domain/profiles/workflow_profile.py:43`
```python
def get_standards_provider(self) -> StandardsProvider:
```

**File:** `profiles/jpa_mt/jpa_mt_profile.py:57`
```python
def get_standards_provider(self) -> StandardsProvider:
    return JpaMtStandardsProvider(self.config)  # Hardcoded!
```

**Impact:** Each profile creates its own standards provider internally. No way to inject a different provider. Companies cannot migrate from file-based to RAG without modifying profiles.

#### Gap 4: Mixed Configuration Concerns

**File:** `profiles/jpa_mt/config.yml` (conceptual)

Profile config currently contains both profile concerns (scopes, layers) and standards provider concerns (file paths, layer mappings). These should be separate.

---

## Proposed Solutions

### Solution 1: Implement Provider Invocation

**Approach:** Replace `run_provider()` stub with actual factory-based invocation.

**Sync vs Async Decision:**

| Option | Pros | Cons |
|--------|------|------|
| A: Make approval_handler async | Clean async throughout | Breaks existing sync callers, CLI complexity |
| B: Use asyncio.run() at call site | Minimal changes | Nested event loop issues |
| C: Sync wrapper in AIProvider | Keeps approval_handler sync | Each provider implements sync version |
| **D: Sync AIProvider interface** | Simplest, providers can internally asyncify | Limits concurrent calls (acceptable for CLI) |

**Recommendation:** Option D - Change `AIProvider.generate()` to synchronous. CLI is inherently sequential. Providers that need async internally can use `asyncio.run()` in their implementation.

```python
# Before
async def generate(self, prompt: str, context: dict[str, Any] | None = None) -> str:

# After
def generate(self, prompt: str, context: dict[str, Any] | None = None) -> str | None:
```

### Solution 2: Standards Provider Factory

**Approach:** Create `StandardsProviderFactory` parallel to `ProfileFactory` and `ProviderFactory`.

```python
class StandardsProviderFactory:
    _registry: dict[str, type[StandardsProvider]] = {}

    @classmethod
    def register(cls, key: str, provider_class: type[StandardsProvider]) -> None:
        cls._registry[key] = provider_class

    @classmethod
    def create(cls, key: str, config: dict[str, Any]) -> StandardsProvider:
        if key not in cls._registry:
            raise KeyError(f"Standards provider '{key}' not found")
        return cls._registry[key](config)
```

### Solution 3: Per-Phase Provider Configuration

**Current:** Session stores `providers: dict[str, str]` mapping role → provider key.

```python
providers = {"planning": "manual", "generating": "claude", ...}
```

**This already supports per-phase configuration!** The gap is that providers aren't invoked.

### Solution 4: Provider Selection Precedence

Provider selection is resolved **once at init time** and stored in session state:

```
Resolution Order:
1. CLI --providers flag (e.g., --providers "planner:claude,generator:manual")
2. Default: "manual" for all roles if not specified
```

Session state becomes the source of truth. No runtime resolution needed.

```python
# At init
state.providers = {
    "planner": "claude",      # from CLI
    "generator": "manual",    # from CLI
    "reviewer": "manual",     # default
    "reviser": "manual",      # default
}

# At approve time
provider_key = state.providers[spec.provider_role]  # simple lookup
```

---

## Provider Validation

Providers implement `validate()` to verify accessibility before workflow execution:

```python
class AIProvider(ABC):
    @abstractmethod
    def validate(self) -> None:
        """
        Verify provider is accessible and configured correctly.
        Called at init time before session creation.

        Raises:
            ProviderError: If provider is misconfigured or unreachable
        """
        ...
```

### What validate() Checks

| Provider Type | Validation |
|---------------|------------|
| FileBasedStandardsProvider | Root directory exists, files readable |
| RAGStandardsProvider | Database connection works, index accessible |
| APIStandardsProvider | Endpoint reachable, auth valid |
| ClaudeProvider | API key valid, endpoint responds |
| ManualProvider | Always valid (no external dependency) |

### Validation CLI Command

```bash
# Validate specific provider
aiwf validate ai ollama
aiwf validate standards rag-standards

# Validate all registered providers of a type
aiwf validate ai
aiwf validate standards

# Validate everything
aiwf validate all
```

**Output example:**
```bash
$ aiwf validate ai
Validating AI providers...

  manual: OK (no external dependencies)
  ollama: FAILED
    Connection refused (http://localhost:11434)
  claude: OK

2 of 3 providers ready.
```

**Exit codes:**
| Scenario | Exit Code |
|----------|-----------|
| All validated providers OK | 0 |
| Any provider failed | 1 |
| Provider not found | 2 |

### Validation at Init Time

`aiwf init` automatically validates all specified providers:
- Fails fast if any provider is unreachable
- Use `--skip-validation` to bypass (offline/CI scenarios)

---

## Provider Error and Timeout Handling

### Timeout Configuration

Different provider types need different timeouts:

| Provider Type | Default Connection Timeout | Default Response Timeout |
|---------------|---------------------------|-------------------------|
| FileBasedStandardsProvider | 5 seconds | 5 seconds |
| RAGStandardsProvider | 10 seconds | 30 seconds |
| APIStandardsProvider | 10 seconds | 30 seconds |
| ClaudeProvider / AI Providers | 10 seconds | 5 minutes |
| ManualProvider | N/A | N/A (returns None immediately) |

Timeouts are defined in provider metadata:

```python
@classmethod
def get_metadata(cls) -> dict[str, Any]:
    return {
        "name": "claude",
        "default_connection_timeout": 10,
        "default_response_timeout": 300,
    }
```

### Error Handling

Providers raise `ProviderError` on failure. Engine handles errors consistently:

```python
# In run_provider()
try:
    response = provider.generate(prompt, timeout=timeout)
except ProviderError as e:
    state.status = WorkflowStatus.ERROR
    state.last_error = f"Provider '{provider_key}' failed: {e}"
    emit(WorkflowEventType.WORKFLOW_FAILED, state)
    return state
```

### Provider Contract

| Return Value | Meaning |
|--------------|---------|
| `str` | Success - response content |
| `None` | ManualProvider only - user will provide response |
| `ProviderError` raised | Failure - network, auth, timeout, etc. |

Providers MUST NOT:
- Hang indefinitely (respect timeouts)
- Return empty string for errors (raise ProviderError instead)
- Swallow exceptions silently

---

## Migration Path

### Profile and Standards Provider Decoupling

This is a **breaking change** for profiles, not for end users.

**Phase 1 (This ADR):**
- Add `StandardsProviderFactory`
- Add `--standards-provider` CLI option
- Existing profiles with `get_standards_provider()` continue to work
- New profiles can omit `get_standards_provider()` if standards provider is always injected

**Phase 2 (Future):**
- Deprecate `get_standards_provider()` on WorkflowProfile
- Require `--standards-provider` for profiles that don't provide their own
- Migrate existing profiles

**Key insight:** Profiles that want full decoupling must be written for it. Legacy profiles (JPA-MT) continue working until explicitly migrated.

### No False Fallback

Once a profile is decoupled, it has **no knowledge** of standards retrieval. There is no fallback - the standards provider must be specified:

```bash
# Decoupled profile - standards provider required
aiwf init --profile decoupled-profile --standards-provider rag-standards

# Legacy profile - uses internal standards provider
aiwf init --profile jpa-mt
```

---

## WorkflowState Schema Changes

### New Fields

```python
class WorkflowState(BaseModel):
    # Existing fields...

    # NEW: Standards provider key (None = use legacy profile method)
    standards_provider: str | None = None

    # EXISTING: Provider map per role (no change needed)
    providers: dict[str, str] = Field(default_factory=dict)
```

### Field Semantics

| Field | Value | Behavior |
|-------|-------|----------|
| `standards_provider` | `None` | Use `profile.get_standards_provider()` (legacy) |
| `standards_provider` | `"rag-standards"` | Use `StandardsProviderFactory.create("rag-standards")` |
| `providers` | `{"planner": "manual", ...}` | Map role → provider key (unchanged) |

### Session Migration

Existing sessions have no `standards_provider` field. Migration strategy:

1. **Deserialization**: Missing field defaults to `None`
2. **Behavior**: `None` triggers legacy path (`profile.get_standards_provider()`)
3. **No data migration needed**: Existing sessions continue working unchanged

### Orchestrator Logic

```python
# At init time
if standards_provider_key:  # CLI arg provided
    state.standards_provider = standards_provider_key
    provider = StandardsProviderFactory.create(standards_provider_key, config)
else:
    state.standards_provider = None  # Legacy mode
    provider = profile.get_standards_provider()

# Provider is used, state is saved with the key (or None)
```

---

## Plugin Registration

Plugins self-register at import time using existing factory pattern:

```python
# In profiles/my_profile/__init__.py
from aiwf.domain.profiles.profile_factory import ProfileFactory
from .my_profile import MyProfile

ProfileFactory.register("my-profile", MyProfile)
```

```python
# In providers/ollama/__init__.py
from aiwf.domain.providers.provider_factory import ProviderFactory
from .ollama_provider import OllamaProvider

ProviderFactory.register("ollama", OllamaProvider)
```

Discovery via CLI (future):
```bash
aiwf list profiles
aiwf list ai
aiwf list standards
```

---

## Information Flow Between Components

### Current Flow

```
User Request
    │
    ▼
┌─────────────────────────────────┐
│  CLI: aiwf init --profile X     │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│  ProfileFactory.create("X")     │
│  → Instantiates profile         │
│  → Profile loads its config     │
│  → Profile creates standards    │
│     provider (HARDCODED)        │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│  Orchestrator.initialize_run()  │
│  → Calls profile.create_bundle()│
│  → Stores session state with    │
│     providers={role: "manual"}  │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│  Orchestrator.step() loop       │
│  → Profile generates prompts    │
│  → Engine writes prompt files   │
│  → (User provides responses)    │
│  → Profile parses responses     │
│  → Engine executes write plans  │
└─────────────────────────────────┘
```

### Proposed Flow

```
User Request
    │
    ▼
┌─────────────────────────────────────────────┐
│  CLI: aiwf init --profile X                 │
│       --standards-provider Y                │
│       --providers "planner:claude,          │
│                    generator:manual"        │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│  Create and validate providers              │
│  → ProfileFactory.create("X")               │
│  → StandardsProviderFactory.create("Y")     │
│  → ProviderFactory.create("claude")         │
│  → Call validate() on each                  │
│  → Fail fast if any validation fails        │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│  Orchestrator.initialize_run()              │
│  → Uses injected standards provider         │
│  → Stores providers map in session          │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│  Orchestrator.approve() on ING phases       │
│  → Looks up provider for current role       │
│  → ProviderFactory.create(provider_key)     │
│  → provider.generate(prompt, timeout=...)   │
│  → On success: write response to file       │
│  → On failure: ERROR status, emit event     │
│  → On None: no-op (manual mode)             │
└─────────────────────────────────────────────┘
```

---

## Implementation Phases

### Phase 1: Provider Invocation (Priority: HIGH)

**Goal:** Make registered AI providers actually callable with proper error handling.

**Changes:**
1. Change `AIProvider.generate()` from async to sync
2. Add `validate()` method to AIProvider and StandardsProvider
3. Add timeout parameter to `generate()` and `create_bundle()`
4. Update `ManualProvider.generate()` to return `None`
5. Implement `run_provider()` to use `ProviderFactory`
6. Add error handling: catch `ProviderError`, set ERROR status, emit event
7. Update `IngPhaseApprovalHandler` to handle provider response

**Files:**
- `aiwf/domain/providers/ai_provider.py` - Change signature, add validate()
- `aiwf/domain/providers/manual_provider.py` - Update implementation
- `aiwf/application/approval_handler.py` - Implement `run_provider()`
- `aiwf/domain/errors.py` - Add `ProviderError`

### Phase 2: Standards Provider Factory (Priority: HIGH)

**Goal:** Allow standards provider injection for enterprise flexibility.

**Changes:**
1. Create `StandardsProviderFactory`
2. Add `validate()` to StandardsProvider protocol
3. Add `--standards-provider` CLI option
4. Store standards provider key in session state
5. Modify orchestrator to use injected provider
6. Add `aiwf validate` CLI command

**Files:**
- `aiwf/domain/standards/standards_provider_factory.py` - New
- `aiwf/application/standards_provider.py` - Add validate() to protocol
- `aiwf/interface/cli/cli.py` - Add options and validate command
- `aiwf/domain/models/workflow_state.py` - Add field
- `aiwf/application/workflow_orchestrator.py` - Use factory

### Phase 3: Provider Configuration Ergonomics (Priority: LOW)

**Goal:** Simplify per-phase provider configuration.

**Changes:**
1. Support `default` provider in config
2. Support per-phase overrides
3. Add `aiwf list` commands for discovery

---

## ADRs/Decisions Needed

| # | Decision | Recommendation |
|---|----------|----------------|
| 1 | Sync vs async for provider invocation | Sync (CLI is sequential) |
| 2 | Standards provider injection mechanism | Factory, required for decoupled profiles |
| 3 | Provider configuration format | Role-based map resolved at init |
| 4 | Plugin discovery mechanism | Explicit registration, list commands |
| 5 | Timeout defaults | Per-provider-type via metadata |
| 6 | Error handling | ProviderError → ERROR status + event |

---

## Risk Assessment

### Risk 1: Breaking ManualProvider Contract

**Risk:** Manual mode users expect step() to create prompt, then wait for manual response.
**Mitigation:** `ManualProvider.generate()` returns `None`, signaling "no response yet."
**Severity:** Medium
**Contingency:** Feature flag to disable provider invocation.

### Risk 2: Async Migration Complexity

**Risk:** Changing `AIProvider.generate()` to sync breaks existing provider implementations.
**Mitigation:** Only one provider exists (ManualProvider). Change is trivial.
**Severity:** Low
**Contingency:** N/A - no external providers yet.

### Risk 3: Configuration Complexity

**Risk:** Too many configuration options confuse users.
**Mitigation:** Good defaults (all phases use "manual").
**Severity:** Low
**Contingency:** Simplify CLI options.

### Risk 4: Plugin Loading/Discovery

**Risk:** Users don't know how to register custom plugins.
**Mitigation:** Clear documentation, example plugins, `aiwf list` commands.
**Severity:** Medium
**Contingency:** Add detailed plugin authoring guide.

### Risk 5: Provider Timeout Tuning

**Risk:** Default timeouts too short for complex generations or too long for failures.
**Mitigation:** Sensible defaults based on provider type, allow override via config.
**Severity:** Low
**Contingency:** Make timeouts configurable per-session.

### Risk 6: Network Failures During Workflow

**Risk:** Provider becomes unreachable mid-workflow.
**Mitigation:** Clear error status, event emission, user can retry after fixing.
**Severity:** Medium
**Contingency:** Workflow state preserved, can resume after provider fixed.

---

## Testing Strategy

1. **Unit tests** for each factory (existing pattern)
2. **Unit tests** for validate() methods
3. **Unit tests** for timeout and error handling
4. **Integration tests** for provider invocation flow
5. **Integration tests** for validation at init
6. **E2E tests** with mocked external providers
7. **E2E tests** for validate CLI command
8. **Manual testing** with actual Claude API (once ClaudeProvider implemented)

---

## Related Decisions

- ADR-0001: Architecture Overview
- ADR-0005: Chain of Responsibility for Approval
- ADR-0006: Observer Pattern for Workflow Events

---

## Appendix: Component Interfaces

### AIProvider (Proposed)

```python
class AIProvider(ABC):
    @classmethod
    @abstractmethod
    def get_metadata(cls) -> dict[str, Any]:
        """Return provider metadata including default timeouts."""
        return {
            "name": "provider-name",
            "description": "Provider description",
            "default_connection_timeout": 10,
            "default_response_timeout": 300,
        }

    @abstractmethod
    def validate(self) -> None:
        """
        Verify provider is accessible and configured correctly.
        Called at init time before session creation.

        Raises:
            ProviderError: If provider is misconfigured or unreachable
        """
        ...

    @abstractmethod
    def generate(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        timeout: int | None = None,
    ) -> str | None:
        """
        Generate AI response for the given prompt.

        Args:
            prompt: The prompt text
            context: Optional metadata
            timeout: Response timeout in seconds (None = use default)

        Returns:
            Response string, or None for ManualProvider

        Raises:
            ProviderError: On failure (network, auth, timeout, etc.)
        """
        ...
```

### StandardsProvider (Proposed)

```python
class StandardsProvider(Protocol):
    def validate(self) -> None:
        """Verify provider is accessible. Raises ProviderError if not."""
        ...

    def create_bundle(
        self,
        context: dict[str, Any],
        timeout: int | None = None,
    ) -> str:
        """
        Create standards bundle.

        Raises:
            ProviderError: On failure
        """
        ...
```

### WorkflowProfile (Existing - Deprecated Path)

```python
class WorkflowProfile(ABC):
    @abstractmethod
    def get_standards_provider(self) -> StandardsProvider:
        """
        Legacy method for profiles that manage their own standards.
        Deprecated: New profiles should use injected standards provider.
        """
        ...
```

### ProviderError

```python
class ProviderError(Exception):
    """Raised when a provider fails (network, auth, timeout, etc.)."""
    pass
```