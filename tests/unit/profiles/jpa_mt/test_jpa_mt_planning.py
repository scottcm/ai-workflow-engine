"""Tests for JPA-MT planning prompt generation and response processing."""
import pytest

# Import profiles to trigger registration
import profiles  # noqa: F401

from aiwf.domain.profiles.profile_factory import ProfileFactory
from aiwf.domain.models.workflow_state import WorkflowStatus


class TestMetadataValidation:
    """Tests for jpa-mt profile metadata validation.

    Note: With ADR-0008 Phase 1, schema_file is now validated via context_schema,
    not metadata. The validate_metadata method is now a no-op for jpa-mt profile.
    """

    def test_validate_metadata_accepts_none(self, jpa_mt_profile):
        """jpa-mt profile accepts None metadata (no-op since ADR-0008)."""
        # Should not raise - schema_file is now validated via context
        jpa_mt_profile.validate_metadata(None)

    def test_validate_metadata_accepts_empty_dict(self, jpa_mt_profile):
        """jpa-mt profile accepts empty metadata (no-op since ADR-0008)."""
        # Should not raise - schema_file is now validated via context
        jpa_mt_profile.validate_metadata({})

    def test_validate_metadata_accepts_arbitrary_metadata(self, jpa_mt_profile):
        """jpa-mt profile accepts any metadata (no-op since ADR-0008)."""
        # Should not raise
        jpa_mt_profile.validate_metadata({"other_field": "value"})
        jpa_mt_profile.validate_metadata({"schema_file": "path/to/schema.sql"})


@pytest.fixture
def jpa_mt_profile(tmp_path, monkeypatch):
    """Create JPA-MT profile with test standards directory."""
    standards_dir = tmp_path / "standards"
    standards_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("STANDARDS_DIR", str(standards_dir))
    return ProfileFactory.create("jpa-mt")


class TestPlanningPromptGeneration:
    """Tests for generate_planning_prompt."""

    def test_generate_planning_prompt_returns_content(self, jpa_mt_profile):
        """Planning prompt should return non-trivial content with entity substituted."""
        context = {
            "entity": "Product",
            "scope": "domain",
            "table": "app.products",
            "bounded_context": "catalog",
        }
        prompt = jpa_mt_profile.generate_planning_prompt(context)

        assert prompt is not None
        assert len(prompt) > 100  # Non-trivial content
        assert "Product" in prompt  # Entity substituted

    def test_planning_prompt_has_required_sections(self, jpa_mt_profile):
        """Planning prompt should contain required sections."""
        context = {
            "entity": "Product",
            "scope": "domain",
            "table": "app.products",
            "bounded_context": "catalog",
        }
        prompt = jpa_mt_profile.generate_planning_prompt(context)

        # Should have some structure - either markdown headers or key sections
        assert "Product" in prompt
        # The prompt should mention planning or entity design
        prompt_lower = prompt.lower()
        assert "plan" in prompt_lower or "entity" in prompt_lower or "design" in prompt_lower


class TestPlanningResponseProcessing:
    """Tests for process_planning_response."""

    def test_process_planning_response_success(self, jpa_mt_profile):
        """Valid planning response should return SUCCESS status."""
        valid_response = """
# Entity Plan for Product

## Fields
- id: Long (primary key)
- name: String
- tenantId: Long

## Relationships
- None

## Notes
Standard JPA entity with multi-tenant support.
"""
        result = jpa_mt_profile.process_planning_response(valid_response)

        assert result.status == WorkflowStatus.SUCCESS

    def test_process_planning_response_empty_returns_error(self, jpa_mt_profile):
        """Empty planning response should return ERROR status."""
        result = jpa_mt_profile.process_planning_response("")

        assert result.status == WorkflowStatus.ERROR

    def test_process_planning_response_whitespace_only_returns_error(self, jpa_mt_profile):
        """Whitespace-only planning response should return ERROR status."""
        result = jpa_mt_profile.process_planning_response("   \n\n\t  ")

        assert result.status == WorkflowStatus.ERROR


class TestSchemaFileRendering:
    """Tests for schema file content rendering."""

    def test_schema_file_content_available_as_schema_ddl(self, jpa_mt_profile, tmp_path, monkeypatch):
        """When schema_file is provided, content is read and available as SCHEMA_DDL."""
        # Create schema file
        schema_file = tmp_path / "schema.sql"
        schema_file.write_text("CREATE TABLE foo (id INT);", encoding="utf-8")

        # Change cwd to tmp_path so relative path resolves
        monkeypatch.chdir(tmp_path)

        # Test _fill_placeholders directly with a template containing {{SCHEMA_DDL}}
        template = "Schema:\n{{SCHEMA_DDL}}\nEnd"
        context = {"schema_file": "schema.sql"}

        result = jpa_mt_profile._fill_placeholders(template, context)

        assert "CREATE TABLE foo (id INT);" in result
        assert "{{SCHEMA_DDL}}" not in result

    def test_schema_file_not_found_at_render_time_errors(self, jpa_mt_profile, tmp_path, monkeypatch):
        """When schema_file path doesn't exist at render time, error is raised."""
        monkeypatch.chdir(tmp_path)

        template = "Schema: {{SCHEMA_DDL}}"
        context = {"schema_file": "nonexistent.sql"}

        with pytest.raises(FileNotFoundError, match="Schema file not found"):
            jpa_mt_profile._fill_placeholders(template, context)

    def test_no_schema_file_renders_empty_schema_ddl(self, jpa_mt_profile):
        """When no schema_file provided, {{SCHEMA_DDL}} renders as empty string."""
        template = "Schema: {{SCHEMA_DDL}} End"
        context = {}

        result = jpa_mt_profile._fill_placeholders(template, context)

        # SCHEMA_DDL replaced with empty string
        assert result == "Schema:  End"
        assert "{{SCHEMA_DDL}}" not in result
