"""Contract tests for JpaMtProfile.

These tests verify the behavioral contracts of JpaMtProfile - what it promises
to do, not how it does it. Contract tests should remain stable even when
implementation details change.

Contract Categories:
1. WorkflowProfile ABC contract - required interface methods
2. Prompt generation contracts - what prompts must contain
3. Response processing contracts - how responses map to workflow status
4. Convention system contracts - variable resolution behavior
"""

import pytest
from pathlib import Path
from unittest.mock import patch

from aiwf.domain.models.workflow_state import WorkflowStatus
from aiwf.domain.profiles.workflow_profile import WorkflowProfile
from profiles.jpa_mt.profile import JpaMtProfile
from profiles.jpa_mt.config import JpaMtConfig


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def profile():
    """Create a JpaMtProfile with default config."""
    return JpaMtProfile(config=JpaMtConfig())


@pytest.fixture
def minimal_context():
    """Minimal valid context for prompt generation."""
    return {
        "entity": "Customer",
        "table": "customers",
        "bounded_context": "crm",
        "scope": "domain",
    }


@pytest.fixture
def full_context(tmp_path):
    """Full context with all optional fields."""
    # Create a mock schema file
    schema_file = tmp_path / "schema.sql"
    schema_file.write_text("CREATE TABLE customers (id BIGINT PRIMARY KEY);")

    return {
        "entity": "Customer",
        "table": "customers",
        "bounded_context": "crm",
        "scope": "api",
        "schema_file": str(schema_file),
        "iteration": 2,
        "working_dir": str(tmp_path),
    }


# =============================================================================
# CONTRACT 1: WorkflowProfile ABC Implementation
# =============================================================================


class TestWorkflowProfileContract:
    """Verify JpaMtProfile implements WorkflowProfile ABC correctly."""

    def test_is_workflow_profile_subclass(self):
        """JpaMtProfile must be a WorkflowProfile subclass."""
        assert issubclass(JpaMtProfile, WorkflowProfile)

    def test_get_metadata_returns_required_keys(self, profile):
        """get_metadata must return all required metadata fields."""
        metadata = profile.get_metadata()

        required_keys = ["name", "description", "scopes", "phases"]
        for key in required_keys:
            assert key in metadata, f"Missing required metadata key: {key}"

    def test_get_metadata_scopes_are_valid(self, profile):
        """Metadata scopes must include standard scope values."""
        metadata = profile.get_metadata()
        scopes = metadata["scopes"]

        # Profile must support at least domain scope
        assert "domain" in scopes

    def test_has_prompt_generation_methods(self, profile):
        """Profile must have all prompt generation methods."""
        assert hasattr(profile, "generate_planning_prompt")
        assert hasattr(profile, "generate_generation_prompt")
        assert hasattr(profile, "generate_review_prompt")
        assert hasattr(profile, "generate_revision_prompt")

    def test_has_response_processing_methods(self, profile):
        """Profile must have all response processing methods."""
        assert hasattr(profile, "process_planning_response")
        assert hasattr(profile, "process_generation_response")
        assert hasattr(profile, "process_review_response")
        assert hasattr(profile, "process_revision_response")


# =============================================================================
# CONTRACT 2: Prompt Generation
# =============================================================================


class TestPromptGenerationContract:
    """Contract: Prompts must contain context information and be well-formed."""

    def test_planning_prompt_contains_entity(self, profile, minimal_context):
        """Planning prompt must contain the entity name."""
        prompt = profile.generate_planning_prompt(minimal_context)
        assert "Customer" in prompt

    def test_planning_prompt_contains_table(self, profile, minimal_context):
        """Planning prompt must contain the table name."""
        prompt = profile.generate_planning_prompt(minimal_context)
        assert "customers" in prompt

    def test_planning_prompt_contains_bounded_context(self, profile, minimal_context):
        """Planning prompt must contain the bounded context."""
        prompt = profile.generate_planning_prompt(minimal_context)
        assert "crm" in prompt

    def test_planning_prompt_returns_string(self, profile, minimal_context):
        """Planning prompt must return a non-empty string."""
        prompt = profile.generate_planning_prompt(minimal_context)
        assert isinstance(prompt, str)
        assert len(prompt) > 100  # Should be substantial

    def test_generation_prompt_contains_iteration(self, profile, full_context):
        """Generation prompt must contain the iteration number."""
        prompt = profile.generate_generation_prompt(full_context)
        # Iteration 2 should appear in the prompt
        assert "2" in prompt or "iteration" in prompt.lower()

    def test_review_prompt_returns_string(self, profile, minimal_context):
        """Review prompt must return a non-empty string."""
        prompt = profile.generate_review_prompt(minimal_context)
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_revision_prompt_returns_string(self, profile, minimal_context):
        """Revision prompt must return a non-empty string."""
        prompt = profile.generate_revision_prompt(minimal_context)
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_invalid_scope_raises_error(self, profile):
        """Unknown scope must raise ValueError."""
        context = {
            "entity": "Customer",
            "table": "customers",
            "bounded_context": "crm",
            "scope": "invalid_scope",
        }
        with pytest.raises(ValueError, match="Unknown scope"):
            profile.generate_planning_prompt(context)

    def test_all_scopes_produce_valid_prompts(self, profile):
        """All declared scopes must produce valid prompts."""
        metadata = profile.get_metadata()
        for scope in metadata["scopes"]:
            context = {
                "entity": "TestEntity",
                "table": "test_entities",
                "bounded_context": "test",
                "scope": scope,
            }
            prompt = profile.generate_planning_prompt(context)
            assert isinstance(prompt, str)
            assert len(prompt) > 0

    def test_prompts_reference_standards(self, profile, minimal_context):
        """Prompts should reference standards for code generation guidance."""
        gen_prompt = profile.generate_generation_prompt(minimal_context)
        review_prompt = profile.generate_review_prompt(minimal_context)

        # At least one prompt should reference standards
        has_standards_ref = "standard" in gen_prompt.lower() or "standard" in review_prompt.lower()
        assert has_standards_ref, "Prompts should reference coding standards"


# =============================================================================
# CONTRACT 3: Response Processing
# =============================================================================


class TestResponseProcessingContract:
    """Contract: Response processing maps content to workflow status correctly."""

    # --- Planning Response ---

    def test_planning_empty_response_returns_error(self, profile):
        """Empty planning response must return ERROR status."""
        result = profile.process_planning_response("")
        assert result.status == WorkflowStatus.ERROR

    def test_planning_whitespace_only_returns_error(self, profile):
        """Whitespace-only planning response must return ERROR status."""
        result = profile.process_planning_response("   \n\t  ")
        assert result.status == WorkflowStatus.ERROR

    def test_planning_valid_response_returns_progress(self, profile):
        """Valid planning response must return IN_PROGRESS status."""
        content = """# Implementation Plan: Customer

## Schema Analysis
- Table: customers
- Columns: id, name, email
"""
        result = profile.process_planning_response(content)
        assert result.status == WorkflowStatus.IN_PROGRESS

    # --- Generation Response ---

    def test_generation_empty_response_returns_error(self, profile, tmp_path):
        """Empty generation response must return ERROR status."""
        result = profile.process_generation_response("", tmp_path, 1)
        assert result.status == WorkflowStatus.ERROR

    def test_generation_valid_response_returns_progress(self, profile, tmp_path):
        """Valid generation response must return IN_PROGRESS status."""
        content = """```java
// Customer.java
package com.example;

@Entity
public class Customer {
    @Id
    private Long id;
}
```"""
        result = profile.process_generation_response(content, tmp_path, 1)
        assert result.status == WorkflowStatus.IN_PROGRESS

    # --- Review Response ---

    def test_review_empty_response_returns_error(self, profile):
        """Empty review response must return ERROR status."""
        result = profile.process_review_response("")
        assert result.status == WorkflowStatus.ERROR

    def test_review_missing_metadata_returns_error(self, profile):
        """Review without @@@REVIEW_META block must return ERROR status."""
        content = "This is a review without the required metadata block."
        result = profile.process_review_response(content)
        assert result.status == WorkflowStatus.ERROR

    def test_review_pass_verdict_returns_success(self, profile):
        """PASS verdict must return SUCCESS status with approved=True."""
        content = """# Code Review

The code looks good.

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

    def test_review_fail_verdict_returns_failed(self, profile):
        """FAIL verdict must return FAILED status with approved=False."""
        content = """# Code Review

Found issues that need fixing.

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

    def test_review_includes_metadata_in_result(self, profile):
        """Review result must include parsed metadata."""
        content = """
@@@REVIEW_META
verdict: FAIL
issues_total: 5
issues_critical: 2
missing_inputs: 1
@@@
"""
        result = profile.process_review_response(content)
        assert result.metadata["verdict"] == "FAIL"
        assert result.metadata["issues_total"] == 5
        assert result.metadata["issues_critical"] == 2
        assert result.metadata["missing_inputs"] == 1

    def test_review_invalid_verdict_returns_error(self, profile):
        """Invalid verdict value must return ERROR status."""
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

    # --- Revision Response ---

    def test_revision_empty_response_returns_error(self, profile, tmp_path):
        """Empty revision response must return ERROR status."""
        result = profile.process_revision_response("", tmp_path, 1)
        assert result.status == WorkflowStatus.ERROR

    def test_revision_valid_response_returns_progress(self, profile, tmp_path):
        """Valid revision response must return IN_PROGRESS status."""
        content = """```java
// Customer.java - Fixed per JPA-ENT-001
package com.example;

@Entity
@Table(schema = "app", name = "customers")
public class Customer {
    @Id
    private Long id;
}
```"""
        result = profile.process_revision_response(content, tmp_path, 2)
        assert result.status == WorkflowStatus.IN_PROGRESS


# =============================================================================
# CONTRACT 4: Convention Variable Resolution
# =============================================================================


class TestConventionContract:
    """Contract: Convention variables are resolved correctly in prompts."""

    def test_undefined_variables_do_not_leave_placeholders(self, profile):
        """Undefined variables should not leave {{placeholder}} in output."""
        context = {
            "entity": "Customer",
            "table": "customers",
            "bounded_context": "crm",
            "scope": "domain",
        }
        prompt = profile.generate_planning_prompt(context)

        # Should not have unresolved {{var}} patterns (except engine-managed ones)
        # Engine-managed: {{STANDARDS}} is resolved by PromptAssembler, not profile
        import re
        unresolved = re.findall(r"\{\{(?!STANDARDS)\w+\}\}", prompt)
        assert len(unresolved) == 0, f"Found unresolved placeholders: {unresolved}"

    def test_context_values_appear_in_prompt(self, profile):
        """Context values (entity, table, etc.) must appear in the prompt."""
        context = {
            "entity": "UniqueEntityName",
            "table": "unique_table_name",
            "bounded_context": "unique_context",
            "scope": "domain",
        }
        prompt = profile.generate_planning_prompt(context)

        assert "UniqueEntityName" in prompt
        assert "unique_table_name" in prompt
        assert "unique_context" in prompt

    def test_scope_affects_artifacts_mentioned(self, profile):
        """Different scopes should produce prompts mentioning different artifacts."""
        domain_context = {
            "entity": "Customer",
            "table": "customers",
            "bounded_context": "crm",
            "scope": "domain",
        }
        api_context = {
            "entity": "Customer",
            "table": "customers",
            "bounded_context": "crm",
            "scope": "api",
        }

        domain_prompt = profile.generate_planning_prompt(domain_context)
        api_prompt = profile.generate_planning_prompt(api_context)

        # API scope should mention controller-related concepts
        assert "controller" in api_prompt.lower() or "endpoint" in api_prompt.lower()

        # Both should mention entity
        assert "entity" in domain_prompt.lower()
        assert "entity" in api_prompt.lower()


# =============================================================================
# CONTRACT 5: Error Handling
# =============================================================================


class TestErrorHandlingContract:
    """Contract: Errors are handled gracefully with meaningful messages."""

    def test_error_result_has_error_message(self, profile):
        """ERROR status results must include an error_message."""
        result = profile.process_review_response("")
        assert result.status == WorkflowStatus.ERROR
        assert result.error_message is not None
        assert len(result.error_message) > 0

    def test_invalid_scope_error_is_descriptive(self, profile):
        """Invalid scope error should mention the invalid value."""
        context = {
            "entity": "Customer",
            "table": "customers",
            "bounded_context": "crm",
            "scope": "nonexistent_scope",
        }
        with pytest.raises(ValueError) as exc_info:
            profile.generate_planning_prompt(context)

        error_msg = str(exc_info.value).lower()
        assert "scope" in error_msg or "nonexistent" in error_msg


# =============================================================================
# CONTRACT 6: Idempotency
# =============================================================================


class TestIdempotencyContract:
    """Contract: Operations should be idempotent where applicable."""

    def test_prompt_generation_is_deterministic(self, profile, minimal_context):
        """Same context should produce same prompt."""
        prompt1 = profile.generate_planning_prompt(minimal_context)
        prompt2 = profile.generate_planning_prompt(minimal_context)
        assert prompt1 == prompt2

    def test_response_processing_is_deterministic(self, profile):
        """Same content should produce same result."""
        content = """
@@@REVIEW_META
verdict: PASS
issues_total: 0
issues_critical: 0
missing_inputs: 0
@@@
"""
        result1 = profile.process_review_response(content)
        result2 = profile.process_review_response(content)

        assert result1.status == result2.status
        assert result1.approved == result2.approved
        assert result1.metadata == result2.metadata
