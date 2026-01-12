# Extending the AI Workflow Engine

Guide to creating custom profiles, AI providers, and approval providers.

---

## Table of Contents

- [Creating a New Profile](#creating-a-new-profile)
- [Creating a New AI Provider](#creating-a-new-ai-provider)
- [Creating a New Approval Provider](#creating-a-new-approval-provider)
- [Creating a New Standards Provider](#creating-a-new-standards-provider)
- [Testing Your Extensions](#testing-your-extensions)
- [Best Practices](#best-practices)

---

## Creating a New Profile

Profiles implement language/framework-specific generation logic. This guide walks through creating a React/TypeScript profile.

### Step 1: Create Profile Directory

```bash
mkdir -p profiles/react-ts
cd profiles/react-ts
```

### Step 2: Implement WorkflowProfile

Create `react_ts_profile.py`:

```python
from pathlib import Path
from typing import Any

from aiwf.domain.profiles.workflow_profile import WorkflowProfile
from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.write_plan import WritePlan, WriteOp
from aiwf.domain.providers.standards_provider import StandardsProvider


class ReactTsProfile(WorkflowProfile):
    """React/TypeScript component generation profile."""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.templates_dir = Path(__file__).parent / "templates"

    def get_metadata(self) -> dict[str, Any]:
        return {
            "name": "react-ts",
            "description": "React/TypeScript component generation",
            "version": "1.0.0",
            "required_context": ["component", "type"],  # component name, type (functional/class)
        }

    def get_standards_provider(self) -> StandardsProvider:
        """Return standards provider for React/TS."""
        from aiwf.domain.providers.bundle_standards_provider import BundleStandardsProvider

        standards_file = Path(__file__).parent / "standards" / "react-standards.md"
        return BundleStandardsProvider(str(standards_file))

    # PLAN phase
    def generate_plan_prompt(self, context: dict[str, Any]) -> str:
        """Generate planning prompt for React component."""
        component = context["component"]
        comp_type = context.get("type", "functional")

        prompt = f"""# React Component Planning Request

## Component Details
- **Component Name:** {component}
- **Type:** {comp_type}
- **Props:** {context.get('props', 'To be determined')}

## Requirements
1. Define component interface (props, state if applicable)
2. List required imports
3. Identify hooks needed (if functional)
4. Plan test strategy

## Deliverable
Provide a structured plan with:
- Component signature
- Key functionality
- Testing approach
"""
        return prompt

    def process_plan_response(self, content: str, context: dict[str, Any]) -> ProcessingResult:
        """Process planning response, save as plan.md."""
        return ProcessingResult(
            write_plan=WritePlan(
                operations=[
                    WriteOp(type="write", path="plan.md", content=content)
                ]
            ),
            success=True,
            message="Plan processed successfully"
        )

    # GENERATE phase
    def generate_generate_prompt(self, context: dict[str, Any]) -> str:
        """Generate code generation prompt."""
        component = context["component"]

        prompt = f"""# Generate React Component

Based on the plan, generate:
1. {component}.tsx - Component implementation
2. {component}.test.tsx - Unit tests
3. index.ts - Barrel export

## Requirements
- TypeScript strict mode
- React 18+ features
- Jest + React Testing Library
- Props interface exported

## Output Format
```typescript:Component.tsx
// Component code here
```

```typescript:Component.test.tsx
// Test code here
```

```typescript:index.ts
// Export here
```
"""
        return prompt

    def process_generate_response(
        self,
        content: str,
        session_dir: Path,
        state: Any,  # WorkflowState
        iteration: int,
    ) -> ProcessingResult:
        """Extract React component code from response."""
        # Parse code blocks from markdown
        files = self._extract_code_blocks(content)

        if not files:
            return ProcessingResult(
                write_plan=WritePlan(operations=[]),
                success=False,
                message="No code blocks found in response"
            )

        # Build WritePlan
        operations = []
        code_dir = session_dir / f"iteration-{iteration}" / "code"

        for filename, code_content in files.items():
            operations.append(
                WriteOp(
                    type="write",
                    path=str(code_dir / filename),
                    content=code_content
                )
            )

        return ProcessingResult(
            write_plan=WritePlan(operations=operations),
            success=True,
            message=f"Extracted {len(files)} files"
        )

    # REVIEW phase
    def generate_review_prompt(self, context: dict[str, Any]) -> str:
        """Generate review prompt."""
        return """# Review React Component

Review the generated component for:
1. TypeScript correctness
2. React best practices
3. Test coverage
4. Accessibility concerns

Provide structured feedback with specific issues and suggested fixes.
"""

    def process_review_response(self, content: str, context: dict[str, Any]) -> ProcessingResult:
        """Process review response."""
        return ProcessingResult(
            write_plan=WritePlan(
                operations=[
                    WriteOp(type="write", path="review-response.md", content=content)
                ]
            ),
            success=True
        )

    # REVISE phase
    def generate_revise_prompt(self, context: dict[str, Any]) -> str:
        """Generate revision prompt."""
        return """# Revise React Component

Address the issues identified in the review.

Output revised files in the same format as generation.
"""

    def process_revise_response(
        self,
        content: str,
        session_dir: Path,
        state: Any,
        iteration: int,
    ) -> ProcessingResult:
        """Process revision response (same as generate)."""
        return self.process_generate_response(content, session_dir, state, iteration)

    # Helper methods
    def _extract_code_blocks(self, markdown: str) -> dict[str, str]:
        """Extract ```language:filename code blocks from markdown."""
        import re

        pattern = r"```(?:typescript|tsx?):([^\n]+)\n(.*?)```"
        matches = re.findall(pattern, markdown, re.DOTALL)

        files = {}
        for filename, code in matches:
            filename = filename.strip()
            files[filename] = code.strip()

        return files
```

### Step 3: Register Profile

In `profiles/react-ts/__init__.py`:

```python
from aiwf.domain.profiles.profile_factory import ProfileFactory
from .react_ts_profile import ReactTsProfile

# Register profile
ProfileFactory.register("react-ts", ReactTsProfile)
```

### Step 4: Create Standards Bundle

Create `profiles/react-ts/standards/react-standards.md`:

```markdown
# React/TypeScript Standards

## Component Structure
- Functional components preferred over class components
- Props interface exported from component file
- Default exports for components

## TypeScript
- Strict mode enabled
- Explicit return types for functions
- No `any` types without justification

## Testing
- One test file per component
- Test user interactions, not implementation
- Aim for 80%+ coverage

## Accessibility
- Semantic HTML elements
- ARIA labels where needed
- Keyboard navigation support
```

### Step 5: Test Profile

```python
# tests/unit/profiles/react_ts/test_react_ts_profile.py

def test_generate_plan_prompt():
    profile = ReactTsProfile({})
    context = {"component": "Button", "type": "functional"}

    prompt = profile.generate_plan_prompt(context)

    assert "Button" in prompt
    assert "functional" in prompt

def test_process_generate_response():
    profile = ReactTsProfile({})
    response = """
```typescript:Button.tsx
export const Button = () => <button>Click</button>;
```

```typescript:Button.test.tsx
test('renders button', () => {});
```
"""

    result = profile.process_generate_response(
        response, Path("/tmp/session"), mock_state, 1
    )

    assert result.success
    assert len(result.write_plan.operations) == 2
```

---

## Creating a New AI Provider

AI providers abstract how AI is accessed. This guide creates an OpenAI API provider.

### Step 1: Implement AIProvider

Create `aiwf/domain/providers/openai_provider.py`:

```python
from aiwf.domain.providers.ai_provider import AIProvider
from aiwf.domain.models.ai_provider_result import AIProviderResult
from aiwf.domain.errors import ProviderError


class OpenAIProvider(AIProvider):
    """OpenAI API provider."""

    def __init__(self, config: dict):
        self.api_key = config.get("api_key")
        self.model = config.get("model", "gpt-4")
        self.base_url = config.get("base_url", "https://api.openai.com/v1")

    @classmethod
    def get_metadata(cls) -> dict:
        return {
            "name": "openai",
            "description": "OpenAI API provider (GPT-4, GPT-3.5, etc.)",
            "requires_config": True,
            "config_keys": ["api_key"],
            "default_connection_timeout": 10,
            "default_response_timeout": 300,
            "fs_ability": "none",  # API-only, no filesystem access
            "supports_system_prompt": True,
            "supports_file_attachments": False,
        }

    def validate(self) -> None:
        """Verify API key is configured."""
        if not self.api_key:
            raise ProviderError("OpenAI API key not configured")

        # Optional: Test connectivity
        try:
            import openai
            client = openai.OpenAI(api_key=self.api_key)
            # Test with minimal request
            client.models.list()
        except Exception as e:
            raise ProviderError(f"OpenAI API validation failed: {e}")

    def generate(
        self,
        prompt: str,
        context: dict | None = None,
        system_prompt: str | None = None,
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
    ) -> AIProviderResult:
        """Call OpenAI API and return result."""
        import openai

        try:
            client = openai.OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=response_timeout or 300,
            )

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
            )

            content = response.choices[0].message.content

            # Determine response filename from context
            response_file = context.get("expected_outputs", ["response.md"])[0] if context else "response.md"

            return AIProviderResult(
                files={response_file: content},
                metadata={
                    "model": self.model,
                    "tokens": response.usage.total_tokens,
                    "finish_reason": response.choices[0].finish_reason,
                }
            )

        except openai.APIError as e:
            raise ProviderError(f"OpenAI API error: {e}")
        except Exception as e:
            raise ProviderError(f"Unexpected error calling OpenAI: {e}")
```

### Step 2: Register Provider

In `aiwf/domain/providers/__init__.py`:

```python
from aiwf.domain.providers.provider_factory import AIProviderFactory
from aiwf.domain.providers.openai_provider import OpenAIProvider

AIProviderFactory.register("openai", OpenAIProvider)
```

### Step 3: Configure Provider

Create `.aiwf/config.yml`:

```yaml
workflow:
  defaults:
    ai_provider: openai
    approval_provider: manual

providers:
  openai:
    api_key: ${OPENAI_API_KEY}  # From environment
    model: gpt-4
```

### Step 4: Test Provider

```python
# tests/unit/domain/providers/test_openai_provider.py

def test_openai_provider_validate():
    config = {"api_key": "test-key"}
    provider = OpenAIProvider(config)

    # Should not raise
    provider.validate()

def test_openai_provider_generate(mocker):
    config = {"api_key": "test-key"}
    provider = OpenAIProvider(config)

    # Mock OpenAI client
    mock_client = mocker.patch("openai.OpenAI")
    mock_response = mocker.Mock()
    mock_response.choices = [mocker.Mock(message=mocker.Mock(content="Generated code"))]
    mock_client.return_value.chat.completions.create.return_value = mock_response

    result = provider.generate("Generate a function")

    assert result.files["response.md"] == "Generated code"
```

---

## Creating a New Approval Provider

Approval providers evaluate content at gates. This guide creates a custom linter-based approver.

### Step 1: Implement ApprovalProvider

Create `aiwf/domain/providers/linter_approver.py`:

```python
from aiwf.domain.providers.approval_provider import ApprovalProvider
from aiwf.domain.models.approval_result import ApprovalResult, ApprovalDecision
from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStage
import subprocess


class LinterApprovalProvider(ApprovalProvider):
    """Approval provider that runs linters on code."""

    def __init__(self, config: dict):
        self.linter_command = config.get("command", "ruff check")

    @classmethod
    def get_metadata(cls) -> dict:
        return {
            "name": "linter",
            "description": "Linter-based approval (ruff, eslint, etc.)",
            "fs_ability": "local-read",  # Needs to read code files
        }

    def evaluate(
        self,
        *,
        phase: WorkflowPhase,
        stage: WorkflowStage,
        files: dict[str, str | None],
        context: dict,
    ) -> ApprovalResult:
        """Run linter on generated code."""

        # Only lint GENERATE and REVISE response stages
        if phase not in (WorkflowPhase.GENERATE, WorkflowPhase.REVISE):
            return ApprovalResult(decision=ApprovalDecision.APPROVED)

        if stage != WorkflowStage.RESPONSE:
            return ApprovalResult(decision=ApprovalDecision.APPROVED)

        # Get code directory
        session_dir = context.get("session_dir")
        iteration = context.get("iteration", 1)
        code_dir = session_dir / f"iteration-{iteration}" / "code"

        if not code_dir.exists():
            return ApprovalResult(
                decision=ApprovalDecision.APPROVED,
                feedback="No code directory found"
            )

        # Run linter
        try:
            result = subprocess.run(
                self.linter_command.split() + [str(code_dir)],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                return ApprovalResult(
                    decision=ApprovalDecision.APPROVED,
                    feedback="Linter checks passed"
                )
            else:
                return ApprovalResult(
                    decision=ApprovalDecision.REJECTED,
                    feedback=f"Linter found issues:\n{result.stdout}"
                )

        except subprocess.TimeoutExpired:
            return ApprovalResult(
                decision=ApprovalDecision.REJECTED,
                feedback="Linter timed out"
            )
        except Exception as e:
            return ApprovalResult(
                decision=ApprovalDecision.REJECTED,
                feedback=f"Linter failed: {e}"
            )
```

### Step 2: Register Provider

In `aiwf/domain/providers/__init__.py`:

```python
from aiwf.domain.providers.approval_factory import ApprovalProviderFactory
from aiwf.domain.providers.linter_approver import LinterApprovalProvider

ApprovalProviderFactory.register("linter", LinterApprovalProvider)
```

### Step 3: Configure Provider

```yaml
workflow:
  generate:
    response:
      approval_provider: linter
      approval_max_retries: 2
      approver_config:
        command: ruff check --fix
```

---

## Creating a New Standards Provider

Standards providers retrieve coding standards. This guide creates a Git-based provider.

### Step 1: Implement StandardsProvider

Create `aiwf/domain/providers/git_standards_provider.py`:

```python
from pathlib import Path
import subprocess

from aiwf.domain.providers.standards_provider import StandardsProvider


class GitStandardsProvider(StandardsProvider):
    """Load standards from a specific Git commit."""

    def __init__(self, repo_path: Path, commit: str, standards_file: str):
        self.repo_path = repo_path
        self.commit = commit
        self.standards_file = standards_file

    def get_standards(self) -> str:
        """Retrieve standards from Git history."""
        try:
            result = subprocess.run(
                ["git", "show", f"{self.commit}:{self.standards_file}"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout

        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to load standards from git: {e}")
```

---

## Testing Your Extensions

### Unit Testing Patterns

**Test profiles without filesystem:**

```python
def test_profile_generate_prompt():
    profile = MyProfile({})
    prompt = profile.generate_plan_prompt({"entity": "User"})
    assert "User" in prompt

def test_profile_process_response():
    profile = MyProfile({})
    result = profile.process_generate_response("code here", Path("/tmp"), mock_state, 1)

    assert result.success
    assert len(result.write_plan.operations) > 0
    assert result.write_plan.operations[0].type == "write"
```

**Test providers with mocking:**

```python
def test_ai_provider_generate(mocker):
    mock_api = mocker.patch("my_provider.api_client")
    mock_api.call.return_value = "response"

    provider = MyProvider({"api_key": "test"})
    result = provider.generate("prompt")

    assert result.files["response.md"] == "response"
```

### Integration Testing

Test full workflow with your extension:

```python
def test_full_workflow_with_react_profile(tmp_path):
    # Initialize session
    orchestrator = WorkflowOrchestrator(...)
    state = orchestrator.initialize_run(
        profile="react-ts",
        context={"component": "Button", "type": "functional"},
        session_dir=tmp_path
    )

    # Verify profile was loaded
    assert state.profile == "react-ts"

    # Continue workflow...
```

---

## Best Practices

### Profile Development

1. **Start simple**: Implement one scope (domain) before adding complexity
2. **Test incrementally**: Write tests for each method as you implement
3. **Reuse patterns**: Study jpa-mt profile for proven patterns
4. **Document context**: Clearly specify required context keys in metadata
5. **Version templates**: Keep templates under version control with profile

### Provider Development

1. **Fail fast**: Implement robust `validate()` method
2. **Handle timeouts**: All network calls should have timeouts
3. **Clear errors**: Wrap exceptions in `ProviderError` with context
4. **Declare capabilities**: Accurate `fs_ability` metadata
5. **Test offline**: Mock external dependencies in unit tests

### General Guidelines

1. **Follow conventions**: Profiles return WritePlans, don't do I/O
2. **Type everything**: Use Pydantic models and mypy
3. **Document decisions**: Add ADRs for non-obvious choices
4. **Consider future**: Design for extensibility, not just current needs
5. **Contribute back**: Share useful profiles/providers with community

---

## Next Steps

- Review [ADR-0007: Plugin Architecture](../adr/0007-plugin-architecture.md) for design rationale
- Study [jpa-mt profile](../../profiles/jpa_mt/) for complete example
- Check [provider implementation guide](../provider-implementation-guide.md) for details
- Join discussions on [GitHub Issues](https://github.com/scottcm/ai-workflow-engine/issues)
