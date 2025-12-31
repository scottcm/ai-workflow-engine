"""Integration test fixtures.

These fixtures set up the full orchestrator with real file I/O
but mocked profiles and providers.
"""

import pytest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStatus
from aiwf.domain.models.write_plan import WriteOp, WritePlan
from aiwf.domain.persistence.session_store import SessionStore
from aiwf.domain.profiles.profile_factory import ProfileFactory
from aiwf.domain.providers.provider_factory import ProviderFactory
from aiwf.domain.standards import StandardsProviderFactory

from tests.integration.providers.fake_response_provider import FakeResponseProvider


class MockStandardsProvider:
    """Mock standards provider for integration tests."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        return {
            "name": "mock-standards",
            "description": "Mock standards provider for testing",
            "requires_config": False,
            "config_keys": [],
            "default_connection_timeout": 5,
            "default_response_timeout": 30,
        }

    def validate(self) -> None:
        pass

    def create_bundle(
        self,
        context: dict[str, Any],
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
    ) -> str:
        return """# Mock Standards Bundle

## Coding Standards
- Write clean code
- Add tests

## Architecture
- Use layered architecture
"""


def create_mock_profile(
    *,
    review_verdict: str = "PASS",
    generate_code: bool = True,
    revise_code: bool = True,
) -> MagicMock:
    """Create a mock profile with configurable behavior.

    Args:
        review_verdict: "PASS" or "FAIL" for review processing
        generate_code: Whether process_generation_response returns a WritePlan
        revise_code: Whether process_revision_response returns a WritePlan
    """
    mock_profile = MagicMock()

    # Standards provider methods
    mock_profile.get_default_standards_provider_key.return_value = "mock-standards"
    mock_profile.get_standards_config.return_value = {}

    # Prompt generation - return strings
    mock_profile.generate_planning_prompt.return_value = """# Planning Prompt

Create an implementation plan for the entity.

---

## Output Destination

Save your response to `planning-response.md`
"""
    mock_profile.generate_generation_prompt.return_value = """# Generation Prompt

Generate the code according to the plan.

---

## Output Destination

Save your response to `generation-response.md`
"""
    mock_profile.generate_review_prompt.return_value = """# Review Prompt

Review the generated code.

---

## Output Destination

Save your response to `review-response.md`
"""
    mock_profile.generate_revision_prompt.return_value = """# Revision Prompt

Revise the code based on feedback.

---

## Output Destination

Save your response to `revision-response.md`
"""

    # Response processing
    mock_profile.process_planning_response.return_value = ProcessingResult(
        status=WorkflowStatus.SUCCESS
    )

    # Generation response - optionally returns code
    if generate_code:
        mock_profile.process_generation_response.return_value = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[
                    WriteOp(path="MockEntity.java", content="public class MockEntity {}")
                ]
            ),
        )
    else:
        mock_profile.process_generation_response.return_value = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(writes=[]),
        )

    # Review response - verdict in metadata
    mock_profile.process_review_response.return_value = ProcessingResult(
        status=WorkflowStatus.SUCCESS,
        metadata={"verdict": review_verdict},
    )

    # Revision response - optionally returns code
    if revise_code:
        mock_profile.process_revision_response.return_value = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(
                writes=[
                    WriteOp(path="MockEntity.java", content="public class MockEntity { /* revised */ }")
                ]
            ),
        )
    else:
        mock_profile.process_revision_response.return_value = ProcessingResult(
            status=WorkflowStatus.SUCCESS,
            write_plan=WritePlan(writes=[]),
        )

    # Validation
    mock_profile.validate_metadata.return_value = None

    return mock_profile


@pytest.fixture
def sessions_root(tmp_path: Path) -> Path:
    """Isolated sessions directory for integration tests."""
    sessions = tmp_path / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    return sessions


@pytest.fixture
def session_store(sessions_root: Path) -> SessionStore:
    """Create session store for integration tests."""
    return SessionStore(sessions_root)


@pytest.fixture
def orchestrator(sessions_root: Path, session_store: SessionStore) -> WorkflowOrchestrator:
    """Create orchestrator for integration tests."""
    return WorkflowOrchestrator(
        session_store=session_store,
        sessions_root=sessions_root,
    )


@pytest.fixture
def mock_profile() -> MagicMock:
    """Default mock profile (PASS verdict, generates code)."""
    return create_mock_profile(review_verdict="PASS", generate_code=True)


@pytest.fixture
def mock_profile_fail_review() -> MagicMock:
    """Mock profile that fails review (requires revision)."""
    return create_mock_profile(review_verdict="FAIL", generate_code=True, revise_code=True)


@pytest.fixture
def fake_provider() -> FakeResponseProvider:
    """Fake provider with default responses."""
    return FakeResponseProvider(review_verdict="PASS")


@pytest.fixture
def fake_provider_fail_review() -> FakeResponseProvider:
    """Fake provider that returns FAIL verdict."""
    return FakeResponseProvider(review_verdict="FAIL")


@pytest.fixture
def register_integration_providers(
    monkeypatch: pytest.MonkeyPatch,
    mock_profile: MagicMock,
    fake_provider: FakeResponseProvider,
) -> None:
    """Register mock profile, standards provider, and fake AI provider.

    This fixture sets up the full mock environment for integration tests.
    """
    # Register mock standards provider
    StandardsProviderFactory.register("mock-standards", MockStandardsProvider)

    # Register fake AI provider
    ProviderFactory.register("fake", lambda: fake_provider)

    # Mock profile factory
    original_create = ProfileFactory.create
    original_get_metadata = ProfileFactory.get_metadata
    original_is_registered = ProfileFactory.is_registered

    def mock_create(profile_key: str, config: dict | None = None) -> Any:
        if profile_key == "test-profile":
            return mock_profile
        return original_create(profile_key, config=config)

    def mock_get_metadata(profile_key: str) -> dict[str, Any] | None:
        if profile_key == "test-profile":
            return {
                "name": "test-profile",
                "description": "Test profile for integration tests",
                "context_schema": {
                    "entity": {"type": "string", "required": True},
                },
            }
        return original_get_metadata(profile_key)

    def mock_is_registered(profile_key: str) -> bool:
        if profile_key == "test-profile":
            return True
        return original_is_registered(profile_key)

    monkeypatch.setattr(
        ProfileFactory, "create",
        classmethod(lambda cls, key, **kw: mock_create(key, kw.get("config")))
    )
    monkeypatch.setattr(
        ProfileFactory, "get_metadata",
        classmethod(lambda cls, key: mock_get_metadata(key))
    )
    monkeypatch.setattr(
        ProfileFactory, "is_registered",
        classmethod(lambda cls, key: mock_is_registered(key))
    )

    yield

    # Cleanup
    if "mock-standards" in StandardsProviderFactory._registry:
        del StandardsProviderFactory._registry["mock-standards"]
    if "fake" in ProviderFactory._registry:
        del ProviderFactory._registry["fake"]