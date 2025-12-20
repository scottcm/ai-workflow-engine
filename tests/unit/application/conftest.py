# tests/unit/application/conftest.py
"""Fixtures for application layer tests."""

import pytest
from unittest.mock import MagicMock

from aiwf.domain.profiles.profile_factory import ProfileFactory
from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.workflow_state import WorkflowStatus
from aiwf.domain.models.write_plan import WriteOp, WritePlan


@pytest.fixture(autouse=True)
def mock_jpa_mt_profile(monkeypatch):
    """Mock jpa-mt profile for orchestrator tests."""
    
    mock_profile = MagicMock()
    mock_profile.get_standards_provider.return_value = MagicMock(
        create_bundle=MagicMock(return_value="# Mock Standards Bundle\n")
    )
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