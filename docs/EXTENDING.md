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
mkdir -p profiles/react_ts
cd profiles/react_ts
```

### Step 2: Implement WorkflowProfile

Create `profile.py`:

```python
from pathlib import Path
from typing import Any

from aiwf.domain.profiles.workflow_profile import WorkflowProfile, PromptResult
from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.write_plan import WritePlan, WriteOp
from aiwf.domain.models.workflow_state import WorkflowStatus


class ReactTsProfile(WorkflowProfile):
    """React/TypeScript component generation profile."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.templates_dir = Path(__file__).parent / "templates"

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        return {
            "name": "react-ts",
            "description": "React/TypeScript component generation",
            "target_stack": "React 18+ / TypeScript 5+",
            "scopes": ["component", "hook", "page"],
            "phases": ["planning", "generation", "review", "revision"],
            "requires_config": False,
            "config_keys": [],
            "context_schema": {
                "component": {"type": "string", "required": True},
                "type": {
                    "type": "string",
                    "required": False,
                    "default": "functional",
                    "choices": ["functional", "class"],
                },
            },
        }

    def get_default_standards_provider_key(self) -> str:
        return "scoped-layer-fs"  # Or create your own provider

    def get_standards_config(self) -> dict[str, Any]:
        # Config structure depends on your standards provider
        return {
            "standards": {"root": str(Path(__file__).parent / "standards")},
            "scopes": {"component": {"layers": ["react"]}},
            "layer_standards": {"react": ["react-standards.md"]},
        }

    # PLAN phase
    def generate_planning_prompt(self, context: dict) -> PromptResult:
        """Generate planning prompt for React component."""
        component = context["component"]
        comp_type = context.get("type", "functional")

        return f"""# React Component Planning Request

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

    def process_planning_response(self, content: str) -> ProcessingResult:
        """Process planning response."""
        return ProcessingResult(
            status=WorkflowStatus.IN_PROGRESS,
            messages=["Plan processed successfully"],
        )

    # GENERATE phase
    def generate_generation_prompt(self, context: dict) -> PromptResult:
        """Generate code generation prompt."""
        component = context["component"]

        return f"""# Generate React Component

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
Use <<<FILE: filename>>> markers for each file:

<<<FILE: {component}.tsx>>>
// Component code here
<<<END_FILE>>>

<<<FILE: {component}.test.tsx>>>
// Test code here
<<<END_FILE>>>
"""

    def process_generation_response(
        self,
        content: str,
        session_dir: Path,
        iteration: int,
    ) -> ProcessingResult:
        """Extract React component code from response."""
        files = self._extract_code_blocks(content)

        if not files:
            return ProcessingResult(
                status=WorkflowStatus.IN_PROGRESS,
                error_message="No code blocks found in response",
            )

        # Build WritePlan with filename-only paths
        # Engine adds iteration-{N}/code/ prefix
        writes = [
            WriteOp(path=filename, content=code)
            for filename, code in files.items()
        ]

        return ProcessingResult(
            status=WorkflowStatus.IN_PROGRESS,
            write_plan=WritePlan(writes=writes),
            messages=[f"Extracted {len(files)} files"],
        )

    # REVIEW phase
    def generate_review_prompt(self, context: dict) -> PromptResult:
        """Generate review prompt."""
        return """# Review React Component

Review the generated component for:
1. TypeScript correctness
2. React best practices
3. Test coverage
4. Accessibility concerns

Provide structured feedback with specific issues and suggested fixes.
"""

    def process_review_response(self, content: str) -> ProcessingResult:
        """Process review response."""
        # Parse for pass/fail verdict if needed
        passed = "PASS" in content.upper() or "APPROVED" in content.upper()

        return ProcessingResult(
            status=WorkflowStatus.SUCCESS if passed else WorkflowStatus.FAILED,
            messages=["Review processed"],
            metadata={"verdict": "pass" if passed else "fail"},
        )

    # REVISE phase
    def generate_revision_prompt(self, context: dict) -> PromptResult:
        """Generate revision prompt."""
        return """# Revise React Component

Address the issues identified in the review.
Output revised files using the same <<<FILE: filename>>> format.
"""

    def process_revision_response(
        self,
        content: str,
        session_dir: Path,
        iteration: int,
    ) -> ProcessingResult:
        """Process revision response (same as generate)."""
        return self.process_generation_response(content, session_dir, iteration)

    # Helper methods
    def _extract_code_blocks(self, content: str) -> dict[str, str]:
        """Extract <<<FILE: filename>>> code blocks from content."""
        import re

        pattern = r"<<<FILE:\s*([^>]+)>>>\s*(.*?)<<<END_FILE>>>"
        matches = re.findall(pattern, content, re.DOTALL)

        files = {}
        for filename, code in matches:
            filename = filename.strip()
            files[filename] = code.strip()

        return files
```

### Step 3: Register Profile

Create `__init__.py`:

```python
"""React/TypeScript Profile CLI Commands."""

from typing import TYPE_CHECKING

import click

from .profile import ReactTsProfile

if TYPE_CHECKING:
    from aiwf.domain.profiles.workflow_profile import WorkflowProfile


def register(cli_group: click.Group) -> type["WorkflowProfile"]:
    """Entry point for profile registration."""

    @cli_group.command("info")
    def info() -> None:
        """Show react-ts profile information."""
        metadata = ReactTsProfile.get_metadata()
        click.echo(f"Profile: {metadata['name']}")
        click.echo(f"Description: {metadata['description']}")
        click.echo(f"Target Stack: {metadata['target_stack']}")
        click.echo(f"Scopes: {', '.join(metadata['scopes'])}")

    return ReactTsProfile
```

### Step 4: Create Standards Bundle

Create `standards/react-standards.md`:

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
```

### Step 5: Test Profile

```python
# tests/unit/profiles/react_ts/test_profile.py
from pathlib import Path
from unittest.mock import Mock

from profiles.react_ts.profile import ReactTsProfile


def test_generate_planning_prompt():
    profile = ReactTsProfile()
    context = {"component": "Button", "type": "functional"}

    prompt = profile.generate_planning_prompt(context)

    assert "Button" in prompt
    assert "functional" in prompt


def test_process_generation_response(tmp_path):
    profile = ReactTsProfile()
    response = """
<<<FILE: Button.tsx>>>
export const Button = () => <button>Click</button>;
<<<END_FILE>>>

<<<FILE: Button.test.tsx>>>
test('renders button', () => {});
<<<END_FILE>>>
"""

    result = profile.process_generation_response(response, tmp_path, 1)

    assert result.write_plan is not None
    assert len(result.write_plan.writes) == 2
    assert result.write_plan.writes[0].path == "Button.tsx"
```

---

## Creating a New AI Provider

AI providers abstract how AI is accessed. This guide creates an OpenAI API provider.

### Step 1: Implement AIProvider

Create `aiwf/domain/providers/openai_provider.py`:

```python
from typing import Any

from aiwf.domain.providers.ai_provider import AIProvider
from aiwf.domain.models.ai_provider_result import AIProviderResult
from aiwf.domain.errors import ProviderError


class OpenAIProvider(AIProvider):
    """OpenAI API provider."""

    def __init__(self, config: dict[str, Any] | None = None):
        config = config or {}
        self.api_key = config.get("api_key")
        self.model = config.get("model", "gpt-4")
        self.base_url = config.get("base_url", "https://api.openai.com/v1")

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        return {
            "name": "openai",
            "description": "OpenAI API provider (GPT-4, GPT-3.5, etc.)",
            "requires_config": True,
            "config_keys": ["api_key"],
            "default_connection_timeout": 10,
            "default_response_timeout": 300,
            "fs_ability": "none",  # API-only, no filesystem access
            "supports_system_prompt": True,
        }

    def validate(self) -> None:
        """Verify API key is configured."""
        if not self.api_key:
            raise ProviderError("OpenAI API key not configured")

    def generate(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        system_prompt: str | None = None,
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
    ) -> AIProviderResult | None:
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
            response_file = "response.md"
            if context and "expected_outputs" in context:
                response_file = context["expected_outputs"][0]

            return AIProviderResult(
                files={response_file: content},
                response=content,  # Optional text response
            )

        except Exception as e:
            raise ProviderError(f"OpenAI API error: {e}")
```

### Step 2: Register Provider

In `aiwf/domain/providers/__init__.py`:

```python
from aiwf.domain.providers.provider_factory import AIProviderFactory
from aiwf.domain.providers.openai_provider import OpenAIProvider

AIProviderFactory.register("openai", OpenAIProvider)
```

### Step 3: Configure Provider

In `.aiwf/config.yml`:

```yaml
providers:
  planner: openai
  generator: openai
  reviewer: manual
  reviser: openai

provider_config:
  openai:
    api_key: ${OPENAI_API_KEY}  # From environment
    model: gpt-4
```

---

## Creating a New Approval Provider

Approval providers evaluate content at gates. This guide creates a linter-based approver.

### Step 1: Implement ApprovalProvider

Create `aiwf/domain/providers/linter_approver.py`:

```python
import subprocess
from typing import Any

from aiwf.domain.providers.approval_provider import ApprovalProvider
from aiwf.domain.models.approval_result import ApprovalResult, ApprovalDecision
from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStage


class LinterApprovalProvider(ApprovalProvider):
    """Approval provider that runs linters on code."""

    def __init__(self, config: dict[str, Any] | None = None):
        config = config or {}
        self.linter_command = config.get("command", "ruff check")

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
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
        context: dict[str, Any],
    ) -> ApprovalResult:
        """Run linter on generated code."""

        # Only lint GENERATE and REVISE response stages
        if phase not in (WorkflowPhase.GENERATE, WorkflowPhase.REVISE):
            return ApprovalResult(decision=ApprovalDecision.APPROVED)

        if stage != WorkflowStage.RESPONSE:
            return ApprovalResult(decision=ApprovalDecision.APPROVED)

        # Get code directory from context
        session_dir = context.get("session_dir")
        iteration = context.get("iteration", 1)

        if not session_dir:
            return ApprovalResult(decision=ApprovalDecision.APPROVED)

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

### Step 1: Implement StandardsProvider Protocol

```python
from pathlib import Path
import subprocess
from typing import Any

from aiwf.domain.errors import ProviderError


class GitStandardsProvider:
    """Load standards from a specific Git commit.

    Implements the StandardsProvider Protocol.
    """

    def __init__(self, config: dict[str, Any]):
        self.repo_path = Path(config.get("repo_path", "."))
        self.commit = config.get("commit", "HEAD")
        self.standards_file = config.get("standards_file", "STANDARDS.md")

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        return {
            "name": "git-standards",
            "description": "Load standards from Git history",
            "requires_config": True,
            "config_keys": ["repo_path", "commit", "standards_file"],
            "default_connection_timeout": None,
            "default_response_timeout": 30,
        }

    def validate(self) -> None:
        """Verify repo exists and commit is accessible."""
        if not self.repo_path.exists():
            raise ProviderError(f"Repo not found: {self.repo_path}")

    def create_bundle(
        self,
        context: dict[str, Any],
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
    ) -> str:
        """Retrieve standards from Git history."""
        try:
            result = subprocess.run(
                ["git", "show", f"{self.commit}:{self.standards_file}"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
                timeout=response_timeout or 30,
            )
            return result.stdout

        except subprocess.CalledProcessError as e:
            raise ProviderError(f"Failed to load standards from git: {e}")
```

---

## Testing Your Extensions

### Unit Testing Patterns

**Test profiles without filesystem:**

```python
def test_profile_generate_prompt():
    profile = MyProfile()
    prompt = profile.generate_planning_prompt({"entity": "User"})
    assert "User" in prompt


def test_profile_process_response(tmp_path):
    profile = MyProfile()
    result = profile.process_generation_response(
        "<<<FILE: User.java>>>\ncode\n<<<END_FILE>>>",
        tmp_path,
        iteration=1,
    )

    assert result.write_plan is not None
    assert len(result.write_plan.writes) > 0
    assert result.write_plan.writes[0].path == "User.java"
```

**Test providers with mocking:**

```python
def test_ai_provider_generate(mocker):
    mock_api = mocker.patch("openai.OpenAI")
    mock_response = mocker.Mock()
    mock_response.choices = [mocker.Mock(message=mocker.Mock(content="response"))]
    mock_api.return_value.chat.completions.create.return_value = mock_response

    provider = OpenAIProvider({"api_key": "test"})
    result = provider.generate("prompt")

    assert result.files["response.md"] == "response"
```

### Integration Testing

Test full workflow with your extension:

```python
def test_full_workflow_with_react_profile(tmp_path):
    from aiwf.application.workflow_orchestrator import WorkflowOrchestrator

    orchestrator = WorkflowOrchestrator(...)
    state = orchestrator.initialize_run(
        profile="react-ts",
        context={"component": "Button", "type": "functional"},
        session_dir=tmp_path,
    )

    assert state.profile == "react-ts"
```

---

## Best Practices

### Profile Development

1. **Start simple**: Implement one scope before adding complexity
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
2. **Type everything**: Use Pydantic models and type hints
3. **Document decisions**: Add ADRs for non-obvious choices
4. **Consider future**: Design for extensibility, not just current needs

---

## Next Steps

- Review [ADR-0007: Plugin Architecture](adr/0007-plugin-architecture.md) for design rationale
- Study [jpa-mt profile](../profiles/jpa_mt/) for complete example
- Check [provider implementation guide](provider-implementation-guide.md) for details
