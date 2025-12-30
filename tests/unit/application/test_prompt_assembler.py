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
            response_relpath="iteration-1/generation-response.md",
        )

        assert "Save your complete response to" in result["user_prompt"]
        assert "iteration-1/generation-response.md" in result["user_prompt"]

    def test_local_read_includes_filename_only(self, session_dir, generating_state):
        """local-read fs_ability includes filename only (no path)."""
        assembler = PromptAssembler(session_dir, generating_state)
        result = assembler.assemble(
            profile_prompt="Generate code",
            fs_ability="local-read",
            response_relpath="iteration-1/generation-response.md",
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
            response_relpath="iteration-1/generation-response.md",
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

    def test_revising_phase_in_iteration_1_no_code(self, session_dir):
        """REVISING phase in iteration 1 should not include code (guard against iteration-0)."""
        # Setup: state with iteration 1 but REVISING phase (edge case)
        state = MagicMock(spec=WorkflowState)
        state.phase = WorkflowPhase.REVISING
        state.current_iteration = 1  # Edge case: REVISING should not happen in iteration 1

        (session_dir / "plan.md").write_text("# Plan")
        (session_dir / "standards-bundle.md").write_text("# Standards")

        assembler = PromptAssembler(session_dir, state)
        result = assembler.assemble(
            profile_prompt="Revise the code",
            fs_ability="local-write",
        )

        # Should NOT include Previous Code section (no iteration-0 to reference)
        assert "## Previous Code" not in result["user_prompt"]

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
            response_relpath="iteration-1/generation-response.md",
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
            response_relpath="iteration-1/generation-response.md",
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