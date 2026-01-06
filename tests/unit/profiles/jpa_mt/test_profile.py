"""Tests for JpaMtProfile."""

import pytest

from aiwf.domain.models.workflow_state import WorkflowStatus
from profiles.jpa_mt.profile import JpaMtProfile


class TestConditionalProcessing:
    """Test conditional template processing."""

    @pytest.fixture
    def profile(self):
        """Create a JpaMtProfile instance."""
        return JpaMtProfile()

    def test_if_block_with_defined_var(self, profile):
        """{{#if var}} includes content when var is defined and non-empty."""
        text = "Hello {{#if name}}{{name}}{{/if}}!"
        variables = {"name": "World"}
        result = profile._resolve_variables(text, variables)
        assert result == "Hello World!"

    def test_if_block_with_undefined_var(self, profile):
        """{{#if var}} excludes content when var is undefined."""
        text = "Hello {{#if name}}{{name}}{{/if}}!"
        variables = {}
        result = profile._resolve_variables(text, variables)
        assert result == "Hello !"

    def test_if_block_with_empty_var(self, profile):
        """{{#if var}} excludes content when var is empty string."""
        text = "Hello {{#if name}}{{name}}{{/if}}!"
        variables = {"name": ""}
        result = profile._resolve_variables(text, variables)
        assert result == "Hello !"

    def test_unless_block_with_undefined_var(self, profile):
        """{{#unless var}} includes content when var is undefined."""
        text = "{{#unless entity_extends}}No base class{{/unless}}"
        variables = {}
        result = profile._resolve_variables(text, variables)
        assert result == "No base class"

    def test_unless_block_with_defined_var(self, profile):
        """{{#unless var}} excludes content when var is defined."""
        text = "{{#unless entity_extends}}No base class{{/unless}}"
        variables = {"entity_extends": "BaseEntity"}
        result = profile._resolve_variables(text, variables)
        assert result == ""

    def test_nested_conditionals(self, profile):
        """Nested conditionals are processed correctly."""
        text = "{{#if a}}A{{#if b}}B{{/if}}{{/if}}"
        variables = {"a": "yes", "b": "yes"}
        result = profile._resolve_variables(text, variables)
        assert result == "AB"

    def test_nested_conditionals_outer_false(self, profile):
        """Nested conditionals - outer false excludes inner."""
        text = "{{#if a}}A{{#if b}}B{{/if}}{{/if}}"
        variables = {"b": "yes"}  # a undefined
        result = profile._resolve_variables(text, variables)
        assert result == ""

    def test_inheritance_pattern(self, profile):
        """Test typical inheritance pattern with extends/implements."""
        text = "public class {{entity_name}}{{#if entity_extends}} extends {{entity_extends}}{{/if}}{{#if entity_implements}} implements {{entity_implements}}{{/if}} {"

        # With both extends and implements
        variables = {
            "entity_name": "User",
            "entity_extends": "BaseEntity",
            "entity_implements": "Serializable"
        }
        result = profile._resolve_variables(text, variables)
        assert result == "public class User extends BaseEntity implements Serializable {"

        # With only extends
        variables = {"entity_name": "User", "entity_extends": "BaseEntity"}
        result = profile._resolve_variables(text, variables)
        assert result == "public class User extends BaseEntity {"

        # With neither
        variables = {"entity_name": "User"}
        result = profile._resolve_variables(text, variables)
        assert result == "public class User {"

    def test_undefined_var_becomes_empty(self, profile):
        """Undefined variables become empty strings."""
        text = "Value: [{{undefined}}]"
        variables = {}
        result = profile._resolve_variables(text, variables)
        assert result == "Value: []"

    def test_multiline_conditional(self, profile):
        """Conditional blocks can span multiple lines."""
        text = """Header
{{#if section}}
## Section
Content here
{{/if}}
Footer"""
        variables = {"section": "yes"}
        result = profile._resolve_variables(text, variables)
        assert "## Section" in result
        assert "Content here" in result

        variables = {}
        result = profile._resolve_variables(text, variables)
        assert "## Section" not in result
        assert "Content here" not in result


class TestProcessReviewResponse:
    """Test process_review_response method."""

    @pytest.fixture
    def profile(self):
        """Create a JpaMtProfile instance."""
        return JpaMtProfile()

    def test_pass_verdict_returns_success(self, profile):
        """PASS verdict returns SUCCESS status."""
        content = """
# Code Review

@@@REVIEW_META
verdict: PASS
issues_total: 0
issues_critical: 0
missing_inputs: 0
@@@
"""
        result = profile.process_review_response(content)
        assert result.status == WorkflowStatus.SUCCESS
        assert result.approved is True
        assert result.metadata["verdict"] == "PASS"
        assert "PASS | issues=0" in result.messages[0]

    def test_fail_verdict_returns_failed(self, profile):
        """FAIL verdict returns FAILED status."""
        content = """
# Code Review

@@@REVIEW_META
verdict: FAIL
issues_total: 3
issues_critical: 1
missing_inputs: 0
@@@
"""
        result = profile.process_review_response(content)
        assert result.status == WorkflowStatus.FAILED
        assert result.approved is False
        assert result.metadata["verdict"] == "FAIL"
        assert result.metadata["issues_total"] == 3
        assert result.metadata["issues_critical"] == 1
        assert "FAIL | issues=3" in result.messages[0]

    def test_empty_content_returns_error(self, profile):
        """Empty content returns ERROR status."""
        result = profile.process_review_response("")
        assert result.status == WorkflowStatus.ERROR
        assert "Empty review response" in result.error_message

    def test_missing_metadata_returns_error(self, profile):
        """Missing @@@REVIEW_META block returns ERROR status."""
        content = "Just a review without metadata."
        result = profile.process_review_response(content)
        assert result.status == WorkflowStatus.ERROR
        assert "@@@REVIEW_META" in result.error_message

    def test_invalid_verdict_returns_error(self, profile):
        """Invalid verdict returns ERROR status."""
        content = """
@@@REVIEW_META
verdict: MAYBE
issues_total: 0
issues_critical: 0
missing_inputs: 0
@@@
"""
        result = profile.process_review_response(content)
        assert result.status == WorkflowStatus.ERROR
        assert "Invalid verdict" in result.error_message

    def test_metadata_fields_in_result(self, profile):
        """All metadata fields are included in result."""
        content = """
@@@REVIEW_META
verdict: PASS
issues_total: 2
issues_critical: 0
missing_inputs: 1
@@@
"""
        result = profile.process_review_response(content)
        assert result.metadata["verdict"] == "PASS"
        assert result.metadata["issues_total"] == 2
        assert result.metadata["issues_critical"] == 0
        assert result.metadata["missing_inputs"] == 1
