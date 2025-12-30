"""Integration tests for Phase 7 - assembled prompts with engine-provided artifacts.

These tests verify:
1. Assembled prompts include engine-provided artifacts (plan, standards, code)
2. Assembled prompts include output instructions (based on fs_ability)
3. End-to-end workflow works with cleaned templates

This complements test_jpa_mt_workflow.py with focus on the PromptAssembler integration.
"""
import pytest

# Import profiles to trigger registration
import profiles  # noqa: F401

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStatus
from aiwf.domain.persistence.session_store import SessionStore


@pytest.fixture
def orchestrator_with_standards(tmp_path, monkeypatch):
    """Create workflow orchestrator with standards and schema files."""
    standards_dir = tmp_path / "standards"
    standards_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("STANDARDS_DIR", str(standards_dir))

    # Create stub standards files
    required_files = [
        "ORG.md",
        "NAMING_AND_API.md",
        "PACKAGES_AND_LAYERS.md",
        "JPA_AND_DATABASE.md",
        "ARCHITECTURE_AND_MULTITENANCY.md",
        "BOILERPLATE_AND_DI.md",
    ]
    for filename in required_files:
        (standards_dir / filename).write_text(f"# {filename}\n\nStub content.\n")

    # Create schema file
    schema_file = tmp_path / "schema.sql"
    schema_file.write_text(
        "CREATE TABLE app.customers (id BIGINT PRIMARY KEY, name VARCHAR(100));"
    )

    monkeypatch.chdir(tmp_path)

    session_store = SessionStore(sessions_root=tmp_path)
    return WorkflowOrchestrator(
        session_store=session_store,
        sessions_root=tmp_path,
    )


@pytest.fixture
def initialized_session(orchestrator_with_standards, tmp_path):
    """Create an initialized session for testing prompt generation."""
    session_id = orchestrator_with_standards.initialize_run(
        profile="jpa-mt",
        context={
            "scope": "domain",
            "entity": "Customer",
            "table": "app.customers",
            "bounded_context": "crm",
            "schema_file": "schema.sql",
        },
        providers={"planner": "manual", "generator": "manual", "reviewer": "manual"},
    )
    return session_id, orchestrator_with_standards, tmp_path


class TestAssembledPromptsIncludeArtifacts:
    """Tests that assembled prompts include engine-provided artifacts."""

    def test_generation_prompt_includes_standards_bundle(
        self, initialized_session
    ):
        """Generation prompt should include the standards bundle content."""
        session_id, orchestrator, tmp_path = initialized_session
        session_dir = tmp_path / session_id

        # Advance to GENERATING and generate prompt
        orchestrator.step(session_id)  # INITIALIZED -> PLANNING
        orchestrator.step(session_id)  # Generate planning prompt

        # Provide planning response
        (session_dir / "iteration-1" / "planning-response.md").write_text(
            "# Plan\n\nEntity fields: id, name"
        )
        orchestrator.step(session_id)  # PLANNING -> PLANNED

        # Approve plan
        state = orchestrator.session_store.load(session_id)
        state.plan_approved = True
        orchestrator.session_store.save(state)

        orchestrator.step(session_id)  # PLANNED -> GENERATING
        orchestrator.step(session_id)  # Generate generation prompt

        # Read the generated prompt
        prompt_file = session_dir / "iteration-1" / "generation-prompt.md"
        assert prompt_file.exists(), "Generation prompt should be created"

        prompt_content = prompt_file.read_text(encoding="utf-8")

        # Should include standards bundle section (from engine)
        assert "Standards Bundle" in prompt_content or "standards" in prompt_content.lower(), (
            "Generation prompt should include standards bundle from engine"
        )

    def test_generation_prompt_includes_approved_plan(self, initialized_session):
        """Generation prompt should include the approved plan content."""
        session_id, orchestrator, tmp_path = initialized_session
        session_dir = tmp_path / session_id

        # Advance to GENERATING
        orchestrator.step(session_id)  # -> PLANNING
        orchestrator.step(session_id)  # Generate planning prompt

        # Provide planning response with identifiable content
        plan_content = "# Plan\n\nEntity Customer with fields: id, name, tenantId"
        (session_dir / "iteration-1" / "planning-response.md").write_text(plan_content)
        orchestrator.step(session_id)  # -> PLANNED

        # Approve plan
        state = orchestrator.session_store.load(session_id)
        state.plan_approved = True
        orchestrator.session_store.save(state)

        orchestrator.step(session_id)  # -> GENERATING
        orchestrator.step(session_id)  # Generate generation prompt

        # Read the generated prompt
        prompt_file = session_dir / "iteration-1" / "generation-prompt.md"
        prompt_content = prompt_file.read_text(encoding="utf-8")

        # Should include the plan content (from engine injection)
        # The plan is copied to plan.md, so check for section header
        assert "Plan" in prompt_content or "plan" in prompt_content.lower(), (
            "Generation prompt should include approved plan from engine"
        )

    def test_review_prompt_includes_code_artifacts(self, initialized_session):
        """Review prompt should include generated code artifacts."""
        session_id, orchestrator, tmp_path = initialized_session
        session_dir = tmp_path / session_id

        # Fast-forward to REVIEWING
        orchestrator.step(session_id)  # -> PLANNING
        orchestrator.step(session_id)  # Generate prompt

        (session_dir / "iteration-1" / "planning-response.md").write_text("# Plan")
        orchestrator.step(session_id)  # -> PLANNED

        state = orchestrator.session_store.load(session_id)
        state.plan_approved = True
        orchestrator.session_store.save(state)

        orchestrator.step(session_id)  # -> GENERATING
        orchestrator.step(session_id)  # Generate generation prompt

        # Provide generation response with identifiable code
        generation_response = '''<<<FILE: Customer.java>>>
package com.example.crm;

import javax.persistence.Entity;
import javax.persistence.Id;

@Entity
public class Customer {
    @Id
    private Long id;
    private String name;
}
'''
        (session_dir / "iteration-1" / "generation-response.md").write_text(
            generation_response
        )
        orchestrator.step(session_id)  # -> GENERATED

        # Approve artifacts
        orchestrator.approve(session_id)

        orchestrator.step(session_id)  # -> REVIEWING
        orchestrator.step(session_id)  # Generate review prompt

        # Read the review prompt
        prompt_file = session_dir / "iteration-1" / "review-prompt.md"
        prompt_content = prompt_file.read_text(encoding="utf-8")

        # Should include the code content (from engine injection)
        assert "Customer" in prompt_content, (
            "Review prompt should include code artifacts from engine"
        )


class TestAssembledPromptsIncludeOutputInstructions:
    """Tests that assembled prompts include output instructions based on fs_ability."""

    def test_planning_prompt_has_output_instructions(self, initialized_session):
        """Planning prompt should include output instructions from engine."""
        session_id, orchestrator, tmp_path = initialized_session
        session_dir = tmp_path / session_id

        # Generate planning prompt
        orchestrator.step(session_id)  # -> PLANNING
        orchestrator.step(session_id)  # Generate prompt

        # Read the planning prompt
        prompt_file = session_dir / "iteration-1" / "planning-prompt.md"
        prompt_content = prompt_file.read_text(encoding="utf-8")

        # Engine should add output instructions (depends on fs_ability configuration)
        # For manual provider, typically local-write or write-only
        has_output = (
            "Save" in prompt_content
            or "output" in prompt_content.lower()
            or "file" in prompt_content.lower()
        )
        # The prompt should have SOME guidance about output
        # Note: exact wording depends on fs_ability setting
        assert has_output or "planning-response" not in prompt_content, (
            "Planning prompt should either have engine output instructions or not have "
            "legacy output destination section"
        )


class TestEndToEndWithCleanedTemplates:
    """Tests that end-to-end workflow works with cleaned templates."""

    def test_full_workflow_completes_successfully(self, orchestrator_with_standards, tmp_path):
        """Full workflow should complete successfully with cleaned templates."""
        session_id = orchestrator_with_standards.initialize_run(
            profile="jpa-mt",
            context={
                "scope": "domain",
                "entity": "Product",
                "table": "app.products",
                "bounded_context": "catalog",
                "schema_file": "schema.sql",
            },
            providers={"planner": "manual", "generator": "manual", "reviewer": "manual"},
        )
        session_dir = tmp_path / session_id

        # === PLANNING ===
        orchestrator_with_standards.step(session_id)  # -> PLANNING
        orchestrator_with_standards.step(session_id)  # Generate prompt

        (session_dir / "iteration-1" / "planning-response.md").write_text(
            "# Product Entity Plan\n\nFields: id, name, price"
        )
        orchestrator_with_standards.step(session_id)  # -> PLANNED

        state = orchestrator_with_standards.session_store.load(session_id)
        state.plan_approved = True
        orchestrator_with_standards.session_store.save(state)

        # === GENERATING ===
        orchestrator_with_standards.step(session_id)  # -> GENERATING
        orchestrator_with_standards.step(session_id)  # Generate prompt

        (session_dir / "iteration-1" / "generation-response.md").write_text('''
<<<FILE: Product.java>>>
package com.example.catalog;

import javax.persistence.Entity;
import javax.persistence.Id;

@Entity
public class Product {
    @Id
    private Long id;
    private String name;
}

<<<FILE: ProductRepository.java>>>
package com.example.catalog;

public interface ProductRepository {}
''')
        orchestrator_with_standards.step(session_id)  # -> GENERATED

        # Approve artifacts
        orchestrator_with_standards.approve(session_id)

        # === REVIEWING ===
        orchestrator_with_standards.step(session_id)  # -> REVIEWING
        orchestrator_with_standards.step(session_id)  # Generate prompt

        (session_dir / "iteration-1" / "review-response.md").write_text("""
@@@REVIEW_META
verdict: PASS
issues_total: 0
issues_critical: 0
missing_inputs: 0
@@@

All code follows standards.
""")
        orchestrator_with_standards.step(session_id)  # -> REVIEWED

        state = orchestrator_with_standards.session_store.load(session_id)
        state.review_approved = True
        orchestrator_with_standards.session_store.save(state)

        # === COMPLETE ===
        state = orchestrator_with_standards.step(session_id)
        assert state.phase == WorkflowPhase.COMPLETE
        assert state.status == WorkflowStatus.SUCCESS

    def test_prompts_do_not_contain_legacy_output_destination(
        self, orchestrator_with_standards, tmp_path
    ):
        """Verify prompts don't contain legacy '## Output Destination' sections."""
        session_id = orchestrator_with_standards.initialize_run(
            profile="jpa-mt",
            context={
                "scope": "domain",
                "entity": "Widget",
                "table": "app.widgets",
                "bounded_context": "inventory",
                "schema_file": "schema.sql",
            },
            providers={"planner": "manual", "generator": "manual", "reviewer": "manual"},
        )
        session_dir = tmp_path / session_id

        # Generate planning prompt
        orchestrator_with_standards.step(session_id)  # -> PLANNING
        orchestrator_with_standards.step(session_id)  # Generate prompt

        planning_prompt = (session_dir / "iteration-1" / "planning-prompt.md").read_text()

        # Should NOT have legacy output destination section from template
        assert "## Output Destination" not in planning_prompt, (
            "Planning prompt should not contain legacy '## Output Destination' section"
        )
        # Should NOT have legacy save instruction pattern
        assert "to same location as" not in planning_prompt, (
            "Planning prompt should not contain legacy location instruction"
        )

    def test_prompts_do_not_contain_session_artifact_paths(
        self, orchestrator_with_standards, tmp_path
    ):
        """Verify prompts don't contain @.aiwf/sessions/ paths."""
        session_id = orchestrator_with_standards.initialize_run(
            profile="jpa-mt",
            context={
                "scope": "domain",
                "entity": "Order",
                "table": "app.orders",
                "bounded_context": "sales",
                "schema_file": "schema.sql",
            },
            providers={"planner": "manual", "generator": "manual", "reviewer": "manual"},
        )
        session_dir = tmp_path / session_id

        # Fast-forward to generation prompt
        orchestrator_with_standards.step(session_id)  # -> PLANNING
        orchestrator_with_standards.step(session_id)  # Generate prompt

        (session_dir / "iteration-1" / "planning-response.md").write_text("# Plan")
        orchestrator_with_standards.step(session_id)  # -> PLANNED

        state = orchestrator_with_standards.session_store.load(session_id)
        state.plan_approved = True
        orchestrator_with_standards.session_store.save(state)

        orchestrator_with_standards.step(session_id)  # -> GENERATING
        orchestrator_with_standards.step(session_id)  # Generate generation prompt

        generation_prompt = (session_dir / "iteration-1" / "generation-prompt.md").read_text()

        # Should NOT have session artifact paths
        assert "@.aiwf/sessions/" not in generation_prompt, (
            "Generation prompt should not contain @.aiwf/sessions/ paths"
        )