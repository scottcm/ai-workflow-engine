# ADR-0007 Phase 1 Implementation Plan: AI Provider Invocation

**Goal:** Enable AI providers to be invoked during workflow execution, allowing another developer to write custom providers.

**Current State:** Providers are registered via `ProviderFactory` but never invoked. `run_provider()` raises `NotImplementedError`.

---

## Summary of Changes

| File | Change Type | Description |
|------|-------------|-------------|
| `aiwf/domain/errors.py` | NEW | `ProviderError` exception class |
| `aiwf/domain/providers/ai_provider.py` | MODIFY | Sync signature, add `validate()`, add timeouts |
| `aiwf/domain/providers/manual_provider.py` | MODIFY | Return `None`, add `validate()` |
| `aiwf/application/approval_handler.py` | MODIFY | Implement `run_provider()` with timeout handling |
| `aiwf/application/workflow_orchestrator.py` | MODIFY | Call `validate()` at init, catch `ProviderError` |
| Tests | NEW/MODIFY | Unit tests for all changes |

---

## Validation and Timeout Strategy

Per ADR-0007:

| Concern | When | Where |
|---------|------|-------|
| **Validation** | At init time | `workflow_orchestrator.initialize_run()` |
| **Connection timeout** | At provider call | `run_provider()` → `provider.generate()` |
| **Response timeout** | At provider call | `run_provider()` → `provider.generate()` |

**Rationale:**
- `validate()` catches misconfigurations early (missing API key, unreachable endpoint)
- Timeouts protect against runtime network issues and slow responses
- Separating connection vs response timeout allows tuning for different failure modes

---

## Step 1: Create ProviderError Exception

**File:** `aiwf/domain/errors.py` (NEW)

```python
class ProviderError(Exception):
    """Raised when a provider fails (network, auth, timeout, etc.)."""
    pass
```

**Rationale:** Distinct exception type allows approval handler to catch provider-specific failures and set appropriate error state.

---

## Step 2: Update AIProvider Interface

**File:** `aiwf/domain/providers/ai_provider.py`

### Changes:

1. **Remove `async` from `generate()`** - CLI is sequential, no benefit from async
2. **Add `timeout` parameter** - Prevent indefinite hangs
3. **Change return type to `str | None`** - `None` signals manual mode
4. **Add `validate()` method** - Fail-fast at init time
5. **Update metadata** - Add timeout defaults

### New Interface:

```python
from abc import ABC, abstractmethod
from typing import Any


class AIProvider(ABC):
    """Abstract interface for AI providers (Strategy pattern)"""

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        """Return provider metadata for discovery commands.

        Returns:
            dict with keys: name, description, requires_config, config_keys,
                           default_connection_timeout, default_response_timeout
        """
        return {
            "name": "unknown",
            "description": "No description available",
            "requires_config": False,
            "config_keys": [],
            "default_connection_timeout": 10,   # seconds
            "default_response_timeout": 300,    # 5 minutes
        }

    @abstractmethod
    def validate(self) -> None:
        """Verify provider is accessible and configured correctly.

        Called at init time before workflow execution begins.
        Implementations should check API keys, connectivity, etc.

        Raises:
            ProviderError: If provider is misconfigured or unreachable
        """
        ...

    @abstractmethod
    def generate(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
    ) -> str | None:
        """Generate AI response for the given prompt.

        Args:
            prompt: The prompt text to send to the AI
            context: Optional context dictionary (metadata, settings, etc.)
            connection_timeout: Timeout for establishing connection (None = use default)
            response_timeout: Timeout for receiving response (None = use default)

        Returns:
            Response string, or None for ManualProvider (signals user provides response)

        Raises:
            ProviderError: If the provider call fails (network, auth, timeout, etc.)
        """
        ...
```

### Breaking Change Note:

This changes the method signature from:
- `async def generate(self, prompt: str, context: ...) -> str`

To:
- `def generate(self, prompt: str, context: ..., timeout: ...) -> str | None`

Any existing provider implementations must be updated.

---

## Step 3: Update ManualProvider

**File:** `aiwf/domain/providers/manual_provider.py`

### Changes:

1. **Return `None` instead of `""`** - Explicitly signals "user will provide response"
2. **Remove `async`** - Match new interface
3. **Add timeout parameters** - Match interface (ignored for manual)
4. **Implement `validate()`** - No-op for manual (no external dependencies)

### New Implementation:

```python
from typing import Any

from .ai_provider import AIProvider


class ManualProvider(AIProvider):
    """Human-in-the-loop provider (prompts written to disk)."""

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        """Return manual provider metadata for discovery commands."""
        return {
            "name": "manual",
            "description": "Human-in-the-loop (prompts written to disk)",
            "requires_config": False,
            "config_keys": [],
            "default_connection_timeout": None,  # No timeout for manual
            "default_response_timeout": None,
        }

    def validate(self) -> None:
        """Manual provider has no external dependencies to validate."""
        pass

    def generate(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
    ) -> str | None:
        """Manual provider does not generate responses automatically.

        Returns None to signal that the response file should be
        created by the human operator.
        """
        return None
```

---

## Step 4: Implement run_provider()

**File:** `aiwf/application/approval_handler.py`

### Changes:

1. **Replace stub with actual implementation**
2. **Use ProviderFactory to create provider**
3. **Handle ProviderError**
4. **Pass timeout from metadata**

### New Implementation:

```python
from aiwf.domain.providers.provider_factory import ProviderFactory


def run_provider(provider_key: str, prompt: str) -> str | None:
    """Invoke an AI provider to generate a response.

    Args:
        provider_key: Registered provider key (e.g., "manual", "claude")
        prompt: The prompt text to send

    Returns:
        Response string, or None if provider signals manual mode

    Raises:
        ProviderError: If provider fails (network, auth, timeout, etc.)
        KeyError: If provider_key is not registered
    """
    provider = ProviderFactory.create(provider_key)
    metadata = provider.get_metadata()
    connection_timeout = metadata.get("default_connection_timeout")
    response_timeout = metadata.get("default_response_timeout")

    return provider.generate(
        prompt,
        connection_timeout=connection_timeout,
        response_timeout=response_timeout,
    )
```

### IngPhaseApprovalHandler Behavior (Already Implemented)

The handler at `approval_handler.py:184-190` already correctly handles provider responses:

```python
# EXISTING CODE - No changes needed
response = run_provider(provider_key, prompt_content)

if response is not None:
    response_relpath = spec.response_relpath_template.format(N=state.current_iteration)
    response_path = session_dir / response_relpath
    response_path.parent.mkdir(parents=True, exist_ok=True)
    response_path.write_text(response, encoding="utf-8")

return state
```

**What this does:**
- Calls `run_provider()` to invoke the provider
- If response is `str`: writes to response file
- If response is `None`: no-op (manual mode - user provides response)
- If `ProviderError` raised: propagates up to orchestrator

**No handler changes needed** - only the `run_provider()` stub needs replacement.

### Error Handling Strategy

**Decision:** Errors propagate to orchestrator level.

**Rationale:**
- `run_provider()` has no access to `state` or `event_emitter`
- Passing them would create tight coupling
- Orchestrator already has the error handling pattern
- Single responsibility: `run_provider()` invokes, orchestrator manages state

The orchestrator's `approve()` method already catches exceptions and sets error state:

```python
# In workflow_orchestrator.py approve() method (existing)
except (FileNotFoundError, ValueError) as e:
    state.status = WorkflowStatus.ERROR
    state.last_error = str(e)
    self.session_store.save(state)
    self._emit(WorkflowEventType.WORKFLOW_FAILED, state)
    return state
```

**Change needed:** Add `ProviderError` to the caught exceptions:

```python
from aiwf.domain.errors import ProviderError

# In approve() method
except (FileNotFoundError, ValueError, ProviderError) as e:
    ...
```

---

## Step 5: Update Orchestrator Error Handling

**File:** `aiwf/application/workflow_orchestrator.py`

### Changes:

1. **Import ProviderError**
2. **Catch ProviderError in approve()**

### Location: Line 155-160

```python
# Before
except (FileNotFoundError, ValueError) as e:

# After
from aiwf.domain.errors import ProviderError
...
except (FileNotFoundError, ValueError, ProviderError) as e:
```

---

## Step 6: Tests

### New Test Files:

1. **`tests/unit/domain/test_errors.py`** - ProviderError basics
2. **`tests/unit/domain/providers/test_ai_provider_contract.py`** - Interface contract tests
3. **`tests/unit/application/test_run_provider.py`** - run_provider() tests

### Modified Test Files:

1. **`tests/unit/domain/providers/test_manual_provider.py`** - Update for new signature
2. **`tests/unit/application/test_approval_ing_phases.py`** - Update mocks

### Test Cases for run_provider():

```python
class TestRunProvider:
    def test_run_provider_invokes_factory_and_generate(self):
        """run_provider creates provider and calls generate()."""
        # Mock ProviderFactory.create to return mock provider
        # Assert generate() called with prompt and timeout

    def test_run_provider_returns_none_for_manual(self):
        """run_provider returns None when ManualProvider returns None."""

    def test_run_provider_propagates_provider_error(self):
        """run_provider lets ProviderError propagate."""

    def test_run_provider_raises_keyerror_for_unknown_provider(self):
        """run_provider raises KeyError for unregistered provider."""
```

### Test Cases for AIProvider Contract:

```python
class TestAIProviderContract:
    def test_generate_is_not_async(self):
        """generate() method is synchronous."""

    def test_generate_accepts_timeout_parameter(self):
        """generate() accepts optional timeout parameter."""

    def test_validate_has_default_implementation(self):
        """validate() has default no-op implementation."""

    def test_metadata_includes_default_timeout(self):
        """get_metadata() includes default_timeout key."""
```

---

## Implementation Order

1. **Create `aiwf/domain/errors.py`** - No dependencies
2. **Update `ai_provider.py`** - New interface
3. **Update `manual_provider.py`** - Implement new interface
4. **Add provider contract tests** - Verify interface
5. **Implement `run_provider()`** - Core change
6. **Update orchestrator error handling** - Catch ProviderError
7. **Update/add tests** - Full coverage
8. **Run full test suite** - Verify no regressions

---

## Verification Checklist

- [ ] `ProviderError` can be raised and caught
- [ ] `AIProvider.generate()` is synchronous
- [ ] `AIProvider.generate()` accepts connection_timeout and response_timeout parameters
- [ ] `AIProvider.generate()` can return `None`
- [ ] `AIProvider.validate()` is abstract (must be implemented)
- [ ] `ManualProvider.validate()` is no-op
- [ ] `ManualProvider.generate()` returns `None`
- [ ] `run_provider("manual", ...)` returns `None`
- [ ] `run_provider("unknown", ...)` raises `KeyError`
- [ ] `ProviderError` from generate() propagates to orchestrator
- [ ] Orchestrator validates providers at init time
- [ ] Orchestrator catches `ProviderError` and sets ERROR status
- [ ] All existing tests pass
- [ ] New tests provide coverage for all changes

---

## What This Enables

After this implementation, another developer can:

1. **Create a new provider:**
```python
from aiwf.domain.providers.ai_provider import AIProvider
from aiwf.domain.errors import ProviderError

class ClaudeProvider(AIProvider):
    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.api_key = self.config.get("api_key")

    @classmethod
    def get_metadata(cls):
        return {
            "name": "claude",
            "description": "Anthropic Claude API",
            "requires_config": True,
            "config_keys": ["api_key"],
            "default_connection_timeout": 10,
            "default_response_timeout": 300,
        }

    def validate(self) -> None:
        if not self.api_key:
            raise ProviderError("API key not configured")
        # Could also ping API to verify connectivity

    def generate(
        self,
        prompt: str,
        context: dict | None = None,
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
    ) -> str | None:
        # Call Claude API with timeouts
        # Raise ProviderError on failure
        return response_text
```

2. **Register it:**
```python
from aiwf.domain.providers.provider_factory import ProviderFactory
ProviderFactory.register("claude", ClaudeProvider)
```

3. **Use it:**
```bash
aiwf init --profile jpa-mt --entity Order --providers "planner:claude"
aiwf approve abc123
```

---

## Step 5.5: Add Provider Validation at Init Time

**File:** `aiwf/application/workflow_orchestrator.py`

### Changes:

Add validation of all configured providers during `initialize_run()`.

### Location: After provider map is established in `initialize_run()`

```python
def initialize_run(self, ..., providers: dict[str, str], ...) -> str:
    # ... existing setup ...

    # Validate all configured providers before creating session
    for role, provider_key in providers.items():
        provider = ProviderFactory.create(provider_key)
        provider.validate()  # Raises ProviderError if misconfigured

    # ... continue with session creation ...
```

**Rationale:** Fail fast at init time rather than mid-workflow during approve().

---

## Out of Scope (Phase 2+)

- `aiwf validate` CLI command
- StandardsProviderFactory
- Standards provider injection
- Provider configuration files
- `--skip-validation` flag

---

## Future Schema Changes (For Awareness)

Phase 1 does not require schema changes to `WorkflowState`. However, future phases will likely add:

| Field | ADR | Purpose |
|-------|-----|---------|
| `standards_provider: str \| None` | ADR-0007 | Track which standards provider was used |
| `generation_params: dict` | ADR-0009 | Per-phase generation parameters |

These are documented here so the other developer is aware they're coming, but they're not needed for Phase 1 AI provider work.