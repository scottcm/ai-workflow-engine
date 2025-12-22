"""Tests for JPA-MT review prompt and response processing."""
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


class TestReviewPromptGeneration:
    """Tests for generate_review_prompt."""

    def test_generate_review_prompt_returns_content(self, jpa_mt_profile):
        """Review prompt should return non-trivial content."""
        context = {
            "entity": "Product",
            "scope": "domain",
            "table": "app.products",
            "bounded_context": "catalog",
            "current_iteration": 1,
        }
        prompt = jpa_mt_profile.generate_review_prompt(context)

        assert prompt is not None
        assert len(prompt) > 100
        # Review template should include review-related content
        assert "review" in prompt.lower() or "Review" in prompt


class TestReviewResponseProcessing:
    """Tests for process_review_response."""

    def test_process_review_response_pass(self, jpa_mt_profile):
        """Review response with PASS verdict should return SUCCESS status."""
        response = """
@@@REVIEW_META
verdict: PASS
issues_total: 0
issues_critical: 0
missing_inputs: 0
@@@

Code looks good. All standards followed correctly.
"""
        result = jpa_mt_profile.process_review_response(response)

        assert result.status == WorkflowStatus.SUCCESS

    def test_process_review_response_fail(self, jpa_mt_profile):
        """Review response with FAIL verdict should return FAILED status."""
        response = """
@@@REVIEW_META
verdict: FAIL
issues_total: 2
issues_critical: 1
missing_inputs: 0
@@@

Critical: Missing @TenantId annotation.
Minor: Inconsistent field naming.
"""
        result = jpa_mt_profile.process_review_response(response)

        assert result.status == WorkflowStatus.FAILED

    def test_process_review_response_empty_returns_error(self, jpa_mt_profile):
        """Empty review response should return ERROR status."""
        result = jpa_mt_profile.process_review_response("")

        assert result.status == WorkflowStatus.ERROR

    def test_process_review_response_no_metadata_returns_error(self, jpa_mt_profile):
        """Review response without metadata block should return ERROR status."""
        response = "This is just some text without the review metadata block."
        result = jpa_mt_profile.process_review_response(response)

        assert result.status == WorkflowStatus.ERROR

    def test_process_review_response_malformed_metadata_returns_error(self, jpa_mt_profile):
        """Review response with malformed metadata should return ERROR status."""
        response = """
@@@REVIEW_META
verdict: MAYBE
issues_total: 1
@@@
"""
        result = jpa_mt_profile.process_review_response(response)

        assert result.status == WorkflowStatus.ERROR
