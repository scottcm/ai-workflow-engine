# Creating Providers

Guide to implementing AI providers and approval providers for the AI Workflow Engine.

---

## Provider Types

The engine uses three provider types:

| Type | Purpose | Interface |
|------|---------|-----------|
| AI Provider | Execute prompts, return responses | `AIProvider` |
| Approval Provider | Evaluate content at gates | `ApprovalProvider` |
| Standards Provider | Retrieve coding standards | `StandardsProvider` |

---

## AI Providers

AI providers handle prompt delivery and response retrieval. They abstract how AI is accessed.

### AIProvider Interface

```python
from abc import ABC, abstractmethod
from typing import Any

from aiwf.domain.models.ai_provider_result import AIProviderResult


class AIProvider(ABC):
    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        """Return provider metadata for discovery."""
        return {
            "name": "unknown",
            "description": "No description available",
            "requires_config": False,
            "config_keys": [],
            "default_connection_timeout": 10,
            "default_response_timeout": 300,
            "fs_ability": "local-write",
            "supports_system_prompt": False,
        }

    @abstractmethod
    def validate(self) -> None:
        """Verify provider is accessible and configured correctly.
        Raises ProviderError if misconfigured.
        """
        ...

    @abstractmethod
    def generate(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        system_prompt: str | None = None,
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
    ) -> AIProviderResult | None:
        """Generate response. Returns None for manual mode."""
        ...
```

### AIProviderResult

The result model has two fields:

```python
class AIProviderResult(BaseModel):
    files: dict[str, str | None] = {}  # path -> content or None
    response: str | None = None        # Optional text response
```

**File values:**
- `str` - Content for engine to write
- `None` - Provider wrote file directly (local-write providers)

### fs_ability Metadata

Providers declare filesystem capability:

| Value | Meaning | Existing Examples |
|-------|---------|-------------------|
| `local-write` | Can read/write project files | `claude-code`, `gemini-cli` |
| `local-read` | Can read but not write | Standards readers |
| `write-only` | Can write but not read | Sandboxed providers |
| `none` | No filesystem access | API-only providers |

### Existing Providers

Study these actual implementations:

| Provider | Location | Pattern |
|----------|----------|---------|
| `claude-code` | [claude_code_provider.py](../../aiwf/domain/providers/claude_code_provider.py) | SDK-based, local-write |
| `gemini-cli` | [gemini_cli_provider.py](../../aiwf/domain/providers/gemini_cli_provider.py) | CLI-based, local-write |
| `manual` | [manual_provider.py](../../aiwf/domain/providers/manual_provider.py) | Returns None (user provides) |

### Implementation Pattern

For a new AI provider, you need:

```python
class MyProvider(AIProvider):
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        # Extract config values you need

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        return {
            "name": "my-provider",
            "description": "...",
            "requires_config": True,  # If needs api_key, etc.
            "config_keys": ["api_key"],
            "fs_ability": "none",     # Or "local-write" if writes files
            "supports_system_prompt": True,
            # ... other metadata
        }

    def validate(self) -> None:
        # Check config, connectivity, etc.
        # Raise ProviderError on failure
        if not self.config.get("api_key"):
            raise ProviderError("API key not configured")

    def generate(self, prompt, context=None, system_prompt=None, **kwargs):
        # Call your AI service
        # Return AIProviderResult with files and/or response
        ...
```

**Key decisions:**
- `fs_ability`: Does your provider write files directly or return content?
- `requires_config`: Does it need API keys or other configuration?
- Error handling: Wrap exceptions in `ProviderError`

### Registration

```python
from aiwf.domain.providers.provider_factory import AIProviderFactory

AIProviderFactory.register("my-provider", MyProvider)
```

Users then specify `--planner my-provider` when initializing workflows.

---

## Approval Providers

Approval providers evaluate content at workflow gates.

### ApprovalProvider Interface

```python
from abc import ABC, abstractmethod
from typing import Any

from aiwf.domain.models.approval_result import ApprovalResult, ApprovalDecision
from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStage


class ApprovalProvider(ABC):
    @abstractmethod
    def evaluate(
        self,
        *,
        phase: WorkflowPhase,
        stage: WorkflowStage,
        files: dict[str, str | None],
        context: dict[str, Any],
    ) -> ApprovalResult:
        """Evaluate content and return approval decision."""
        ...

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        return {
            "name": "base",
            "description": "Base approval provider",
            "fs_ability": "none",
        }
```

### ApprovalResult

```python
class ApprovalDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING = "pending"

class ApprovalResult(BaseModel):
    decision: ApprovalDecision
    feedback: str | None = None           # Required for REJECTED
    suggested_content: str | None = None  # Optional fix suggestion
```

**Important:** Rejected decisions must include feedback explaining why.

### Built-in Approval Providers

| Provider | Behavior | Location |
|----------|----------|----------|
| `skip` | Always returns APPROVED | [approval_provider.py](../../aiwf/domain/providers/approval_provider.py) |
| `manual` | Returns PENDING, waits for user | [approval_provider.py](../../aiwf/domain/providers/approval_provider.py) |

### Implementation Pattern

```python
class MyApprovalProvider(ApprovalProvider):
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        return {
            "name": "my-approver",
            "description": "...",
            "fs_ability": "local-read",  # If needs to read files
        }

    def evaluate(self, *, phase, stage, files, context) -> ApprovalResult:
        # The engine calls this based on per-phase/stage configuration.
        # phase/stage tell you what content is being evaluated.

        # Your evaluation logic here
        # ...

        if passes:
            return ApprovalResult(decision=ApprovalDecision.APPROVED)
        else:
            return ApprovalResult(
                decision=ApprovalDecision.REJECTED,
                feedback="Explanation of what's wrong",  # Required!
            )
```

**Note:** The engine selects which provider to call based on workflow configuration. Configure your provider for the phase/stages where it makes sense - it doesn't need to filter internally.

### Using AI Provider as Approver

Any AI provider can be wrapped as an approval provider:

```python
from aiwf.domain.providers.ai_approval_provider import AIApprovalProvider
from aiwf.domain.providers.provider_factory import AIProviderFactory

ai_provider = AIProviderFactory.create("claude-code")
approver = AIApprovalProvider(ai_provider)
```

### Registration

```python
from aiwf.domain.providers.approval_factory import ApprovalProviderFactory

ApprovalProviderFactory.register("my-approver", MyApprovalProvider)
```

---

## Standards Providers

Standards providers retrieve coding standards for profiles.

### StandardsProvider Interface

```python
from typing import Any, Protocol

class StandardsProvider(Protocol):
    @classmethod
    def get_metadata(cls) -> dict[str, Any]: ...

    def validate(self) -> None: ...

    def create_bundle(
        self,
        context: dict[str, Any],
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
    ) -> str:
        """Create standards bundle for the given context."""
        ...
```

See [standards_provider_factory.py](../../aiwf/domain/standards/standards_provider_factory.py) for the full interface.

---

## Configuration

### AI Provider Config

```yaml
# .aiwf/config.yml
providers:
  planner: claude-code
  generator: claude-code
  reviewer: manual
  reviser: claude-code

provider_config:
  my-provider:
    api_key: ${MY_API_KEY}
```

### Approval Provider Config

```yaml
workflow:
  generate:
    response:
      approval_provider: my-approver
      approval_max_retries: 2
```

---

## Testing

### AI Provider Tests

```python
def test_validate_fails_without_config():
    provider = MyProvider({})
    with pytest.raises(ProviderError):
        provider.validate()


def test_generate_returns_result(mocker):
    # Mock your external service
    provider = MyProvider({"api_key": "test"})
    result = provider.generate("test prompt")

    assert isinstance(result, AIProviderResult)
    # Assert on result.files, result.response
```

### Approval Provider Tests

```python
def test_approves_valid_content():
    provider = MyApprovalProvider()

    result = provider.evaluate(
        phase=WorkflowPhase.GENERATE,
        stage=WorkflowStage.RESPONSE,
        files={"test.py": "valid content"},
        context={},
    )

    assert result.decision == ApprovalDecision.APPROVED


def test_rejects_with_feedback():
    provider = MyApprovalProvider()

    result = provider.evaluate(
        phase=WorkflowPhase.GENERATE,
        stage=WorkflowStage.RESPONSE,
        files={"test.py": "invalid content"},
        context={},
    )

    assert result.decision == ApprovalDecision.REJECTED
    assert result.feedback  # Must have feedback
```

---

## Best Practices

### AI Providers

1. **Fail fast** - Implement robust `validate()` to catch config issues early
2. **Handle timeouts** - Network calls should have timeouts
3. **Clear errors** - Wrap exceptions in `ProviderError` with helpful messages
4. **Accurate metadata** - Declare correct `fs_ability` so engine knows what to expect
5. **Test offline** - Mock external dependencies in unit tests

### Approval Providers

1. **Configure appropriately** - Only configure your provider for phases where it applies
2. **Graceful degradation** - If evaluation fails for unexpected reasons, decide whether to APPROVE or REJECT based on safety
3. **Helpful feedback** - Rejection messages should be actionable
4. **Efficient** - Don't run expensive checks unnecessarily

---

## Next Steps

- [Configuration Guide](configuration.md) - Configure providers
- [ADR-0013](../adr/0013-claude-code-provider.md) - Claude Code provider design
- [ADR-0015](../adr/0015-approval-providers.md) - Approval system design
