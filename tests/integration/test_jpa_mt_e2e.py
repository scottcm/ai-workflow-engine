"""E2E Integration Tests for jpa-mt Profile.

Tests the full workflow using the orchestrator API with the real jpa-mt profile.
Uses mock standards files to verify scope filtering behavior.
"""

from pathlib import Path
from typing import Any

import pytest

from aiwf.application.approval_config import ApprovalConfig
from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStage, WorkflowStatus
from aiwf.domain.persistence.session_store import SessionStore
from aiwf.domain.standards import StandardsProviderFactory

from profiles.jpa_mt.config import JpaMtConfig, ScopeConfig, ScopeStandardsConfig, StandardsConfig, StandardsSource
from profiles.jpa_mt.profile import JpaMtProfile
from profiles.jpa_mt.standards import JpaMtStandardsProvider


def create_mock_standards(rules_path: Path) -> None:
    """Create mock standards files with distinct rules for each scope.

    Creates rules that can be used to verify scope filtering:
    - DOM-001: Only in domain scope
    - SVC-001: Only in service scope
    - API-001: Only in api scope
    - JV-001: Universal (in all scopes)
    """
    rules_path.mkdir(parents=True, exist_ok=True)

    # Domain-specific rules
    (rules_path / "DOMAIN-marked.rules.yml").write_text(
        """domain:
  entity:
    DOM-ENT-001: 'C: Domain entities MUST have proper annotations.'
    JPA-ENT-001: 'C: JPA entities MUST use explicit schema.'
"""
    )

    # Service-specific rules
    (rules_path / "SERVICE-marked.rules.yml").write_text(
        """service:
  SVC-BIZ-001: 'C: Service methods MUST be transactional.'
"""
    )

    # API-specific rules
    (rules_path / "API-marked.rules.yml").write_text(
        """api:
  CTL-NAM-001: 'C: Controller names MUST end with Controller.'
  API-REST-001: 'C: REST endpoints MUST use proper HTTP methods.'
"""
    )

    # Universal rules (in all scopes)
    (rules_path / "JAVA_STANDARDS-marked.rules.yml").write_text(
        """java:
  standards:
    JV-DI-001: 'C: Constructor injection MUST be used.'
    PKG-LAY-001: 'C: Package structure MUST follow conventions.'
"""
    )


def create_mock_schema(schema_path: Path) -> None:
    """Create a minimal mock schema file."""
    schema_path.write_text(
        """-- Mock schema for testing
CREATE TABLE app.tiers (
    id BIGINT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT
);
"""
    )


def create_test_config(rules_path: Path) -> JpaMtConfig:
    """Create a JpaMtConfig for testing with mock standards."""
    return JpaMtConfig(
        base_package="com.test.app",
        standards=StandardsConfig(
            sources=[StandardsSource(type="local", path=str(rules_path))],
        ),
        scopes={
            "domain": ScopeConfig(
                description="Entity + Repository",
                artifacts=["entity", "repository"],
                standards=ScopeStandardsConfig(
                    files=[
                        "DOMAIN-marked.rules.yml",
                        "JAVA_STANDARDS-marked.rules.yml",
                    ],
                    prefixes=["DOM-", "JPA-", "JV-", "PKG-"],
                ),
            ),
            "service": ScopeConfig(
                description="Service layer only",
                artifacts=["service"],
                standards=ScopeStandardsConfig(
                    files=[
                        "SERVICE-marked.rules.yml",
                        "JAVA_STANDARDS-marked.rules.yml",
                    ],
                    prefixes=["SVC-"],
                ),
            ),
            "api": ScopeConfig(
                description="Controller + DTO + Mapper",
                artifacts=["controller", "dto", "mapper"],
                standards=ScopeStandardsConfig(
                    files=[
                        "API-marked.rules.yml",
                        "JAVA_STANDARDS-marked.rules.yml",
                    ],
                    prefixes=["CTL-", "API-"],
                ),
            ),
            "full": ScopeConfig(
                description="All artifacts",
                artifacts=["entity", "repository", "service", "controller", "dto", "mapper"],
                standards=ScopeStandardsConfig(
                    files=[
                        "DOMAIN-marked.rules.yml",
                        "SERVICE-marked.rules.yml",
                        "API-marked.rules.yml",
                        "JAVA_STANDARDS-marked.rules.yml",
                    ],
                    prefixes=[],  # Empty = include all
                ),
            ),
        },
    )


def write_mock_response(session_path: Path, iteration: int, filename: str, content: str) -> None:
    """Write a mock response file to simulate AI/user response."""
    iteration_dir = session_path / f"iteration-{iteration}"
    iteration_dir.mkdir(parents=True, exist_ok=True)
    (iteration_dir / filename).write_text(content)


# Mock response templates
PLANNING_RESPONSE = """# Implementation Plan: Tier

## Schema Analysis
- Table: app.tiers
- Columns: id (BIGINT), name (VARCHAR), description (TEXT)

## Multi-Tenancy Classification
- Classification: Global Reference
- Rationale: Tier data is shared across all tenants

## Entity Design
### Fields
- id: Long (primary key)
- name: String (required)
- description: String (optional)

## File List
| File | Package | Class |
|------|---------|-------|
| Tier.java | com.test.app.domain | Tier |
| TierRepository.java | com.test.app.domain | TierRepository |
"""

GENERATION_RESPONSE = """# Generated Code

## Tier.java

```java
package com.test.app.domain;

import jakarta.persistence.*;

@Entity
@Table(schema = "app", name = "tiers")
public class Tier {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    private String description;

    // Getters and setters
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public String getDescription() { return description; }
    public void setDescription(String description) { this.description = description; }
}
```

## TierRepository.java

```java
package com.test.app.domain;

import org.springframework.data.jpa.repository.JpaRepository;

public interface TierRepository extends JpaRepository<Tier, Long> {
}
```
"""

REVIEW_PASS_RESPONSE = """# Code Review

## Summary
The generated code meets all requirements.

## Standards Compliance
- All JPA annotations are correct
- Package structure follows conventions
- Multi-tenancy classification is appropriate

@@@REVIEW_META
verdict: PASS
issues_total: 0
issues_critical: 0
missing_inputs: 0
@@@
"""

REVIEW_FAIL_RESPONSE = """# Code Review

## Summary
The generated code has issues that need to be addressed.

## Issues Found
1. **[JPA-ENT-001]** Missing explicit column definitions for some fields
2. **[DOM-ENT-001]** Missing Javadoc on entity class

@@@REVIEW_META
verdict: FAIL
issues_total: 2
issues_critical: 0
missing_inputs: 0
@@@
"""


@pytest.fixture
def e2e_env(tmp_path: Path):
    """Set up complete E2E test environment.

    Creates:
    - Temporary sessions directory
    - Mock standards files
    - Mock schema file
    - Test JpaMtConfig
    - Orchestrator with skip approval
    """
    # Create directory structure
    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir()

    rules_path = tmp_path / "rules"
    create_mock_standards(rules_path)

    schema_path = tmp_path / "schema.sql"
    create_mock_schema(schema_path)

    # Create config object (not file)
    config = create_test_config(rules_path)

    # Create profile with test config
    profile = JpaMtProfile(config=config)

    # Create orchestrator
    session_store = SessionStore(sessions_root=sessions_root)
    orchestrator = WorkflowOrchestrator(
        session_store=session_store,
        sessions_root=sessions_root,
        approval_config=ApprovalConfig(default_approver="skip"),
    )

    return {
        "tmp_path": tmp_path,
        "sessions_root": sessions_root,
        "rules_path": rules_path,
        "schema_path": schema_path,
        "config": config,
        "profile": profile,
        "session_store": session_store,
        "orchestrator": orchestrator,
    }


class TestE2EInfrastructure:
    """Tests for E2E test infrastructure itself."""

    def test_mock_standards_created(self, e2e_env):
        """Mock standards files are created correctly."""
        rules_path = e2e_env["rules_path"]

        assert (rules_path / "DOMAIN-marked.rules.yml").exists()
        assert (rules_path / "SERVICE-marked.rules.yml").exists()
        assert (rules_path / "API-marked.rules.yml").exists()
        assert (rules_path / "JAVA_STANDARDS-marked.rules.yml").exists()

    def test_mock_schema_created(self, e2e_env):
        """Mock schema file is created correctly."""
        schema_path = e2e_env["schema_path"]
        assert schema_path.exists()
        content = schema_path.read_text()
        assert "app.tiers" in content

    def test_config_created(self, e2e_env):
        """Test config is created correctly."""
        config = e2e_env["config"]
        assert config.base_package == "com.test.app"
        assert "domain" in config.scopes
        assert "service" in config.scopes

    def test_profile_created(self, e2e_env):
        """Profile is created with test config."""
        profile = e2e_env["profile"]
        assert profile.config.base_package == "com.test.app"


class TestScopeFiltering:
    """Tests for scope-based standards filtering."""

    def test_domain_scope_includes_only_domain_prefixes(self, e2e_env):
        """Domain scope includes only DOM-, JPA-, JV-, PKG- prefixed rules."""
        rules_path = e2e_env["rules_path"]
        config = e2e_env["config"]

        # Create standards provider
        provider = JpaMtStandardsProvider({"rules_path": str(rules_path)})

        # Get domain scope config
        scope_config = config.scopes["domain"]

        # Create bundle with domain prefixes
        bundle = provider.create_bundle({
            "scope": "domain",
            "standards_files": scope_config.standards.files,
            "standards_prefixes": scope_config.standards.prefixes,
        })

        # Should include domain rules
        assert "DOM-ENT-001" in bundle
        assert "JPA-ENT-001" in bundle
        assert "JV-DI-001" in bundle

        # Should NOT include service or api rules
        assert "SVC-BIZ-001" not in bundle
        assert "CTL-NAM-001" not in bundle
        assert "API-REST-001" not in bundle

    def test_service_scope_includes_only_service_prefixes(self, e2e_env):
        """Service scope includes only SVC- prefixed rules."""
        rules_path = e2e_env["rules_path"]
        config = e2e_env["config"]

        provider = JpaMtStandardsProvider({"rules_path": str(rules_path)})
        scope_config = config.scopes["service"]

        bundle = provider.create_bundle({
            "scope": "service",
            "standards_files": scope_config.standards.files,
            "standards_prefixes": scope_config.standards.prefixes,
        })

        # Should include only service rules
        assert "SVC-BIZ-001" in bundle

        # Should NOT include domain or api rules
        assert "DOM-ENT-001" not in bundle
        assert "JPA-ENT-001" not in bundle
        assert "CTL-NAM-001" not in bundle

    def test_api_scope_includes_only_api_prefixes(self, e2e_env):
        """API scope includes only CTL-, API- prefixed rules."""
        rules_path = e2e_env["rules_path"]
        config = e2e_env["config"]

        provider = JpaMtStandardsProvider({"rules_path": str(rules_path)})
        scope_config = config.scopes["api"]

        bundle = provider.create_bundle({
            "scope": "api",
            "standards_files": scope_config.standards.files,
            "standards_prefixes": scope_config.standards.prefixes,
        })

        # Should include api rules
        assert "CTL-NAM-001" in bundle
        assert "API-REST-001" in bundle

        # Should NOT include domain or service rules
        assert "DOM-ENT-001" not in bundle
        assert "SVC-BIZ-001" not in bundle

    def test_full_scope_includes_all_rules(self, e2e_env):
        """Full scope includes all rules (empty prefixes = all)."""
        rules_path = e2e_env["rules_path"]
        config = e2e_env["config"]

        provider = JpaMtStandardsProvider({"rules_path": str(rules_path)})
        scope_config = config.scopes["full"]

        bundle = provider.create_bundle({
            "scope": "full",
            "standards_files": scope_config.standards.files,
            "standards_prefixes": scope_config.standards.prefixes,
        })

        # Should include all rules
        assert "DOM-ENT-001" in bundle
        assert "JPA-ENT-001" in bundle
        assert "SVC-BIZ-001" in bundle
        assert "CTL-NAM-001" in bundle
        assert "API-REST-001" in bundle
        assert "JV-DI-001" in bundle


class TestHappyPath:
    """Test complete workflow from init to complete (path 9).

    Uses FakeAIProvider for all phases with skip approval gates.
    Workflow: INIT → PLAN → GENERATE → REVIEW(PASS) → COMPLETE
    """

    @pytest.fixture
    def happy_path_env(self, e2e_env, monkeypatch):
        """Extend e2e_env with FakeAIProvider registration."""
        from aiwf.domain.providers.provider_factory import AIProviderFactory
        from aiwf.domain.profiles.profile_factory import ProfileFactory
        from tests.integration.providers.fake_ai_provider import FakeAIProvider

        # Create fake provider with PASS verdict
        fake_provider = FakeAIProvider(review_verdict="PASS")

        # Register fake provider
        AIProviderFactory.register("fake", lambda: fake_provider)

        # Mock ProfileFactory to return our test profile
        profile = e2e_env["profile"]
        original_create = ProfileFactory.create
        original_get_metadata = ProfileFactory.get_metadata
        original_is_registered = ProfileFactory.is_registered

        def mock_create(profile_key: str, config=None):
            if profile_key == "jpa-mt":
                return profile
            return original_create(profile_key, config=config)

        def mock_get_metadata(profile_key: str):
            if profile_key == "jpa-mt":
                return JpaMtProfile.get_metadata()
            return original_get_metadata(profile_key)

        def mock_is_registered(profile_key: str):
            if profile_key == "jpa-mt":
                return True
            return original_is_registered(profile_key)

        monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, key, **kw: mock_create(key, kw.get("config"))))
        monkeypatch.setattr(ProfileFactory, "get_metadata", classmethod(lambda cls, key: mock_get_metadata(key)))
        monkeypatch.setattr(ProfileFactory, "is_registered", classmethod(lambda cls, key: mock_is_registered(key)))

        yield {
            **e2e_env,
            "fake_provider": fake_provider,
        }

        # Cleanup
        if "fake" in AIProviderFactory._registry:
            del AIProviderFactory._registry["fake"]

    def test_full_workflow_completes_with_pass_verdict(self, happy_path_env):
        """Full workflow reaches COMPLETE with PASS verdict."""
        orchestrator = happy_path_env["orchestrator"]
        schema_path = happy_path_env["schema_path"]
        config = happy_path_env["config"]

        # Initialize session
        session_id = orchestrator.initialize_run(
            profile="jpa-mt",
            providers={
                "planner": "fake",
                "generator": "fake",
                "reviewer": "fake",
                "reviser": "fake",
            },
            context={
                "scope": "domain",
                "entity": "Tier",
                "table": "app.tiers",
                "bounded_context": "pricing",
                "schema_file": str(schema_path),
                "standards_files": config.scopes["domain"].standards.files,
                "standards_prefixes": config.scopes["domain"].standards.prefixes,
            },
        )

        # Start workflow - with skip approvers, should auto-progress to COMPLETE
        state = orchestrator.init(session_id)

        # Verify final state
        assert state.phase == WorkflowPhase.COMPLETE
        assert state.status == WorkflowStatus.SUCCESS

    def test_workflow_creates_expected_files(self, happy_path_env):
        """Workflow creates all expected prompt and response files."""
        orchestrator = happy_path_env["orchestrator"]
        sessions_root = happy_path_env["sessions_root"]
        schema_path = happy_path_env["schema_path"]
        config = happy_path_env["config"]

        session_id = orchestrator.initialize_run(
            profile="jpa-mt",
            providers={
                "planner": "fake",
                "generator": "fake",
                "reviewer": "fake",
                "reviser": "fake",
            },
            context={
                "scope": "domain",
                "entity": "Tier",
                "table": "app.tiers",
                "bounded_context": "pricing",
                "schema_file": str(schema_path),
                "standards_files": config.scopes["domain"].standards.files,
                "standards_prefixes": config.scopes["domain"].standards.prefixes,
            },
        )

        orchestrator.init(session_id)

        # Check files created
        session_dir = sessions_root / session_id
        iteration_dir = session_dir / "iteration-1"

        assert (iteration_dir / "planning-prompt.md").exists()
        assert (iteration_dir / "planning-response.md").exists()
        assert (iteration_dir / "generation-prompt.md").exists()
        assert (iteration_dir / "generation-response.md").exists()
        assert (iteration_dir / "review-prompt.md").exists()
        assert (iteration_dir / "review-response.md").exists()
        assert (session_dir / "plan.md").exists()

    def test_fake_provider_called_for_each_phase(self, happy_path_env):
        """FakeAIProvider is called once per phase."""
        orchestrator = happy_path_env["orchestrator"]
        fake_provider = happy_path_env["fake_provider"]
        schema_path = happy_path_env["schema_path"]
        config = happy_path_env["config"]

        fake_provider.reset_history()

        session_id = orchestrator.initialize_run(
            profile="jpa-mt",
            providers={
                "planner": "fake",
                "generator": "fake",
                "reviewer": "fake",
                "reviser": "fake",
            },
            context={
                "scope": "domain",
                "entity": "Tier",
                "table": "app.tiers",
                "bounded_context": "pricing",
                "schema_file": str(schema_path),
                "standards_files": config.scopes["domain"].standards.files,
                "standards_prefixes": config.scopes["domain"].standards.prefixes,
            },
        )

        orchestrator.init(session_id)

        # Should have 3 calls: PLAN, GENERATE, REVIEW (no REVISE since PASS)
        assert len(fake_provider.call_history) == 3


class TestRevisionPath:
    """Test workflow with FAIL verdict and revision cycle (path 10).

    Workflow: INIT → PLAN → GENERATE → REVIEW(FAIL) → REVISE → REVIEW(PASS) → COMPLETE
    """

    @pytest.fixture
    def revision_path_env(self, e2e_env, monkeypatch):
        """Extend e2e_env with FakeAIProvider that fails first review."""
        from aiwf.domain.providers.provider_factory import AIProviderFactory
        from aiwf.domain.profiles.profile_factory import ProfileFactory
        from aiwf.domain.models.ai_provider_result import AIProviderResult
        from tests.integration.providers.fake_ai_provider import FakeAIProvider

        # Track review calls to return FAIL first, then PASS
        review_call_count = {"count": 0}

        def revision_generator(prompt: str, context: dict | None) -> str:
            """Return appropriate response for each phase, FAIL on first review."""
            # Get phase from context (set by orchestrator)
            phase = context.get("phase") if context else None

            if phase == "plan":
                return PLANNING_RESPONSE
            elif phase == "generate":
                return GENERATION_RESPONSE
            elif phase == "review":
                review_call_count["count"] += 1
                if review_call_count["count"] == 1:
                    return REVIEW_FAIL_RESPONSE
                return REVIEW_PASS_RESPONSE
            elif phase == "revise":
                return FakeAIProvider.DEFAULT_REVISE_RESPONSE

            return "# Mock Response\n\nFallback response."

        # Create fake provider with custom generator
        fake_provider = FakeAIProvider(generator=revision_generator)

        # Register fake provider
        AIProviderFactory.register("fake-revision", lambda: fake_provider)

        # Mock ProfileFactory to return our test profile
        profile = e2e_env["profile"]
        original_create = ProfileFactory.create
        original_get_metadata = ProfileFactory.get_metadata
        original_is_registered = ProfileFactory.is_registered

        def mock_create(profile_key: str, config=None):
            if profile_key == "jpa-mt":
                return profile
            return original_create(profile_key, config=config)

        def mock_get_metadata(profile_key: str):
            if profile_key == "jpa-mt":
                return JpaMtProfile.get_metadata()
            return original_get_metadata(profile_key)

        def mock_is_registered(profile_key: str):
            if profile_key == "jpa-mt":
                return True
            return original_is_registered(profile_key)

        monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, key, **kw: mock_create(key, kw.get("config"))))
        monkeypatch.setattr(ProfileFactory, "get_metadata", classmethod(lambda cls, key: mock_get_metadata(key)))
        monkeypatch.setattr(ProfileFactory, "is_registered", classmethod(lambda cls, key: mock_is_registered(key)))

        yield {
            **e2e_env,
            "fake_provider": fake_provider,
            "review_call_count": review_call_count,
        }

        # Cleanup
        if "fake-revision" in AIProviderFactory._registry:
            del AIProviderFactory._registry["fake-revision"]

    def test_workflow_enters_revise_on_fail_verdict(self, revision_path_env):
        """Workflow enters REVISE phase when review verdict is FAIL."""
        orchestrator = revision_path_env["orchestrator"]
        schema_path = revision_path_env["schema_path"]
        config = revision_path_env["config"]
        review_call_count = revision_path_env["review_call_count"]

        session_id = orchestrator.initialize_run(
            profile="jpa-mt",
            providers={
                "planner": "fake-revision",
                "generator": "fake-revision",
                "reviewer": "fake-revision",
                "reviser": "fake-revision",
            },
            context={
                "scope": "domain",
                "entity": "Tier",
                "table": "app.tiers",
                "bounded_context": "pricing",
                "schema_file": str(schema_path),
                "standards_files": config.scopes["domain"].standards.files,
                "standards_prefixes": config.scopes["domain"].standards.prefixes,
            },
        )

        state = orchestrator.init(session_id)

        # Should complete after revision cycle
        assert state.phase == WorkflowPhase.COMPLETE
        assert state.status == WorkflowStatus.SUCCESS
        # Review should have been called twice (FAIL, then PASS)
        assert review_call_count["count"] == 2

    def test_revision_creates_revision_files(self, revision_path_env):
        """Revision cycle creates revision prompt and response files."""
        orchestrator = revision_path_env["orchestrator"]
        sessions_root = revision_path_env["sessions_root"]
        schema_path = revision_path_env["schema_path"]
        config = revision_path_env["config"]

        session_id = orchestrator.initialize_run(
            profile="jpa-mt",
            providers={
                "planner": "fake-revision",
                "generator": "fake-revision",
                "reviewer": "fake-revision",
                "reviser": "fake-revision",
            },
            context={
                "scope": "domain",
                "entity": "Tier",
                "table": "app.tiers",
                "bounded_context": "pricing",
                "schema_file": str(schema_path),
                "standards_files": config.scopes["domain"].standards.files,
                "standards_prefixes": config.scopes["domain"].standards.prefixes,
            },
        )

        orchestrator.init(session_id)

        # Check files created including revision files
        session_dir = sessions_root / session_id
        iteration_1_dir = session_dir / "iteration-1"
        iteration_2_dir = session_dir / "iteration-2"

        # Standard files in iteration-1 (before FAIL verdict)
        assert (iteration_1_dir / "planning-prompt.md").exists()
        assert (iteration_1_dir / "planning-response.md").exists()
        assert (iteration_1_dir / "generation-prompt.md").exists()
        assert (iteration_1_dir / "generation-response.md").exists()
        assert (iteration_1_dir / "review-prompt.md").exists()
        assert (iteration_1_dir / "review-response.md").exists()

        # Revision files in iteration-2 (after FAIL verdict increments iteration)
        assert (iteration_2_dir / "revision-prompt.md").exists()
        assert (iteration_2_dir / "revision-response.md").exists()
        # Second review also in iteration-2
        assert (iteration_2_dir / "review-prompt.md").exists()
        assert (iteration_2_dir / "review-response.md").exists()

    def test_provider_called_correct_number_of_times(self, revision_path_env):
        """Provider is called correct number of times including revision."""
        orchestrator = revision_path_env["orchestrator"]
        fake_provider = revision_path_env["fake_provider"]
        schema_path = revision_path_env["schema_path"]
        config = revision_path_env["config"]

        fake_provider.reset_history()

        session_id = orchestrator.initialize_run(
            profile="jpa-mt",
            providers={
                "planner": "fake-revision",
                "generator": "fake-revision",
                "reviewer": "fake-revision",
                "reviser": "fake-revision",
            },
            context={
                "scope": "domain",
                "entity": "Tier",
                "table": "app.tiers",
                "bounded_context": "pricing",
                "schema_file": str(schema_path),
                "standards_files": config.scopes["domain"].standards.files,
                "standards_prefixes": config.scopes["domain"].standards.prefixes,
            },
        )

        orchestrator.init(session_id)

        # Should have 5 calls: PLAN, GENERATE, REVIEW(FAIL), REVISE, REVIEW(PASS)
        assert len(fake_provider.call_history) == 5
