# ADR-0007 Phase 2 Implementation Plan: Standards Provider Factory

**Goal:** Allow standards provider injection for enterprise flexibility, enabling companies to swap standards sources (file-based, RAG, API) without modifying profiles.

**Current State:** Standards providers are tightly coupled to profiles. Each profile creates its own standards provider via `get_standards_provider()`. There's no factory, no validation, and no CLI option to override.

---

## Summary of Changes

| File | Change Type | Description |
|------|-------------|-------------|
| `aiwf/domain/standards/standards_provider_factory.py` | NEW | Factory for standards provider registration/creation |
| `aiwf/application/standards_provider.py` | MODIFY | Add `validate()` to protocol, add timeout param |
| `aiwf/domain/models/workflow_state.py` | MODIFY | Add `standards_provider` field |
| `aiwf/application/workflow_orchestrator.py` | MODIFY | Use factory, validate at init, store in state |
| `aiwf/interface/cli/cli.py` | MODIFY | Add `--standards-provider` option, add `validate` command |
| `aiwf/interface/cli/output_models.py` | MODIFY | Add validation output models |
| `aiwf/domain/standards/scoped_layer_fs_provider.py` | NEW | Scope→layer→file provider with `validate()` |
| Tests | NEW/MODIFY | Unit tests for all changes |

---

## Architecture Overview

### Current Flow (Coupled)

```
Profile.get_standards_provider()
    ↓
ScopedLayerFsProvider (hardcoded creation)
    ↓
create_bundle(context)
```

### New Flow (Decoupled)

```
CLI --standards-provider OR config OR profile default
    ↓
StandardsProviderFactory.create(key)
    ↓
provider.validate()  ← Fail fast
    ↓
provider.create_bundle(context)
```

### Resolution Precedence

```
1. CLI --standards-provider flag (if provided)
2. Profile's default (via get_default_standards_provider_key())
```

**Note:** The middle "config file" layer is intentionally omitted. The profile IS the configuration source for standards providers. If a config file override is desired, that's Phase 3 ergonomics.

---

## Step 1: Create StandardsProviderFactory

**File:** `aiwf/domain/standards/standards_provider_factory.py` (NEW)

```python
from typing import Any, Type

from aiwf.application.standards_provider import StandardsProvider


class StandardsProviderFactory:
    """Factory for creating standards provider instances.

    Follows the same pattern as ProviderFactory for AI providers.
    """

    _registry: dict[str, Type[StandardsProvider]] = {}

    @classmethod
    def register(cls, key: str, provider_class: Type[StandardsProvider]) -> None:
        """Register a standards provider class.

        Args:
            key: Unique identifier for the provider (e.g., "jpa-mt-file")
            provider_class: Class implementing StandardsProvider protocol
        """
        cls._registry[key] = provider_class

    @classmethod
    def create(cls, key: str, config: dict[str, Any] | None = None) -> StandardsProvider:
        """Create a standards provider instance.

        Args:
            key: Registered provider key
            config: Optional configuration dict passed to provider constructor

        Returns:
            Configured StandardsProvider instance

        Raises:
            KeyError: If provider key is not registered
        """
        if key not in cls._registry:
            raise KeyError(f"Standards provider '{key}' not registered")

        provider_class = cls._registry[key]
        return provider_class(config) if config else provider_class({})

    @classmethod
    def list_providers(cls) -> list[str]:
        """Return list of registered provider keys."""
        return list(cls._registry.keys())

    @classmethod
    def is_registered(cls, key: str) -> bool:
        """Check if a provider key is registered."""
        return key in cls._registry
```

**Directory:** Create `aiwf/domain/standards/` with `__init__.py`.

---

## Step 2: Update StandardsProvider Protocol

**File:** `aiwf/application/standards_provider.py`

### Changes:

1. **Add `validate()` method** - Fail-fast verification
2. **Add `get_metadata()` classmethod** - For discovery/listing with dual timeouts
3. **Add dual timeout parameters to `create_bundle()`** - Consistent with AI providers per ADR-0007

### New Interface:

```python
from typing import Protocol, Any


class StandardsProvider(Protocol):
    """Protocol for standards bundle providers.

    Implementations retrieve standards from various sources:
    - File-based (current JpaMtStandardsProvider)
    - RAG/vector database
    - REST API
    - Database
    """

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        """Return provider metadata for discovery commands.

        Returns:
            dict with keys: name, description, requires_config, config_keys,
                           default_connection_timeout, default_response_timeout
        """
        ...

    def validate(self) -> None:
        """Verify provider is accessible and configured correctly.

        Called at init time before workflow execution begins.
        Implementations should check paths exist, connections work, etc.

        Raises:
            ProviderError: If provider is misconfigured or unreachable
        """
        ...

    def create_bundle(
        self,
        context: dict[str, Any],
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
    ) -> str:
        """Create standards bundle for the given context.

        Args:
            context: Workflow context (scope, entity, etc.)
            connection_timeout: Timeout for establishing connection/accessing path
            response_timeout: Timeout for reading/receiving all data

        Returns:
            Concatenated standards bundle as string

        Raises:
            ProviderError: If bundle creation fails or times out
            ValueError: If context is invalid (e.g., unknown scope)
        """
        ...
```

---

## Step 3: Create ScopedLayerFsProvider

**File:** `aiwf/domain/standards/scoped_layer_fs_provider.py`

### Changes:

1. **Add `get_metadata()` classmethod** with dual timeouts
2. **Add `validate()` method** - Check standards_root exists, files readable
3. **Add dual timeout parameters** with timeout enforcement for file I/O
4. **Register with factory**

### Timeout Rationale for File-Based Providers

File I/O can hang or be slow in real-world scenarios:
- Network-mounted drives (NFS, SMB/CIFS)
- Overloaded storage systems
- Disk I/O contention / failing drives
- Cloud-mounted storage (S3FS, Azure Files)
- VPN-accessed file shares with latency

Default timeouts for file-based providers:
| Timeout | Default | Rationale |
|---------|---------|-----------|
| `connection_timeout` | 5 seconds | Time to access/stat the file path |
| `response_timeout` | 30 seconds | Time to read all standards files |

### Updated Implementation:

```python
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Any

from aiwf.domain.errors import ProviderError


class ScopedLayerFsProvider:
    """Scope-aware filesystem standards provider.

    Selects standards files based on scope→layer mappings:
    1. Scope defines which layers are active
    2. Each layer maps to a list of standards files
    3. Files are read from filesystem and concatenated
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.standards_root = Path(config.get('standards', {}).get('root', ''))
        self.scopes = config.get('scopes', {})
        self.layer_standards = config.get('layer_standards', {})

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        return {
            "name": "scoped-layer-fs",
            "description": "Scope-aware filesystem standards provider",
            "requires_config": True,
            "config_keys": ["standards.root", "scopes", "layer_standards"],
            "default_connection_timeout": 5,   # seconds to access path
            "default_response_timeout": 30,    # seconds to read all files
        }

    def validate(self) -> None:
        """Verify standards root exists and is readable."""
        if not self.standards_root:
            raise ProviderError("Standards root not configured")

        if not self.standards_root.exists():
            raise ProviderError(f"Standards root not found: {self.standards_root}")

        if not self.standards_root.is_dir():
            raise ProviderError(f"Standards root is not a directory: {self.standards_root}")

        # Optionally verify at least one scope's files exist
        # (Full validation happens at create_bundle time)

    def create_bundle(
        self,
        context: dict[str, Any],
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
    ) -> str:
        """Create standards bundle with timeout protection.

        Uses ThreadPoolExecutor to enforce timeout on file I/O operations,
        protecting against hung network mounts or slow storage.
        """
        # Use provided timeouts or fall back to defaults
        metadata = self.get_metadata()
        conn_timeout = connection_timeout or metadata["default_connection_timeout"]
        resp_timeout = response_timeout or metadata["default_response_timeout"]

        # Total timeout for the entire operation
        total_timeout = conn_timeout + resp_timeout

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self._read_files, context)
            try:
                return future.result(timeout=total_timeout)
            except FuturesTimeoutError:
                raise ProviderError(
                    f"Standards read timed out after {total_timeout}s"
                )

    def _read_files(self, context: dict[str, Any]) -> str:
        """Internal method to read and concatenate standards files."""
        # ... existing implementation moved here ...
```

### Registration:

```python
# In aiwf/domain/standards/__init__.py
from aiwf.domain.standards.standards_provider_factory import StandardsProviderFactory
from aiwf.domain.standards.scoped_layer_fs_provider import ScopedLayerFsProvider

StandardsProviderFactory.register("scoped-layer-fs", ScopedLayerFsProvider)
```

---

## Step 4: Update WorkflowState

**File:** `aiwf/domain/models/workflow_state.py`

### Add Field:

```python
class WorkflowState(BaseModel):
    # ... existing fields ...

    standards_provider: str = Field(
        default="",
        description="Standards provider key used for this session"
    )
```

**Note:** Default empty string maintains backward compatibility with existing sessions.

---

## Step 5: Update WorkflowOrchestrator

**File:** `aiwf/application/workflow_orchestrator.py`

### Changes:

1. **Accept `standards_provider` parameter in `initialize_run()`**
2. **Use factory to create provider**
3. **Validate standards provider at init**
4. **Store provider key in state**
5. **Clean up session dir on validation failure**

### Updated `initialize_run()`:

```python
def initialize_run(
    self,
    profile: str,
    providers: dict[str, str],
    scope: str,
    entity: str,
    bounded_context: str,
    standards_provider: str | None = None,  # NEW parameter
    # ... other params ...
) -> str:
    # ... session dir creation ...

    # Create initial state with standards_provider field
    state = WorkflowState(
        # ... existing fields ...
        standards_provider=standards_provider or "",  # Will be resolved below
    )

    # Validate all configured AI providers
    try:
        for role, provider_key in providers.items():
            ai_provider = ProviderFactory.create(provider_key)
            ai_provider.validate()
    except (KeyError, ProviderError):
        shutil.rmtree(session_dir, ignore_errors=True)
        raise

    # Resolve and validate standards provider
    profile_instance = ProfileFactory.create(profile)
    profile_instance.validate_metadata(metadata)

    # Resolution: CLI > config > profile default
    resolved_standards_provider = standards_provider
    if not resolved_standards_provider:
        resolved_standards_provider = profile_instance.get_default_standards_provider_key()

    # Create and validate standards provider
    try:
        from aiwf.domain.standards.standards_provider_factory import StandardsProviderFactory

        # Get config from profile for the standards provider
        standards_config = profile_instance.get_standards_config()
        sp = StandardsProviderFactory.create(resolved_standards_provider, standards_config)
        sp.validate()

        state.standards_provider = resolved_standards_provider
    except (KeyError, ProviderError):
        shutil.rmtree(session_dir, ignore_errors=True)
        raise

    # ... rest of initialization using sp.create_bundle() ...
```

---

## Step 6: Update WorkflowProfile ABC

**File:** `aiwf/domain/profiles/workflow_profile.py`

### Add Methods:

```python
class WorkflowProfile(ABC):
    # ... existing methods ...

    def get_default_standards_provider_key(self) -> str:
        """Return the default standards provider key for this profile.

        Returns:
            Registered standards provider key (e.g., "scoped-layer-fs")
        """
        # Default implementation - profiles should override
        raise NotImplementedError("Profile must define default standards provider")

    def get_standards_config(self) -> dict[str, Any]:
        """Return configuration dict for standards provider.

        This config is passed to StandardsProviderFactory.create().

        Returns:
            Configuration dict with provider-specific settings
        """
        # Default implementation - profiles should override
        return {}
```

### Remove `get_standards_provider()`:

The existing `get_standards_provider()` abstract method is removed from `WorkflowProfile`. This is a v2.0 breaking change - all profiles must implement the new factory-based methods.

**Rationale:** This is a v2.0 fork with no backward compatibility requirements. Clean break is preferred over deprecation warnings.

---

## Step 7: Update CLI

**File:** `aiwf/interface/cli/cli.py`

### Add `--standards-provider` Option to `init`:

```python
@cli.command("init")
@click.option("--scope", required=True, type=str)
@click.option("--entity", required=True, type=str)
# ... existing options ...
@click.option(
    "--standards-provider",
    "standards_provider",
    required=False,
    type=str,
    help="Standards provider key (overrides config and profile default)",
)
@click.pass_context
def init_cmd(
    ctx: click.Context,
    scope: str,
    entity: str,
    # ... existing params ...
    standards_provider: str | None,
) -> None:
    # Pass to orchestrator
    session_id = orchestrator.initialize_run(
        # ... existing params ...
        standards_provider=standards_provider,
    )
```

### Add `validate` Command:

```python
@cli.command("validate")
@click.argument("provider_type", type=click.Choice(["ai", "standards", "all"]))
@click.argument("provider_key", required=False)
@click.pass_context
def validate_cmd(
    ctx: click.Context,
    provider_type: str,
    provider_key: str | None,
) -> None:
    """Validate provider configuration.

    Examples:
        aiwf validate ai claude
        aiwf validate standards scoped-layer-fs
        aiwf validate ai  # validates all AI providers
        aiwf validate all  # validates everything
    """
    from aiwf.domain.providers.provider_factory import ProviderFactory
    from aiwf.domain.standards.standards_provider_factory import StandardsProviderFactory
    from aiwf.domain.errors import ProviderError

    results = []

    if provider_type in ("ai", "all"):
        if provider_key and provider_type == "ai":
            # Validate specific AI provider
            results.extend(_validate_ai_provider(provider_key))
        else:
            # Validate all AI providers
            for key in ProviderFactory.list_providers():
                results.extend(_validate_ai_provider(key))

    if provider_type in ("standards", "all"):
        if provider_key and provider_type == "standards":
            # Validate specific standards provider
            results.extend(_validate_standards_provider(provider_key))
        else:
            # Validate all standards providers
            for key in StandardsProviderFactory.list_providers():
                results.extend(_validate_standards_provider(key))

    # Output results
    if ctx.obj.get("json"):
        output = ValidationOutput(
            schema_version="1.0",
            results=results,
            all_passed=all(r.passed for r in results),
        )
        click.echo(output.model_dump_json(indent=2))
    else:
        for r in results:
            status = "OK" if r.passed else "FAILED"
            click.echo(f"  {r.provider_key}: {status}")
            if r.error:
                click.echo(f"    {r.error}")

        passed = sum(1 for r in results if r.passed)
        click.echo(f"\n{passed} of {len(results)} providers ready.")

    # Exit code
    if not all(r.passed for r in results):
        ctx.exit(1)


def _validate_ai_provider(key: str) -> list[ValidationResult]:
    """Validate a single AI provider."""
    try:
        provider = ProviderFactory.create(key)
        provider.validate()
        return [ValidationResult(provider_type="ai", provider_key=key, passed=True)]
    except ProviderError as e:
        return [ValidationResult(provider_type="ai", provider_key=key, passed=False, error=str(e))]
    except KeyError:
        return [ValidationResult(provider_type="ai", provider_key=key, passed=False, error="Not registered")]


def _validate_standards_provider(key: str, profile_key: str | None) -> list[ValidationResult]:
    """Validate a single standards provider.

    Standards providers require config from a profile. If no profile is specified,
    uses the project's configured profile from load_config().
    """
    try:
        # Get config from profile
        cfg = load_config(project_root=Path.cwd(), user_home=Path.home())
        profile_to_use = profile_key or cfg["profile"]

        profile_instance = ProfileFactory.create(profile_to_use)
        standards_config = profile_instance.get_standards_config()

        provider = StandardsProviderFactory.create(key, standards_config)
        provider.validate()
        return [ValidationResult(provider_type="standards", provider_key=key, passed=True)]
    except ProviderError as e:
        return [ValidationResult(provider_type="standards", provider_key=key, passed=False, error=str(e))]
    except KeyError as e:
        return [ValidationResult(provider_type="standards", provider_key=key, passed=False, error=f"Not registered: {e}")]
```

**Note:** The validate command requires profile context to get standards provider config. Add `--profile` option:

```python
@cli.command("validate")
@click.argument("provider_type", type=click.Choice(["ai", "standards", "all"]))
@click.argument("provider_key", required=False)
@click.option("--profile", "profile_key", required=False, type=str,
              help="Profile to use for standards provider config (defaults to project config)")
```

---

## Step 8: Add Output Models

**File:** `aiwf/interface/cli/output_models.py`

```python
class ValidationResult(BaseModel):
    """Result of validating a single provider."""
    provider_type: str  # "ai" or "standards"
    provider_key: str
    passed: bool
    error: str | None = None


class ValidationOutput(BaseModel):
    """Output for validate command."""
    schema_version: str = "1.0"
    results: list[ValidationResult]
    all_passed: bool
```

---

## Step 9: Tests

### New Test Files:

1. **`tests/unit/domain/standards/test_standards_provider_factory.py`**
2. **`tests/unit/application/test_standards_provider_validation.py`**
3. **`tests/unit/interface/test_validate_command.py`**

### Test Cases for StandardsProviderFactory:

```python
class TestStandardsProviderFactory:
    def test_register_and_create(self):
        """Factory can register and create providers."""

    def test_create_unknown_raises_keyerror(self):
        """Creating unknown provider raises KeyError."""

    def test_list_providers_returns_registered_keys(self):
        """list_providers returns all registered keys."""

    def test_is_registered(self):
        """is_registered correctly checks registry."""
```

### Test Cases for Standards Provider Validation:

```python
class TestStandardsProviderValidation:
    def test_scoped_layer_fs_validates_existing_root(self):
        """ScopedLayerFsProvider validates when root exists."""

    def test_scoped_layer_fs_fails_missing_root(self):
        """ScopedLayerFsProvider raises ProviderError for missing root."""

    def test_initialize_run_validates_standards_provider(self):
        """initialize_run calls validate() on standards provider."""

    def test_initialize_run_cleans_up_on_standards_validation_failure(self):
        """Session dir cleaned up when standards validation fails."""
```

### Test Cases for Validate Command:

```python
class TestValidateCommand:
    def test_validate_ai_provider(self):
        """validate ai <key> validates specific AI provider."""

    def test_validate_all_ai_providers(self):
        """validate ai validates all registered AI providers."""

    def test_validate_standards_provider(self):
        """validate standards <key> validates specific standards provider."""

    def test_validate_all(self):
        """validate all validates all providers of all types."""

    def test_exit_code_on_failure(self):
        """Exit code is 1 when any validation fails."""

    def test_json_output(self):
        """--json flag produces valid JSON output."""
```

---

## Implementation Order

1. **Create `aiwf/domain/standards/` directory** with `__init__.py`
2. **Create `StandardsProviderFactory`** - No dependencies
3. **Update `StandardsProvider` protocol** - Add validate(), get_metadata()
4. **Create `ScopedLayerFsProvider`** - Implement new interface
5. **Add factory registration** - In profile module
6. **Update `WorkflowState`** - Add standards_provider field
7. **Update `WorkflowProfile` ABC** - Add new methods
8. **Update `WorkflowOrchestrator`** - Use factory, validate
9. **Update CLI** - Add --standards-provider and validate command
10. **Add output models** - ValidationResult, ValidationOutput
11. **Add tests** - Factory, validation, CLI
12. **Run full test suite** - Verify no regressions

---

## Verification Checklist

- [ ] `StandardsProviderFactory` can register and create providers
- [ ] `StandardsProviderFactory.create()` raises `KeyError` for unknown keys
- [ ] `StandardsProvider.validate()` is called at init time
- [ ] `ScopedLayerFsProvider.validate()` checks standards_root exists
- [ ] `ScopedLayerFsProvider` registered with factory as "scoped-layer-fs"
- [ ] `WorkflowState` has `standards_provider` field
- [ ] `initialize_run()` accepts `standards_provider` parameter
- [ ] `initialize_run()` resolves provider: CLI > config > profile default
- [ ] `initialize_run()` validates standards provider before continuing
- [ ] Session dir cleaned up on standards validation failure
- [ ] `aiwf init --standards-provider <key>` works
- [ ] `aiwf validate ai` lists and validates AI providers
- [ ] `aiwf validate standards` lists and validates standards providers
- [ ] `aiwf validate all` validates everything
- [ ] Exit code is 1 when validation fails
- [ ] JSON output works for validate command
- [ ] All existing tests pass
- [ ] New tests provide coverage for all changes

---

## Backward Compatibility

**This is a v2.0 breaking change.** No backward compatibility is provided.

### Session State Migration

Existing sessions without `standards_provider` field:
- Default value is empty string `""`
- Orchestrator treats empty as "use profile default"
- No migration needed

### Profile Breaking Changes

All profiles must be updated:
- Implement `get_default_standards_provider_key()` - returns provider key
- Implement `get_standards_config()` - returns config dict
- Remove `get_standards_provider()` - no longer used

---

## What This Enables

After this implementation:

1. **Enterprise flexibility:**
```bash
# Use RAG-based standards instead of files
aiwf init --scope domain --entity Order --standards-provider rag-standards
```

2. **Validation before workflow:**
```bash
# Check all providers are configured correctly
aiwf validate all
```

3. **Provider discovery:**
```bash
# List available standards providers
aiwf list standards  # (Phase 3)
```

4. **Custom standards providers:**
```python
from aiwf.domain.standards.standards_provider_factory import StandardsProviderFactory
from aiwf.domain.errors import ProviderError


class RAGStandardsProvider:
    def __init__(self, config: dict):
        self.config = config

    @classmethod
    def get_metadata(cls) -> dict:
        return {
            "name": "rag-standards",
            "description": "RAG-based standards provider",
            "requires_config": True,
            "config_keys": ["vector_db_url"],
            "default_connection_timeout": 10,
            "default_response_timeout": 60,
        }

    def validate(self) -> None:
        if not self.config.get("vector_db_url"):
            raise ProviderError("vector_db_url not configured")
        # Check vector DB connection...

    def create_bundle(
        self,
        context: dict,
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
    ) -> str:
        # Query RAG, return concatenated standards
        ...


StandardsProviderFactory.register("rag-standards", RAGStandardsProvider)
```

---

## Out of Scope (Phase 3)

- `aiwf list ai` command
- `aiwf list standards` command
- `aiwf list profiles` command
- Default provider in config file
- Per-phase provider overrides
- Provider configuration file format

---

## Open Questions

~~1. **Config passing:** How should standards provider config be passed when using CLI override?~~
**Resolved:** Config comes from the profile via `get_standards_config()`. The validate command uses `--profile` option to specify which profile's config to use.

~~2. **Timeout parameter:** Is timeout needed for file-based providers?~~
**Resolved:** Yes. File I/O can hang on network mounts, slow storage, etc. File-based providers use 5s connection + 30s response defaults with `ThreadPoolExecutor` timeout enforcement.

~~3. **Provider key naming:** Should we enforce a naming convention (e.g., `<profile>-<type>` like `jpa-mt-file`)?~~
**Resolved:** No profile-specific naming. Use descriptive keys based on behavior (e.g., `scoped-layer-fs`, `rag-standards`). The provider is profile-agnostic; profiles just reference keys.