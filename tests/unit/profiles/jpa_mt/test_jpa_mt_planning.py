"""Tests for JPA-MT planning prompt generation and response processing."""
import pytest

# Import profiles to trigger registration
import profiles  # noqa: F401

from aiwf.domain.profiles.profile_factory import ProfileFactory
from aiwf.domain.models.workflow_state import WorkflowStatus


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
