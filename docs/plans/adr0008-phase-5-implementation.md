# Phase 5: Engine Prompt Assembly - Implementation Guide

**Goal:** Engine assembles final prompt from session artifacts, profile content, and output instructions.

**Dependencies:** Phase 3 (Provider Capability Metadata)

**TDD Approach:** This phase has a well-defined PromptAssembler class with clear input/output behavior. Write tests first to specify assembly logic.

---

## Overview

Create a prompt assembly module that:
1. Injects session artifacts (plan, standards bundle, previous code)
2. Combines with profile-generated prompt
3. Appends output instructions based on fs_ability
4. Optionally uses system prompt for capable providers

**Parallelism note:** This phase modifies the orchestrator's prompt generation. If running in parallel with Phase 6 (WritePlan Simplification), coordinate to ensure orchestrator changes don't conflict. Phase 6 primarily modifies artifact_writer, so conflicts should be minimal.

---

## Step 1: Write Tests First

Write tests before any implementation. These tests define the expected behavior.

### 1.1 Output Instructions Tests

**File:** `tests/unit/application/test_prompt_assembler.py`

```python
"""Tests for PromptAssembler - output instructions based on fs_ability."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from aiwf.application.prompt_assembler import PromptAssembler
from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowState


@pytest.fixture
def session_dir(tmp_path):
    """Create a temporary session directory."""
    return tmp_path


@pytest.fixture
def planning_state():
    """Create a WorkflowState in PLANNING phase."""
    state = MagicMock(spec=WorkflowState)
    state.phase = WorkflowPhase.PLANNING
    state.current_iteration = 1
    return state


@pytest.fixture
def generating_state():
    """Create a WorkflowState in GENERATING phase."""
    state = MagicMock(spec=WorkflowState)
    state.phase = WorkflowPhase.GENERATING
    state.current_iteration = 1
    return state


@pytest.fixture
def reviewing_state():
    """Create a WorkflowState in REVIEWING phase."""
    state = MagicMock(spec=WorkflowState)
    state.phase = WorkflowPhase.REVIEWING
    state.current_iteration = 1
    return state


@pytest.fixture
def revising_state():
    """Create a WorkflowState in REVISING phase."""
    state = MagicMock(spec=WorkflowState)
    state.phase = WorkflowPhase.REVISING
    state.current_iteration = 2  # Revision happens in iteration 2+
    return state


class TestOutputInstructions:
    """Tests for output instruction generation based on fs_ability."""

    def test_local_write_includes_full_path(self, session_dir, generating_state):
        """local-write fs_ability includes full path for saving."""
        assembler = PromptAssembler(session_dir, generating_state)
        result = assembler.assemble(
            profile_prompt="Generate code",
            fs_ability="local-write",
        )

        assert "Save your complete response to" in result["user_prompt"]
        assert "generation-response.md" in result["user_prompt"]

    def test_local_read_includes_filename_only(self, session_dir, generating_state):
        """local-read fs_ability includes filename only (no path)."""
        assembler = PromptAssembler(session_dir, generating_state)
        result = assembler.assemble(
            profile_prompt="Generate code",
            fs_ability="local-read",
        )

        assert "Name your output file" in result["user_prompt"]
        assert "generation-response.md" in result["user_prompt"]
        # Should NOT include iteration path for local-read
        assert "iteration-" not in result["user_prompt"].split("Name your output file")[1]

    def test_write_only_mentions_downloadable(self, session_dir, generating_state):
        """write-only fs_ability mentions creating downloadable file."""
        assembler = PromptAssembler(session_dir, generating_state)
        result = assembler.assemble(
            profile_prompt="Generate code",
            fs_ability="write-only",
        )

        assert "Create a downloadable file" in result["user_prompt"]
        assert "generation-response.md" in result["user_prompt"]

    def test_none_fs_ability_no_output_instructions(self, session_dir, generating_state):
        """none fs_ability produces no output instructions."""
        assembler = PromptAssembler(session_dir, generating_state)
        result = assembler.assemble(
            profile_prompt="Generate code",
            fs_ability="none",
        )

        assert "Save your" not in result["user_prompt"]
        assert "Name your output" not in result["user_prompt"]
        assert "downloadable" not in result["user_prompt"]

    def test_unknown_fs_ability_no_output_instructions(self, session_dir, generating_state):
        """Unknown fs_ability produces no output instructions (safe fallback)."""
        assembler = PromptAssembler(session_dir, generating_state)
        result = assembler.assemble(
            profile_prompt="Generate code",
            fs_ability="unknown-value",
        )

        assert "Save your" not in result["user_prompt"]
        assert "## Output" not in result["user_prompt"]


class TestSessionArtifactInjection:
    """Tests for session artifact injection based on phase."""

    def test_planning_phase_includes_standards_only(self, session_dir, planning_state):
        """PLANNING phase includes standards bundle but not plan or code."""
        # Setup: create standards bundle
        (session_dir / "standards-bundle.md").write_text("# Standards\n\nRule 1")

        assembler = PromptAssembler(session_dir, planning_state)
        result = assembler.assemble(
            profile_prompt="Create a plan",
            fs_ability="local-write",
        )

        assert "## Standards Bundle" in result["user_prompt"]
        assert "Rule 1" in result["user_prompt"]
        assert "## Approved Plan" not in result["user_prompt"]
        assert "## Previous Code" not in result["user_prompt"]

    def test_generating_phase_includes_plan_and_standards(self, session_dir, generating_state):
        """GENERATING phase includes both plan and standards bundle."""
        # Setup: create plan and standards
        (session_dir / "plan.md").write_text("# Plan\n\nStep 1: Do X")
        (session_dir / "standards-bundle.md").write_text("# Standards\n\nRule 1")

        assembler = PromptAssembler(session_dir, generating_state)
        result = assembler.assemble(
            profile_prompt="Generate code",
            fs_ability="local-write",
        )

        assert "## Approved Plan" in result["user_prompt"]
        assert "Step 1: Do X" in result["user_prompt"]
        assert "## Standards Bundle" in result["user_prompt"]
        assert "Rule 1" in result["user_prompt"]
        assert "## Previous Code" not in result["user_prompt"]

    def test_reviewing_phase_includes_all_artifacts(self, session_dir, reviewing_state):
        """REVIEWING phase includes plan, standards, and code."""
        # Setup: create all artifacts
        (session_dir / "plan.md").write_text("# Plan")
        (session_dir / "standards-bundle.md").write_text("# Standards")
        code_dir = session_dir / "iteration-1" / "code"
        code_dir.mkdir(parents=True)
        (code_dir / "Customer.java").write_text("public class Customer {}")

        assembler = PromptAssembler(session_dir, reviewing_state)
        result = assembler.assemble(
            profile_prompt="Review the code",
            fs_ability="local-write",
        )

        assert "## Approved Plan" in result["user_prompt"]
        assert "## Standards Bundle" in result["user_prompt"]
        assert "## Previous Code" in result["user_prompt"]
        assert "Customer.java" in result["user_prompt"]

    def test_revising_phase_includes_previous_iteration_code(self, session_dir, revising_state):
        """REVISING phase includes code from previous iteration."""
        # Setup: create code in iteration-1 (previous)
        (session_dir / "plan.md").write_text("# Plan")
        (session_dir / "standards-bundle.md").write_text("# Standards")
        code_dir = session_dir / "iteration-1" / "code"  # Previous iteration
        code_dir.mkdir(parents=True)
        (code_dir / "Customer.java").write_text("public class Customer {}")

        assembler = PromptAssembler(session_dir, revising_state)
        result = assembler.assemble(
            profile_prompt="Revise the code",
            fs_ability="local-write",
        )

        assert "## Previous Code" in result["user_prompt"]
        assert "Customer.java" in result["user_prompt"]

    def test_missing_artifacts_handled_gracefully(self, session_dir, generating_state):
        """Missing artifacts don't cause errors."""
        # No artifacts exist
        assembler = PromptAssembler(session_dir, generating_state)
        result = assembler.assemble(
            profile_prompt="Generate code",
            fs_ability="local-write",
        )

        # Should still have profile prompt
        assert "Generate code" in result["user_prompt"]
        # Should not crash, just omit missing sections
        assert "## Approved Plan" not in result["user_prompt"]


class TestFileReferenceMode:
    """Tests for file reference mode (when provider supports file attachments)."""

    def test_inline_mode_includes_content(self, session_dir, generating_state):
        """Without file attachment support, content is inlined."""
        (session_dir / "plan.md").write_text("Plan content here")

        assembler = PromptAssembler(session_dir, generating_state)
        result = assembler.assemble(
            profile_prompt="Generate",
            fs_ability="local-write",
            supports_file_attachments=False,
        )

        assert "Plan content here" in result["user_prompt"]
        assert "@" not in result["user_prompt"] or "@ " in result["user_prompt"]  # No file refs

    def test_file_ref_mode_uses_references(self, session_dir, generating_state):
        """With file attachment support, uses @path references."""
        (session_dir / "plan.md").write_text("Plan content here")

        assembler = PromptAssembler(session_dir, generating_state)
        result = assembler.assemble(
            profile_prompt="Generate",
            fs_ability="local-write",
            supports_file_attachments=True,
        )

        # Should use file reference instead of content
        assert "@" in result["user_prompt"]
        assert "plan.md" in result["user_prompt"]
        # Content should NOT be inlined
        assert "Plan content here" not in result["user_prompt"]


class TestSystemPromptSeparation:
    """Tests for system prompt separation when provider supports it."""

    def test_no_system_prompt_support_combines_all(self, session_dir, generating_state):
        """Without system prompt support, everything in user_prompt."""
        assembler = PromptAssembler(session_dir, generating_state)
        result = assembler.assemble(
            profile_prompt="Generate code",
            fs_ability="local-write",
            supports_system_prompt=False,
        )

        assert result["system_prompt"] == ""
        assert "Generate code" in result["user_prompt"]
        assert "## Output" in result["user_prompt"]  # Output instructions in user prompt

    def test_system_prompt_support_separates_output_instructions(
        self, session_dir, generating_state
    ):
        """With system prompt support, output instructions go to system prompt."""
        assembler = PromptAssembler(session_dir, generating_state)
        result = assembler.assemble(
            profile_prompt="Generate code",
            fs_ability="local-write",
            supports_system_prompt=True,
        )

        # Output instructions should be in system prompt
        assert "Save your complete response" in result["system_prompt"]
        # Profile prompt should be in user prompt
        assert "Generate code" in result["user_prompt"]
        # Output instructions should NOT be duplicated in user prompt
        assert "Save your complete response" not in result["user_prompt"]

    def test_system_prompt_empty_when_no_output_instructions(
        self, session_dir, generating_state
    ):
        """System prompt empty when fs_ability=none (no output instructions)."""
        assembler = PromptAssembler(session_dir, generating_state)
        result = assembler.assemble(
            profile_prompt="Generate code",
            fs_ability="none",
            supports_system_prompt=True,
        )

        # No output instructions to put in system prompt
        assert result["system_prompt"] == ""


class TestCodeSectionBuilding:
    """Tests for code section building in review/revision phases."""

    def test_code_section_includes_all_files(self, session_dir, reviewing_state):
        """Code section includes all files in code directory."""
        code_dir = session_dir / "iteration-1" / "code"
        code_dir.mkdir(parents=True)
        (code_dir / "Customer.java").write_text("public class Customer {}")
        (code_dir / "CustomerRepository.java").write_text("public interface CustomerRepository {}")

        assembler = PromptAssembler(session_dir, reviewing_state)
        result = assembler.assemble(
            profile_prompt="Review",
            fs_ability="local-write",
        )

        assert "Customer.java" in result["user_prompt"]
        assert "CustomerRepository.java" in result["user_prompt"]
        assert "public class Customer" in result["user_prompt"]
        assert "public interface CustomerRepository" in result["user_prompt"]

    def test_code_section_sorted_alphabetically(self, session_dir, reviewing_state):
        """Code files are sorted alphabetically."""
        code_dir = session_dir / "iteration-1" / "code"
        code_dir.mkdir(parents=True)
        (code_dir / "Zebra.java").write_text("class Zebra {}")
        (code_dir / "Apple.java").write_text("class Apple {}")

        assembler = PromptAssembler(session_dir, reviewing_state)
        result = assembler.assemble(
            profile_prompt="Review",
            fs_ability="local-write",
        )

        # Apple should appear before Zebra
        apple_pos = result["user_prompt"].find("Apple.java")
        zebra_pos = result["user_prompt"].find("Zebra.java")
        assert apple_pos < zebra_pos

    def test_nested_code_files_included(self, session_dir, reviewing_state):
        """Nested code files (subdirectories) are included."""
        code_dir = session_dir / "iteration-1" / "code"
        (code_dir / "entity").mkdir(parents=True)
        (code_dir / "entity" / "Customer.java").write_text("package entity;")

        assembler = PromptAssembler(session_dir, reviewing_state)
        result = assembler.assemble(
            profile_prompt="Review",
            fs_ability="local-write",
        )

        assert "Customer.java" in result["user_prompt"]
        assert "package entity" in result["user_prompt"]


class TestLanguageDetection:
    """Tests for language detection for syntax highlighting."""

    def test_java_file_detected(self, session_dir, reviewing_state):
        """Java files get java syntax highlighting."""
        code_dir = session_dir / "iteration-1" / "code"
        code_dir.mkdir(parents=True)
        (code_dir / "Test.java").write_text("class Test {}")

        assembler = PromptAssembler(session_dir, reviewing_state)
        result = assembler.assemble(
            profile_prompt="Review",
            fs_ability="local-write",
        )

        assert "```java" in result["user_prompt"]

    def test_python_file_detected(self, session_dir, reviewing_state):
        """Python files get python syntax highlighting."""
        code_dir = session_dir / "iteration-1" / "code"
        code_dir.mkdir(parents=True)
        (code_dir / "test.py").write_text("def test(): pass")

        assembler = PromptAssembler(session_dir, reviewing_state)
        result = assembler.assemble(
            profile_prompt="Review",
            fs_ability="local-write",
        )

        assert "```python" in result["user_prompt"]

    def test_unknown_extension_no_language(self, session_dir, reviewing_state):
        """Unknown extensions get no language hint."""
        code_dir = session_dir / "iteration-1" / "code"
        code_dir.mkdir(parents=True)
        (code_dir / "config.xyz").write_text("some content")

        assembler = PromptAssembler(session_dir, reviewing_state)
        result = assembler.assemble(
            profile_prompt="Review",
            fs_ability="local-write",
        )

        # Should have ``` without language
        assert "```\nsome content\n```" in result["user_prompt"]

    @pytest.mark.parametrize(
        "extension,expected_lang",
        [
            (".java", "java"),
            (".py", "python"),
            (".js", "javascript"),
            (".ts", "typescript"),
            (".md", "markdown"),
            (".yaml", "yaml"),
            (".yml", "yaml"),
            (".json", "json"),
            (".xml", "xml"),
            (".sql", "sql"),
        ],
    )
    def test_all_supported_extensions(
        self, session_dir, reviewing_state, extension, expected_lang
    ):
        """All documented extensions are detected correctly."""
        code_dir = session_dir / "iteration-1" / "code"
        code_dir.mkdir(parents=True)
        (code_dir / f"file{extension}").write_text("content")

        assembler = PromptAssembler(session_dir, reviewing_state)
        result = assembler.assemble(
            profile_prompt="Review",
            fs_ability="local-write",
        )

        assert f"```{expected_lang}" in result["user_prompt"]


class TestLargeArtifacts:
    """Tests for behavior with large session artifacts."""

    def test_large_plan_included_without_crash(self, session_dir, generating_state):
        """Large plan files (>100KB) are handled without crash."""
        # Create a 150KB plan
        large_content = "# Plan\n\n" + ("Step details. " * 10000)
        assert len(large_content) > 100000  # >100KB

        (session_dir / "plan.md").write_text(large_content)

        assembler = PromptAssembler(session_dir, generating_state)
        result = assembler.assemble(
            profile_prompt="Generate",
            fs_ability="local-write",
        )

        # Should include the content without error
        assert "Step details" in result["user_prompt"]

    def test_large_standards_bundle_included(self, session_dir, generating_state):
        """Large standards bundle files are handled."""
        large_content = "# Standards\n\n" + ("Rule explanation. " * 10000)
        (session_dir / "standards-bundle.md").write_text(large_content)

        assembler = PromptAssembler(session_dir, generating_state)
        result = assembler.assemble(
            profile_prompt="Generate",
            fs_ability="local-write",
        )

        assert "Rule explanation" in result["user_prompt"]
```

---

## Step 2: Implement to Pass Tests

### 2.1 Create Prompt Assembler Module

**File:** `aiwf/application/prompt_assembler.py` (new)

```python
from pathlib import Path
from typing import Any

from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowState


class PromptAssembler:
    """Assembles final prompts from session artifacts, profile content, and engine instructions."""

    def __init__(self, session_dir: Path, state: WorkflowState):
        self.session_dir = session_dir
        self.state = state

    def assemble(
        self,
        profile_prompt: str,
        fs_ability: str,
        supports_system_prompt: bool = False,
        supports_file_attachments: bool = False,
    ) -> dict[str, str]:
        """Assemble the final prompt.

        Returns:
            dict with keys:
            - "user_prompt": The main prompt content
            - "system_prompt": System instructions (if supports_system_prompt)
        """
        # 1. Build session artifacts section
        artifacts = self._build_session_artifacts(supports_file_attachments)

        # 2. Build output instructions
        output_instructions = self._build_output_instructions(fs_ability)

        # 3. Combine based on provider capabilities
        if supports_system_prompt and output_instructions:
            return {
                "system_prompt": output_instructions,
                "user_prompt": artifacts + "\n\n---\n\n" + profile_prompt,
            }
        else:
            user_prompt = artifacts + "\n\n---\n\n" + profile_prompt
            if output_instructions:
                user_prompt += "\n\n---\n\n" + output_instructions
            return {
                "system_prompt": "",
                "user_prompt": user_prompt,
            }

    def _build_session_artifacts(self, use_file_refs: bool) -> str:
        """Build the session artifacts section."""
        sections = []

        # Plan (for generation, review, revision phases)
        if self.state.phase in (
            WorkflowPhase.GENERATING,
            WorkflowPhase.REVIEWING,
            WorkflowPhase.REVISING,
        ):
            plan_content = self._get_artifact_content("plan.md", use_file_refs)
            if plan_content:
                sections.append(f"## Approved Plan\n\n{plan_content}")

        # Standards bundle (for all phases except INITIALIZED)
        if self.state.phase != WorkflowPhase.INITIALIZED:
            standards_content = self._get_artifact_content(
                "standards-bundle.md", use_file_refs
            )
            if standards_content:
                sections.append(f"## Standards Bundle\n\n{standards_content}")

        # Previous code (for review and revision phases)
        if self.state.phase in (WorkflowPhase.REVIEWING, WorkflowPhase.REVISING):
            code_section = self._build_code_section(use_file_refs)
            if code_section:
                sections.append(code_section)

        return "\n\n---\n\n".join(sections)

    def _get_artifact_content(self, filename: str, use_file_refs: bool) -> str:
        """Get artifact content, either as file reference or inline."""
        path = self.session_dir / filename
        if not path.exists():
            return ""

        if use_file_refs:
            return f"@{path}"
        else:
            return path.read_text(encoding="utf-8")

    def _build_code_section(self, use_file_refs: bool) -> str:
        """Build the previous code section for review/revision."""
        # Determine which iteration's code to include
        if self.state.phase == WorkflowPhase.REVIEWING:
            code_iteration = self.state.current_iteration
        else:  # REVISING - code is from previous iteration
            code_iteration = self.state.current_iteration - 1

        code_dir = self.session_dir / f"iteration-{code_iteration}" / "code"
        if not code_dir.exists():
            return ""

        sections = ["## Previous Code"]
        for file_path in sorted(code_dir.rglob("*")):
            if file_path.is_file():
                filename = file_path.name
                if use_file_refs:
                    sections.append(f"### {filename}\n\n@{file_path}")
                else:
                    content = file_path.read_text(encoding="utf-8")
                    # Detect language for syntax highlighting
                    lang = self._detect_language(filename)
                    sections.append(f"### {filename}\n\n```{lang}\n{content}\n```")

        return "\n\n".join(sections)

    def _detect_language(self, filename: str) -> str:
        """Detect language from filename for syntax highlighting."""
        ext_map = {
            ".java": "java",
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".md": "markdown",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".json": "json",
            ".xml": "xml",
            ".sql": "sql",
        }
        ext = Path(filename).suffix.lower()
        return ext_map.get(ext, "")

    def _build_output_instructions(self, fs_ability: str) -> str:
        """Build output instructions based on fs_ability."""
        response_filename = self._get_response_filename()
        response_path = self._get_response_path()

        if fs_ability == "local-write":
            return f"## Output\n\nSave your complete response to `{response_path}`"
        elif fs_ability == "local-read":
            return f"## Output\n\nName your output file `{response_filename}`"
        elif fs_ability == "write-only":
            return f"## Output\n\nCreate a downloadable file named `{response_filename}`"
        else:  # none or unknown
            return ""

    def _get_response_filename(self) -> str:
        """Get expected response filename for current phase."""
        from aiwf.application.approval_specs import ING_APPROVAL_SPECS

        phase = self.state.phase
        if phase in ING_APPROVAL_SPECS:
            spec = ING_APPROVAL_SPECS[phase]
            # Extract filename from template like "iteration-{N}/generation-response.md"
            template = spec.response_relpath_template
            # Replace {N} and extract filename
            relpath = template.format(N=self.state.current_iteration)
            return Path(relpath).name
        return "response.md"

    def _get_response_path(self) -> str:
        """Get full response path relative to session directory."""
        from aiwf.application.approval_specs import ING_APPROVAL_SPECS

        phase = self.state.phase
        if phase in ING_APPROVAL_SPECS:
            spec = ING_APPROVAL_SPECS[phase]
            return spec.response_relpath_template.format(N=self.state.current_iteration)
        return "response.md"
```

---

## Step 3: Integrate with Workflow Orchestrator

**File:** `aiwf/application/workflow_orchestrator.py`

Update the `_step_*` methods that generate prompts to use the assembler.

Before (current pattern):
```python
# In _step_initialized:
content = profile_instance.generate_planning_prompt(self._prompt_context(state=state))
prompt_file.write_text(content, encoding="utf-8")
```

After:
```python
# In _step_initialized:
from aiwf.application.prompt_assembler import PromptAssembler

profile_content = profile_instance.generate_planning_prompt(self._prompt_context(state=state))

# Get provider capabilities
provider_key = state.providers.get("planner", "manual")
provider = ProviderFactory.create(provider_key)
metadata = provider.get_metadata()

# Resolve fs_ability (from Phase 3)
fs_ability = resolve_fs_ability(
    cli_override=None,  # Would come from CLI if passed
    provider_key=provider_key,
    config=self._load_config(),
    provider_metadata=metadata,
)

# Assemble final prompt
assembler = PromptAssembler(session_dir, state)
result = assembler.assemble(
    profile_prompt=profile_content,
    fs_ability=fs_ability,
    supports_system_prompt=metadata.get("supports_system_prompt", False),
    supports_file_attachments=metadata.get("supports_file_attachments", False),
)

# Write prompt (for now, just user_prompt; system_prompt used when invoking provider)
prompt_file.write_text(result["user_prompt"], encoding="utf-8")

# Store system_prompt somewhere if needed for provider invocation
if result["system_prompt"]:
    # Could write to separate file or pass to approval handler
    pass
```

---

## Step 3: Update Approval Handler

**File:** `aiwf/application/approval_handler.py`

When invoking the provider, pass system prompt if available:

```python
def run_provider(
    provider_key: str,
    prompt: str,
    system_prompt: str | None = None,
) -> str | None:
    """Invoke an AI provider to generate a response."""
    provider = ProviderFactory.create(provider_key)
    metadata = provider.get_metadata()

    # If provider supports system prompt and we have one, pass it
    # (This requires updating AIProvider.generate() signature)
    return provider.generate(
        prompt,
        system_prompt=system_prompt,
        connection_timeout=metadata.get("default_connection_timeout"),
        response_timeout=metadata.get("default_response_timeout"),
    )
```

**Note:** This may require updating the `AIProvider.generate()` signature to accept `system_prompt`. Alternatively, store system prompt in a convention-based file that providers can read.

---

## Step 4: Handle Provider Invocation

**File:** `aiwf/domain/providers/ai_provider.py`

Consider updating the generate signature:

```python
@abstractmethod
def generate(
    self,
    prompt: str,
    context: dict[str, Any] | None = None,
    system_prompt: str | None = None,  # NEW
    connection_timeout: int | None = None,
    response_timeout: int | None = None,
) -> str | None:
    ...
```

Providers that support system prompts can use it; others ignore it.

---

## Testing Requirements

**File:** `tests/unit/application/test_prompt_assembler.py` (new)

1. Test session artifact injection for each phase
2. Test file reference mode vs inline mode
3. Test output instruction generation for each fs_ability value
4. Test system prompt separation when supported
5. Test code section building for review/revision phases
6. Test language detection for syntax highlighting
7. Test behavior with large session artifacts (>100KB plan/standards) - verify no crashes, content included

**File:** `tests/integration/test_workflow_orchestrator.py`

8. Test prompts include session artifacts
9. Test prompts include output instructions based on fs_ability
10. Test end-to-end workflow with assembled prompts

---

## Files Changed

| File | Change |
|------|--------|
| `aiwf/application/prompt_assembler.py` | New module |
| `aiwf/application/workflow_orchestrator.py` | Integrate assembler |
| `aiwf/application/approval_handler.py` | Pass system prompt to provider |
| `aiwf/domain/providers/ai_provider.py` | Add system_prompt parameter |
| `aiwf/domain/providers/manual_provider.py` | Accept system_prompt (ignore) |
| `tests/unit/application/test_prompt_assembler.py` | New tests |
| `tests/integration/test_workflow_orchestrator.py` | Updated tests |

---

## Acceptance Criteria

- [ ] `PromptAssembler` correctly injects plan, standards bundle, previous code
- [ ] Output instructions generated based on fs_ability
- [ ] System prompt separated when provider supports it
- [ ] File references used when provider supports attachments
- [ ] Prompts written to disk include assembled content
- [ ] All tests pass