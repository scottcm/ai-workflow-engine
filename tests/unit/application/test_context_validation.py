import pytest
from pathlib import Path

from aiwf.application.context_validation import validate_context, ValidationError


class TestValidateContext:
    """Tests for context validation against profile schema."""

    @pytest.fixture
    def jpa_mt_schema(self):
        """Schema matching jpa-mt profile requirements."""
        return {
            "scope": {"type": "string", "required": True, "choices": ["domain", "vertical"]},
            "entity": {"type": "string", "required": True},
            "table": {"type": "string", "required": True},
            "bounded_context": {"type": "string", "required": True},
            "schema_file": {"type": "path", "required": True, "exists": True},
            "dev": {"type": "string", "required": False},
            "task_id": {"type": "string", "required": False},
        }

    def test_valid_context_returns_no_errors(self, jpa_mt_schema, tmp_path):
        """Valid context passes validation."""
        schema_file = tmp_path / "schema.sql"
        schema_file.write_text("CREATE TABLE customer (...);")

        context = {
            "scope": "domain",
            "entity": "Customer",
            "table": "customer",
            "bounded_context": "sales",
            "schema_file": str(schema_file),
        }
        errors = validate_context(jpa_mt_schema, context)
        assert errors == []

    def test_missing_required_field_returns_error(self, jpa_mt_schema, tmp_path):
        """Missing required field produces error with field name."""
        schema_file = tmp_path / "schema.sql"
        schema_file.write_text("CREATE TABLE customer (...);")

        context = {
            "scope": "domain",
            # "entity" is missing
            "table": "customer",
            "bounded_context": "sales",
            "schema_file": str(schema_file),
        }
        errors = validate_context(jpa_mt_schema, context)
        assert len(errors) == 1
        assert errors[0].field == "entity"
        assert "required" in errors[0].message.lower() or "missing" in errors[0].message.lower()

    def test_invalid_choice_returns_error_with_value(self, jpa_mt_schema, tmp_path):
        """Invalid choice produces error with expected values and actual value."""
        schema_file = tmp_path / "schema.sql"
        schema_file.write_text("CREATE TABLE customer (...);")

        context = {
            "scope": "invalid_scope",  # Not in ["domain", "vertical"]
            "entity": "Customer",
            "table": "customer",
            "bounded_context": "sales",
            "schema_file": str(schema_file),
        }
        errors = validate_context(jpa_mt_schema, context)
        assert len(errors) == 1
        assert errors[0].field == "scope"
        assert "domain" in errors[0].message
        assert "vertical" in errors[0].message
        assert "invalid_scope" in errors[0].message

    def test_wrong_type_returns_error(self, jpa_mt_schema, tmp_path):
        """Wrong type produces error with expected and actual type."""
        schema_file = tmp_path / "schema.sql"
        schema_file.write_text("CREATE TABLE customer (...);")

        context = {
            "scope": "domain",
            "entity": 123,  # Should be string, not int
            "table": "customer",
            "bounded_context": "sales",
            "schema_file": str(schema_file),
        }
        errors = validate_context(jpa_mt_schema, context)
        assert len(errors) == 1
        assert errors[0].field == "entity"
        assert "string" in errors[0].message.lower()
        assert "int" in errors[0].message.lower()

    def test_nonexistent_path_returns_error(self, jpa_mt_schema):
        """Path that doesn't exist produces error."""
        context = {
            "scope": "domain",
            "entity": "Customer",
            "table": "customer",
            "bounded_context": "sales",
            "schema_file": "/nonexistent/path/schema.sql",
        }
        errors = validate_context(jpa_mt_schema, context)
        assert len(errors) == 1
        assert errors[0].field == "schema_file"
        assert "exist" in errors[0].message.lower()

    def test_optional_field_can_be_omitted(self, jpa_mt_schema, tmp_path):
        """Optional fields don't cause errors when omitted."""
        schema_file = tmp_path / "schema.sql"
        schema_file.write_text("CREATE TABLE customer (...);")

        context = {
            "scope": "domain",
            "entity": "Customer",
            "table": "customer",
            "bounded_context": "sales",
            "schema_file": str(schema_file),
            # dev and task_id are optional, not provided
        }
        errors = validate_context(jpa_mt_schema, context)
        assert errors == []

    def test_multiple_errors_returned(self, jpa_mt_schema):
        """Multiple validation failures return multiple errors."""
        context = {
            "scope": "invalid",
            # entity missing
            "table": "customer",
            # bounded_context missing
            "schema_file": "/nonexistent/path.sql",
        }
        errors = validate_context(jpa_mt_schema, context)
        assert len(errors) >= 3  # scope invalid, entity missing, bounded_context missing, path invalid
        fields_with_errors = {e.field for e in errors}
        assert "scope" in fields_with_errors
        assert "entity" in fields_with_errors
        assert "bounded_context" in fields_with_errors

    def test_empty_schema_accepts_any_context(self):
        """Profile with no schema accepts any context."""
        errors = validate_context({}, {"anything": "goes", "count": 42})
        assert errors == []

    def test_path_rejects_directory(self, tmp_path):
        """Path validation rejects directories when exists=True."""
        schema = {"data_dir": {"type": "path", "required": True, "exists": True}}
        # tmp_path is a directory, not a file
        context = {"data_dir": str(tmp_path)}
        errors = validate_context(schema, context)
        assert len(errors) == 1
        assert errors[0].field == "data_dir"
        assert "not a file" in errors[0].message.lower()

    def test_choices_work_for_int_type(self):
        """Choices validation works for non-string types."""
        schema = {"level": {"type": "int", "required": True, "choices": [1, 2, 3]}}

        # Valid choice
        errors = validate_context(schema, {"level": 2})
        assert errors == []

        # Invalid choice
        errors = validate_context(schema, {"level": 5})
        assert len(errors) == 1
        assert errors[0].field == "level"
        assert "5" in errors[0].message

    def test_choices_work_for_bool_type(self):
        """Choices validation works for bool type (edge case)."""
        schema = {"flag": {"type": "bool", "required": True, "choices": [True]}}

        # Valid choice
        errors = validate_context(schema, {"flag": True})
        assert errors == []

        # Invalid choice
        errors = validate_context(schema, {"flag": False})
        assert len(errors) == 1
        assert errors[0].field == "flag"