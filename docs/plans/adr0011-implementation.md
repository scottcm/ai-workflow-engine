# ADR-0011: Prompt Builder API - Implementation Guide

**Goal:** Provide profiles with a structured API for building prompts, enabling system/user prompt separation while maintaining pass-through flexibility.

**Dependencies:** ADR-0008 Phase 5 (Engine Prompt Assembly) must be complete.

**TDD Approach:** Define the API contract through tests first, then implement.

---

## Overview

Currently, profiles return a single string from `generate_*_prompt()`. This plan introduces:

1. A `PromptSections` model with discrete sections:
   - `role: str` - Who the AI is acting as
   - `required_inputs: dict[str, str]` - Profile's input files with descriptions (engine merges its own)
   - `context: str` - How to use the inputs
   - `task: str` - What the AI needs to do (required)
   - `constraints: str` - Rules and boundaries
   - `expected_outputs: list[str]` - Files to produce (under /code)
   - `output_format: str` - Content formatting instructions (NOT delimiting)
2. Updated profile methods that can return either `PromptSections` or `str`
3. Engine assembly logic that handles both return types

The engine continues to own:
- Metadata injection
- Session artifact injection (plan, standards, code) - merged with profile's `required_inputs`
- Expected output file list rendering in prompt (from `expected_outputs`)
- Output file instructions (response filename based on fs_ability)
- Provider result validation (files exist after provider execution)

---

## Step 1: Write Tests First

### 1.1 PromptSections Model Tests

**File:** `tests/unit/domain/models/test_prompt_sections.py`

```python
"""Tests for PromptSections model."""

import pytest
from aiwf.domain.models.prompt_sections import PromptSections


class TestPromptSectionsCreation:
    """Tests for creating PromptSections."""

    def test_create_with_all_sections(self):
        """All sections can be provided."""
        sections = PromptSections(
            role="You are an expert Java developer.",
            required_inputs={"schema.sql": "Database DDL defining table structure"},
            context="The schema defines the database structure.",
            task="Generate a JPA entity for the Customer table.",
            constraints="Do not add fields not in the schema.",
            expected_outputs=["Customer.java", "CustomerRepository.java"],
            output_format="Use Lombok @Data annotation on entities.",
        )

        assert sections.role == "You are an expert Java developer."
        assert sections.required_inputs == {"schema.sql": "Database DDL defining table structure"}
        assert sections.context == "The schema defines the database structure."
        assert sections.task == "Generate a JPA entity for the Customer table."
        assert sections.constraints == "Do not add fields not in the schema."
        assert sections.expected_outputs == ["Customer.java", "CustomerRepository.java"]
        assert sections.output_format == "Use Lombok @Data annotation on entities."

    def test_required_inputs_is_dict_with_descriptions(self):
        """Required inputs maps filename to description."""
        sections = PromptSections(
            task="Generate code.",
            required_inputs={
                "schema.sql": "Database DDL",
                "config.yml": "Application configuration",
            },
        )

        assert "schema.sql" in sections.required_inputs
        assert sections.required_inputs["schema.sql"] == "Database DDL"
        assert sections.required_inputs["config.yml"] == "Application configuration"

    def test_create_with_minimal_sections(self):
        """Only task is required."""
        sections = PromptSections(
            task="Review the code for standards compliance.",
        )

        assert sections.task == "Review the code for standards compliance."
        assert sections.role is None
        assert sections.required_inputs is None
        assert sections.context is None
        assert sections.constraints is None
        assert sections.expected_outputs is None
        assert sections.output_format is None

    def test_task_is_required(self):
        """Task section is required."""
        with pytest.raises(ValueError):
            PromptSections()

    def test_expected_outputs_supports_subdirectories(self):
        """Expected outputs can include subdirectory paths."""
        sections = PromptSections(
            task="Generate code.",
            expected_outputs=[
                "entity/Customer.java",
                "repository/CustomerRepository.java",
            ],
        )

        assert "entity/Customer.java" in sections.expected_outputs
        assert "repository/CustomerRepository.java" in sections.expected_outputs


class TestPromptSectionsSystemUserSplit:
    """Tests for splitting sections into system vs user prompt."""

    def test_get_system_sections_returns_role_and_constraints(self):
        """System sections include role and constraints."""
        sections = PromptSections(
            role="You are an expert.",
            task="Do the thing.",
            constraints="Follow the rules.",
        )

        system = sections.get_system_sections()

        assert "You are an expert." in system
        assert "Follow the rules." in system
        assert "Do the thing." not in system

    def test_get_user_sections_returns_context_and_task(self):
        """User sections include context and task."""
        sections = PromptSections(
            role="You are an expert.",
            context="Here is the data.",
            task="Do the thing.",
            constraints="Follow the rules.",
        )

        user = sections.get_user_sections()

        assert "Here is the data." in user
        assert "Do the thing." in user
        assert "You are an expert." not in user
        assert "Follow the rules." not in user

    def test_output_format_goes_in_user_sections(self):
        """Output format is part of user prompt (task-specific)."""
        sections = PromptSections(
            task="Generate code.",
            output_format="Use <<<FILE:>>> markers.",
        )

        user = sections.get_user_sections()

        assert "Use <<<FILE:>>> markers." in user

    def test_empty_system_sections_returns_empty_string(self):
        """No role or constraints returns empty system section."""
        sections = PromptSections(task="Just do it.")

        assert sections.get_system_sections() == ""
```

### 1.2 Profile Return Type Tests

**File:** `tests/unit/domain/profiles/test_workflow_profile.py`

```python
"""Tests for WorkflowProfile prompt generation return types."""

import pytest
from unittest.mock import MagicMock

from aiwf.domain.models.prompt_sections import PromptSections


class TestProfilePromptReturnTypes:
    """Tests for profiles returning PromptSections or str."""

    def test_profile_can_return_prompt_sections(self):
        """Profile returning PromptSections is valid."""
        # Mock profile that returns PromptSections
        profile = MagicMock()
        profile.generate_planning_prompt.return_value = PromptSections(
            role="You are an architect.",
            task="Create a plan.",
        )

        result = profile.generate_planning_prompt({})

        assert isinstance(result, PromptSections)

    def test_profile_can_return_string(self):
        """Profile returning str is valid (pass-through mode)."""
        profile = MagicMock()
        profile.generate_planning_prompt.return_value = "Full prompt content here."

        result = profile.generate_planning_prompt({})

        assert isinstance(result, str)
```

### 1.3 Engine Assembly Tests

**File:** `tests/unit/application/test_prompt_assembler.py` (add to existing)

```python
"""Tests for engine handling PromptSections vs str."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from aiwf.application.prompt_assembler import PromptAssembler
from aiwf.domain.models.prompt_sections import PromptSections
from aiwf.domain.models.workflow_state import WorkflowPhase


class TestPromptAssemblerWithSections:
    """Tests for assembling prompts from PromptSections."""

    @pytest.fixture
    def assembler(self, tmp_path):
        return PromptAssembler(
            session_dir=tmp_path,
            fs_ability="local-write",
        )

    def test_assemble_from_sections_includes_all_parts(self, assembler):
        """Assembling from PromptSections includes all sections in order."""
        sections = PromptSections(
            role="You are an expert.",
            context="Here is context.",
            task="Do the task.",
            constraints="Follow rules.",
            output_format="Format like this.",
        )

        result = assembler.assemble(
            profile_prompt=sections,
            phase=WorkflowPhase.PLANNING,
            metadata={"entity": "Customer"},
        )

        # All sections present
        assert "You are an expert." in result.user_prompt
        assert "Here is context." in result.user_prompt
        assert "Do the task." in result.user_prompt
        assert "Follow rules." in result.user_prompt
        assert "Format like this." in result.user_prompt

    def test_assemble_from_string_uses_passthrough(self, assembler):
        """Assembling from str uses pass-through mode."""
        prompt_str = "This is the complete profile prompt."

        result = assembler.assemble(
            profile_prompt=prompt_str,
            phase=WorkflowPhase.PLANNING,
            metadata={"entity": "Customer"},
        )

        assert "This is the complete profile prompt." in result.user_prompt

    def test_system_prompt_separation_when_supported(self, assembler):
        """When supports_system_prompt, role/constraints go to system prompt."""
        assembler.supports_system_prompt = True
        sections = PromptSections(
            role="You are an expert.",
            task="Do the task.",
            constraints="Follow rules.",
        )

        result = assembler.assemble(
            profile_prompt=sections,
            phase=WorkflowPhase.PLANNING,
            metadata={},
        )

        assert "You are an expert." in result.system_prompt
        assert "Follow rules." in result.system_prompt
        assert "Do the task." in result.user_prompt
        assert "Do the task." not in result.system_prompt

    def test_no_system_separation_for_string_prompt(self, assembler):
        """String prompts cannot be split into system/user."""
        assembler.supports_system_prompt = True
        prompt_str = "Complete prompt as string."

        result = assembler.assemble(
            profile_prompt=prompt_str,
            phase=WorkflowPhase.PLANNING,
            metadata={},
        )

        # String goes entirely to user prompt
        assert "Complete prompt as string." in result.user_prompt
        # System prompt only has engine content (output instructions)
        assert "Complete prompt as string." not in result.system_prompt


class TestMetadataInjection:
    """Tests for engine injecting metadata."""

    @pytest.fixture
    def assembler(self, tmp_path):
        return PromptAssembler(session_dir=tmp_path, fs_ability="local-write")

    def test_metadata_injected_at_top(self, assembler):
        """Metadata appears at top of assembled prompt."""
        sections = PromptSections(task="Do something.")

        result = assembler.assemble(
            profile_prompt=sections,
            phase=WorkflowPhase.PLANNING,
            metadata={"entity": "Customer", "table": "customers"},
        )

        # Metadata should appear before task
        prompt = result.user_prompt
        metadata_pos = prompt.find("entity:")
        task_pos = prompt.find("Do something.")
        assert metadata_pos < task_pos

    def test_metadata_injected_for_string_prompt(self, assembler):
        """Metadata injected even for string prompts."""
        result = assembler.assemble(
            profile_prompt="Profile content.",
            phase=WorkflowPhase.PLANNING,
            metadata={"entity": "Order"},
        )

        assert "entity:" in result.user_prompt
        assert "Order" in result.user_prompt


class TestRequiredInputsMerging:
    """Tests for merging profile's required_inputs with engine's session artifacts."""

    @pytest.fixture
    def assembler_with_artifacts(self, tmp_path):
        """Assembler with session artifacts present."""
        # Create session artifacts
        (tmp_path / "standards-bundle.md").write_text("# Standards")
        (tmp_path / "plan.md").write_text("# Plan")
        return PromptAssembler(session_dir=tmp_path, fs_ability="local-write")

    def test_planning_merges_profile_inputs_with_standards(self, assembler_with_artifacts):
        """PLANNING phase: profile inputs + standards-bundle."""
        sections = PromptSections(
            task="Create a plan.",
            required_inputs={"schema.sql": "Database DDL"},
        )

        result = assembler_with_artifacts.assemble(
            profile_prompt=sections,
            phase=WorkflowPhase.PLANNING,
            metadata={},
        )

        # Both profile input and engine artifact listed
        assert "schema.sql" in result.user_prompt
        assert "Database DDL" in result.user_prompt  # Description included
        assert "standards-bundle" in result.user_prompt.lower()

    def test_generating_merges_profile_inputs_with_plan_and_standards(
        self, assembler_with_artifacts
    ):
        """GENERATING phase: profile inputs + plan + standards-bundle."""
        sections = PromptSections(
            task="Generate code.",
            required_inputs={"schema.sql": "Database DDL"},
        )

        result = assembler_with_artifacts.assemble(
            profile_prompt=sections,
            phase=WorkflowPhase.GENERATING,
            metadata={},
        )

        assert "schema.sql" in result.user_prompt
        assert "plan" in result.user_prompt.lower()
        assert "standards" in result.user_prompt.lower()

    def test_required_inputs_rendered_as_bulleted_list(self, assembler_with_artifacts):
        """Required inputs are rendered as a bulleted list with descriptions."""
        sections = PromptSections(
            task="Generate code.",
            required_inputs={
                "schema.sql": "Database DDL defining table structure",
                "config.yml": "Application configuration",
            },
        )

        result = assembler_with_artifacts.assemble(
            profile_prompt=sections,
            phase=WorkflowPhase.GENERATING,
            metadata={},
        )

        # Should render as bulleted list
        assert "- **schema.sql**:" in result.user_prompt or "- schema.sql:" in result.user_prompt
        assert "Database DDL" in result.user_prompt


class TestProviderResultModel:
    """Tests for ProviderResult model."""

    def test_provider_result_with_all_files_written(self):
        """Provider wrote all files directly - values are None."""
        from aiwf.domain.models.provider_result import ProviderResult

        result = ProviderResult(
            files={
                "Customer.java": None,
                "CustomerRepository.java": None,
            },
            response="Generated entity and repository successfully.",
        )

        assert result.files["Customer.java"] is None
        assert result.files["CustomerRepository.java"] is None
        assert result.response == "Generated entity and repository successfully."

    def test_provider_result_with_content_returned(self):
        """Provider returned content (non-writing provider)."""
        from aiwf.domain.models.provider_result import ProviderResult

        result = ProviderResult(
            files={
                "Customer.java": "public class Customer { }",
                "CustomerRepository.java": "public interface CustomerRepository { }",
            },
        )

        assert result.files["Customer.java"] == "public class Customer { }"
        assert result.files["CustomerRepository.java"] == "public interface CustomerRepository { }"
        assert result.response is None

    def test_provider_result_mixed_written_and_content(self):
        """Provider wrote some files and returned content for others."""
        from aiwf.domain.models.provider_result import ProviderResult

        result = ProviderResult(
            files={
                "Customer.java": None,  # Written by provider
                "CustomerDTO.java": "public class CustomerDTO { }",  # Returned content
            },
        )

        assert result.files["Customer.java"] is None
        assert result.files["CustomerDTO.java"] == "public class CustomerDTO { }"


class TestProviderResultValidation:
    """Tests for engine validating provider results against expected_outputs."""

    @pytest.fixture
    def code_dir(self, tmp_path):
        """Create a code directory for testing."""
        code = tmp_path / "iteration-1" / "code"
        code.mkdir(parents=True)
        return code

    def test_validate_all_expected_files_exist(self, code_dir):
        """Engine validates all expected output files exist."""
        from aiwf.domain.models.provider_result import ProviderResult

        # Provider wrote files directly
        (code_dir / "Customer.java").write_text("public class Customer {}")
        (code_dir / "CustomerRepository.java").write_text("public interface CustomerRepository {}")

        result = ProviderResult(
            files={
                "Customer.java": None,
                "CustomerRepository.java": None,
            },
        )

        expected_outputs = ["Customer.java", "CustomerRepository.java"]

        # Validation should pass - all files exist
        missing = [f for f in expected_outputs if not (code_dir / f).exists()]
        assert missing == []

    def test_warn_on_missing_files(self, code_dir):
        """Engine warns but does not fail when expected files are missing."""
        from aiwf.domain.models.provider_result import ProviderResult

        # Only one file written
        (code_dir / "Customer.java").write_text("public class Customer {}")

        result = ProviderResult(
            files={
                "Customer.java": None,
            },
        )

        expected_outputs = ["Customer.java", "CustomerRepository.java"]

        # Find missing files
        missing = [f for f in expected_outputs if not (code_dir / f).exists()]
        assert missing == ["CustomerRepository.java"]
        # Engine should warn about this, not fail


class TestExpectedOutputsInPrompt:
    """Tests for expected_outputs appearing in assembled prompt."""

    @pytest.fixture
    def assembler(self, tmp_path):
        return PromptAssembler(session_dir=tmp_path, fs_ability="local-write")

    def test_expected_outputs_listed_in_prompt(self, assembler):
        """Expected outputs appear as a list in the prompt."""
        sections = PromptSections(
            task="Generate entity and repository.",
            expected_outputs=["Customer.java", "CustomerRepository.java"],
        )

        result = assembler.assemble(
            profile_prompt=sections,
            phase=WorkflowPhase.GENERATING,
            metadata={},
        )

        assert "Customer.java" in result.user_prompt
        assert "CustomerRepository.java" in result.user_prompt

    def test_expected_outputs_with_subdirectories(self, assembler):
        """Expected outputs with subdirectories shown correctly."""
        sections = PromptSections(
            task="Generate layered code.",
            expected_outputs=[
                "entity/Customer.java",
                "repository/CustomerRepository.java",
            ],
        )

        result = assembler.assemble(
            profile_prompt=sections,
            phase=WorkflowPhase.GENERATING,
            metadata={},
        )

        assert "entity/Customer.java" in result.user_prompt
        assert "repository/CustomerRepository.java" in result.user_prompt
```

---

## Step 2: Implement

### 2.1 Create PromptSections Model

**File:** `aiwf/domain/models/prompt_sections.py`

```python
"""Structured prompt sections for profile prompts."""

from pydantic import BaseModel


class PromptSections(BaseModel):
    """Structured prompt with discrete sections.

    Profiles can return this instead of a raw string to enable:
    - System/user prompt separation
    - Consistent section ordering
    - Engine validation of required sections
    """

    role: str | None = None
    """Who the AI is acting as. Goes to system prompt if supported."""

    required_inputs: dict[str, str] | None = None
    """Profile's required input files: {filename: description}. Engine merges with session artifacts."""

    context: str | None = None
    """How to use the inputs, domain-specific guidance. Goes to user prompt."""

    task: str
    """What the AI needs to do. Required. Goes to user prompt."""

    constraints: str | None = None
    """Rules and boundaries. Goes to system prompt if supported."""

    expected_outputs: list[str] | None = None
    """Files to produce. Written under /code, supports subdirectories."""

    output_format: str | None = None
    """Content formatting instructions (e.g., Lombok, Javadoc). Goes to user prompt."""

    def get_system_sections(self) -> str:
        """Return sections suitable for system prompt."""
        parts = []
        if self.role:
            parts.append(f"## Role\n\n{self.role}")
        if self.constraints:
            parts.append(f"## Constraints\n\n{self.constraints}")
        return "\n\n---\n\n".join(parts)

    def get_user_sections(self) -> str:
        """Return sections suitable for user prompt.

        Note: required_inputs is NOT included here - engine handles merging
        and rendering required_inputs with session artifacts.
        """
        parts = []
        if self.context:
            parts.append(f"## Context\n\n{self.context}")
        parts.append(f"## Task\n\n{self.task}")
        if self.expected_outputs:
            outputs_list = "\n".join(f"- {f}" for f in self.expected_outputs)
            parts.append(f"## Expected Outputs\n\n{outputs_list}")
        if self.output_format:
            parts.append(f"## Output Format\n\n{self.output_format}")
        return "\n\n---\n\n".join(parts)
```

### 2.2 Update WorkflowProfile ABC

**File:** `aiwf/domain/profiles/workflow_profile.py`

Update return type annotation to accept both:

```python
from aiwf.domain.models.prompt_sections import PromptSections

PromptResult = str | PromptSections

class WorkflowProfile(ABC):
    @abstractmethod
    def generate_planning_prompt(self, context: dict) -> PromptResult:
        ...

    @abstractmethod
    def generate_generation_prompt(self, context: dict) -> PromptResult:
        ...

    @abstractmethod
    def generate_review_prompt(self, context: dict) -> PromptResult:
        ...

    @abstractmethod
    def generate_revision_prompt(self, context: dict) -> PromptResult:
        ...
```

### 2.3 Create ProviderResult Model

**File:** `aiwf/domain/models/provider_result.py`

```python
"""Provider result model for multi-file output support."""

from pydantic import BaseModel


class ProviderResult(BaseModel):
    """Result from AI provider execution.

    Providers return this structured result to support multiple output files.
    The files dict maps relative paths to either content (if provider couldn't
    write) or None (if provider wrote the file directly).
    """

    files: dict[str, str | None]
    """Output files: {path: content or None if already written}.

    - Keys are paths relative to /code directory
    - Value is file content string if provider returned content
    - Value is None if provider wrote the file directly
    """

    response: str | None = None
    """Optional commentary/explanation for the response file.

    This is written to the response file (e.g., generation-response.md)
    and can contain the AI's explanation of what was generated.
    """
```

### 2.4 Update PromptAssembler

**File:** `aiwf/application/prompt_assembler.py`

Add handling for `PromptSections`:

```python
from aiwf.domain.models.prompt_sections import PromptSections

def assemble(
    self,
    profile_prompt: str | PromptSections,
    phase: WorkflowPhase,
    metadata: dict,
) -> AssembledPrompt:
    """Assemble final prompt from profile prompt and engine content."""

    # Handle structured vs pass-through
    if isinstance(profile_prompt, PromptSections):
        return self._assemble_from_sections(profile_prompt, phase, metadata)
    else:
        return self._assemble_from_string(profile_prompt, phase, metadata)

def _assemble_from_sections(
    self,
    sections: PromptSections,
    phase: WorkflowPhase,
    metadata: dict,
) -> AssembledPrompt:
    """Assemble from structured sections."""
    system_prompt = ""
    user_prompt = ""

    # Metadata at top of user prompt
    user_prompt += self._format_metadata(metadata)

    # Session artifacts
    user_prompt += self._get_session_artifacts(phase)

    if self.supports_system_prompt:
        # Split sections
        system_prompt = sections.get_system_sections()
        user_prompt += sections.get_user_sections()
        # Output instructions in system prompt
        system_prompt += self._get_output_instructions()
    else:
        # All in user prompt
        user_prompt += sections.get_system_sections()
        user_prompt += sections.get_user_sections()
        user_prompt += self._get_output_instructions()

    return AssembledPrompt(system_prompt=system_prompt, user_prompt=user_prompt)

def _assemble_from_string(
    self,
    prompt_str: str,
    phase: WorkflowPhase,
    metadata: dict,
) -> AssembledPrompt:
    """Assemble from pass-through string."""
    user_prompt = ""

    # Metadata at top
    user_prompt += self._format_metadata(metadata)

    # Session artifacts
    user_prompt += self._get_session_artifacts(phase)

    # Profile prompt (cannot split)
    user_prompt += prompt_str

    # Output instructions
    if self.supports_system_prompt:
        system_prompt = self._get_output_instructions()
    else:
        user_prompt += self._get_output_instructions()
        system_prompt = ""

    return AssembledPrompt(system_prompt=system_prompt, user_prompt=user_prompt)
```

---

## Step 3: Verify

Run all tests:

```bash
poetry run pytest tests/unit/domain/models/test_prompt_sections.py -v
poetry run pytest tests/unit/application/test_prompt_assembler.py -v
poetry run pytest tests/ -v --tb=short
```

---

## Files Changed

| File | Change |
|------|--------|
| `aiwf/domain/models/prompt_sections.py` | New model for structured prompt sections |
| `aiwf/domain/models/provider_result.py` | New model for provider multi-file results |
| `aiwf/domain/models/__init__.py` | Export PromptSections and ProviderResult |
| `aiwf/domain/profiles/workflow_profile.py` | Update return type to `str \| PromptSections` |
| `aiwf/domain/providers/ai_provider.py` | Update return type to `ProviderResult \| None` |
| `aiwf/application/prompt_assembler.py` | Handle both return types |
| `aiwf/application/approval_handler.py` | Handle ProviderResult, validate expected files |
| `tests/unit/domain/models/test_prompt_sections.py` | New tests |
| `tests/unit/domain/models/test_provider_result.py` | New tests |
| `tests/unit/application/test_prompt_assembler.py` | Updated tests |

---

## Migration Notes

### Existing Profiles

No changes required. Existing profiles return `str` and continue to work via pass-through mode.

### Adopting PromptSections

Profiles can migrate incrementally by:
1. Changing return type from `str` to `PromptSections`
2. Mapping existing template content to sections
3. No engine changes needed

---

## Acceptance Criteria

### PromptSections Model
- [ ] `PromptSections` model exists with: role, required_inputs, context, task, constraints, expected_outputs, output_format
- [ ] `required_inputs` is `dict[str, str]` mapping filename → description
- [ ] `expected_outputs` is `list[str]` of file paths (supports subdirectories, written under /code)
- [ ] `output_format` is content format only (e.g., Lombok, Javadoc)
- [ ] `task` is the only required field
- [ ] `get_system_sections()` returns role + constraints
- [ ] `get_user_sections()` returns context + task + expected_outputs + output_format

### ProviderResult Model
- [ ] `ProviderResult` model exists with: files (dict), response (optional str)
- [ ] `files` is `dict[str, str | None]` mapping path → content or None if written
- [ ] Provider returns `ProviderResult | None` (None for manual mode)
- [ ] Engine writes files where content is provided
- [ ] Engine validates files exist where value is None
- [ ] Engine warns (does not fail) on missing expected files

### Engine Assembly
- [ ] `WorkflowProfile` methods accept return type `str | PromptSections`
- [ ] `PromptAssembler` handles both return types (structured and pass-through)
- [ ] `PromptAssembler` merges profile's `required_inputs` with engine's session artifacts
- [ ] Required inputs rendered as bulleted list with descriptions
- [ ] Expected outputs listed in prompt for provider to know what files to create
- [ ] System/user split works when `supports_system_prompt=True`

### Backward Compatibility
- [ ] Existing profiles (returning str) continue to work via pass-through mode
- [ ] jpa-mt profile unchanged (uses pass-through)

### Tests
- [ ] All tests pass