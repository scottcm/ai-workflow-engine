"""Tests for PromptSections model."""

import pytest
from pydantic import ValidationError

from aiwf.domain.models.prompt_sections import PromptSections


class TestPromptSectionsFields:
    """Tests for PromptSections field definitions."""

    def test_task_is_required(self) -> None:
        """Task field is required - cannot create without it."""
        with pytest.raises(ValidationError):
            PromptSections()  # type: ignore[call-arg]

    def test_minimal_prompt_sections(self) -> None:
        """Can create with only required task field."""
        sections = PromptSections(task="Generate entity classes")
        assert sections.task == "Generate entity classes"
        assert sections.role is None
        assert sections.context is None
        assert sections.constraints is None
        assert sections.output_format is None

    def test_optional_fields_with_defaults(self) -> None:
        """Optional collection fields have correct defaults."""
        sections = PromptSections(task="Test task")
        assert sections.required_inputs == {}
        assert sections.expected_outputs == []

    def test_all_fields_populated(self) -> None:
        """All fields can be populated."""
        sections = PromptSections(
            role="Senior Java developer",
            required_inputs={"schema.sql": "Database DDL"},
            context="Use existing patterns from codebase",
            task="Generate JPA entities",
            constraints="Use Lombok annotations",
            expected_outputs=["entity/Customer.java", "entity/Order.java"],
            output_format="Include Javadoc comments",
        )
        assert sections.role == "Senior Java developer"
        assert sections.required_inputs == {"schema.sql": "Database DDL"}
        assert sections.context == "Use existing patterns from codebase"
        assert sections.task == "Generate JPA entities"
        assert sections.constraints == "Use Lombok annotations"
        assert sections.expected_outputs == ["entity/Customer.java", "entity/Order.java"]
        assert sections.output_format == "Include Javadoc comments"


class TestPromptSectionsSystemSections:
    """Tests for get_system_sections() method."""

    def test_returns_role_and_constraints(self) -> None:
        """System sections include role and constraints."""
        sections = PromptSections(
            role="Expert architect",
            task="Design system",
            constraints="Follow SOLID principles",
        )
        system = sections.get_system_sections()
        assert system["role"] == "Expert architect"
        assert system["constraints"] == "Follow SOLID principles"

    def test_returns_none_for_unset_fields(self) -> None:
        """System sections return None for unset optional fields."""
        sections = PromptSections(task="Do something")
        system = sections.get_system_sections()
        assert system["role"] is None
        assert system["constraints"] is None

    def test_only_includes_system_fields(self) -> None:
        """System sections only include role and constraints."""
        sections = PromptSections(
            role="Developer",
            context="Some context",
            task="Some task",
            constraints="Some constraints",
        )
        system = sections.get_system_sections()
        assert set(system.keys()) == {"role", "constraints"}


class TestPromptSectionsUserSections:
    """Tests for get_user_sections() method."""

    def test_returns_user_content_fields(self) -> None:
        """User sections include context, task, expected_outputs, output_format."""
        sections = PromptSections(
            context="Background info",
            task="Generate code",
            expected_outputs=["Foo.java"],
            output_format="Use tabs",
        )
        user = sections.get_user_sections()
        assert user["context"] == "Background info"
        assert user["task"] == "Generate code"
        assert user["expected_outputs"] == ["Foo.java"]
        assert user["output_format"] == "Use tabs"

    def test_returns_none_for_unset_optional_fields(self) -> None:
        """User sections return None/empty for unset optional fields."""
        sections = PromptSections(task="Do task")
        user = sections.get_user_sections()
        assert user["context"] is None
        assert user["task"] == "Do task"
        assert user["expected_outputs"] == []
        assert user["output_format"] is None

    def test_only_includes_user_fields(self) -> None:
        """User sections exclude role and constraints."""
        sections = PromptSections(
            role="Developer",
            context="Context",
            task="Task",
            constraints="Constraints",
            expected_outputs=["file.txt"],
            output_format="Format",
        )
        user = sections.get_user_sections()
        assert set(user.keys()) == {"context", "task", "expected_outputs", "output_format"}
        assert "role" not in user
        assert "constraints" not in user


class TestPromptSectionsContract:
    """Tests verifying model contract for external callers."""

    def test_model_fields_exist(self) -> None:
        """All documented fields exist on the model."""
        expected_fields = {
            "role",
            "required_inputs",
            "context",
            "task",
            "constraints",
            "expected_outputs",
            "output_format",
        }
        assert expected_fields == set(PromptSections.model_fields.keys())

    def test_required_inputs_is_mutable_dict(self) -> None:
        """Required inputs can be modified after creation."""
        sections = PromptSections(task="Test")
        sections.required_inputs["new_file.txt"] = "Description"
        assert "new_file.txt" in sections.required_inputs

    def test_expected_outputs_is_mutable_list(self) -> None:
        """Expected outputs can be modified after creation."""
        sections = PromptSections(task="Test")
        sections.expected_outputs.append("output.java")
        assert "output.java" in sections.expected_outputs