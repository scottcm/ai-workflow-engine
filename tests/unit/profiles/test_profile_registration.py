"""Tests for profile registration in the factory."""
import pytest

from aiwf.domain.profiles.profile_factory import ProfileFactory
from aiwf.domain.profiles.workflow_profile import WorkflowProfile


def test_jpa_mt_profile_registered(standards_dir):
    """jpa-mt profile should be retrievable from factory."""
    profile = ProfileFactory.create("jpa-mt")
    assert profile is not None
    assert isinstance(profile, WorkflowProfile)


def test_unknown_profile_raises():
    """Unknown profile key should raise KeyError."""
    with pytest.raises(KeyError):
        ProfileFactory.create("nonexistent-profile-xyz")
