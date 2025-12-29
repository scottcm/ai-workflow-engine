# Phase 3: Provider Capability Metadata - Implementation Guide

**Goal:** Providers advertise capabilities that affect how the engine assembles prompts.

**Dependencies:** None (can run in parallel with Phases 1, 2)

**TDD Approach:** This phase has clear interfaces with well-defined precedence rules. Write tests first to specify the behavior, then implement to pass.

---

## Overview

Add three new metadata fields to the provider interface:
- `fs_ability`: Filesystem capability (local-write, local-read, write-only, none)
- `supports_system_prompt`: Can receive separate system instructions
- `supports_file_attachments`: Can receive file references/attachments

Add CLI and config support for overriding fs_ability (especially for ManualProvider).

**fs_ability values:**
- `"local-write"`: Can read and write local files (Claude Code, Aider, Cursor)
- `"local-read"`: Can read local files but not write (read-only IDE plugins)
- `"write-only"`: Can create downloadable files but no local access (Claude.ai web)
- `"none"`: No file capabilities (Gemini web chat, basic chat interfaces)

---

## Step 1: Write Tests First

Write tests before any implementation. These tests define the expected behavior.

### 1.1 Provider Metadata Tests

**File:** `tests/unit/domain/providers/test_ai_provider.py`

```python
"""Tests for AI provider capability metadata."""

import pytest
from aiwf.domain.providers.ai_provider import AIProvider
from aiwf.domain.providers.manual_provider import ManualProvider


class TestProviderCapabilityMetadata:
    """Tests for provider capability metadata fields."""

    def test_default_metadata_includes_fs_ability(self):
        """Base AIProvider metadata includes fs_ability field."""
        metadata = AIProvider.get_metadata()
        assert "fs_ability" in metadata
        assert metadata["fs_ability"] == "local-write"  # Default: assume best case

    def test_default_metadata_includes_supports_system_prompt(self):
        """Base AIProvider metadata includes supports_system_prompt field."""
        metadata = AIProvider.get_metadata()
        assert "supports_system_prompt" in metadata
        assert metadata["supports_system_prompt"] is False

    def test_default_metadata_includes_supports_file_attachments(self):
        """Base AIProvider metadata includes supports_file_attachments field."""
        metadata = AIProvider.get_metadata()
        assert "supports_file_attachments" in metadata
        assert metadata["supports_file_attachments"] is False

    def test_capability_fields_have_correct_types(self):
        """Capability fields have expected types."""
        metadata = AIProvider.get_metadata()

        # fs_ability is string or None
        assert metadata["fs_ability"] is None or isinstance(metadata["fs_ability"], str)
        # Boolean fields
        assert isinstance(metadata["supports_system_prompt"], bool)
        assert isinstance(metadata["supports_file_attachments"], bool)


class TestManualProviderMetadata:
    """Tests for ManualProvider capability metadata."""

    def test_manual_provider_fs_ability_is_none(self):
        """ManualProvider has fs_ability=None since it depends on where user pastes."""
        metadata = ManualProvider.get_metadata()
        assert metadata["fs_ability"] is None

    def test_manual_provider_no_system_prompt_support(self):
        """ManualProvider doesn't inherently support system prompts."""
        metadata = ManualProvider.get_metadata()
        assert metadata["supports_system_prompt"] is False

    def test_manual_provider_no_file_attachment_support(self):
        """ManualProvider doesn't inherently support file attachments."""
        metadata = ManualProvider.get_metadata()
        assert metadata["supports_file_attachments"] is False
```

### 1.2 fs_ability Resolution Tests

**File:** `tests/unit/application/test_config_loader.py`

```python
"""Tests for fs_ability resolution with precedence rules."""

import pytest
from aiwf.application.config_loader import resolve_fs_ability


class TestResolveFsAbility:
    """Tests for resolve_fs_ability() precedence: CLI > config > provider > default."""

    # --- CLI Override (Highest Precedence) ---

    def test_cli_override_takes_precedence_over_all(self):
        """CLI --fs-ability overrides everything else."""
        result = resolve_fs_ability(
            cli_override="none",
            provider_key="claude-code",
            config={
                "providers": {
                    "defaults": {"fs_ability": "write-only"},
                    "claude-code": {"fs_ability": "local-read"},
                }
            },
            provider_metadata={"fs_ability": "local-write"},
        )
        assert result == "none"

    def test_cli_override_with_empty_config(self):
        """CLI override works with empty config."""
        result = resolve_fs_ability(
            cli_override="local-read",
            provider_key="manual",
            config={},
            provider_metadata={"fs_ability": None},
        )
        assert result == "local-read"

    # --- Per-Provider Config (Second Precedence) ---

    def test_per_provider_config_overrides_defaults_and_metadata(self):
        """Per-provider config overrides global defaults and provider metadata."""
        result = resolve_fs_ability(
            cli_override=None,
            provider_key="manual",
            config={
                "providers": {
                    "defaults": {"fs_ability": "local-write"},
                    "manual": {"fs_ability": "write-only"},
                }
            },
            provider_metadata={"fs_ability": None},
        )
        assert result == "write-only"

    def test_per_provider_config_without_global_defaults(self):
        """Per-provider config works without global defaults section."""
        result = resolve_fs_ability(
            cli_override=None,
            provider_key="claude-code",
            config={
                "providers": {
                    "claude-code": {"fs_ability": "local-write"},
                }
            },
            provider_metadata={"fs_ability": "local-read"},
        )
        assert result == "local-write"

    # --- Global Default Config (Third Precedence) ---

    def test_global_default_overrides_provider_metadata(self):
        """Global default config overrides provider metadata."""
        result = resolve_fs_ability(
            cli_override=None,
            provider_key="some-provider",
            config={
                "providers": {
                    "defaults": {"fs_ability": "none"},
                }
            },
            provider_metadata={"fs_ability": "local-write"},
        )
        assert result == "none"

    def test_global_default_used_when_no_per_provider_config(self):
        """Global default used when provider has no specific config."""
        result = resolve_fs_ability(
            cli_override=None,
            provider_key="unknown-provider",
            config={
                "providers": {
                    "defaults": {"fs_ability": "write-only"},
                    "other-provider": {"fs_ability": "local-write"},
                }
            },
            provider_metadata={"fs_ability": None},
        )
        assert result == "write-only"

    # --- Provider Metadata (Fourth Precedence) ---

    def test_provider_metadata_used_when_no_config(self):
        """Provider metadata used when no CLI or config override."""
        result = resolve_fs_ability(
            cli_override=None,
            provider_key="claude-code",
            config={},
            provider_metadata={"fs_ability": "local-write"},
        )
        assert result == "local-write"

    def test_provider_metadata_used_with_empty_providers_section(self):
        """Provider metadata used when providers section is empty."""
        result = resolve_fs_ability(
            cli_override=None,
            provider_key="claude-code",
            config={"providers": {}},
            provider_metadata={"fs_ability": "local-read"},
        )
        assert result == "local-read"

    # --- Engine Default (Lowest Precedence) ---

    def test_engine_default_when_all_sources_empty(self):
        """Falls back to engine default 'local-write' when all sources empty."""
        result = resolve_fs_ability(
            cli_override=None,
            provider_key="manual",
            config={},
            provider_metadata={},
        )
        assert result == "local-write"

    def test_engine_default_when_provider_metadata_is_none(self):
        """Falls back to engine default when provider metadata fs_ability is None."""
        result = resolve_fs_ability(
            cli_override=None,
            provider_key="manual",
            config={},
            provider_metadata={"fs_ability": None},
        )
        assert result == "local-write"

    def test_engine_default_when_provider_metadata_missing_key(self):
        """Falls back to engine default when provider metadata lacks fs_ability key."""
        result = resolve_fs_ability(
            cli_override=None,
            provider_key="manual",
            config={},
            provider_metadata={"name": "manual"},  # No fs_ability key
        )
        assert result == "local-write"

    # --- Precedence Order Verification ---

    def test_full_precedence_chain(self):
        """Verify complete precedence chain with all sources populated."""
        config = {
            "providers": {
                "defaults": {"fs_ability": "level-3-global"},
                "test-provider": {"fs_ability": "level-2-provider"},
            }
        }
        provider_metadata = {"fs_ability": "level-4-metadata"}

        # CLI wins
        assert resolve_fs_ability("level-1-cli", "test-provider", config, provider_metadata) == "level-1-cli"

        # Per-provider config wins (no CLI)
        assert resolve_fs_ability(None, "test-provider", config, provider_metadata) == "level-2-provider"

        # Global default wins (no CLI, no per-provider)
        config_no_provider = {"providers": {"defaults": {"fs_ability": "level-3-global"}}}
        assert resolve_fs_ability(None, "other-provider", config_no_provider, provider_metadata) == "level-3-global"

        # Provider metadata wins (no CLI, no config)
        assert resolve_fs_ability(None, "test-provider", {}, provider_metadata) == "level-4-metadata"

        # Engine default (nothing else)
        assert resolve_fs_ability(None, "test-provider", {}, {}) == "local-write"
```

### 1.3 CLI Flag Tests

**File:** `tests/integration/test_cli.py` (add to existing)

```python
"""Tests for --fs-ability CLI flag on approve command."""

import pytest
from click.testing import CliRunner
from aiwf.interface.cli.cli import cli


class TestFsAbilityCliFlag:
    """Tests for --fs-ability flag on approve command."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_fs_ability_flag_accepted(self, runner):
        """--fs-ability flag is recognized by approve command."""
        # This tests the CLI accepts the flag (will fail on missing session, that's OK)
        result = runner.invoke(cli, ["approve", "nonexistent", "--fs-ability", "none"])
        # Should not fail with "no such option" error
        assert "no such option" not in result.output.lower()
        assert "--fs-ability" not in result.output or "Error" not in result.output

    def test_fs_ability_invalid_value_rejected(self, runner):
        """Invalid fs_ability value is rejected with helpful error."""
        result = runner.invoke(cli, ["approve", "test-session", "--fs-ability", "invalid-value"])
        assert result.exit_code != 0
        assert "invalid" in result.output.lower() or "choice" in result.output.lower()

    def test_fs_ability_valid_values_accepted(self, runner):
        """All valid fs_ability values are accepted."""
        valid_values = ["local-write", "local-read", "write-only", "none"]
        for value in valid_values:
            result = runner.invoke(cli, ["approve", "test", "--fs-ability", value])
            # Should not fail on the fs-ability value itself
            assert f"'{value}' is not" not in result.output

    def test_fs_ability_help_shows_choices(self, runner):
        """Help text shows available fs_ability choices."""
        result = runner.invoke(cli, ["approve", "--help"])
        assert "--fs-ability" in result.output
        assert "local-write" in result.output
        assert "local-read" in result.output
        assert "write-only" in result.output
        assert "none" in result.output
```

### 1.4 ProviderCapabilities Dataclass Tests

**File:** `tests/unit/application/test_approval_handler.py` (add to existing or new)

```python
"""Tests for ProviderCapabilities dataclass."""

import pytest
from aiwf.application.approval_handler import ProviderCapabilities


class TestProviderCapabilities:
    """Tests for ProviderCapabilities dataclass."""

    def test_create_with_all_fields(self):
        """Can create ProviderCapabilities with all fields."""
        caps = ProviderCapabilities(
            fs_ability="local-write",
            supports_system_prompt=True,
            supports_file_attachments=True,
        )
        assert caps.fs_ability == "local-write"
        assert caps.supports_system_prompt is True
        assert caps.supports_file_attachments is True

    def test_create_with_minimal_capabilities(self):
        """Can create ProviderCapabilities with minimal capabilities."""
        caps = ProviderCapabilities(
            fs_ability="none",
            supports_system_prompt=False,
            supports_file_attachments=False,
        )
        assert caps.fs_ability == "none"
        assert caps.supports_system_prompt is False
        assert caps.supports_file_attachments is False

    def test_all_fs_ability_values_valid(self):
        """All documented fs_ability values can be used."""
        for fs_ability in ["local-write", "local-read", "write-only", "none"]:
            caps = ProviderCapabilities(
                fs_ability=fs_ability,
                supports_system_prompt=False,
                supports_file_attachments=False,
            )
            assert caps.fs_ability == fs_ability
```

---

## Step 2: Implement to Pass Tests

### 2.1 Update Provider Metadata Schema

**File:** `aiwf/domain/providers/ai_provider.py`

```python
@classmethod
def get_metadata(cls) -> dict[str, Any]:
    return {
        "name": "unknown",
        "description": "No description available",
        "requires_config": False,
        "config_keys": [],
        "default_connection_timeout": 10,
        "default_response_timeout": 300,
        # New capability fields
        "fs_ability": "local-write",  # Default: assume best case
        "supports_system_prompt": False,
        "supports_file_attachments": False,
    }
```

### 2.2 Update ManualProvider Metadata

**File:** `aiwf/domain/providers/manual_provider.py`

```python
@classmethod
def get_metadata(cls) -> dict[str, Any]:
    return {
        "name": "manual",
        "description": "Human-in-the-loop (prompts written to disk)",
        "requires_config": False,
        "config_keys": [],
        "default_connection_timeout": None,
        "default_response_timeout": None,
        # ManualProvider: no inherent capability, user specifies via CLI/config
        "fs_ability": None,  # Must be specified by user or use default
        "supports_system_prompt": False,
        "supports_file_attachments": False,
    }
```

### 2.3 Add fs_ability Resolution

**File:** `aiwf/application/config_loader.py`

```python
def resolve_fs_ability(
    cli_override: str | None,
    provider_key: str,
    config: dict[str, Any],
    provider_metadata: dict[str, Any],
) -> str:
    """Resolve fs_ability with precedence: CLI > config > provider > default.

    Args:
        cli_override: Value from --fs-ability CLI flag
        provider_key: Provider name (e.g., "manual", "claude-code")
        config: Loaded config dict
        provider_metadata: Provider's get_metadata() result

    Returns:
        Resolved fs_ability value
    """
    # 1. CLI override (highest precedence)
    if cli_override:
        return cli_override

    # 2. Config: per-provider setting
    providers_config = config.get("providers", {})
    provider_config = providers_config.get(provider_key, {})
    if "fs_ability" in provider_config:
        return provider_config["fs_ability"]

    # 3. Config: global default
    defaults_config = providers_config.get("defaults", {})
    if "fs_ability" in defaults_config:
        return defaults_config["fs_ability"]

    # 4. Provider metadata
    provider_fs_ability = provider_metadata.get("fs_ability")
    if provider_fs_ability:
        return provider_fs_ability

    # 5. Engine default
    return "local-write"
```

### 2.4 Add CLI Flag

**File:** `aiwf/interface/cli/cli.py`

```python
@cli.command("approve")
@click.argument("session_id")
@click.option(
    "--fs-ability",
    type=click.Choice(["local-write", "local-read", "write-only", "none"]),
    default=None,
    help="Override provider's filesystem capability for this invocation",
)
@click.option("--hash-prompts", is_flag=True, help="Compute and store prompt hashes")
@pass_json_context
def approve(json_mode, session_id, fs_ability, hash_prompts):
    """Approve current phase and optionally invoke AI provider."""
    # ... existing logic ...
    # Pass fs_ability to orchestrator.approve()
    result = orchestrator.approve(
        session_id=session_id,
        fs_ability=fs_ability,  # NEW
        hash_prompts=hash_prompts,
    )
```

### 2.5 Add ProviderCapabilities Dataclass

**File:** `aiwf/application/approval_handler.py`

```python
from dataclasses import dataclass


@dataclass
class ProviderCapabilities:
    """Provider capabilities for prompt assembly."""
    fs_ability: str
    supports_system_prompt: bool
    supports_file_attachments: bool
```

### 2.6 Update Orchestrator approve()

**File:** `aiwf/application/workflow_orchestrator.py`

```python
def approve(
    self,
    session_id: str,
    fs_ability: str | None = None,  # NEW
    hash_prompts: bool = False,
) -> WorkflowState:
    """Approve current phase and optionally invoke AI provider."""
    state = self._load_state(session_id)

    # Resolve fs_ability
    provider_key = self._get_provider_for_phase(state)
    provider = ProviderFactory.create(provider_key)
    provider_metadata = provider.get_metadata()

    resolved_fs_ability = resolve_fs_ability(
        cli_override=fs_ability,
        provider_key=provider_key,
        config=self._load_config(),
        provider_metadata=provider_metadata,
    )

    # Store for use in prompt assembly (Phase 5)
    # Could pass to approval handler or store temporarily
    # ...
```

### 2.7 Config File Schema

**File:** Documentation / `aiwf/application/config_loader.py`

Document supported config structure:

```yaml
# Example config.yml structure
providers:
  defaults:
    fs_ability: local-write  # Global default

  manual:
    fs_ability: write-only  # User typically pastes into Claude.ai

  claude-code:
    fs_ability: local-write
    supports_system_prompt: true
    supports_file_attachments: true
```

Update config loader to handle providers section:

```python
def load_config(config_path: Path | None = None) -> dict[str, Any]:
    """Load configuration from YAML file."""
    # ... existing loading logic ...

    # Ensure providers section exists
    config.setdefault("providers", {})
    config["providers"].setdefault("defaults", {})

    return config
```

---

## Step 3: Verify All Tests Pass

Run the test suite:

```bash
poetry run pytest tests/unit/domain/providers/test_ai_provider.py -v
poetry run pytest tests/unit/application/test_config_loader.py::TestResolveFsAbility -v
poetry run pytest tests/unit/application/test_approval_handler.py::TestProviderCapabilities -v
poetry run pytest tests/integration/test_cli.py::TestFsAbilityCliFlag -v
```

All tests should pass before considering the phase complete.

---

## Files Changed

| File | Change |
|------|--------|
| `aiwf/domain/providers/ai_provider.py` | Add capability fields to metadata |
| `aiwf/domain/providers/manual_provider.py` | Set `fs_ability=None` |
| `aiwf/interface/cli/cli.py` | Add `--fs-ability` flag |
| `aiwf/application/config_loader.py` | Add `resolve_fs_ability()` |
| `aiwf/application/workflow_orchestrator.py` | Accept and resolve fs_ability |
| `aiwf/application/approval_handler.py` | Accept capabilities |
| `tests/unit/domain/providers/test_ai_provider.py` | New tests |
| `tests/unit/application/test_config_loader.py` | New tests |
| `tests/integration/test_cli.py` | New tests |

---

## Acceptance Criteria

- [ ] `AIProvider.get_metadata()` returns `fs_ability`, `supports_system_prompt`, `supports_file_attachments`
- [ ] `ManualProvider.get_metadata()` returns `fs_ability=None`
- [ ] `aiwf approve --fs-ability <value>` accepted
- [ ] Invalid fs_ability values rejected with helpful error
- [ ] Config file supports `providers.defaults.fs_ability`
- [ ] Config file supports `providers.<name>.fs_ability`
- [ ] `resolve_fs_ability()` follows documented precedence
- [ ] All tests pass