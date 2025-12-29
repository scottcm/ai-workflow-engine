# tests/unit/application/conftest.py
"""Fixtures for application layer tests."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from aiwf.domain.profiles.profile_factory import ProfileFactory
from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.workflow_state import WorkflowStatus
from aiwf.domain.models.write_plan import WriteOp, WritePlan
from aiwf.domain.standards import StandardsProviderFactory


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

    def mock_create(profile_key, config=None):
        if profile_key == "jpa-mt":
            return mock_profile
        return original_create(profile_key, config=config)

    monkeypatch.setattr(ProfileFactory, "create", classmethod(lambda cls, key, **kw: mock_create(key, kw.get("config"))))

    return mock_profile