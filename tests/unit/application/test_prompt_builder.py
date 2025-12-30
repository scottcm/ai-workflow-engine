"""Tests for PromptBuilder - constructs prompts from PromptSections.

TDD Tests for Phase 3.
"""

import pytest

from aiwf.application.prompt_builder import PromptBuilder
from aiwf.domain.models.prompt_sections import PromptSections


class TestPromptBuilderBasicConstruction:
    """Tests for basic prompt construction from sections."""

    def test_build_with_task_only(self) -> None:
        """Minimal prompt: task is required, renders as Task section."""
        builder = PromptBuilder()
        builder.with_task("Generate JPA entities")
        result = builder.build()

        assert "## Task" in result["user_prompt"]
        assert "Generate JPA entities" in result["user_prompt"]

    def test_build_with_role_renders_role_section(self) -> None:
        """Role section rendered with ## Role header when provided."""
        builder = PromptBuilder()
        builder.with_task("Do something")
        builder.with_role("Senior Java developer")
        result = builder.build()

        assert "## Role" in result["user_prompt"]
        assert "Senior Java developer" in result["user_prompt"]

    def test_build_with_context_renders_context_section(self) -> None:
        """Context section rendered with ## Context header when provided."""
        builder = PromptBuilder()
        builder.with_task("Do something")
        builder.with_context("Use existing patterns from codebase")
        result = builder.build()

        assert "## Context" in result["user_prompt"]
        assert "Use existing patterns from codebase" in result["user_prompt"]

    def test_build_with_constraints_renders_constraints_section(self) -> None:
        """Constraints section rendered with ## Constraints header when provided."""
        builder = PromptBuilder()
        builder.with_task("Do something")
        builder.with_constraints("Use Lombok annotations")
        result = builder.build()

        assert "## Constraints" in result["user_prompt"]
        assert "Use Lombok annotations" in result["user_prompt"]

    def test_build_with_output_format_renders_output_format_section(self) -> None:
        """Output format section rendered with ## Output Format header when provided."""
        builder = PromptBuilder()
        builder.with_task("Do something")
        builder.with_output_format("Include Javadoc comments")
        result = builder.build()

        assert "## Output Format" in result["user_prompt"]
        assert "Include Javadoc comments" in result["user_prompt"]

    def test_build_omits_none_sections(self) -> None:
        """Sections with None values are omitted from output."""
        builder = PromptBuilder()
        builder.with_task("Do something")
        builder.with_role(None)
        builder.with_context(None)
        result = builder.build()

        assert "## Task" in result["user_prompt"]
        assert "## Role" not in result["user_prompt"]
        assert "## Context" not in result["user_prompt"]


class TestPromptBuilderRequiredInputs:
    """Tests for required inputs rendering."""

    def test_required_inputs_rendered_as_bulleted_list(self) -> None:
        """Required inputs rendered as markdown bulleted list with bold filenames."""
        builder = PromptBuilder()
        builder.with_task("Do something")
        builder.with_required_inputs({
            "schema.sql": "Database DDL defining table structure",
            "config.yml": "Configuration settings",
        })
        result = builder.build()

        assert "## Required Inputs" in result["user_prompt"]
        assert "- **schema.sql**:" in result["user_prompt"]
        assert "Database DDL defining table structure" in result["user_prompt"]
        assert "- **config.yml**:" in result["user_prompt"]
        assert "Configuration settings" in result["user_prompt"]

    def test_required_inputs_merged_with_session_artifacts(self) -> None:
        """Session artifacts merged into required inputs dict."""
        builder = PromptBuilder()
        builder.with_task("Do something")
        builder.with_required_inputs({"schema.sql": "Database DDL"})
        builder.with_session_artifacts({
            "standards-bundle.md": "Coding standards (engine-provided)",
            "plan.md": "Approved implementation plan (engine-provided)",
        })
        result = builder.build()

        assert "schema.sql" in result["user_prompt"]
        assert "standards-bundle.md" in result["user_prompt"]
        assert "plan.md" in result["user_prompt"]

    def test_session_artifacts_do_not_override_profile_inputs(self) -> None:
        """Profile-provided input descriptions take precedence over session artifacts."""
        builder = PromptBuilder()
        builder.with_task("Do something")
        builder.with_required_inputs({"schema.sql": "Profile description"})
        builder.with_session_artifacts({"schema.sql": "Engine description"})
        result = builder.build()

        assert "Profile description" in result["user_prompt"]
        assert "Engine description" not in result["user_prompt"]

    def test_empty_required_inputs_omits_section(self) -> None:
        """Empty required inputs dict omits the section entirely."""
        builder = PromptBuilder()
        builder.with_task("Do something")
        builder.with_required_inputs({})
        result = builder.build()

        assert "## Required Inputs" not in result["user_prompt"]


class TestPromptBuilderExpectedOutputs:
    """Tests for expected outputs rendering."""

    def test_expected_outputs_rendered_as_bulleted_list(self) -> None:
        """Expected outputs rendered as markdown bulleted list."""
        builder = PromptBuilder()
        builder.with_task("Do something")
        builder.with_expected_outputs(["Customer.java", "Order.java"])
        result = builder.build()

        assert "## Expected Outputs" in result["user_prompt"]
        assert "- Customer.java" in result["user_prompt"]
        assert "- Order.java" in result["user_prompt"]

    def test_expected_outputs_with_subdirectories(self) -> None:
        """Expected outputs can include subdirectory paths."""
        builder = PromptBuilder()
        builder.with_task("Do something")
        builder.with_expected_outputs([
            "entity/Customer.java",
            "repository/CustomerRepository.java",
        ])
        result = builder.build()

        assert "- entity/Customer.java" in result["user_prompt"]
        assert "- repository/CustomerRepository.java" in result["user_prompt"]

    def test_empty_expected_outputs_omits_section(self) -> None:
        """Empty expected outputs list omits the section entirely."""
        builder = PromptBuilder()
        builder.with_task("Do something")
        builder.with_expected_outputs([])
        result = builder.build()

        assert "## Expected Outputs" not in result["user_prompt"]


class TestPromptBuilderSectionOrdering:
    """Tests for section ordering in output."""

    def test_sections_ordered_correctly(self) -> None:
        """Sections appear in canonical order."""
        builder = PromptBuilder()
        builder.with_role("Developer")
        builder.with_required_inputs({"input.txt": "Input file"})
        builder.with_context("Some context")
        builder.with_task("Do task")
        builder.with_constraints("Some constraints")
        builder.with_expected_outputs(["output.txt"])
        builder.with_output_format("Plain text")
        result = builder.build()

        prompt = result["user_prompt"]
        # Find positions of each section
        role_pos = prompt.find("## Role")
        inputs_pos = prompt.find("## Required Inputs")
        context_pos = prompt.find("## Context")
        task_pos = prompt.find("## Task")
        constraints_pos = prompt.find("## Constraints")
        outputs_pos = prompt.find("## Expected Outputs")
        format_pos = prompt.find("## Output Format")

        # Verify order: Role < Required Inputs < Context < Task < Constraints < Expected Outputs < Output Format
        assert role_pos < inputs_pos < context_pos < task_pos < constraints_pos < outputs_pos < format_pos


class TestPromptBuilderSystemUserSplit:
    """Tests for system/user prompt separation."""

    def test_build_without_system_support_combines_all(self) -> None:
        """Without system prompt support, all sections go to user_prompt."""
        builder = PromptBuilder()
        builder.with_role("Developer")
        builder.with_task("Do task")
        builder.with_constraints("Be careful")
        result = builder.build(supports_system_prompt=False)

        assert result["system_prompt"] == ""
        assert "## Role" in result["user_prompt"]
        assert "## Task" in result["user_prompt"]
        assert "## Constraints" in result["user_prompt"]

    def test_build_with_system_support_separates_sections(self) -> None:
        """With system prompt support, role+constraints go to system_prompt."""
        builder = PromptBuilder()
        builder.with_role("Developer")
        builder.with_task("Do task")
        builder.with_constraints("Be careful")
        result = builder.build(supports_system_prompt=True)

        # Role and constraints in system prompt
        assert "## Role" in result["system_prompt"]
        assert "Developer" in result["system_prompt"]
        assert "## Constraints" in result["system_prompt"]
        assert "Be careful" in result["system_prompt"]
        # Task in user prompt
        assert "## Task" in result["user_prompt"]
        assert "Do task" in result["user_prompt"]
        # Role and constraints NOT in user prompt
        assert "## Role" not in result["user_prompt"]
        assert "## Constraints" not in result["user_prompt"]

    def test_system_prompt_empty_when_no_system_sections(self) -> None:
        """System prompt is empty string when role and constraints are both None."""
        builder = PromptBuilder()
        builder.with_task("Do task")
        result = builder.build(supports_system_prompt=True)

        assert result["system_prompt"] == ""
        assert "## Task" in result["user_prompt"]


class TestPromptBuilderFluentInterface:
    """Tests for fluent builder interface."""

    def test_with_methods_return_self(self) -> None:
        """All with_* methods return self for chaining."""
        builder = PromptBuilder()

        assert builder.with_role("Dev") is builder
        assert builder.with_required_inputs({}) is builder
        assert builder.with_session_artifacts({}) is builder
        assert builder.with_context("ctx") is builder
        assert builder.with_task("task") is builder
        assert builder.with_constraints("con") is builder
        assert builder.with_expected_outputs([]) is builder
        assert builder.with_output_format("fmt") is builder

    def test_chained_calls_accumulate(self) -> None:
        """Multiple chained calls accumulate all sections."""
        result = (
            PromptBuilder()
            .with_role("Developer")
            .with_task("Build feature")
            .with_constraints("Follow standards")
            .build()
        )

        assert "Developer" in result["user_prompt"]
        assert "Build feature" in result["user_prompt"]
        assert "Follow standards" in result["user_prompt"]


class TestPromptBuilderFromSections:
    """Tests for building from PromptSections model."""

    def test_from_sections_populates_all_fields(self) -> None:
        """PromptBuilder.from_sections() populates builder from PromptSections."""
        sections = PromptSections(
            role="Senior developer",
            required_inputs={"schema.sql": "Database schema"},
            context="Use existing patterns",
            task="Generate entities",
            constraints="Use Lombok",
            expected_outputs=["Customer.java"],
            output_format="Include Javadoc",
        )
        result = PromptBuilder.from_sections(sections).build()

        assert "Senior developer" in result["user_prompt"]
        assert "schema.sql" in result["user_prompt"]
        assert "Use existing patterns" in result["user_prompt"]
        assert "Generate entities" in result["user_prompt"]
        assert "Use Lombok" in result["user_prompt"]
        assert "Customer.java" in result["user_prompt"]
        assert "Include Javadoc" in result["user_prompt"]

    def test_from_sections_with_minimal_sections(self) -> None:
        """from_sections() works with minimal PromptSections (task only)."""
        sections = PromptSections(task="Just do the task")
        result = PromptBuilder.from_sections(sections).build()

        assert "## Task" in result["user_prompt"]
        assert "Just do the task" in result["user_prompt"]