"""Tests for Phase 7 template cleanup - engine concerns removed from profile templates.

These tests verify that templates no longer contain:
1. Output destination instructions (engine now provides these)
2. Session artifact path references (@.aiwf/sessions/...)
3. Session path variables used for path construction ({{SESSION_ID}}, {{ITERATION}} in paths)

Templates should still contain:
1. Domain variables ({{ENTITY}}, {{TABLE}}, etc.)
2. Output format instructions (<<<FILE:>>>, @@@REVIEW_META)
3. Standards application instructions
"""
import pytest
import re

# Import profiles to trigger registration
import profiles  # noqa: F401

from aiwf.domain.profiles.profile_factory import ProfileFactory


@pytest.fixture
def jpa_mt_profile(tmp_path, monkeypatch):
    """Create JPA-MT profile with test standards directory."""
    standards_dir = tmp_path / "standards"
    standards_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("STANDARDS_DIR", str(standards_dir))
    return ProfileFactory.create("jpa-mt")


@pytest.fixture
def minimal_context(tmp_path, monkeypatch):
    """Provide minimal context for rendering templates."""
    schema_file = tmp_path / "schema.sql"
    schema_file.write_text("CREATE TABLE test.sample (id BIGINT PRIMARY KEY);")
    monkeypatch.chdir(tmp_path)

    return {
        "entity": "Sample",
        "table": "test.sample",
        "bounded_context": "testing",
        "schema_file": str(schema_file),
        "task_id": "TEST-001",
        "dev": "testdev",
        "date": "2025-01-01",
        "session_id": "test-session-123",
        "profile": "jpa-mt",
        "iteration": "1",
    }


class TestTemplatesNoOutputDestination:
    """Tests that templates no longer contain output destination instructions."""

    # Patterns that indicate output destination instructions (should NOT be present)
    OUTPUT_DEST_PATTERNS = [
        r"##\s*Output\s+Destination",  # Section header
        r"Save your complete.*response",  # Save instruction
        r"Save your complete code bundle as",
        r"Save your complete planning document as",
        r"Save your complete review as",
        r"planning-response\.md",  # Output filename reference in destination context
        r"generation-response\.md",
        r"review-response\.md",
        r"revision-response\.md",
        r"to same location as.*-prompt\.md",  # Location instruction
    ]

    def _assert_no_output_destination(self, rendered_content: str, phase: str):
        """Assert that rendered content does not contain output destination patterns."""
        for pattern in self.OUTPUT_DEST_PATTERNS:
            matches = re.findall(pattern, rendered_content, re.IGNORECASE)
            assert not matches, (
                f"{phase} template should not contain output destination pattern '{pattern}'. "
                f"Found: {matches}"
            )

    @pytest.mark.parametrize("scope", ["domain", "vertical"])
    def test_planning_template_no_output_destination(
        self, jpa_mt_profile, minimal_context, scope
    ):
        """Planning templates should not contain output destination instructions."""
        minimal_context["scope"] = scope
        rendered = jpa_mt_profile.generate_planning_prompt(minimal_context)
        self._assert_no_output_destination(rendered, f"planning/{scope}")

    @pytest.mark.parametrize("scope", ["domain", "vertical"])
    def test_generation_template_no_output_destination(
        self, jpa_mt_profile, minimal_context, scope
    ):
        """Generation templates should not contain output destination instructions."""
        minimal_context["scope"] = scope
        rendered = jpa_mt_profile.generate_generation_prompt(minimal_context)
        self._assert_no_output_destination(rendered, f"generation/{scope}")

    @pytest.mark.parametrize("scope", ["domain", "vertical"])
    def test_review_template_no_output_destination(
        self, jpa_mt_profile, minimal_context, scope
    ):
        """Review templates should not contain output destination instructions."""
        minimal_context["scope"] = scope
        rendered = jpa_mt_profile.generate_review_prompt(minimal_context)
        self._assert_no_output_destination(rendered, f"review/{scope}")

    @pytest.mark.parametrize("scope", ["domain", "vertical"])
    def test_revision_template_no_output_destination(
        self, jpa_mt_profile, minimal_context, scope
    ):
        """Revision templates should not contain output destination instructions."""
        minimal_context["scope"] = scope
        rendered = jpa_mt_profile.generate_revision_prompt(minimal_context)
        self._assert_no_output_destination(rendered, f"revision/{scope}")


class TestTemplatesNoSessionPaths:
    """Tests that templates no longer contain session artifact path references."""

    # Patterns for session artifact paths (should NOT be present)
    SESSION_PATH_PATTERNS = [
        r"@\.aiwf/sessions/",  # Session artifact reference
        r"\.aiwf/sessions/\{\{SESSION_ID\}\}",  # Session path with variable
        r"@\.aiwf/sessions/\{\{SESSION_ID\}\}/plan\.md",  # Plan path
        r"@\.aiwf/sessions/\{\{SESSION_ID\}\}/standards-bundle\.md",  # Standards path
    ]

    def _assert_no_session_paths(self, rendered_content: str, phase: str):
        """Assert that rendered content does not contain session path patterns."""
        for pattern in self.SESSION_PATH_PATTERNS:
            matches = re.findall(pattern, rendered_content, re.IGNORECASE)
            assert not matches, (
                f"{phase} template should not contain session path pattern '{pattern}'. "
                f"Found: {matches}"
            )

    @pytest.mark.parametrize("scope", ["domain", "vertical"])
    def test_generation_template_no_session_paths(
        self, jpa_mt_profile, minimal_context, scope
    ):
        """Generation templates should not contain session artifact paths."""
        minimal_context["scope"] = scope
        rendered = jpa_mt_profile.generate_generation_prompt(minimal_context)
        self._assert_no_session_paths(rendered, f"generation/{scope}")

    @pytest.mark.parametrize("scope", ["domain", "vertical"])
    def test_revision_template_no_session_paths(
        self, jpa_mt_profile, minimal_context, scope
    ):
        """Revision templates should not contain session artifact paths."""
        minimal_context["scope"] = scope
        rendered = jpa_mt_profile.generate_revision_prompt(minimal_context)
        self._assert_no_session_paths(rendered, f"revision/{scope}")


class TestTemplatesPreserveDomainVariables:
    """Tests that templates still correctly use domain variables."""

    def test_planning_template_renders_entity(self, jpa_mt_profile, minimal_context):
        """Planning template should render {{ENTITY}} variable."""
        minimal_context["scope"] = "domain"
        rendered = jpa_mt_profile.generate_planning_prompt(minimal_context)
        assert "Sample" in rendered, "Planning template should render entity name"

    def test_planning_template_renders_table(self, jpa_mt_profile, minimal_context):
        """Planning template should render {{TABLE}} variable."""
        minimal_context["scope"] = "domain"
        rendered = jpa_mt_profile.generate_planning_prompt(minimal_context)
        assert "test.sample" in rendered, "Planning template should render table name"

    def test_planning_template_renders_bounded_context(
        self, jpa_mt_profile, minimal_context
    ):
        """Planning template should render {{BOUNDED_CONTEXT}} variable."""
        minimal_context["scope"] = "domain"
        rendered = jpa_mt_profile.generate_planning_prompt(minimal_context)
        assert "testing" in rendered, "Planning template should render bounded context"

    def test_generation_template_renders_schema_ddl(
        self, jpa_mt_profile, minimal_context
    ):
        """Generation template should include schema DDL content."""
        minimal_context["scope"] = "domain"
        rendered = jpa_mt_profile.generate_generation_prompt(minimal_context)
        # The schema DDL content should be included
        assert "CREATE TABLE" in rendered or "BIGINT" in rendered, (
            "Generation template should include schema DDL content"
        )


class TestTemplatesPreserveFormatInstructions:
    """Tests that templates preserve output format instructions (profile's responsibility)."""

    def test_generation_template_preserves_file_marker_instructions(
        self, jpa_mt_profile, minimal_context
    ):
        """Generation template should preserve <<<FILE:>>> format instructions."""
        minimal_context["scope"] = "domain"
        rendered = jpa_mt_profile.generate_generation_prompt(minimal_context)
        assert "<<<FILE:" in rendered, (
            "Generation template should preserve file marker format instructions"
        )

    def test_generation_template_preserves_code_bundle_format(
        self, jpa_mt_profile, minimal_context
    ):
        """Generation template should preserve code bundle format section."""
        minimal_context["scope"] = "domain"
        rendered = jpa_mt_profile.generate_generation_prompt(minimal_context)
        # Check for format instructions section
        assert "Output Format" in rendered or "Code Bundle" in rendered, (
            "Generation template should preserve output format instructions"
        )

    def test_review_template_preserves_review_meta_instructions(
        self, jpa_mt_profile, minimal_context
    ):
        """Review template should preserve @@@REVIEW_META format instructions."""
        minimal_context["scope"] = "domain"
        rendered = jpa_mt_profile.generate_review_prompt(minimal_context)
        assert "@@@REVIEW_META" in rendered, (
            "Review template should preserve review metadata format instructions"
        )


class TestTemplatesPreserveStandardsInstructions:
    """Tests that templates preserve standards application instructions."""

    def test_planning_template_has_standards_authority(
        self, jpa_mt_profile, minimal_context
    ):
        """Planning template should preserve standards authority rule."""
        minimal_context["scope"] = "domain"
        rendered = jpa_mt_profile.generate_planning_prompt(minimal_context)
        assert "standards" in rendered.lower(), (
            "Planning template should reference standards"
        )

    def test_generation_template_has_standards_authority(
        self, jpa_mt_profile, minimal_context
    ):
        """Generation template should preserve standards authority rule."""
        minimal_context["scope"] = "domain"
        rendered = jpa_mt_profile.generate_generation_prompt(minimal_context)
        assert "standards" in rendered.lower(), (
            "Generation template should reference standards"
        )


class TestGenerationGuidelinesUpdated:
    """Tests that generation guidelines have updated input references."""

    def test_generation_guidelines_no_attachment_paths(
        self, jpa_mt_profile, minimal_context
    ):
        """Generation guidelines should not have @.aiwf session paths."""
        minimal_context["scope"] = "domain"
        rendered = jpa_mt_profile.generate_generation_prompt(minimal_context)

        # Should NOT have the old attachment format with session paths
        assert "@.aiwf/sessions/" not in rendered, (
            "Generation guidelines should not contain @.aiwf/sessions/ paths"
        )

    def test_generation_guidelines_mention_provided_inputs(
        self, jpa_mt_profile, minimal_context
    ):
        """Generation guidelines should describe engine-provided inputs."""
        minimal_context["scope"] = "domain"
        rendered = jpa_mt_profile.generate_generation_prompt(minimal_context)

        # Check that it mentions inputs are provided (in some form)
        # The exact wording depends on implementation, but it should have some reference
        # to plan/standards being available
        has_plan_ref = "plan" in rendered.lower()
        has_standards_ref = "standards" in rendered.lower()
        assert has_plan_ref and has_standards_ref, (
            "Generation guidelines should reference plan and standards as available inputs"
        )