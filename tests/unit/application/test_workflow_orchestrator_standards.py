import hashlib
from pathlib import Path
from typing import Any

import pytest

from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.models.workflow_state import ExecutionMode
from aiwf.domain.persistence.session_store import SessionStore
from aiwf.domain.profiles import profile_factory as profile_factory_module
from aiwf.domain.standards import StandardsProviderFactory


# Track provider calls at module level so factory instances can report them
_provider_calls: int = 0


class _FakeProvider:
    """Factory-registered standards provider for testing."""

    bundle_text: str = "standards\n"

    def __init__(self, config: dict):
        self.config = config

    @classmethod
    def get_metadata(cls):
        return {
            "name": "fake-provider",
            "description": "Fake provider for testing",
            "requires_config": False,
            "config_keys": [],
            "default_connection_timeout": 5,
            "default_response_timeout": 30,
        }

    def validate(self):
        pass  # Always valid

    def create_bundle(self, context, connection_timeout=None, response_timeout=None) -> str:
        global _provider_calls
        _provider_calls += 1
        return self.bundle_text


class _StubProfile:
    """Profile using factory-based standards provider (ADR-0007 Phase 2)."""

    def __init__(self, provider_key: str = "fake-provider"):
        self._provider_key = provider_key

    def validate_metadata(self, metadata):
        pass  # No validation needed for tests

    def get_default_standards_provider_key(self) -> str:
        return self._provider_key

    def get_standards_config(self) -> dict:
        return {}


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def test_orchestrator_materializes_standards_on_initialize(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, valid_jpa_mt_context: dict[str, Any]) -> None:
    global _provider_calls
    _provider_calls = 0

    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir(parents=True, exist_ok=True)

    # Register fake provider in factory
    original_registry = dict(StandardsProviderFactory._registry)
    StandardsProviderFactory.register("fake-provider", _FakeProvider)

    try:
        session_store = SessionStore(sessions_root=sessions_root)
        orchestrator = WorkflowOrchestrator(session_store=session_store, sessions_root=sessions_root)

        profile = _StubProfile(provider_key="fake-provider")

        # Capture the state object saved during initialization without asserting persistence behavior.
        saved: dict[str, object] = {}
        orig_save = session_store.save

        def _save_capture(state):
            saved["state"] = state
            return orig_save(state)

        monkeypatch.setattr(session_store, "save", _save_capture)

        monkeypatch.setattr(profile_factory_module.ProfileFactory, "create", staticmethod(lambda profile_name, config=None: profile))

        session_id = orchestrator.initialize_run(
            profile="jpa-mt",
            context=valid_jpa_mt_context,
            providers={"planner": "manual", "generator": "manual", "reviewer": "manual", "reviser": "manual"},
            execution_mode=ExecutionMode.INTERACTIVE,
        )

        assert session_id

        # Standards provider call path enforced via factory
        assert _provider_calls == 1

        # Engine must write standards-bundle.md into the session directory
        bundle_path = sessions_root / session_id / "standards-bundle.md"
        assert bundle_path.exists()
        assert bundle_path.read_text(encoding="utf-8") == "standards\n"

        # Engine must compute hash of exact bytes written and store raw digest into state
        assert "state" in saved
        assert saved["state"].standards_hash == _sha256_hex("standards\n")
        # Standards provider key should be stored in state
        assert saved["state"].standards_provider == "fake-provider"
    finally:
        StandardsProviderFactory._registry.clear()
        StandardsProviderFactory._registry.update(original_registry)


class _FactoryBasedProfile:
    """Profile that uses factory-based standards provider (ADR-0007 Phase 2)."""

    def __init__(self, provider_key: str, config: dict):
        self._provider_key = provider_key
        self._config = config

    def validate_metadata(self, metadata):
        pass

    def get_default_standards_provider_key(self) -> str:
        return self._provider_key

    def get_standards_config(self) -> dict:
        return self._config


class _FactoryStandardsProvider:
    """Standards provider registered in StandardsProviderFactory."""

    def __init__(self, config: dict):
        self.config = config
        self.bundle_text = "factory-bundle\n"

    @classmethod
    def get_metadata(cls):
        return {
            "name": "factory-test",
            "description": "Test provider for factory-based resolution",
            "requires_config": False,
            "config_keys": [],
            "default_connection_timeout": 5,
            "default_response_timeout": 30,
        }

    def validate(self):
        pass

    def create_bundle(self, context, connection_timeout=None, response_timeout=None) -> str:
        return self.bundle_text


def test_orchestrator_uses_standards_provider_parameter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, valid_jpa_mt_context: dict[str, Any]
) -> None:
    """initialize_run uses standards_provider parameter when provided."""
    from aiwf.domain.standards import StandardsProviderFactory

    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir(parents=True, exist_ok=True)

    # Register a test provider in the factory
    original_registry = dict(StandardsProviderFactory._registry)
    StandardsProviderFactory.register("test-factory-provider", _FactoryStandardsProvider)

    try:
        session_store = SessionStore(sessions_root=sessions_root)
        orchestrator = WorkflowOrchestrator(session_store=session_store, sessions_root=sessions_root)

        profile = _FactoryBasedProfile(
            provider_key="profile-default-provider",
            config={},
        )

        saved: dict[str, object] = {}
        orig_save = session_store.save

        def _save_capture(state):
            saved["state"] = state
            return orig_save(state)

        monkeypatch.setattr(session_store, "save", _save_capture)
        monkeypatch.setattr(
            profile_factory_module.ProfileFactory,
            "create",
            staticmethod(lambda profile_name, config=None: profile),
        )

        session_id = orchestrator.initialize_run(
            profile="jpa-mt",
            context=valid_jpa_mt_context,
            providers={"planner": "manual", "generator": "manual", "reviewer": "manual", "reviser": "manual"},
            execution_mode=ExecutionMode.INTERACTIVE,
            standards_provider="test-factory-provider",
        )

        assert session_id
        assert "state" in saved
        # Should store the explicit parameter value, not the profile default
        assert saved["state"].standards_provider == "test-factory-provider"

        # Bundle should be created using the factory provider
        bundle_path = sessions_root / session_id / "standards-bundle.md"
        assert bundle_path.exists()
        assert bundle_path.read_text(encoding="utf-8") == "factory-bundle\n"
    finally:
        # Restore original registry
        StandardsProviderFactory._registry.clear()
        StandardsProviderFactory._registry.update(original_registry)


def test_orchestrator_uses_profile_default_when_no_standards_provider_param(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, valid_jpa_mt_context: dict[str, Any]
) -> None:
    """initialize_run falls back to profile's get_default_standards_provider_key() when no parameter."""
    from aiwf.domain.standards import StandardsProviderFactory

    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir(parents=True, exist_ok=True)

    # Register the profile's default provider
    original_registry = dict(StandardsProviderFactory._registry)
    StandardsProviderFactory.register("profile-default-provider", _FactoryStandardsProvider)

    try:
        session_store = SessionStore(sessions_root=sessions_root)
        orchestrator = WorkflowOrchestrator(session_store=session_store, sessions_root=sessions_root)

        profile = _FactoryBasedProfile(
            provider_key="profile-default-provider",
            config={"custom": "config"},
        )

        saved: dict[str, object] = {}
        orig_save = session_store.save

        def _save_capture(state):
            saved["state"] = state
            return orig_save(state)

        monkeypatch.setattr(session_store, "save", _save_capture)
        monkeypatch.setattr(
            profile_factory_module.ProfileFactory,
            "create",
            staticmethod(lambda profile_name, config=None: profile),
        )

        session_id = orchestrator.initialize_run(
            profile="jpa-mt",
            context=valid_jpa_mt_context,
            providers={"planner": "manual", "generator": "manual", "reviewer": "manual", "reviser": "manual"},
            execution_mode=ExecutionMode.INTERACTIVE,
            # No standards_provider parameter - should use profile default
        )

        assert session_id
        assert "state" in saved
        # Should store the profile's default provider key
        assert saved["state"].standards_provider == "profile-default-provider"
    finally:
        StandardsProviderFactory._registry.clear()
        StandardsProviderFactory._registry.update(original_registry)