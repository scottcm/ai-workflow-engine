# V2 Workflow Config & Provider Naming – Implementation Plan

**Status:** In Progress (Class Renames Complete)
**Related ADRs:** 0016 (config/naming), 0015 (approval providers)
**Goal:** Implement the unified per-stage workflow config and rename Response Provider to AI Provider. V2 is breaking; no backward compat.

---

## Scope

**In scope:**
- Config models: `StageConfig`, `PhaseConfig`, `WorkflowConfig` with cascade resolution
- Config loader: parse YAML, validate provider keys
- Class renames: ResponseProvider → AIProvider, ResponseProviderFactory → AIProviderFactory
- Update orchestrator to use new config structure
- Update docs/tests

**Out of scope (covered by ADR-0015 spec):**
- ApprovalProvider interface changes
- How approval providers use `allow_rewrite` (already in context per ADR-0015 spec)
- Approval flow changes

---

## Class Renames

| Current Name | New Name | Location |
|--------------|----------|----------|
| `ResponseProvider` | `AIProvider` | `aiwf/domain/providers/response_provider.py` → `ai_provider.py` |
| `ResponseProviderFactory` | `AIProviderFactory` | `aiwf/domain/providers/provider_factory.py` |
| `ManualProvider` | `ManualAIProvider` | `aiwf/domain/providers/manual_provider.py` |
| `ClaudeCodeProvider` | `ClaudeCodeAIProvider` | `aiwf/domain/providers/claude_code_provider.py` |
| `GeminiCliProvider` | `GeminiCliAIProvider` | `aiwf/domain/providers/gemini_cli_provider.py` |
| `ProviderResult` | `AIProviderResult` | `aiwf/domain/models/provider_result.py` → `ai_provider_result.py` |
| `state.providers` | `state.ai_providers` | `aiwf/domain/models/workflow_state.py` |

**Note:** Registration keys remain unchanged (`manual`, `claude-code`, `gemini-cli`).

---

## Work Plan

### 1. Config Models (TDD)

**Spec:**

```python
# New models in aiwf/application/config_models.py

class StageConfig(BaseModel):
    """Unified stage configuration (parsed from YAML).

    Note: ai_provider is only used for RESPONSE stages; ignored for PROMPT.
    """
    ai_provider: str | None = None
    approval_provider: str = "manual"
    approval_max_retries: int = 0
    approval_allow_rewrite: bool = False
    approver_config: dict[str, Any] = Field(default_factory=dict)

class PhaseConfig(BaseModel):
    """Phase configuration with optional stage overrides."""
    prompt: StageConfig | None = None
    response: StageConfig | None = None

class WorkflowConfig(BaseModel):
    """Top-level workflow configuration."""
    defaults: StageConfig = Field(default_factory=StageConfig)
    plan: PhaseConfig | None = None
    generate: PhaseConfig | None = None
    review: PhaseConfig | None = None
    revise: PhaseConfig | None = None

    def get_stage_config(self, phase: WorkflowPhase, stage: WorkflowStage) -> StageConfig:
        """Resolve config for phase/stage with cascade: defaults → phase → stage."""
        ...
```

**Cascade Resolution (`get_stage_config`):**
1. Start with `defaults` values
2. If phase config exists and has stage config, merge stage values (non-None fields override)
3. Return resolved `StageConfig`

**Validation Rules:**
- `ai_provider` required for RESPONSE stages (after cascade resolution)
- `ai_provider` ignored for PROMPT stages (no error if present, just unused)
- Unknown phase names in YAML → error
- Unknown stage names in YAML → error

**Tests (TDD):**
- `test_parse_minimal_config` - defaults only, no phase overrides
- `test_parse_full_config` - all phases and stages specified
- `test_cascade_defaults_to_stage` - stage inherits from defaults
- `test_cascade_stage_overrides_defaults` - stage-level values override defaults
- `test_partial_override_preserves_defaults` - overriding one field preserves others
- `test_response_stage_requires_ai_provider` - validation error if missing after cascade
- `test_prompt_stage_ignores_ai_provider` - no error if ai_provider on prompt
- `test_unknown_phase_rejected` - error on `workflow.foo`
- `test_unknown_stage_rejected` - error on `workflow.plan.bar`
- `test_approver_config_preserved` - dict passed through unchanged

---

### 2. Config Loader Updates (TDD)

**Spec:**

```python
# In aiwf/application/config_loader.py

def load_workflow_config(yaml_path: Path) -> WorkflowConfig:
    """Load and validate workflow configuration from YAML."""
    ...

def validate_provider_keys(config: WorkflowConfig) -> None:
    """Dry-run validation: ensure all AI/approval provider keys resolve.

    Raises:
        ConfigurationError: If any provider key is not registered.
    """
    ...
```

**Validation Flow:**
1. Parse YAML into `WorkflowConfig`
2. For each phase/stage combination:
   - Resolve via `get_stage_config()`
   - Check `ai_provider` key exists in `AIProviderFactory` (RESPONSE only)
   - Check `approval_provider` key exists in `ApprovalProviderFactory` OR `AIProviderFactory` (for wrapping)
3. Fail fast with clear error message if any key unresolved

**Tests (TDD):**
- `test_load_valid_yaml` - parses without error
- `test_load_missing_file` - raises appropriate error
- `test_validate_known_ai_provider` - passes validation
- `test_validate_unknown_ai_provider` - fails with clear message
- `test_validate_known_approval_provider` - passes validation
- `test_validate_ai_provider_as_approval` - passes (wrapping path)
- `test_validate_unknown_approval_provider` - fails with clear message
- `test_validate_all_stages` - iterates all phase/stage combinations

---

### 3. Class Renames (Non-TDD)

**Steps:**
1. Rename files per table above
2. Rename classes per table above
3. Update all imports across codebase
4. Update factory registrations (keys unchanged)
5. Update `WorkflowState.providers` → `WorkflowState.ai_providers`
6. Update docstrings/comments to use "AI provider" terminology

**Verification:** Run full test suite after renames; all existing tests should pass.

---

### 4. AIProviderFactory Updates (TDD)

**Spec:**

```python
# In aiwf/domain/providers/ai_provider_factory.py (renamed)

class AIProviderFactory:
    """Factory for creating AI providers."""

    _registry: ClassVar[dict[str, type[AIProvider]]] = {}

    @classmethod
    def register(cls, key: str, provider_class: type[AIProvider]) -> None:
        """Register an AI provider class."""
        ...

    @classmethod
    def create(cls, key: str) -> AIProvider:
        """Create an AI provider instance by key.

        Raises:
            ProviderError: If key is not registered.
        """
        ...

    @classmethod
    def is_registered(cls, key: str) -> bool:
        """Check if a provider key is registered."""
        ...
```

**Tests (TDD):**
- `test_create_registered_provider` - returns instance
- `test_create_unregistered_provider` - raises ProviderError
- `test_is_registered_true` - returns True for known key
- `test_is_registered_false` - returns False for unknown key

---

### 5. Orchestrator Wiring (TDD)

**Spec:**

```python
# In aiwf/application/workflow_orchestrator.py

class WorkflowOrchestrator:
    def __init__(self, config: WorkflowConfig, ...):
        self.config = config
        ...

    def _get_ai_provider(self, phase: WorkflowPhase) -> AIProvider:
        """Get AI provider for phase's RESPONSE stage."""
        stage_config = self.config.get_stage_config(phase, WorkflowStage.RESPONSE)
        return AIProviderFactory.create(stage_config.ai_provider)

    def _get_stage_config(self, phase: WorkflowPhase, stage: WorkflowStage) -> StageConfig:
        """Get resolved stage config for approval handler."""
        return self.config.get_stage_config(phase, stage)
```

**Integration with existing approval system:**
- Approval handler already reads `allow_rewrite` from context (per ADR-0015 spec)
- Orchestrator builds context with `stage_config.approval_allow_rewrite`
- No changes needed to ApprovalProvider interface

**Tests (TDD):**
- `test_get_ai_provider_from_config` - resolves correct provider
- `test_get_stage_config_cascade` - cascade resolution works through orchestrator
- `test_different_approval_per_stage` - PROMPT vs RESPONSE can differ

---

### 6. Documentation Updates (Non-TDD)

**Files to Update:**
- `README.md` - Configuration section, provider terminology
- `docs/adr/0015-approval-provider-implementation.md` - Config examples
- `docs/plans/adr0015-approval-providers.md` - Update config examples
- `API-CONTRACT.md` - Config schema if documented
- Inline docstrings throughout codebase

**Changes:**
- Replace "response provider" with "AI provider"
- Update all config examples to unified per-stage structure
- Add v2 breaking change notes

---

### 7. Test Updates (TDD/Adjust)

**Existing Test Updates:**
- Update all config fixtures to new YAML structure
- Update imports for renamed classes
- Update `state.providers` → `state.ai_providers` references

**New Contract Tests:**

```python
# tests/unit/application/test_config_cascade_contract.py

class TestConfigCascadeContract:
    """Contract tests: cascade resolution must follow spec."""

    def test_defaults_apply_when_no_override(self):
        """Stage config inherits all defaults when phase/stage not specified."""
        config = WorkflowConfig(defaults=StageConfig(ai_provider="claude-code"))
        resolved = config.get_stage_config(WorkflowPhase.PLAN, WorkflowStage.RESPONSE)
        assert resolved.ai_provider == "claude-code"

    def test_stage_override_wins(self):
        """Stage-level value overrides defaults."""
        config = WorkflowConfig(
            defaults=StageConfig(approval_provider="manual"),
            plan=PhaseConfig(
                response=StageConfig(approval_provider="skip")
            )
        )
        resolved = config.get_stage_config(WorkflowPhase.PLAN, WorkflowStage.RESPONSE)
        assert resolved.approval_provider == "skip"

    def test_partial_override_preserves_defaults(self):
        """Overriding one field preserves other defaults."""
        config = WorkflowConfig(
            defaults=StageConfig(
                ai_provider="claude-code",
                approval_provider="manual",
                approval_max_retries=3
            ),
            plan=PhaseConfig(
                response=StageConfig(approval_provider="skip")
            )
        )
        resolved = config.get_stage_config(WorkflowPhase.PLAN, WorkflowStage.RESPONSE)
        assert resolved.ai_provider == "claude-code"  # from defaults
        assert resolved.approval_provider == "skip"   # overridden
        assert resolved.approval_max_retries == 3     # from defaults
```

---

## Acceptance Criteria

- [ ] New config shape parses and validates; unknown phase/stage/provider keys fail fast
- [ ] Cascade resolution works: defaults → phase → stage
- [ ] AI providers only required for RESPONSE stages; PROMPT stages ignore `ai_provider`
- [x] Class renames complete: ResponseProvider → AIProvider, etc.
- [x] `state.ai_providers` replaces `state.providers` in WorkflowState
- [x] All existing tests pass after updates (832 tests)
- [ ] Contract tests verify cascade behavior
- [x] Docs/ADRs reflect new terminology and config layout