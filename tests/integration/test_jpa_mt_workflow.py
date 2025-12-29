"""Integration tests for JPA-MT profile with workflow orchestrator."""
import pytest

# Import profiles to trigger registration
import profiles  # noqa: F401

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStatus
from aiwf.domain.persistence.session_store import SessionStore


@pytest.fixture
def orchestrator(tmp_path, monkeypatch):
    """Create workflow orchestrator with temp directory."""
    standards_dir = tmp_path / "standards"
    standards_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("STANDARDS_DIR", str(standards_dir))

    # Create required stub standards files
    required_files = [
        "ORG.md",
        "NAMING_AND_API.md",
        "PACKAGES_AND_LAYERS.md",
        "JPA_AND_DATABASE.md",
        "ARCHITECTURE_AND_MULTITENANCY.md",
        "BOILERPLATE_AND_DI.md",
    ]
    for filename in required_files:
        (standards_dir / filename).write_text(f"# {filename}\n\nStub content for testing.\n")

    # Create schema file for jpa-mt profile
    schema_file = tmp_path / "schema.sql"
    schema_file.write_text("CREATE TABLE app.products (id BIGINT PRIMARY KEY);", encoding="utf-8")

    # Change cwd to tmp_path so schema file can be found
    monkeypatch.chdir(tmp_path)

    session_store = SessionStore(sessions_root=tmp_path)
    return WorkflowOrchestrator(
        session_store=session_store,
        sessions_root=tmp_path,
    )


class TestJpaMtWorkflowIntegration:
    """Integration tests for jpa-mt profile with workflow orchestrator."""

    def test_initialize_run_creates_session(self, orchestrator):
        """initialize_run should create a valid session."""
        session_id = orchestrator.initialize_run(
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

        assert session_id is not None
        assert len(session_id) > 0

        # Load state and verify
        state = orchestrator.session_store.load(session_id)
        assert state.phase == WorkflowPhase.INITIALIZED
        assert state.status == WorkflowStatus.IN_PROGRESS
        assert state.profile == "jpa-mt"
        assert state.context["scope"] == "domain"
        assert state.context["entity"] == "Product"

    def test_step_to_planning_generates_prompt(self, orchestrator, tmp_path):
        """Stepping from INITIALIZED should generate planning prompt."""
        session_id = orchestrator.initialize_run(
            profile="jpa-mt",
            context={
                "scope": "domain",
                "entity": "Product",
                "table": "app.products",
                "bounded_context": "catalog",
                "schema_file": "schema.sql",
            },
            providers={"planner": "manual"},
        )

        # Step to PLANNING
        state = orchestrator.step(session_id)
        assert state.phase == WorkflowPhase.PLANNING

        # Step again to generate prompt
        state = orchestrator.step(session_id)
        assert state.phase == WorkflowPhase.PLANNING  # Still waiting for response

        # Verify prompt was generated
        prompt_file = tmp_path / session_id / "iteration-1" / "planning-prompt.md"
        assert prompt_file.exists()
        content = prompt_file.read_text(encoding="utf-8")
        assert "Product" in content

    def test_planning_to_planned_on_response(self, orchestrator, tmp_path):
        """Providing planning response should transition to PLANNED."""
        session_id = orchestrator.initialize_run(
            profile="jpa-mt",
            context={
                "scope": "domain",
                "entity": "Product",
                "table": "app.products",
                "bounded_context": "catalog",
                "schema_file": "schema.sql",
            },
            providers={"planner": "manual"},
        )

        # Step to PLANNING and generate prompt
        orchestrator.step(session_id)
        orchestrator.step(session_id)

        # Write planning response
        response_file = tmp_path / session_id / "iteration-1" / "planning-response.md"
        response_file.write_text("""
# Entity Plan for Product

## Fields
- id: Long (primary key)
- name: String
- tenantId: Long

## Summary
Standard JPA entity.
""")

        # Step to PLANNED
        state = orchestrator.step(session_id)
        assert state.phase == WorkflowPhase.PLANNED

    def test_full_workflow_to_complete(self, orchestrator, tmp_path):
        """Full workflow from init to COMPLETE with passing review."""
        session_id = orchestrator.initialize_run(
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

        # INITIALIZED -> PLANNING
        state = orchestrator.step(session_id)
        assert state.phase == WorkflowPhase.PLANNING

        # Generate planning prompt
        orchestrator.step(session_id)

        # Write planning response
        (session_dir / "iteration-1" / "planning-response.md").write_text("""
# Entity Plan for Product

## Fields
- id: Long
- name: String
""")

        # PLANNING -> PLANNED
        state = orchestrator.step(session_id)
        assert state.phase == WorkflowPhase.PLANNED

        # Approve plan to advance
        state = orchestrator.session_store.load(session_id)
        state.plan_approved = True
        orchestrator.session_store.save(state)

        # PLANNED -> GENERATING
        state = orchestrator.step(session_id)
        assert state.phase == WorkflowPhase.GENERATING

        # Generate generation prompt (step once more)
        orchestrator.step(session_id)

        # Write generation response
        (session_dir / "iteration-1" / "generation-response.md").write_text('''
Here is the code:

<<<FILE: Product.java>>>
package com.example.domain;

import javax.persistence.Entity;
import javax.persistence.Id;

@Entity
public class Product {
    @Id
    private Long id;
    private String name;
}

<<<FILE: ProductRepository.java>>>
package com.example.domain;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository extends JpaRepository<Product, Long> {
}
''')

        # GENERATING -> GENERATED (process response, write artifacts)
        state = orchestrator.step(session_id)
        assert state.phase == WorkflowPhase.GENERATED

        # Verify code files were written
        code_dir = session_dir / "iteration-1" / "code"
        assert (code_dir / "Product.java").exists()
        assert (code_dir / "ProductRepository.java").exists()

        # Approve code artifacts to advance
        state = orchestrator.approve(session_id)

        # GENERATED -> REVIEWING
        state = orchestrator.step(session_id)
        assert state.phase == WorkflowPhase.REVIEWING

        # Generate review prompt
        orchestrator.step(session_id)

        # Write passing review response
        (session_dir / "iteration-1" / "review-response.md").write_text("""
@@@REVIEW_META
verdict: PASS
issues_total: 0
issues_critical: 0
missing_inputs: 0
@@@

Code looks good. All standards followed.
""")

        # REVIEWING -> REVIEWED
        state = orchestrator.step(session_id)
        assert state.phase == WorkflowPhase.REVIEWED

        # Approve review to advance
        state = orchestrator.session_store.load(session_id)
        state.review_approved = True
        orchestrator.session_store.save(state)

        # REVIEWED -> COMPLETE (on PASS verdict)
        state = orchestrator.step(session_id)
        assert state.phase == WorkflowPhase.COMPLETE
        assert state.status == WorkflowStatus.SUCCESS

    def test_review_fail_triggers_revision(self, orchestrator, tmp_path):
        """Review with FAIL verdict should trigger REVISING phase."""
        session_id = orchestrator.initialize_run(
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

        # Fast-forward to REVIEWED with failing review
        # INITIALIZED -> PLANNING
        orchestrator.step(session_id)
        orchestrator.step(session_id)  # Generate prompt

        # Write planning response
        (session_dir / "iteration-1").mkdir(parents=True, exist_ok=True)
        (session_dir / "iteration-1" / "planning-response.md").write_text("# Plan\n...")

        orchestrator.step(session_id)  # -> PLANNED

        # Approve plan
        state = orchestrator.session_store.load(session_id)
        state.plan_approved = True
        orchestrator.session_store.save(state)

        orchestrator.step(session_id)  # -> GENERATING
        orchestrator.step(session_id)  # Generate prompt

        # Write generation response
        (session_dir / "iteration-1" / "generation-response.md").write_text('''
<<<FILE: Product.java>>>
package com.example;

@Entity
public class Product { @Id Long id; }
''')

        orchestrator.step(session_id)  # -> GENERATED

        # Approve code
        orchestrator.approve(session_id)

        orchestrator.step(session_id)  # -> REVIEWING
        orchestrator.step(session_id)  # Generate prompt

        # Write FAILING review response
        (session_dir / "iteration-1" / "review-response.md").write_text("""
@@@REVIEW_META
verdict: FAIL
issues_total: 1
issues_critical: 1
missing_inputs: 0
@@@

Critical: Missing @TenantId annotation.
""")

        orchestrator.step(session_id)  # -> REVIEWED

        # Approve review
        state = orchestrator.session_store.load(session_id)
        state.review_approved = True
        orchestrator.session_store.save(state)

        # REVIEWED -> REVISING (on FAIL verdict)
        state = orchestrator.step(session_id)
        assert state.phase == WorkflowPhase.REVISING
        assert state.current_iteration == 2

        # Verify new iteration directory was created
        assert (session_dir / "iteration-2").exists()

    def test_full_revision_cycle_to_complete(self, orchestrator, tmp_path):
        """Full workflow with FAIL review, revision, and eventual PASS to COMPLETE."""
        session_id = orchestrator.initialize_run(
            profile="jpa-mt",
            context={
                "scope": "domain",
                "entity": "Product",
                "table": "app.products",
                "bounded_context": "catalog",
                "schema_file": "schema.sql",
            },
            providers={
                "planner": "manual",
                "generator": "manual",
                "reviewer": "manual",
                "reviser": "manual",
            },
        )
        session_dir = tmp_path / session_id

        # === ITERATION 1: Initial generation with failing review ===

        # INITIALIZED -> PLANNING
        orchestrator.step(session_id)
        orchestrator.step(session_id)  # Generate prompt

        # Write planning response
        (session_dir / "iteration-1").mkdir(parents=True, exist_ok=True)
        (session_dir / "iteration-1" / "planning-response.md").write_text(
            "# Plan\n\nCreate Product entity with id and name fields."
        )

        orchestrator.step(session_id)  # -> PLANNED

        # Approve plan
        state = orchestrator.session_store.load(session_id)
        state.plan_approved = True
        orchestrator.session_store.save(state)

        orchestrator.step(session_id)  # -> GENERATING
        orchestrator.step(session_id)  # Generate prompt

        # Write generation response (missing @TenantId - will fail review)
        (session_dir / "iteration-1" / "generation-response.md").write_text('''
<<<FILE: Product.java>>>
package com.example;

import javax.persistence.Entity;
import javax.persistence.Id;

@Entity
public class Product {
    @Id
    private Long id;
    private String name;
}
''')

        orchestrator.step(session_id)  # -> GENERATED
        orchestrator.approve(session_id)  # Hash artifacts

        orchestrator.step(session_id)  # -> REVIEWING
        orchestrator.step(session_id)  # Generate review prompt

        # Write FAILING review response
        (session_dir / "iteration-1" / "review-response.md").write_text("""
@@@REVIEW_META
verdict: FAIL
issues_total: 1
issues_critical: 1
missing_inputs: 0
@@@

Critical: Missing @TenantId annotation required for multi-tenant support.
""")

        orchestrator.step(session_id)  # -> REVIEWED

        # Approve review to proceed to revision
        state = orchestrator.session_store.load(session_id)
        state.review_approved = True
        orchestrator.session_store.save(state)

        state = orchestrator.step(session_id)  # -> REVISING (iteration 2)
        assert state.phase == WorkflowPhase.REVISING
        assert state.current_iteration == 2

        # === ITERATION 2: Revision with passing review ===

        # Verify revision prompt was generated
        orchestrator.step(session_id)  # Generate revision prompt
        revision_prompt = session_dir / "iteration-2" / "revision-prompt.md"
        assert revision_prompt.exists()

        # Write revision response (fixed code with @TenantId)
        (session_dir / "iteration-2" / "revision-response.md").write_text('''
<<<FILE: Product.java>>>
package com.example;

import javax.persistence.Entity;
import javax.persistence.Id;
import com.example.multitenancy.TenantId;

@Entity
public class Product {
    @Id
    private Long id;

    @TenantId
    private Long tenantId;

    private String name;
}
''')

        state = orchestrator.step(session_id)  # -> REVISED
        assert state.phase == WorkflowPhase.REVISED

        # Verify revised code was written
        revised_code = session_dir / "iteration-2" / "code" / "Product.java"
        assert revised_code.exists()
        assert "@TenantId" in revised_code.read_text(encoding="utf-8")

        # Approve revised artifacts
        orchestrator.approve(session_id)

        state = orchestrator.step(session_id)  # -> REVIEWING
        assert state.phase == WorkflowPhase.REVIEWING

        orchestrator.step(session_id)  # Generate review prompt

        # Write PASSING review response
        (session_dir / "iteration-2" / "review-response.md").write_text("""
@@@REVIEW_META
verdict: PASS
issues_total: 0
issues_critical: 0
missing_inputs: 0
@@@

All issues resolved. Code now includes @TenantId annotation.
""")

        state = orchestrator.step(session_id)  # -> REVIEWED
        assert state.phase == WorkflowPhase.REVIEWED

        # Approve review
        state = orchestrator.session_store.load(session_id)
        state.review_approved = True
        orchestrator.session_store.save(state)

        # Final step -> COMPLETE
        state = orchestrator.step(session_id)
        assert state.phase == WorkflowPhase.COMPLETE
        assert state.status == WorkflowStatus.SUCCESS
        assert state.current_iteration == 2

    def test_multiple_revision_iterations(self, orchestrator, tmp_path):
        """Test that multiple failed reviews correctly increment iterations."""
        session_id = orchestrator.initialize_run(
            profile="jpa-mt",
            context={
                "scope": "domain",
                "entity": "Widget",
                "table": "app.widgets",
                "bounded_context": "catalog",
                "schema_file": "schema.sql",
            },
            providers={
                "planner": "manual",
                "generator": "manual",
                "reviewer": "manual",
                "reviser": "manual",
            },
        )
        session_dir = tmp_path / session_id

        # Fast-forward to GENERATED in iteration 1
        orchestrator.step(session_id)  # -> PLANNING
        orchestrator.step(session_id)  # Generate prompt
        (session_dir / "iteration-1").mkdir(parents=True, exist_ok=True)
        (session_dir / "iteration-1" / "planning-response.md").write_text("# Plan")
        orchestrator.step(session_id)  # -> PLANNED

        state = orchestrator.session_store.load(session_id)
        state.plan_approved = True
        orchestrator.session_store.save(state)

        orchestrator.step(session_id)  # -> GENERATING
        orchestrator.step(session_id)  # Generate prompt
        (session_dir / "iteration-1" / "generation-response.md").write_text(
            "<<<FILE: Widget.java>>>\nclass Widget {}"
        )
        orchestrator.step(session_id)  # -> GENERATED
        orchestrator.approve(session_id)

        # Helper to run a failing review cycle
        def fail_review(iteration: int):
            orchestrator.step(session_id)  # -> REVIEWING
            orchestrator.step(session_id)  # Generate prompt
            (session_dir / f"iteration-{iteration}" / "review-response.md").write_text(f"""
@@@REVIEW_META
verdict: FAIL
issues_total: 1
issues_critical: 1
missing_inputs: 0
@@@

Issue in iteration {iteration}.
""")
            orchestrator.step(session_id)  # -> REVIEWED
            state = orchestrator.session_store.load(session_id)
            state.review_approved = True
            orchestrator.session_store.save(state)
            return orchestrator.step(session_id)  # -> REVISING

        def write_revision(iteration: int):
            orchestrator.step(session_id)  # Generate revision prompt
            (session_dir / f"iteration-{iteration}" / "revision-response.md").write_text(
                f"<<<FILE: Widget.java>>>\nclass Widget {{ /* v{iteration} */ }}"
            )
            orchestrator.step(session_id)  # -> REVISED
            orchestrator.approve(session_id)

        # Iteration 1 -> 2 (first fail)
        state = fail_review(1)
        assert state.phase == WorkflowPhase.REVISING
        assert state.current_iteration == 2
        write_revision(2)

        # Iteration 2 -> 3 (second fail)
        state = fail_review(2)
        assert state.phase == WorkflowPhase.REVISING
        assert state.current_iteration == 3
        write_revision(3)

        # Iteration 3 -> PASS
        orchestrator.step(session_id)  # -> REVIEWING
        orchestrator.step(session_id)  # Generate prompt
        (session_dir / "iteration-3" / "review-response.md").write_text("""
@@@REVIEW_META
verdict: PASS
issues_total: 0
issues_critical: 0
missing_inputs: 0
@@@

Finally passing!
""")
        orchestrator.step(session_id)  # -> REVIEWED
        state = orchestrator.session_store.load(session_id)
        state.review_approved = True
        orchestrator.session_store.save(state)

        state = orchestrator.step(session_id)  # -> COMPLETE
        assert state.phase == WorkflowPhase.COMPLETE
        assert state.status == WorkflowStatus.SUCCESS
        assert state.current_iteration == 3


class TestContextValidationIntegration:
    """Integration tests for context validation at workflow initialization."""

    def test_missing_required_field_raises_error(self, orchestrator):
        """Missing required context field should raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            orchestrator.initialize_run(
                profile="jpa-mt",
                context={
                    "scope": "domain",
                    # "entity" is missing
                    "table": "app.products",
                    "bounded_context": "catalog",
                    "schema_file": "schema.sql",
                },
                providers={"planner": "manual"},
            )
        assert "entity" in str(exc_info.value)

    def test_invalid_scope_choice_raises_error(self, orchestrator):
        """Invalid choice for scope should raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            orchestrator.initialize_run(
                profile="jpa-mt",
                context={
                    "scope": "invalid_scope",  # Not in ["domain", "vertical"]
                    "entity": "Product",
                    "table": "app.products",
                    "bounded_context": "catalog",
                    "schema_file": "schema.sql",
                },
                providers={"planner": "manual"},
            )
        assert "scope" in str(exc_info.value)
        assert "invalid_scope" in str(exc_info.value)

    def test_nonexistent_schema_file_raises_error(self, orchestrator):
        """Non-existent schema_file path should raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            orchestrator.initialize_run(
                profile="jpa-mt",
                context={
                    "scope": "domain",
                    "entity": "Product",
                    "table": "app.products",
                    "bounded_context": "catalog",
                    "schema_file": "nonexistent.sql",
                },
                providers={"planner": "manual"},
            )
        assert "schema_file" in str(exc_info.value)

    def test_multiple_validation_errors_reported(self, orchestrator):
        """Multiple validation errors should all be reported."""
        with pytest.raises(ValueError) as exc_info:
            orchestrator.initialize_run(
                profile="jpa-mt",
                context={
                    "scope": "invalid",
                    # entity missing
                    # table missing
                    "bounded_context": "catalog",
                    "schema_file": "nonexistent.sql",
                },
                providers={"planner": "manual"},
            )
        error_msg = str(exc_info.value)
        # Should mention multiple fields
        assert "scope" in error_msg
        assert "entity" in error_msg
        assert "table" in error_msg
