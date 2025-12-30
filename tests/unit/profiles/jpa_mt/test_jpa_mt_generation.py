"""Tests for JPA-MT generation prompt and response processing."""
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


class TestGenerationPromptGeneration:
    """Tests for generate_generation_prompt."""

    def test_generate_generation_prompt_returns_content(self, jpa_mt_profile):
        """Generation prompt should return non-trivial content."""
        context = {
            "entity": "Product",
            "scope": "domain",
            "table": "app.products",
            "bounded_context": "catalog",
        }
        prompt = jpa_mt_profile.generate_generation_prompt(context)

        assert prompt is not None
        assert len(prompt) > 100
        assert "Product" in prompt


class TestGenerationResponseProcessing:
    """Tests for process_generation_response."""

    def test_process_generation_response_extracts_files(self, jpa_mt_profile, tmp_path):
        """Generation response with code blocks should extract files."""
        response = '''<<<FILE: Product.java>>>
    package com.example;

    public class Product {
        private Long id;
    }

<<<FILE: ProductRepository.java>>>
    package com.example;

    public interface ProductRepository {
    }
'''
        result = jpa_mt_profile.process_generation_response(response, tmp_path, iteration=1)

        assert result.status == WorkflowStatus.SUCCESS
        assert result.write_plan is not None
        assert len(result.write_plan.writes) == 2

    def test_process_generation_response_empty_returns_error(self, jpa_mt_profile, tmp_path):
        """Empty generation response should return ERROR status."""
        result = jpa_mt_profile.process_generation_response("", tmp_path, iteration=1)

        assert result.status == WorkflowStatus.ERROR

    def test_process_generation_response_no_code_blocks_returns_error(self, jpa_mt_profile, tmp_path):
        """Generation response without code blocks should return ERROR."""
        response = "Here is some text but no code blocks."
        result = jpa_mt_profile.process_generation_response(response, tmp_path, iteration=1)

        assert result.status == WorkflowStatus.ERROR


class TestWritePlanFilenamesOnly:
    """Tests for profile returning filenames only (no iteration prefix)."""

    def test_generation_response_returns_filename_only(self, jpa_mt_profile, tmp_path):
        """process_generation_response returns filename without path prefix."""
        response_content = '''
<<<FILE: Customer.java>>>
public class Customer {}
'''
        result = jpa_mt_profile.process_generation_response(response_content, tmp_path, iteration=1)

        assert result.write_plan is not None
        assert len(result.write_plan.writes) == 1
        write_op = result.write_plan.writes[0]
        # Should be just filename, NOT "iteration-1/code/Customer.java"
        assert write_op.path == "Customer.java"
        assert "iteration" not in write_op.path

    def test_revision_response_returns_filename_only(self, jpa_mt_profile, tmp_path):
        """process_revision_response returns filename without path prefix."""
        response_content = '''
<<<FILE: Customer.java>>>
public class Customer { /* revised */ }
'''
        result = jpa_mt_profile.process_revision_response(response_content, tmp_path, iteration=2)

        assert result.write_plan is not None
        write_op = result.write_plan.writes[0]
        # Should be just filename, even in iteration 2
        assert write_op.path == "Customer.java"
        assert "iteration" not in write_op.path

    def test_multiple_files_all_have_filenames_only(self, jpa_mt_profile, tmp_path):
        """Multiple files in response all have filenames only."""
        response_content = '''
<<<FILE: Customer.java>>>
public class Customer {}

<<<FILE: Order.java>>>
public class Order {}
'''
        result = jpa_mt_profile.process_generation_response(response_content, tmp_path, iteration=1)

        assert result.write_plan is not None
        assert len(result.write_plan.writes) == 2
        for write_op in result.write_plan.writes:
            assert "iteration" not in write_op.path
            assert "/" not in write_op.path  # No path separators
