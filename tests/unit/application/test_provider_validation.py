"""Tests for provider validation at init time."""

from pathlib import Path
from typing import Any

import pytest

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.errors import ProviderError
from aiwf.domain.persistence.session_store import SessionStore
from aiwf.domain.providers.ai_provider import AIProvider
from aiwf.domain.providers.provider_factory import ProviderFactory


class ValidatingProvider(AIProvider):
    """Provider that tracks validation calls."""

    validation_calls: list[str] = []

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        return {
            "name": "validating",
            "description": "Provider that tracks validation",
            "requires_config": False,
            "config_keys": [],
            "default_connection_timeout": 10,
            "default_response_timeout": 60,
        }

    def validate(self) -> None:
        ValidatingProvider.validation_calls.append("validated")

    def generate(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
    ) -> str | None:
        return None


class FailingValidationProvider(AIProvider):
    """Provider whose validate() always fails."""

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        return {
            "name": "failing-validation",
            "description": "Provider that fails validation",
            "requires_config": True,
            "config_keys": ["api_key"],
            "default_connection_timeout": 10,
            "default_response_timeout": 60,
        }

    def validate(self) -> None:
        raise ProviderError("API key not configured")

    def generate(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
    ) -> str | None:
        return None


@pytest.fixture
def register_validating_providers():
    """Register test providers and clean up after."""
    ProviderFactory.register("validating", ValidatingProvider)
    ProviderFactory.register("failing-validation", FailingValidationProvider)
    ValidatingProvider.validation_calls = []
    yield
    if "validating" in ProviderFactory._registry:
        del ProviderFactory._registry["validating"]
    if "failing-validation" in ProviderFactory._registry:
        del ProviderFactory._registry["failing-validation"]


def test_initialize_run_validates_all_providers(
    sessions_root: Path, register_validating_providers
):
    """initialize_run() calls validate() on each configured provider."""
    store = SessionStore(sessions_root=sessions_root)
    orchestrator = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    ValidatingProvider.validation_calls = []

    orchestrator.initialize_run(
        profile="jpa-mt",
        scope="domain",
        entity="TestEntity",
        providers={
            "planner": "validating",
            "generator": "validating",
        },
        bounded_context="test",
    )

    # Should have been validated twice (once per role)
    assert len(ValidatingProvider.validation_calls) == 2


def test_initialize_run_fails_fast_on_invalid_provider(
    sessions_root: Path, register_validating_providers
):
    """initialize_run() raises ProviderError when validation fails."""
    store = SessionStore(sessions_root=sessions_root)
    orchestrator = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    with pytest.raises(ProviderError, match="API key not configured"):
        orchestrator.initialize_run(
            profile="jpa-mt",
            scope="domain",
            entity="TestEntity",
            providers={"planner": "failing-validation"},
            bounded_context="test",
        )


def test_initialize_run_cleans_up_session_dir_on_validation_failure(
    sessions_root: Path, register_validating_providers
):
    """initialize_run() removes session directory when provider validation fails."""
    store = SessionStore(sessions_root=sessions_root)
    orchestrator = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    # Count directories before
    dirs_before = set(sessions_root.iterdir()) if sessions_root.exists() else set()

    with pytest.raises(ProviderError):
        orchestrator.initialize_run(
            profile="jpa-mt",
            scope="domain",
            entity="TestEntity",
            providers={"planner": "failing-validation"},
            bounded_context="test",
        )

    # Count directories after - should be same as before (no orphaned dirs)
    dirs_after = set(sessions_root.iterdir()) if sessions_root.exists() else set()
    assert dirs_before == dirs_after, "Session directory should be cleaned up on validation failure"


def test_manual_provider_validates_successfully(sessions_root: Path):
    """ManualProvider.validate() succeeds (no external dependencies)."""
    store = SessionStore(sessions_root=sessions_root)
    orchestrator = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    # Should not raise - manual provider has no validation to fail
    session_id = orchestrator.initialize_run(
        profile="jpa-mt",
        scope="domain",
        entity="TestEntity",
        providers={"planner": "manual"},
        bounded_context="test",
    )

    assert session_id is not None


# --- Standards Provider Validation Tests ---

from aiwf.domain.standards import StandardsProviderFactory


class FailingStandardsProvider:
    """Standards provider whose validate() always fails."""

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        return {
            "name": "failing-standards",
            "description": "Standards provider that fails validation",
            "requires_config": True,
            "config_keys": ["standards_root"],
            "default_connection_timeout": 5,
            "default_response_timeout": 30,
        }

    def validate(self) -> None:
        raise ProviderError("Standards root not configured")

    def create_bundle(
        self,
        context: dict[str, Any],
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
    ) -> str:
        return ""


@pytest.fixture
def register_failing_standards_provider():
    """Register failing standards provider and clean up after."""
    original_registry = dict(StandardsProviderFactory._registry)
    StandardsProviderFactory.register("failing-standards", FailingStandardsProvider)
    yield
    StandardsProviderFactory._registry.clear()
    StandardsProviderFactory._registry.update(original_registry)


def test_initialize_run_fails_on_unregistered_standards_provider(sessions_root: Path):
    """initialize_run() raises KeyError when standards_provider key is not registered."""
    store = SessionStore(sessions_root=sessions_root)
    orchestrator = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    with pytest.raises(KeyError):
        orchestrator.initialize_run(
            profile="jpa-mt",
            scope="domain",
            entity="TestEntity",
            providers={"planner": "manual"},
            bounded_context="test",
            standards_provider="nonexistent-standards-provider",
        )


def test_initialize_run_fails_on_standards_provider_validation_failure(
    sessions_root: Path, register_failing_standards_provider
):
    """initialize_run() raises ProviderError when standards provider validation fails."""
    store = SessionStore(sessions_root=sessions_root)
    orchestrator = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    with pytest.raises(ProviderError, match="Standards root not configured"):
        orchestrator.initialize_run(
            profile="jpa-mt",
            scope="domain",
            entity="TestEntity",
            providers={"planner": "manual"},
            bounded_context="test",
            standards_provider="failing-standards",
        )


def test_initialize_run_cleans_up_session_on_standards_provider_failure(
    sessions_root: Path, register_failing_standards_provider
):
    """initialize_run() removes session directory when standards provider validation fails."""
    store = SessionStore(sessions_root=sessions_root)
    orchestrator = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    # Count directories before
    dirs_before = set(sessions_root.iterdir()) if sessions_root.exists() else set()

    with pytest.raises(ProviderError):
        orchestrator.initialize_run(
            profile="jpa-mt",
            scope="domain",
            entity="TestEntity",
            providers={"planner": "manual"},
            bounded_context="test",
            standards_provider="failing-standards",
        )

    # Count directories after - should be same as before (no orphaned dirs)
    dirs_after = set(sessions_root.iterdir()) if sessions_root.exists() else set()
    assert dirs_before == dirs_after, "Session directory should be cleaned up on standards provider failure"


def test_initialize_run_cleans_up_session_on_unregistered_standards_provider(
    sessions_root: Path,
):
    """initialize_run() removes session directory when standards provider key is not found."""
    store = SessionStore(sessions_root=sessions_root)
    orchestrator = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    # Count directories before
    dirs_before = set(sessions_root.iterdir()) if sessions_root.exists() else set()

    with pytest.raises(KeyError):
        orchestrator.initialize_run(
            profile="jpa-mt",
            scope="domain",
            entity="TestEntity",
            providers={"planner": "manual"},
            bounded_context="test",
            standards_provider="nonexistent-provider",
        )

    # Count directories after - should be same as before (no orphaned dirs)
    dirs_after = set(sessions_root.iterdir()) if sessions_root.exists() else set()
    assert dirs_before == dirs_after, "Session directory should be cleaned up on unknown standards provider"