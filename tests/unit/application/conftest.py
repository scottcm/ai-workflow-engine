# tests/unit/application/conftest.py
"""Fixtures for application layer tests."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock
from typing import Any

from aiwf.domain.profiles.profile_factory import ProfileFactory
from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.workflow_state import WorkflowStatus
from aiwf.domain.models.write_plan import WriteOp, WritePlan
from aiwf.domain.standards import StandardsProviderFactory


@pytest.fixture
def valid_jpa_mt_context(tmp_path: Path) -> dict[str, Any]:
    """Return a valid context dict for jpa-mt profile tests."""
    schema_file = tmp_path / "schema.sql"
    schema_file.write_text("CREATE TABLE foo (...);")
    return {
        "scope": "domain",
        "entity": "Foo",
        "table": "foo",
        "bounded_context": "core",
        "schema_file": str(schema_file),
    }


@pytest.fixture(autouse=True)
def create_schema_file_for_tests(tmp_path: Path, monkeypatch):
    """Create a dummy schema file for tests using metadata with schema_file.

    This fixture intercepts context validation to create a temp schema file
    if the test doesn't provide one.
    """
    # Create a default schema file path for use by tests
    schema_file = tmp_path / "test_schema.sql"
    schema_file.write_text("CREATE TABLE test (...);")

    # Store on tmp_path for tests that need it
    monkeypatch.setattr("tests.unit.application.conftest._default_schema_file", str(schema_file), raising=False)


class MockStandardsProvider:
    """Mock standards provider for testing."""

    def __init__(self, config):
        self.config = config

    @classmethod
    def get_metadata(cls):
        return {
            "name": "mock-standards",
            "description": "Mock standards provider for testing",
            "requires_config": False,
            "config_keys": [],
            "default_connection_timeout": 5,
            "default_response_timeout": 30,
        }

    def validate(self):
        pass  # Always valid in tests

    def create_bundle(self, context, connection_timeout=None, response_timeout=None):
        return "# Mock Standards Bundle\n"


@pytest.fixture(autouse=True)
def register_mock_standards_provider():
    """Register mock standards provider for tests.

    Only adds mock-standards, preserves existing registrations like scoped-layer-fs.
    """
    StandardsProviderFactory.register("mock-standards", MockStandardsProvider)

    yield

    # Only remove what we added
    if "mock-standards" in StandardsProviderFactory._registry:
        del StandardsProviderFactory._registry["mock-standards"]


@pytest.fixture(autouse=True)
def mock_jpa_mt_profile(monkeypatch, register_mock_standards_provider):
    """Mock jpa-mt profile for orchestrator tests."""

    mock_profile = MagicMock()

    # Standards provider methods - Phase 2 ADR-0007
    mock_profile.get_default_standards_provider_key.return_value = "mock-standards"
    mock_profile.get_standards_config.return_value = {}

    # Prompt generation methods must return strings
    mock_profile.generate_planning_prompt.return_value = "# Mock Planning Prompt\n"
    mock_profile.generate_generation_prompt.return_value = "# Mock Generation Prompt\n"
    mock_profile.generate_review_prompt.return_value = "# Mock Review Prompt\n"
    mock_profile.generate_revision_prompt.return_value = "# Mock Revision Prompt\n"
    # Response processing methods
    mock_profile.process_planning_response.return_value = ProcessingResult(
        status=WorkflowStatus.SUCCESS
    )
    mock_profile.process_generation_response.return_value = ProcessingResult(
        status=WorkflowStatus.SUCCESS,
        write_plan=WritePlan(writes=[])
    )
    mock_profile.process_review_response.return_value = ProcessingResult(
        status=WorkflowStatus.SUCCESS
    )
    mock_profile.process_revision_response.return_value = ProcessingResult(
        status=WorkflowStatus.SUCCESS,
        write_plan=WritePlan(writes=[])
    )

    original_create = ProfileFactory.create
    original_get_metadata = ProfileFactory.get_metadata

    def mock_create(profile_key, config=None):
        if profile_key == "jpa-mt":
            return mock_profile
        return original_create(profile_key, config=config)

    def mock_get_metadata(profile_key):
        if profile_key == "jpa-mt":
            # Return metadata with context_schema for jpa-mt profile
            return {
                "name": "jpa-mt",
                "description": "Mock JPA-MT profile",
                "context_schema": {
                    "scope": {"type": "string", "required": True, "choices": ["domain", "vertical"]},
                    "entity": {"type": "string", "required": True},
                    "table": {"type": "string", "required": True},
                    "bounded_context": {"type": "string", "required": True},
                    "schema_file": {"type": "path", "required": True, "exists": True},
                    "dev": {"type": "string", "required": False},
                    "task_id": {"type": "string", "required": False},
                },
            }
        return original_get_metadata(profile_key)

    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, key, **kw: mock_create(key, kw.get("config"))))
    monkeypatch.setattr(ProfileFactory, "get_metadata", classmethod(lambda cls, key: mock_get_metadata(key)))

    return mock_profile