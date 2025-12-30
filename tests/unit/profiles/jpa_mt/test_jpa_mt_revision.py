"""Tests for JPA-MT revision prompt and response processing."""
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


class TestRevisionPromptGeneration:
    """Tests for generate_revision_prompt."""

    def test_generate_revision_prompt_returns_content(self, jpa_mt_profile):
        """Revision prompt should return non-trivial content."""
        context = {
            "entity": "Product",
            "scope": "domain",
            "table": "app.products",
            "bounded_context": "catalog",
            "current_iteration": 2,
        }
        prompt = jpa_mt_profile.generate_revision_prompt(context)

        assert prompt is not None
        assert len(prompt) > 100
        # Revision template should include revision-related content
        prompt_lower = prompt.lower()
        assert "revision" in prompt_lower or "fix" in prompt_lower or "correct" in prompt_lower

    def test_generate_revision_prompt_includes_code_files(self, jpa_mt_profile):
        """Revision prompt should format code_files as markdown list."""
        context = {
            "entity": "Product",
            "scope": "domain",
            "table": "app.products",
            "bounded_context": "catalog",
            "current_iteration": 2,
            "code_files": [
                "iteration-1/code/Product.java",
                "iteration-1/code/ProductRepository.java",
            ],
        }
        prompt = jpa_mt_profile.generate_revision_prompt(context)

        assert "- `iteration-1/code/Product.java`" in prompt
        assert "- `iteration-1/code/ProductRepository.java`" in prompt


class TestRevisionResponseProcessing:
    """Tests for process_revision_response."""

    def test_process_revision_response_extracts_files(self, jpa_mt_profile, tmp_path):
        """Revision response with code blocks should extract files."""
        response = '''<<<FILE: Product.java>>>
    package com.example;

    public class Product {
        private Long id;
        private Long tenantId;
    }

<<<FILE: ProductRepository.java>>>
    package com.example;

    public interface ProductRepository {
    }
'''
        result = jpa_mt_profile.process_revision_response(response, tmp_path, iteration=2)

        assert result.status == WorkflowStatus.SUCCESS
        assert result.write_plan is not None
        assert len(result.write_plan.writes) == 2
        # Profile returns filenames only - engine adds iteration prefix
        paths = [w.path for w in result.write_plan.writes]
        assert "Product.java" in paths
        assert "ProductRepository.java" in paths

    def test_process_revision_response_empty_returns_error(self, jpa_mt_profile, tmp_path):
        """Empty revision response should return ERROR status."""
        result = jpa_mt_profile.process_revision_response("", tmp_path, iteration=2)

        assert result.status == WorkflowStatus.ERROR

    def test_process_revision_response_no_code_blocks_returns_error(self, jpa_mt_profile, tmp_path):
        """Revision response without code blocks should return ERROR."""
        response = "Here is some text explaining the changes but no actual code."
        result = jpa_mt_profile.process_revision_response(response, tmp_path, iteration=2)

        assert result.status == WorkflowStatus.ERROR
